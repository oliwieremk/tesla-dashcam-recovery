"""Exercise playable video export/preparation and local page decryption without Tesla APIs."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from Crypto.Cipher import AES
from teslarecover import decrypt, export, repair
from teslarecover.scan import Scanner
from teslarecover.telemetry import read_telemetry
import tesla_dashcam_decrypt as tdd


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg/ffprobe needed for generated-video tests')
class VideoPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.video = cls.root / 'fixture.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30',
                        '-t', '3', '-c:v', 'libx264', '-profile:v', 'baseline', '-bf', '0',
                        '-x264-params', 'repeat-headers=1', '-pix_fmt', 'yuv420p', '-brand', 'mp42',
                        '-metadata', 'creation_time=2026-10-12T12:00:00Z', str(cls.video)], check=True)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def assert_decodes(self, path):
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-f', 'null', '-'], check=True, capture_output=True)

    def test_real_mp4_scan_export_prepare_and_decode(self):
        from test_macos import partition_image
        image = self.root / 'playable.img'
        partition_image(image)
        video = self.video.read_bytes()
        count = (len(video) + 511) // 512
        cluster_count = count + 8
        original = image.read_bytes()
        fat_sectors = ((cluster_count + 2) * 4 + 511) // 512
        heap = 1 + fat_sectors
        offset = lambda cluster: (heap + cluster - 2) * 512
        data = bytearray((heap + cluster_count) * 512)
        data[:512] = original[:512]
        struct.pack_into('<IIIII', data, 0x50, 1, fat_sectors, heap, cluster_count, 2)
        data[offset(2):offset(2) + 512] = original[2 * 512:3 * 512]
        for cluster in (2, 3): struct.pack_into('<I', data, 512 + cluster * 4, 0xffffffff)
        # Contiguous file starts at cluster 5; its FAT can span multiple sectors.
        for cluster in range(5, 5 + count):
            struct.pack_into('<I', data, 512 + cluster * 4, cluster + 1 if cluster < 4 + count else 0xffffffff)
        struct.pack_into('<Q', data, offset(2) + 64 + 0x18, len(video))
        struct.pack_into('<Q', data, offset(2) + 0x18, (cluster_count + 7) // 8)
        for cluster in (2, 3, *range(5, 5 + count)):
            data[offset(3) + (cluster - 2) // 8] |= 1 << ((cluster - 2) % 8)
        data[offset(5):offset(5) + len(video)] = video
        image.write_bytes(data)
        before = hashlib.sha256(data).hexdigest()
        scanned = Scanner(str(image)).run()
        live = [clip for clip in scanned['clips'] if clip['source'] == 'live']
        self.assertEqual(len(live), 1)
        out = self.root / 'recovered'
        lib = export.export(str(image), scanned, live, str(out), lambda *args: None)
        entry = next(iter(lib.entries.values()))
        self.assertEqual((out / 'encrypted' / entry['encrypted_file']).read_bytes(), video)
        decrypt.prepare_plain(lib); decrypt.finalize(lib, lambda *args: None)
        self.assertEqual(lib.summary().get('ok'), 1)
        entry = lib.playable()[0]
        self.assertEqual(entry['camera'], 'front')
        self.assert_decodes(out / entry['file'])
        telemetry = read_telemetry(str(out / entry['file']))
        self.assertEqual(telemetry['frames'], 90)
        self.assertTrue(all(value is None for value in telemetry['speed']))
        self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(), before)

    def test_missing_mp4_index_can_be_repaired_and_decoded(self):
        from teslarecover.naming import boxes
        with open(self.video, 'rb') as source:
            source.seek(0, 2); end = source.tell()
            moov = next(start - 8 for kind, start, finish in boxes(source, 0, end) if kind == b'moov')
        damaged = self.root / 'missing-index.mp4'
        damaged.write_bytes(self.video.read_bytes()[:moov])
        destination = self.root / 'repaired.mp4'
        info = repair.repair(str(damaged), str(destination), 1791806400)
        self.assertEqual((info['width'], info['height']), (320, 180))
        self.assertEqual(info['frames'], 90)
        self.assert_decodes(destination)

    def test_ecryptfs_page_decryption_preserves_playable_mp4(self):
        plain = self.video.read_bytes()
        key = bytes(range(16))  # Synthetic test key; no account or network required.
        header = bytearray(0x2000)
        struct.pack_into('>Q', header, 0, len(plain))
        root_iv = hashlib.md5(key).digest()
        encrypted = bytearray(header)
        for page, start in enumerate(range(0, len(plain), 4096)):
            payload = plain[start:start + 4096].ljust(4096, b'\0')
            material = (root_iv + str(page).encode()).ljust(32, b'\0')
            iv = hashlib.md5(material).digest()
            encrypted.extend(AES.new(key, AES.MODE_CBC, iv).encrypt(payload))
        source = self.root / 'encrypted-pages.mp4'; source.write_bytes(encrypted)
        destination = self.root / 'decrypted.mp4'
        self.assertEqual(tdd._decrypt_real_file(source, destination, key), len(plain))
        self.assertEqual(destination.read_bytes(), plain)
        self.assert_decodes(destination)
        source.write_bytes(encrypted[:-10])
        with self.assertRaises(ValueError): tdd._decrypt_real_file(source, self.root / 'truncated.mp4', key)


if __name__ == '__main__': unittest.main()
