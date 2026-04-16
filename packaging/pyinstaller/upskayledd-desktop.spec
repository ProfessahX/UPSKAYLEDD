# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


ROOT = Path.cwd()
SRC_DIR = ROOT / "src"
DESKTOP_DIR = ROOT / "apps" / "desktop"
CONFIG_DIR = ROOT / "config"

if str(DESKTOP_DIR) not in sys.path:
    sys.path.insert(0, str(DESKTOP_DIR))

datas = [
    (str(CONFIG_DIR), "config"),
    (str(ROOT / "README.md"), "."),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "icon.png"), "."),
    (str(ROOT / "LOGO-HEADER.png"), "."),
    (str(ROOT / "Shitposting_pitch_refined.png"), "."),
]

hiddenimports = collect_submodules("pyside_app")

a = Analysis(
    [str(SRC_DIR / "upskayledd" / "desktop_entry.py")],
    pathex=[str(SRC_DIR), str(DESKTOP_DIR)],
    binaries=[],
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
    name="upskayledd-desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / "build" / "branding" / "upskayledd.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="upskayledd-desktop",
)
