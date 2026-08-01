import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH).resolve().parents[1]
agent_root = project_root / "agent"
entry_script = agent_root / "print_collect" / "__main__.py"

if str(agent_root) not in sys.path:
    sys.path.insert(0, str(agent_root))

# -----------------------------------------------------------------------------
# TARGET_ARCH: OBRIGATORIO para builds 32 bits.
# Para INSTALAR EM QUALQUER WINDOWS, DEVE-SE GERAR x86 (32 bits)!
#   - Exe x86 (32 bits) roda em Windows 32 bits E Windows 64 bits (WOW64)
#   - Exe x64 (64 bits) NAO roda em Windows 32 bits (erro "arquivo valido mas
#     para outro tipo de computador")
# Como forcar:
#   - Use o script build-setup-x86.ps1 (ele ja roda tudo com TARGET_ARCH=x86)
#   - Ou, manualmente, rode o build com Python 32 bits instalado:
#       CMD:      set TARGET_ARCH=x86 && pyinstaller ...
#       PowerShell: $env:TARGET_ARCH='x86'; pyinstaller ...
# -----------------------------------------------------------------------------
_target_arch = os.environ.get("TARGET_ARCH", "").strip().lower()
if not _target_arch:
    _target_arch = None  # None = mesma arquitetura do Python que esta rodando

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
    target_arch=_target_arch,
    codesign_identity=None,
    entitlements_file=None,
)
