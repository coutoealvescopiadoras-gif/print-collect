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

# =============================================================================
# HIDDEN IMPORTS OBRIGATORIOS v6.9.3 — ERRO no cliente: ModuleNotFound yaml!
#   (collect_submodules("requests") nao puxa seus deps internos, yaml tem que ser
#    explicito pois eh import dinamicamente em print_collect.config.load_config())
# =============================================================================
hiddenimports = sorted(
    set(
        [
            "print_collect",
            "print_collect.__main__",
            "print_collect.collector",
            "print_collect.config",
            "print_collect.sender",
            "print_collect.snmp",
            "print_collect.usb",
            # --- PyYAML (NAO FALTAR MAIS! yaml = modulo importado por yaml.safe_load())
            "yaml",
            "_yaml",
            # --- requests + TODOS seus deps (pra nao dar ModuleNotFound de urllib3 charset-normalizer etc):
            "requests",
            "requests.adapters",
            "requests.api",
            "requests.auth",
            "requests.cookies",
            "requests.exceptions",
            "requests.hooks",
            "requests.models",
            "requests.sessions",
            "requests.status_codes",
            "requests.structures",
            "requests.utils",
            "urllib3",
            "urllib3.util",
            "urllib3.util.retry",
            "urllib3.util.ssl_",
            "urllib3.poolmanager",
            "urllib3.connectionpool",
            "urllib3.response",
            "urllib3.exceptions",
            "urllib3.contrib",
            "charset_normalizer",
            "charset_normalizer.api",
            "idna",
            "certifi",
            # --- colorlog / psutil / pystray / PIL (tray icon):
            "colorlog",
            "psutil",
            "psutil._pswindows",
            "psutil._common",
            "psutil._psposix",
            "pystray",
            "pystray._base",
            "pystray._win32",
            "PIL",
            "PIL.Image",
            "PIL._imaging",
            "PIL.ImageDraw",
            "PIL.ImageFont",
            # --- Outros usados no agente (marcadores toner, contadores etc):
            "dateutil",
            "dateutil.parser",
            "dateutil.relativedelta",
            "six",
            "pyasn1",
            "pyasn1.type",
            "pyasn1.codec",
            "pyasn1.compat",
            "pysnmp",
            "pysnmp.carrier",
            "pysnmp.carrier.asyncio",
            "pysnmp.proto",
            "pysnmp.proto.rfc1902",
            "pysnmp.smi",
            "pysnmp.smi.builder",
            "pysnmp.entity",
            "pysnmp.hlapi",
            "pysnmp.hlapi.asyncio",
            "pysnmp.lexer",
            "ply",
            "ply.lex",
            "ply.yacc",
            # --- pywin32: usamos no register-startup-task (tarefa agendada):
            "win32com",
            "win32com.client",
            "win32com.shell",
            "pywintypes",
            "pythoncom",
            "win32api",
            "win32con",
            "win32evtlog",
            "win32net",
            "win32security",
            "win32service",
            "win32ts",
            "win32wnet",
            "pywin32_bootstrap",
            # --- Pacotes de infra PyInstaller (pre-safe-import):
            "packaging",
            "packaging.version",
            "packaging.specifiers",
        ]
        + collect_submodules("print_collect")
        + collect_submodules("pysnmp")
        + collect_submodules("pyasn1")
        + collect_submodules("requests")
        + collect_submodules("urllib3")
        + collect_submodules("colorlog")
        + collect_submodules("psutil")
        + collect_submodules("pystray")
        + collect_submodules("PIL")
        + collect_submodules("ply")
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
