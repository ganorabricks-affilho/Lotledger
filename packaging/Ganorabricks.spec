# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Ganorabricks Mac app."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(root / "mac_app.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "templates"), "templates"),
        (str(root / "static"), "static"),
        (str(root / "data" / "lotledger.db"), "data"),
    ],
    hiddenimports=collect_submodules("webview")
    + [
        "paths",
        "database",
        "money",
        "drawer_layout",
        "bricklink",
        "brickowl",
        "brickstore",
        "minifig_catalog",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Ganorabricks",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Ganorabricks",
)
app = BUNDLE(
    coll,
    name="Ganorabricks.app",
    icon=str(root / "packaging" / "Ganorabricks.icns"),
    bundle_identifier="local.ganorabricks.lotledger",
    info_plist={
        "CFBundleName": "Ganorabricks",
        "CFBundleDisplayName": "Ganorabricks",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
    },
)
