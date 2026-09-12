# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['charset_normalizer', 'idna', 'certifi', 'colorlog', 'psutil', 'psutil._pswindows', 'pystray', 'pystray._win32', 'PIL._imaging', 'pythoncom', 'pywintypes', 'win32com.client', 'win32api', 'win32con', 'pysnmp', 'pysnmp.hlapi', 'pysnmp.hlapi.asyncio', 'ply', 'ply.lex', 'ply.yacc', 'pyasn1', 'pyasn1.type', 'pyasn1.codec.ber', 'pyasn1.codec.der', 'dateutil.parser', 'six', 'packaging']
hiddenimports += collect_submodules('yaml')
hiddenimports += collect_submodules('requests')
hiddenimports += collect_submodules('urllib3')
hiddenimports += collect_submodules('PIL')
hiddenimports += collect_submodules('dateutil')
tmp_ret = collect_all('pyyaml')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('requests')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['../WizardPareamento.py'],
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
    a.binaries,
    a.datas,
    [],
    name='WizardPareamento',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
