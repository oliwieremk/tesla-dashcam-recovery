"""A short-lived privileged helper passes one read-only device FD to the user app.

The HTTP server and browser never run as root. The private Unix socket belongs to
our user; only an external FAT32/exFAT device may be opened. No writes are exposed.
"""
import array
import json
import os
import re
import shlex
import socket
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from .platforms import diskutil
from .localize import translate

_handle = None
_device = None
_info = None
_lock = threading.Lock()


def current_device():
    return _device


def device_info():
    return dict(_info) if _info else None


def duplicate_handle(device):
    with _lock:
        return os.dup(_handle) if _handle is not None and device == _device else None


def release():
    global _handle, _device, _info
    with _lock:
        handle, info = _handle, _info
        _handle = _device = _info = None
    if handle is not None:
        os.close(handle)
    if info:
        subprocess.run(['/usr/sbin/diskutil', 'mount', info['block']],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)


def _validated_device(device):
    if not re.fullmatch(r'/dev/rdisk\d+(?:s\d+)*', device):
        raise ValueError('Nieprawidłowy identyfikator nośnika USB.')
    info = diskutil('info', '-plist', device.replace('/dev/rdisk', '/dev/disk'))
    if info.get('Internal', True) or info.get('FilesystemType', '').lower() not in ('exfat', 'msdos', 'fat32'):
        raise ValueError('Można otworzyć wyłącznie zewnętrzną partycję FAT32 lub exFAT.')
    return info


def _send_device(device, socket_path, uid):
    """This is the only privileged entry point. It exits immediately after FD transfer."""
    if os.geteuid() != 0 or uid <= 0:
        raise PermissionError('Brak uprawnień do odczytu USB.')
    parent = os.stat(os.path.dirname(socket_path))
    target = os.stat(socket_path)
    if parent.st_uid != uid or stat.S_IMODE(parent.st_mode) != 0o700 or \
            target.st_uid != uid or not stat.S_ISSOCK(target.st_mode):
        raise PermissionError('Nieprawidłowe połączenie z aplikacją.')
    info = _validated_device(device)
    mount = info.get('MountPoint', '')
    metadata = {'device': device, 'block': info['DeviceNode'], 'mount': mount,
                'teslacam': bool(mount and os.path.isdir(os.path.join(mount, 'TeslaCam'))),
                'label': info.get('VolumeName', device), 'fs': info.get('FilesystemType'),
                'size': info.get('TotalSize', 0)}
    subprocess.run(['/usr/sbin/diskutil', 'unmount', info['DeviceNode']],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)
    fd = None
    transferred = False
    try:
        fd = os.open(device, os.O_RDONLY)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(30)
            client.connect(socket_path)
            client.sendmsg([json.dumps(metadata).encode()],
                           [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', [fd]))])
            transferred = client.recv(2) == b'OK'
            if not transferred:
                raise RuntimeError('Przekazanie dostępu do USB nie powiodło się.')
    finally:
        if fd is not None:
            os.close(fd)
        if not transferred:
            subprocess.run(['/usr/sbin/diskutil', 'mount', info['DeviceNode']],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)


def authorize(device, progress, cancelled=lambda: False, language='pl'):
    global _handle, _device, _info
    if sys.platform != 'darwin':
        raise RuntimeError('Autoryzacja USB w oknie jest dostępna na macOS.')
    if device == current_device():
        return {'drive': device}
    _validated_device(device)  # Refuse internal disks before showing any password prompt.
    release()
    progress('Czekam na zgodę macOS na odczyt USB', 0, 1)
    fd = None
    proc = None
    acquired = None
    try:
        with tempfile.TemporaryDirectory(prefix='teslarecover-') as folder:
            socket_path = os.path.join(folder, 'access.sock')
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.bind(socket_path)
                os.chmod(socket_path, 0o600)
                listener.listen(1)
                listener.settimeout(0.25)
                root = str(Path(__file__).resolve().parent.parent)
                args = [sys.executable, '-B', '-m', 'teslarecover.macos_access', device, socket_path, str(os.getuid())]
                command = 'cd ' + shlex.quote(root) + ' && ' + shlex.join(args)
                script = ('do shell script ' + json.dumps(command, ensure_ascii=False)
                          + ' with administrator privileges with prompt ' + json.dumps(translate('Tesla Recovery potrzebuje zgody na odczyt wybranego USB. Nośnik nie będzie zapisywany.', language), ensure_ascii=False))
                proc = subprocess.Popen(['/usr/bin/osascript', '-e', script],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                while True:
                    if cancelled():
                        raise InterruptedError('Anulowano autoryzację USB.')
                    if proc.poll() is not None:
                        _, err = proc.communicate()
                        if proc.returncode:
                            message = err.decode('utf-8', 'replace')
                            if '-128' in message:
                                raise InterruptedError('Anulowano zgodę macOS.')
                            raise PermissionError('macOS odmówił odczytu USB. Sprawdź uprawnienia aplikacji i pełny dostęp do dysku. ' + message[-500:])
                        raise RuntimeError('Pomocnik zakończył pracę bez przekazania nośnika.')
                    try:
                        connection, _ = listener.accept()
                        break
                    except socket.timeout:
                        continue
                with connection:
                    connection.settimeout(10)
                    payload, ancillary, _, _ = connection.recvmsg(4096, socket.CMSG_SPACE(array.array('i').itemsize))
                    descriptors = array.array('i')
                    for level, kind, value in ancillary:
                        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                            descriptors.frombytes(value[:len(value) - len(value) % descriptors.itemsize])
                    if len(descriptors) != 1:
                        for extra in descriptors:
                            os.close(extra)
                        raise RuntimeError('Nieprawidłowy dostęp do nośnika.')
                    fd = descriptors[0]
                    os.set_inheritable(fd, False)
                    metadata = json.loads(payload)
                    if metadata['device'] != device:
                        raise RuntimeError('Wybrany nośnik się zmienił. Wybierz go ponownie.')
                    acquired = metadata
                    connection.sendall(b'OK')
                proc.communicate(timeout=15)
                if proc.returncode:
                    raise RuntimeError('Nie udało się ukończyć autoryzacji USB.')
                if cancelled():
                    raise InterruptedError('Anulowano autoryzację USB.')
                with _lock:
                    _handle, _device, _info = fd, device, metadata
                fd = None
                acquired = None
        progress('Dostęp do USB gotowy', 1, 1)
        return {'drive': device}
    finally:
        if fd is not None:
            os.close(fd)
        if acquired:
            subprocess.run(['/usr/sbin/diskutil', 'mount', acquired['block']], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == '__main__':
    _send_device(sys.argv[1], sys.argv[2], int(sys.argv[3]))
