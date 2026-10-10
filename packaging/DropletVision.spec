# Onedir Windows GUI. Only application resources are copied from the checkout.
from pathlib import Path
import runpy
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH).parent
version = runpy.run_path(str(root / 'src/droplet_vision/_version.py'))
# PIMS imports imageio, which asks importlib.metadata for its installed version.
datas = [(str(root / 'LICENSE'), '.')] + copy_metadata('imageio')
for folder in ('annotations', 'photometry', 'sampling'):
    datas += [(str(p), 'configs/' + folder) for p in sorted((root / 'configs' / folder).glob('*.json'))
              if '.local.' not in p.name]
for folder in ('translations', 'assets/icons'):
    datas += [(str(p), 'droplet_vision/ui/' + folder)
              for p in sorted((root / 'src/droplet_vision/ui' / folder).iterdir())
              if p.suffix in ('.json', '.png', '.ico')]

a = Analysis([str(root / 'packaging/entry.py')], pathex=[str(root / 'src')],
             datas=datas, hiddenimports=['pims.cine'],
             # Optional PIMS readers/plotters are not used by the Cine backend.
             excludes=['matplotlib', 'scipy', 'skimage', 'cv2', 'torch', 'tensorflow',
                       'IPython', 'notebook', 'tkinter', 'PyQt5', 'PyQt6', 'PySide2',
                       'pytest', 'pims.bioformats', 'pims.pyav_reader', 'pims.moviepy_reader'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='DropletVision',
          console=False, debug=False, strip=False, upx=False,
          icon=str(root / 'src/droplet_vision/ui/assets/icons/planico.ico'),
          version=str(root / 'build/windows/version_info.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='DropletVision')
