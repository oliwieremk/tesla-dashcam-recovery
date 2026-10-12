#!/usr/bin/env python3
"""Build a universal Finder launcher; source and runtime setup stay inside Resources."""
import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE = {'.git', '.venv', '.tools', '__pycache__', 'build', 'dist', '.DS_Store', 'CLAUDE.md'}


def build(target):
    app = target / 'Tesla Recovery.app'
    if app.exists():
        shutil.rmtree(app)
    resources = app / 'Contents' / 'Resources'
    executable = app / 'Contents' / 'MacOS'
    executable.mkdir(parents=True)
    resources.mkdir(parents=True)
    shutil.copytree(ROOT, resources / 'app', ignore=lambda folder, names: [
        n for n in names if n in EXCLUDE or n.endswith(('.egg-info', '.pyc', '.img'))])
    shutil.copy2(ROOT / 'macos' / 'TeslaRecovery.icns', resources / 'TeslaRecovery.icns')
    sdk = subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip()
    with tempfile.TemporaryDirectory(prefix='tesla-build-') as folder:
        binaries = []
        for arch in ('arm64', 'x86_64'):
            binary = str(Path(folder) / arch)
            subprocess.run(['swiftc', '-O', '-sdk', sdk, '-target', f'{arch}-apple-macos13.0',
                            '-framework', 'Cocoa', str(ROOT / 'macos' / 'Launcher.swift'), '-o', binary], check=True)
            binaries.append(binary)
        subprocess.run(['lipo', '-create', *binaries, '-output', str(executable / 'TeslaRecovery')], check=True)
    info = {'CFBundleName': 'Tesla Recovery', 'CFBundleDisplayName': 'Tesla Recovery',
            'CFBundleIdentifier': 'local.teslarecover.macos.pl', 'CFBundleExecutable': 'TeslaRecovery',
            'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': '0.3.0',
            'CFBundleVersion': '3', 'CFBundleIconFile': 'TeslaRecovery.icns',
            'CFBundleDevelopmentRegion': 'en', 'CFBundleLocalizations': ['pl', 'en'], 'LSMinimumSystemVersion': '13.0',
            'NSHighResolutionCapable': True,
            'NSHumanReadableCopyright': 'MIT — original: Arquiteto; local macOS port',
            'NSAppTransportSecurity': {'NSAllowsLocalNetworking': True}}
    with open(app / 'Contents' / 'Info.plist', 'wb') as destination:
        plistlib.dump(info, destination)
    subprocess.run(['codesign', '--force', '--sign', '-', str(app)], check=True)
    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    print(build(args.destination))
