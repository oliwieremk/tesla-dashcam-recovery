import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from teslarecover import auth, export, platforms, server
from teslarecover.scan import MP4_SIGNATURE, Scanner
from teslarecover.volume import AlignedReader, Volume
from teslarecover import macos_access
from teslarecover.localize import quality
import array
import json
import socket
import threading
from teslarecover import __main__ as app_main


def partition_image(path):
    """Small exFAT image with a fragmented live clip and a carved deleted clip."""
    data = bytearray(34 * 512)
    data[3:11] = b'EXFAT   '
    data[0x6c:0x6f] = bytes([9, 0, 1])
    struct.pack_into('<IIIII', data, 0x50, 1, 1, 2, 32, 2)
    for cluster, nxt in ((2, 0xffffffff), (3, 0xffffffff), (5, 9), (9, 0xffffffff)):
        struct.pack_into('<I', data, 512 + cluster * 4, nxt)
    root = bytearray(512)
    root[0] = 0x81
    struct.pack_into('<IQ', root, 0x14, 3, 4)
    name = '2026-10-11_12-00-00-front.mp4'
    name_chunks = [name[i:i + 15] for i in range(0, len(name), 15)]
    root[32] = 0x85
    root[33] = 1 + len(name_chunks)
    root[64] = 0xc0
    root[67] = len(name)
    struct.pack_into('<IQ', root, 64 + 0x14, 5, 1024)
    for i, text in enumerate(name_chunks):
        pos = 96 + 32 * i
        root[pos] = 0xc1
        root[pos + 2:pos + 2 + len(text) * 2] = text.encode('utf-16-le')
    data[1024:1536] = root
    for c in (2, 3, 5, 9):
        data[1536 + (c - 2) // 8] |= 1 << ((c - 2) % 8)
    live = MP4_SIGNATURE + b'L' * (512 - len(MP4_SIGNATURE)) + b'F' * 512
    data[5 * 512:6 * 512] = live[:512]
    data[9 * 512:10 * 512] = live[512:]
    data[6 * 512:6 * 512 + len(MP4_SIGNATURE)] = MP4_SIGNATURE
    path.write_bytes(data)
    return live


class MacTests(unittest.TestCase):
    def test_scan_export_fragmented_live_and_deleted_image(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / 'usb.img'
            live = partition_image(image)
            original = image.read_bytes()
            result = Scanner(str(image)).run()
            clips = result['clips']
            self.assertEqual({c['source'] for c in clips}, {'live', 'carved'})
            clip = next(c for c in clips if c['source'] == 'live')
            self.assertEqual(clip['runs'], [[5, 1], [9, 1]])
            lib = export.export(str(image), result, clips, str(Path(folder) / 'out'), lambda *a: None)
            dest = Path(lib.folder) / 'encrypted' / export.encrypted_name(clip)
            self.assertEqual(dest.read_bytes(), live)
            self.assertEqual(image.read_bytes(), original)
            with open(image, 'rb') as source, patch.object(macos_access, '_handle', source.fileno()), patch.object(macos_access, '_device', str(image)):
                readers = [AlignedReader(str(image), 512) for _ in range(4)]
                with ThreadPoolExecutor(4) as pool:
                    reads = list(pool.map(lambda pair: readers[pair[0] % 4].read_at(pair[1], 31),
                                          enumerate(range(100, 800))))
                self.assertEqual(reads, [original[n:n + 31] for n in range(100, 800)])
                for reader in readers:
                    reader.close()
                self.assertEqual(os.pread(source.fileno(), 12, 5 * 512), MP4_SIGNATURE)

    def test_discovery_excludes_internal_and_keeps_partition(self):
        listing = {'AllDisksAndPartitions': [{'DeviceIdentifier': 'disk2', 'Partitions': [
            {'DeviceIdentifier': 'disk2s1'}, {'DeviceIdentifier': 'disk2s2'}]}]}
        info = {'Internal': False, 'FilesystemType': 'exfat', 'VolumeName': 'TESLA',
                'TotalSize': 128000, 'MountPoint': '/Volumes/TESLA'}
        with patch.object(platforms, 'diskutil', side_effect=[listing, info, dict(info, Internal=True)]), \
                patch('os.path.isdir', return_value=True):
            drives = platforms.mac_drives()
        self.assertEqual(len(drives), 1)
        self.assertEqual(drives[0]['drive'], '/dev/rdisk2s1')
        self.assertTrue(drives[0]['teslacam'])

    def test_mac_browser_path(self):
        chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        with patch.object(auth.sys, 'platform', 'darwin'), \
                patch.object(auth.os.path, 'isfile', side_effect=lambda p: p == chrome):
            self.assertEqual(auth.find_browser(), chrome)

    def test_internal_disk_rejected_before_permission_prompt(self):
        with patch.object(macos_access, 'diskutil', return_value={'Internal': True}), \
                patch.object(macos_access.subprocess, 'Popen') as process:
            with self.assertRaisesRegex(ValueError, 'zewnętrzną'):
                macos_access.authorize('/dev/rdisk0s1', lambda *a: None)
            process.assert_not_called()

    def test_readonly_device_descriptor_transfer(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / 'volume.img'
            image.write_bytes(b'read-only data')
            socket_path = str(Path(folder) / 'access.sock')
            info = {'Internal': False, 'FilesystemType': 'exfat', 'DeviceNode': '/dev/disk2s1'}
            actual_open = os.open
            errors = []
            def send():
                try:
                    macos_access._send_device('/dev/rdisk2s1', socket_path, os.getuid())
                except Exception as exc:
                    errors.append(exc)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.bind(socket_path); listener.listen(1); listener.settimeout(5)
                with patch.object(macos_access.os, 'geteuid', return_value=0), \
                        patch.object(macos_access, '_validated_device', return_value=info), \
                        patch.object(macos_access.os, 'open', side_effect=lambda path, flags: actual_open(image if path == '/dev/rdisk2s1' else path, flags)), \
                        patch.object(macos_access.subprocess, 'run') as run:
                    worker = threading.Thread(target=send); worker.start()
                    connection, _ = listener.accept()
                    with connection:
                        payload, ancillary, _, _ = connection.recvmsg(4096, socket.CMSG_SPACE(4))
                        self.assertEqual(json.loads(payload)['device'], '/dev/rdisk2s1')
                        descriptors = array.array('i'); descriptors.frombytes(ancillary[0][2][:4])
                        descriptor = descriptors[0]
                        self.assertEqual(os.pread(descriptor, 14, 0), b'read-only data')
                        with self.assertRaises(OSError):
                            os.write(descriptor, b'overwrite')
                        connection.sendall(b'OK')
                    worker.join(timeout=5)
                    os.close(descriptor)
                    self.assertFalse(worker.is_alive())
                    self.assertEqual(errors, [])
                    run.assert_called_once()
            self.assertEqual(image.read_bytes(), b'read-only data')

    def test_quality_does_not_claim_unverified_footage_is_complete(self):
        self.assertEqual(quality({'source': 'live'})['code'], 'unverified')
        self.assertEqual(quality({'source': 'carved', 'status': 'ok', 'truncated': True})['code'], 'partial')
        self.assertEqual(quality({'status': 'ok', 'repaired': True, 'repaired_seconds': 32})['code'], 'repaired')
        self.assertEqual(quality({'status': 'unplayable', 'truncated': True})['code'], 'unplayable')
        self.assertNotIn('kompletne', quality({'status': 'ok'})['label'].lower())

    def test_image_picker_validation_and_quality_api(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / 'usb.img'; partition_image(image)
            with patch.object(server.state, 'job', None), patch.object(server.state, 'image', None, create=True):
                self.assertEqual(server.pick_image(str(image))['path'], str(image))
                self.assertTrue(server.get_drives()[-1]['image'])
                bad = Path(folder) / 'gpt.img'; bad.write_bytes(bytes(512))
                with self.assertRaises(server.HTTPException) as exc:
                    server.pick_image(str(bad))
                self.assertEqual(exc.exception.status_code, 400)
            self.assertEqual(server.clip_summary({'id': '1', 'truncated': True})['quality']['code'], 'partial')

    def test_output_and_library_on_tesla_volume_are_protected(self):
        with patch.object(server, 'mac_drives', return_value=[{'mount': '/Volumes/TESLA', 'teslacam': True}]), \
                patch.object(macos_access, 'device_info', return_value=None):
            self.assertTrue(server.source_folder('/Volumes/TESLA/TeslaCam/RecentClips'))
            self.assertFalse(server.source_folder('/Volumes/TESLA-copy/recovered'))

    def test_source_volume_cannot_be_used_for_decryption_or_save(self):
        library = type('ReadOnlyLibrary', (), {'read_only': True})()
        with patch.object(server.state, 'library', library), patch.object(server.state, 'job', None), \
                patch.object(server, 'source_folder', return_value=True):
            with self.assertRaises(server.HTTPException) as decrypt_error:
                server.start_decrypt(True)
            with self.assertRaises(server.HTTPException) as save_error:
                server.start_save([], '/Volumes/TESLA')
        self.assertEqual(decrypt_error.exception.status_code, 400)
        self.assertEqual(save_error.exception.status_code, 400)

    def test_cancelled_macos_prompt_leaves_no_active_handle(self):
        process = type('Process', (), {'returncode': 1, 'poll': lambda self: 1,
                                     'communicate': lambda self: (b'', b'User canceled. (-128)')})()
        with patch.object(macos_access, '_validated_device'), patch.object(macos_access, 'release'), \
                patch.object(macos_access.subprocess, 'Popen', return_value=process):
            with self.assertRaises(InterruptedError):
                macos_access.authorize('/dev/rdisk2s1', lambda *a: None)
            self.assertIsNone(macos_access.current_device())

    def test_settings_path_and_nonwindows_elevation(self):
        from teslarecover.__main__ import relaunch_as_admin
        self.assertIn('/Library/Application Support/TeslaRecover', platforms.data_dir())
        self.assertFalse(relaunch_as_admin())
        self.assertEqual(server.get_state()['platform'], 'darwin')

    def test_invalid_image_reports_filesystem(self):
        with tempfile.NamedTemporaryFile() as source:
            source.write(bytes(512))
            source.flush()
            with self.assertRaisesRegex(ValueError, 'not an exFAT or FAT32'):
                Volume(source.name)


if __name__ == '__main__':
    unittest.main()
