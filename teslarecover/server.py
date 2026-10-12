"""Local HTTP API + static frontend. Long steps run as one background job at a time;
the page polls /api/state for progress."""

import ctypes
import json
import os
import string
import sys
import subprocess
import threading
import time
import traceback

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth, decrypt, export, scan
from .platforms import data_dir, mac_drives
from .localize import phase, localized_error, localize_quality, translate, native_strings
from .library import Library
from .telemetry import read_telemetry

STATIC = os.path.join(os.path.dirname(__file__), 'static')
SETTINGS = os.path.join(data_dir(), 'settings.json')


class Job:
    def __init__(self, kind, fn):
        self.kind = kind
        self.phase = 'Starting'
        self.done = 0
        self.total = 0
        self.status = 'running'
        self.error = None
        self.result = None
        self.error_details = None
        self.cancel_requested = False
        self.thread = threading.Thread(target=self._run, args=(fn,), daemon=True)

    def progress(self, phase, done, total):
        self.phase, self.done, self.total = phase, done, total

    def cancelled(self):
        return self.cancel_requested

    def _run(self, fn):
        try:
            self.result = fn(self)
            self.status = 'done'
        except InterruptedError:
            self.status = 'cancelled'
        except decrypt.AuthError as e:
            self.status, self.error = 'auth', str(e)
            self.error_details = str(e)
        except Exception as e:
            traceback.print_exc()
            self.error_details = str(e) or type(e).__name__
            self.status, self.error = 'error', self.error_details

    def as_dict(self):
        return {'kind': self.kind, 'phase': phase(self.phase, language()), 'done': self.done, 'total': self.total,
                'status': self.status, 'error': localized_error(self.error, language()) if self.error else None, 'error_details': self.error_details, 'result': self.result}


class State:
    def __init__(self):
        self.drive = None
        self.scan = None
        self.out_dir = None
        self.token = None
        self.job = None
        self.window = None
        self.library = None
        self.lock = threading.Lock()
        self.settings = {}
        try:
            with open(SETTINGS, encoding='utf-8') as f:
                self.settings = json.load(f)
        except (OSError, ValueError):
            pass

    def save_settings(self, **values):
        with self.lock:
            self.settings.update(values)
            os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
            temporary = SETTINGS + '.tmp'
            with open(temporary, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=1)
            os.replace(temporary, SETTINGS)

    def start(self, kind, fn):
        with self.lock:
            if self.job and self.job.status == 'running':
                raise HTTPException(409, 'Trwa inna operacja. Poczekaj lub ją anuluj.')
            self.job = Job(kind, fn)
            self.job.thread.start()
            return self.job.as_dict()


state = State()
app = FastAPI()


def language():
    return state.settings.get('language') if state.settings.get('language') in ('pl', 'en') else 'pl'


@app.exception_handler(HTTPException)
async def localized_http_exception(request, exc):
    detail = translate(exc.detail, language()) if isinstance(exc.detail, str) else exc.detail
    return JSONResponse(status_code=exc.status_code, content={'detail': detail}, headers=exc.headers)


@app.post('/api/language')
def set_language(language: str = Body(..., embed=True)):
    if language not in ('pl', 'en'):
        raise HTTPException(400, 'Supported languages: pl, en.')
    state.save_settings(language=language)
    if state.window:
        state.window.localization.update(native_strings(language))
        state.window.set_title(translate('Tesla Recovery — odzyskiwanie nagrań', language))
        if sys.platform == 'darwin':
            from .native import update_menu
            update_menu(state.window)
    return {'language': language}


@app.middleware('http')
async def no_cache_frontend(request, call_next):
    # The page and its scripts change with app updates; always revalidate them.
    response = await call_next(request)
    if not request.url.path.startswith(('/media/', '/api/')):
        response.headers['Cache-Control'] = 'no-cache'
    return response


def list_drives():
    drives = []
    if sys.platform == 'darwin':
        return mac_drives()
    if os.name != 'nt':
        return drives
    k32 = ctypes.windll.kernel32
    mask = k32.GetLogicalDrives()
    for i, letter in enumerate(string.ascii_uppercase):
        if not mask & (1 << i):
            continue
        root = letter + ':\\'
        kind = k32.GetDriveTypeW(root)
        if kind not in (2, 3):  # removable, fixed (some USB SSDs report as fixed)
            continue
        label = ctypes.create_unicode_buffer(261)
        fs = ctypes.create_unicode_buffer(261)
        if not k32.GetVolumeInformationW(root, label, 261, None, None, None, fs, 261):
            continue
        tesla = os.path.isdir(root + 'TeslaCam')
        if kind == 3 and not tesla:
            continue
        free, total = ctypes.c_ulonglong(), ctypes.c_ulonglong()
        k32.GetDiskFreeSpaceExW(root, None, ctypes.byref(total), ctypes.byref(free))
        drives.append({'drive': letter + ':', 'label': label.value, 'fs': fs.value, 'teslacam': tesla,
                       'removable': kind == 2, 'size': total.value,
                       'supported': fs.value.upper() in ('EXFAT', 'FAT32')})
    return drives


