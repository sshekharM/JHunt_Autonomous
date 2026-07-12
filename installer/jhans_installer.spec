# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for jHANS_Setup.exe
# Run:  python build_exe.py
# Or:   pyinstaller --clean jhans_installer.spec

import sys
import os

block_cipher = None

a = Analysis(
    ['wizard.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('assets/', 'installer/assets/'),
        ('pages/', 'installer/pages/'),
        ('core/', 'installer/core/'),
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.scrolledtext',
        'installer.pages.welcome',
        'installer.pages.prerequisites',
        'installer.pages.install_dir',
        'installer.pages.database',
        'installer.pages.oauth',
        'installer.pages.llm',
        'installer.pages.notifications',
        'installer.pages.portals',
        'installer.pages.admin',
        'installer.pages.install',
        'installer.core.env_writer',
        'installer.core.docker_runner',
        'installer.core.prereq_checker',
        'installer.core.autostart',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='jHANS_Setup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # No console window (windowed app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
    uac_admin=True,       # Request UAC elevation on Windows
    version=None,
)
