"""Build the Windows onedir distribution, optional Inno installer and checksums."""
from __future__ import annotations
import argparse
import hashlib
from importlib.metadata import distribution, PackageNotFoundError
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def version_info(version):
    numeric = version['WINDOWS_VERSION']
    fields = {'CompanyName': 'xiaorouqiuzi-ai', 'FileDescription': 'Droplet Vision',
              'FileVersion': version['DISPLAY_VERSION'], 'ProductName': 'Droplet Vision',
              'ProductVersion': version['DISPLAY_VERSION'], 'OriginalFilename': 'DropletVision.exe',
              'LegalCopyright': 'Copyright (c) 2026 xiaorouqiuzi-ai'}
    strings = ',\n'.join(f'StringStruct({key!r}, {value!r})' for key, value in fields.items())
    return (f'VSVersionInfo(ffi=FixedFileInfo(filevers={numeric!r}, prodvers={numeric!r}, '
            'mask=0x3f, flags=2, OS=0x40004, fileType=1, subtype=0, date=(0, 0)), '
            f"kids=[StringFileInfo([StringTable('040904B0', [{strings}])]), "
            "VarFileInfo([VarStruct('Translation', [1033, 1200])])])")


def audit_distribution(directory):
    prohibited = {'.cine', '.dvapkg', '.dvrpkg', '.pyc'}
    prohibited_dirs = {'tests', 'outputs', '.git', '__pycache__', 'example'}
    for path in directory.rglob('*'):
        relative = path.relative_to(directory)
        if path.suffix.lower() in prohibited or any(p.lower() in prohibited_dirs for p in relative.parts):
            raise ValueError(f'Unexpected release artifact: {relative}')
        if path.is_file() and path.suffix.lower() in {'.json', '.toml', '.ini', '.cfg', '.md', '.txt', '.py'}:
            text = path.read_text(encoding='utf-8', errors='replace')
            for private in (str(ROOT), str(Path(sys.prefix)), str(Path.home())):
                if private.casefold() in text.casefold() or private.replace('\\', '/').casefold() in text.casefold():
                    raise ValueError(f'Local build path in release text: {relative}')
    if not (directory / 'DropletVision.exe').is_file():
        raise ValueError('Executable missing')
    if not list(directory.rglob('qwindows.dll')):
        raise ValueError('Qt Windows platform plugin missing')


def make_zip(directory, destination):
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(directory.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(directory.parent).as_posix())


def copy_dependency_licenses(portable):
    """Keep the license files shipped with the actual build dependencies."""
    for name in ('PySide6_Essentials', 'shiboken6', 'numpy', 'Pillow', 'pims',
                 'slicerator', 'imageio', 'tifffile', 'packaging', 'psutil'):
        try:
            dist = distribution(name)
        except PackageNotFoundError:
            continue
        for path in dist.files or []:
            if '.dist-info' in str(path) and ('license' in path.name.lower() or 'copying' in path.name.lower()):
                target = portable / 'licenses' / name / path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dist.locate_file(path), target)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.is_file():
        shutil.copy2(python_license, portable / 'licenses/Python-LICENSE.txt')


def find_iscc():
    executable = shutil.which('ISCC.exe')
    if executable:
        return executable
    for base in (os.environ.get('ProgramFiles(x86)'), os.environ.get('ProgramFiles'),
                 str(Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs')):
        if base:
            candidate = Path(base) / 'Inno Setup 6/ISCC.exe'
            if candidate.is_file():
                return str(candidate)
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installer-only', action='store_true', help='Reuse already audited portable directory')
    parser.add_argument('--iscc', help='Optional path to Inno Setup 6 compiler')
    args = parser.parse_args(argv)
    if sys.platform != 'win32' or sys.maxsize < 2**32:
        parser.error('Build with 64-bit Python on Windows')
    version = runpy.run_path(str(ROOT / 'src/droplet_vision/_version.py'))
    tag = 'v' + version['DISPLAY_VERSION']
    release = ROOT / 'release' / tag
    portable = release / f'DropletVision-{tag}-win64'
    work = ROOT / 'build/windows'
    release.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    (work / 'version_info.txt').write_text(version_info(version), encoding='utf-8')
    if not args.installer_only:
        # DLL discovery must not inherit unrelated Qt/ICU tools from a developer PATH.
        environment = dict(os.environ)
        environment.pop('PYTHONPATH', None)
        environment['PATH'] = os.pathsep.join([str(Path(sys.executable).parent),
            sys.base_prefix, str(Path(os.environ['SystemRoot']) / 'System32'), os.environ['SystemRoot']])
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                        '--workpath', str(work / 'pyinstaller'), '--distpath', str(ROOT / 'dist'),
                        str(ROOT / 'packaging/DropletVision.spec')], cwd=ROOT, env=environment, check=True)
        if portable.exists():
            # Delete only this exact generated version directory, never caller input.
            if portable.resolve().parent != release.resolve() or portable.is_symlink():
                raise ValueError('Unsafe build output path')
            shutil.rmtree(portable)
        shutil.copytree(ROOT / 'dist/DropletVision', portable)
        shutil.copy2(ROOT / 'LICENSE', portable / 'LICENSE')
        copy_dependency_licenses(portable)
    audit_distribution(portable)
    archive = release / (portable.name + '.zip')
    if not args.installer_only:
        make_zip(portable, archive)
    notes = (ROOT / 'packaging/RELEASE_NOTES.md').read_text(encoding='utf-8')
    (release / 'RELEASE_NOTES.md').write_text(notes.replace('@VERSION@', tag), encoding='utf-8')
    compiler = args.iscc or find_iscc()
    assets = [archive]
    if compiler:
        subprocess.run([compiler, '/DAppVersion=' + version['DISPLAY_VERSION'],
                        '/DNumericVersion=' + '.'.join(map(str, version['WINDOWS_VERSION'])),
                        '/DPortableDir=' + str(portable), '/DReleaseDir=' + str(release),
                        str(ROOT / 'packaging/DropletVision.iss')], cwd=ROOT, check=True)
        assets.append(release / f'DropletVision-Setup-{tag}.exe')
    else:
        print('Installer unavailable: Inno Setup 6 not installed. Portable ZIP is ready.')
    sums = []
    for path in assets:
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        sums.append(f'{digest.hexdigest()}  {path.name}\n')
    (release / 'SHA256SUMS.txt').write_text(''.join(sums), encoding='ascii')
    print(f'Release assets: {release}')


if __name__ == '__main__':
    main()