def pick_folder(initial=None):
    if state.window is not None:
        import webview
        result = state.window.create_file_dialog(webview.FileDialog.FOLDER, directory=initial or '')
        return result[0] if result else None
    if sys.platform == 'darwin':
        result = subprocess.run(['/usr/bin/osascript', '-e',
                                 'POSIX path of (choose folder with prompt ' + json.dumps(translate('Wybierz folder docelowy', language()), ensure_ascii=False) + ')'],
                                capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    import tkinter
    from tkinter import filedialog
    root = tkinter.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    path = filedialog.askdirectory(initialdir=initial or None)
    root.destroy()
    return path or None


def clip_summary(c):
    return {**{k: c.get(k) for k in ('id', 'source', 'name', 'camera', 'folder', 'start_utc', 'size',
                                  'encrypted', 'truncated', 'gap', 'status')}, 'quality': localize_quality(c, language())}


def authorized_device():
    if sys.platform == 'darwin':
        from .macos_access import current_device
        return current_device()
    return None


@app.get('/api/state')
def get_state():
    lib = state.library
    return {
        'language': language(),
        'platform': sys.platform,
        'authorized_device': authorized_device(),
        'drive': state.drive,
        'scanned': state.scan is not None,
        'clip_count': len(state.scan['clips']) if state.scan else 0,
        'out_dir': state.out_dir,
        'last_out_dir': state.settings.get('out_dir'),
        'signed_in': state.token is not None,
        'job': state.job.as_dict() if state.job else None,
        'library': {'folder': lib.folder, 'counts': lib.summary()} if lib else None,
    }


@app.get('/api/drives')
def get_drives():
    drives = list_drives()
    if getattr(state, 'image', None):
        drives.append({'drive': state.image, 'label': translate('Obraz partycji', language()), 'fs': 'FAT32 / exFAT',
                       'size': os.path.getsize(state.image), 'teslacam': False, 'image': True,
                       'removable': False, 'supported': True})
    return drives


def ensure_idle():
    if state.job and state.job.status == 'running':
        raise HTTPException(409, 'Trwa inna operacja. Poczekaj lub ją anuluj.')


@app.post('/api/authorize-usb')
def authorize_usb(drive: str = Body(..., embed=True)):
    if sys.platform != 'darwin':
        raise HTTPException(400, 'Ta funkcja jest dostępna na macOS.')
    ensure_idle()
    from .macos_access import authorize
    state.drive = None
    state.scan = None
    return state.start('authorize', lambda job: authorize(drive, job.progress, job.cancelled, language=language()))


@app.post('/api/release-usb')
def release_usb():
    ensure_idle()
    if sys.platform == 'darwin':
        from .macos_access import release
        release()
    state.drive = None
    state.scan = None
    return {'ok': True}


@app.post('/api/pick-image')
def pick_image(path: str = Body(None, embed=True)):
    ensure_idle()
    if not path:
        if state.window:
            import webview
            result = state.window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False,
                                                     file_types=(translate('Obrazy partycji (*.img;*.raw;*.dd)', language()), translate('Wszystkie pliki (*.*)', language())))
            path = result[0] if result else None
        elif sys.platform == 'darwin':
            result = subprocess.run(['/usr/bin/osascript', '-e',
                                     'POSIX path of (choose file with prompt ' + json.dumps(translate('Wybierz obraz partycji FAT32 lub exFAT', language()), ensure_ascii=False) + ')'],
                                    capture_output=True, text=True)
            path = result.stdout.strip() if result.returncode == 0 else None
    if not path:
        return {'path': None}
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(path):
        raise HTTPException(400, 'Obraz partycji nie istnieje.')
    # Validate just the boot sector, not the entire FAT (which may take seconds).
    with open(path, 'rb') as source:
        boot = source.read(512)
    if len(boot) < 512 or not (boot[3:8] == b'EXFAT' or boot[0x52:0x57] == b'FAT32'):
        raise HTTPException(400, 'To nie jest obraz partycji FAT32/exFAT. Wybierz nieskompresowany obraz samej partycji, bez tablicy GPT/MBR.')
    state.image = path
    return {'path': path}


