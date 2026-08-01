import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH).resolve().parents[1]
agent_root = project_root / "agent"
entry_script = agent_root / "print_collect" / "__main__.py"

if str(agent_root) not in sys.path:
    sys.path.insert(0, str(agent_root))

hiddenimports = sorted(
    set(
        [
            "print_collect",
            "print_collect.collector",
            "print_collect.config",
            "print_collect.sender",
            "print_collect.snmp",
        ]
        + collect_submodules("print_collect")
        + collect_submodules("pysnmp")
        + collect_submodules("pyasn1")
        + collect_submodules("requests")
    )
)

a = Analysis(
    [str(entry_script)],
    pathex=[str(agent_root)],
    binaries=[],
    datas=[],
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
    name="PrintCollectAgent",
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
