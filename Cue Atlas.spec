# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_all
import runpy
from pathlib import Path

app_version = runpy.run_path(str(Path(SPECPATH) / 'cueatlas' / '__init__.py'))['__version__']

datas = []
binaries = []
hiddenimports = []
datas += collect_data_files('scipy')
datas += [(str(Path(SPECPATH)/'cueatlas'/'ai_assets'),'cueatlas/ai_assets')]
tmp_ret = collect_all('imageio_ffmpeg')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Cue Atlas',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Cue Atlas',
)
app = BUNDLE(
    coll,
    name='Cue Atlas.app',
    icon=None,
    bundle_identifier='com.cueatlas.desktop',
    version=app_version,
)