@app.post('/api/scan')
def start_scan(drive: str = Body(..., embed=True)):
    ensure_idle()
    if sys.platform == 'darwin' and drive.startswith('/dev/'):
        from .macos_access import current_device
        if current_device() != drive:
            raise HTTPException(403, 'Najpierw zezwól na odczyt wybranego USB.')
    def run(job):
        result = scan.Scanner(drive, job.progress, job.cancelled).run()
        state.drive, state.scan = drive, result
        clips = result['clips']
        return {'clips': len(clips), 'live': sum(c['source'] == 'live' for c in clips),
                'deleted': sum(c['source'] != 'live' for c in clips)}
    state.scan = None
    return state.start('scan', run)


@app.get('/api/clips')
def get_clips():
    if not state.scan:
        raise HTTPException(404, 'Najpierw przeskanuj nośnik.')
    return [clip_summary(c) for c in state.scan['clips']]


@app.post('/api/pick-folder')
def post_pick_folder(initial: str = Body(None, embed=True)):
    return {'path': pick_folder(initial or state.settings.get('out_dir'))}


def source_folder(folder):
    path = os.path.realpath(os.path.abspath(os.path.expanduser(folder)))
    if os.name == 'nt':
        root = os.path.splitdrive(path)[0] + os.sep
        return bool(os.path.isdir(os.path.join(root, 'TeslaCam')) or
                    (state.drive and os.path.splitdrive(path)[0].lower() == state.drive.rstrip('\\/').lower()))
    if sys.platform == 'darwin':
        from .macos_access import device_info
        authorized = device_info()
        sources = [d['mount'] for d in mac_drives() if d.get('mount') and d.get('teslacam')]
        if authorized and authorized.get('mount'):
            sources.append(authorized['mount'])
        return any(path == mount or path.startswith(mount + os.sep) for mount in sources)
    return False


@app.post('/api/export')
def start_export(out_dir: str = Body(...), start_utc: float = Body(None), end_utc: float = Body(None)):
    if not state.scan:
        raise HTTPException(400, 'Najpierw przeskanuj nośnik.')
    ensure_idle()
    if source_folder(out_dir):
        raise HTTPException(400, 'Wybierz folder na komputerze lub innym dysku. Nie zapisujemy wyników na nośniku Tesli.')
    clips = export.select(state.scan['clips'], start_utc, end_utc)
    if not clips:
        raise HTTPException(400, 'Brak nagrań w wybranym zakresie.')
    state.out_dir = out_dir
    state.save_settings(out_dir=out_dir)

    def run(job):
        state.library = export.export(state.drive, state.scan, clips, out_dir, job.progress, job.cancelled)
        return {'copied': len(clips), 'size': sum(c['size'] for c in clips)}
    return state.start('export', run)


def sample_clip():
    """An encrypted clip for the sign-in page to open (see auth.sign_in)."""
    lib = state.library
    if lib:
        for e in lib.entries.values():
            path = os.path.join(lib.folder, 'encrypted', e.get('encrypted_file') or '')
            if e.get('encrypted_file') and os.path.isfile(path):
                return path
    if state.scan:
        for c in state.scan['clips']:
            path = state.drive.rstrip('\\/') + (c['path'] or '').replace('/', os.sep)
            if c['source'] == 'live' and c['encrypted'] and os.path.isfile(path):
                return path
    return None


@app.post('/api/signin')
def start_signin():
    def run(job):
        state.token = auth.sign_in(job.progress, job.cancelled, sample_clip=sample_clip())
        return {'signed_in': True}
    return state.start('signin', run)


@app.post('/api/token')
def set_token(token: str = Body(..., embed=True)):
    token = token.strip()
    if token.lower().startswith('bearer '):
        token = token[7:].strip()
    if not token:
        raise HTTPException(400, 'Wklej token dostępu.')
    state.token = token
    return {'signed_in': True}


