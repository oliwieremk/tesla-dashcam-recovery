"""Platform paths and read-only macOS partition discovery."""

import os
import plistlib
import re
import subprocess
import sys


def data_dir():
    if os.environ.get('TESLARECOVER_DATA_DIR'):
        return os.path.abspath(os.path.expanduser(os.environ['TESLARECOVER_DATA_DIR']))
    if sys.platform == 'darwin':
        return os.path.expanduser('~/Library/Application Support/TeslaRecover')
    return os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'TeslaRecover')


def diskutil(*args):
    result = subprocess.run(['/usr/sbin/diskutil', *args], check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    return plistlib.loads(result.stdout)


def mac_drives():
    """List external partitions, never internal disks or whole partitioned devices."""
    drives = []
    listing = diskutil('list', '-plist', 'external')
    for disk in listing.get('AllDisksAndPartitions', []):
        for part in disk.get('Partitions', [disk]):
            ident = part.get('DeviceIdentifier', '')
            if not re.fullmatch(r'disk\d+(?:s\d+)*', ident):
                continue
            info = diskutil('info', '-plist', ident)
            if info.get('Internal', True):
                continue
            fs = info.get('FilesystemType', '')
            if not fs:  # Partition maps and EFI partitions aren't recording volumes.
                continue
            mount = info.get('MountPoint', '')
            raw = '/dev/r' + ident
            tesla = bool(mount and os.path.isdir(os.path.join(mount, 'TeslaCam')))
            from .macos_access import device_info
            authorized = device_info()
            if authorized and raw == authorized['device']:
                tesla = tesla or authorized['teslacam']
            drives.append({'drive': raw, 'label': info.get('VolumeName', ident),
                           'fs': fs, 'teslacam': tesla, 'removable': True,
                           'size': info.get('TotalSize', part.get('Size', 0)),
                           'supported': fs.lower() in ('exfat', 'msdos', 'fat32'),
                           'mount': mount})
    return drives