@app.post('/api/decrypt')
def start_decrypt(keep_encrypted: bool = Body(True, embed=True)):
    lib = state.library
    if lib is None:
        raise HTTPException(400, 'Najpierw skopiuj nagrania do folderu docelowego.')
    if lib.read_only:
        raise HTTPException(400, 'Najpierw skopiuj nagrania na komputer. Nie zmieniamy plików na nośniku Tesli.')
    needs_key = any(e.get('status') in ('encrypted', 'key_error') for e in lib.entries.values())
    if needs_key and not state.token:
        raise HTTPException(400, 'Najpierw zaloguj się do Tesli.')

    def run(job):
        decrypt.prepare_plain(lib)
        try:
            if needs_key:
                decrypt.decrypt_all(lib, state.token, job.progress, job.cancelled)
        except decrypt.AuthError:
            state.token = None
            raise
        finally:
            # Rename whatever was decrypted, even if a later batch failed.
            decrypt.finalize(lib, job.progress, keep_encrypted)
        return lib.summary()
    return state.start('decrypt', run)


@app.post('/api/repair')
def start_repair():
    lib = state.library
    if lib is None:
        raise HTTPException(400, 'Najpierw otwórz bibliotekę nagrań.')
    if lib.read_only:
        raise HTTPException(400, 'Nie można zmieniać nagrań bezpośrednio na nośniku Tesli.')

    def run(job):
        decrypt.repair_unplayable(lib, job.progress)
        return lib.summary()
    return state.start('repair', run)


@app.post('/api/open-library')
def open_library(folder: str = Body(..., embed=True)):
    ensure_idle()
    if not os.path.isdir(folder):
        raise HTTPException(404, 'Nie znaleziono folderu.')
    lib = Library(folder, read_only=source_folder(folder))
    added = lib.index_folder()
    if added:
        lib.save()
    state.library = lib
    state.out_dir = lib.folder
    return {'folder': lib.folder, 'counts': lib.summary()}


@app.get('/api/library')
def get_library():
    lib = state.library
    if lib is None:
        raise HTTPException(404, 'Najpierw otwórz bibliotekę nagrań.')
    clips = [{k: e.get(k) for k in ('id', 'file', 'camera', 'recorded_utc', 'title', 'comment', 'source', 'width', 'truncated', 'gap', 'repaired', 'repaired_seconds')} | {'quality': localize_quality(e, language())}
             for e in lib.playable()]
    clips.sort(key=lambda c: (c['recorded_utc'] or 0, c['camera'] or ''))
    unplayable = [{k: e.get(k) for k in ('id', 'file', 'camera', 'start_utc', 'error')} | {'quality': localize_quality(e, language())}
                  for e in lib.entries.values() if e.get('status') != 'ok']
    return {'folder': lib.folder, 'clips': clips, 'other': unplayable}


def _library_file(name):
    lib = state.library
    if lib is None:
        raise HTTPException(404, 'Najpierw otwórz bibliotekę nagrań.')
    path = os.path.abspath(os.path.join(lib.folder, name))
    if not path.startswith(lib.folder + os.sep) or not os.path.isfile(path):
        raise HTTPException(404, 'Nie znaleziono pliku.')
    return path


@app.get('/media/{name:path}')
def media(name: str):
    return FileResponse(_library_file(name), media_type='video/mp4')


@app.get('/api/telemetry')
def telemetry(file: str):
    path = _library_file(file)
    cache_dir = os.path.join(state.library.folder, '.telemetry')
    cache = os.path.join(cache_dir, os.path.basename(file) + '.json')
    if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(path):
        return FileResponse(cache, media_type='application/json')
    try:
        data = read_telemetry(path)
    except Exception as e:
        raise HTTPException(422, 'Brak telemetrii: %s' % e)
    if not state.library.read_only:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache, 'w') as f:
            json.dump(data, f, separators=(',', ':'))
    return JSONResponse(data)


@app.post('/api/save')
def start_save(files: list[str] = Body(...), dest: str = Body(...)):
    ensure_idle()
    if source_folder(dest):
        raise HTTPException(400, 'Wybierz folder na komputerze lub innym dysku. Nie zapisujemy wyników na nośniku Tesli.')
    for name in files:
        _library_file(name)
    return state.start('save', lambda job: export.save_files(state.library.folder, files, dest, job.progress))


@app.post('/api/cancel')
def cancel():
    if state.job:
        state.job.cancel_requested = True
    return {'ok': True}


@app.post('/api/open-folder')
def open_folder(folder: str = Body(None, embed=True)):
    folder = folder or (state.library.folder if state.library else None)
    if folder and os.path.isdir(folder):
        if sys.platform == 'darwin':
            subprocess.Popen(['/usr/bin/open', folder])
        elif os.name == 'nt':
            os.startfile(folder)
        else:
            subprocess.Popen(['xdg-open', folder])
    return {'ok': True}


app.mount('/', StaticFiles(directory=STATIC, html=True), name='static')
