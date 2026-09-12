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
            "print_collect.__main__",
            "print_collect.collector",
            "print_collect.config",
            "print_collect.sender",
            "print_collect.snmp",
            "print_collect.usb",
            # ============ FIX YAML (ModuleNotFound: No module named 'yaml') ============
            # PyYAML - modulo EXATO que faltava no cliente. Incluir SEMPRE!
            "yaml",
            "_yaml",
            "yaml.constructor",
            "yaml.dumper",
            "yaml.emitter",
            "yaml.error",
            "yaml.loader",
            "yaml.nodes",
            "yaml.parser",
            "yaml.reader",
            "yaml.representer",
            "yaml.resolver",
            "yaml.scanner",
            "yaml.serializer",
            "yaml.events",
            "yaml.tokens",
            "yaml.composer",
            "yaml.cyaml",
            # --- requests + TODOS os seus submódulos e dependências ---
            "requests",
            "requests.__version__",
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
            "requests.packages",
            "requests.packages.urllib3",
            "urllib3",
            "urllib3.util",
            "urllib3.util.retry",
            "urllib3.util.ssl_",
            "urllib3.util.url",
            "urllib3.util.request",
            "urllib3.util.response",
            "urllib3.util.timeout",
            "urllib3.util.connection",
            "urllib3.poolmanager",
            "urllib3.connectionpool",
            "urllib3.response",
            "urllib3.exceptions",
            "urllib3.contrib",
            "urllib3.contrib.socks",
            "urllib3.fields",
            "urllib3.filepost",
            "urllib3.request",
            "urllib3.connection",
            "urllib3._collections",
            "urllib3.collections",
            "urllib3.http",
            "urllib3.http.response",
            "urllib3.http.parser",
            "urllib3.http.util",
            "charset_normalizer",
            "charset_normalizer.api",
            "charset_normalizer.cd",
            "charset_normalizer.md",
            "charset_normalizer.models",
            "charset_normalizer.utils",
            "charset_normalizer.version",
            "charset_normalizer.assets",
            "idna",
            "idna.idnadata",
            "idna.core",
            "idna.intranet",
            "idna.package_data",
            "certifi",
            "certifi.core",
            # --- colorlog, psutil, pystray / PIL (icone bandeja) ---
            "colorlog",
            "colorlog.colorlog",
            "colorlog.escape_codes",
            "colorlog.logging",
            "psutil",
            "psutil._common",
            "psutil._pswindows",
            "psutil._compat",
            "pystray",
            "pystray._base",
            "pystray._win32",
            "pystray._win32_cffi",
            "pystray._util",
            "PIL",
            "PIL.Image",
            "PIL._imaging",
            "PIL.ImageDraw",
            "PIL.ImageFont",
            "PIL.ImageFilter",
            "PIL._imagingcms",
            "PIL._imagingmath",
            "PIL._imagingmorph",
            "PIL.BmpImagePlugin",
            "PIL.GifImagePlugin",
            "PIL.IcoImagePlugin",
            "PIL.JpegImagePlugin",
            "PIL.PngImagePlugin",
            "PIL.TiffImagePlugin",
            # --- dateutil / six / packaging ---
            "dateutil",
            "dateutil._common",
            "dateutil.parser",
            "dateutil.parser._parser",
            "dateutil.parser.isoparser",
            "dateutil.relativedelta",
            "dateutil.rrule",
            "dateutil.tz",
            "dateutil.tz.win",
            "dateutil.tz._common",
            "six",
            "six.moves",
            "packaging",
            "packaging.version",
            "packaging.specifiers",
            "packaging.requirements",
            "packaging.markers",
            "packaging.tags",
            "packaging._structures",
            # --- pysnmp + ply lex/yacc (SNMP scanner) ---
            "pysnmp",
            "pysnmp.carrier",
            "pysnmp.carrier.asyncio",
            "pysnmp.carrier.asyncio.dgram",
            "pysnmp.carrier.asyncio.dgram.udp",
            "pysnmp.entity",
            "pysnmp.entity.engine",
            "pysnmp.entity.rfc3413",
            "pysnmp.hlapi",
            "pysnmp.hlapi.asyncio",
            "pysnmp.proto",
            "pysnmp.proto.api",
            "pysnmp.proto.rfc1902",
            "pysnmp.proto.rfc1905",
            "pysnmp.smi",
            "pysnmp.smi.builder",
            "pysnmp.smi.mibs",
            "pysnmp.smi.exval",
            "pysnmp.smi.view",
            "pysnmp.lexer",
            "pysnmp.lexer.buf",
            "ply",
            "ply.lex",
            "ply.yacc",
            # --- pyasn1 (dependencia do pysnmp) ---
            "pyasn1",
            "pyasn1.type",
            "pyasn1.type.base",
            "pyasn1.type.constraint",
            "pyasn1.type.error",
            "pyasn1.type.namedtype",
            "pyasn1.type.namedval",
            "pyasn1.type.opentype",
            "pyasn1.type.tag",
            "pyasn1.type.tagmap",
            "pyasn1.type.univ",
            "pyasn1.type.useful",
            "pyasn1.codec",
            "pyasn1.codec.ber",
            "pyasn1.codec.ber.decoder",
            "pyasn1.codec.ber.encoder",
            "pyasn1.codec.cer",
            "pyasn1.codec.der",
            "pyasn1.codec.native",
            "pyasn1.compat",
            "pyasn1.compat.octets",
            "pyasn1.compat.integer",
            "pyasn1.error",
            "pyasn1.debug",
            # --- pywin32 (tarefa agendada, COM, shell) ---
            "win32com",
            "win32com.client",
            "win32com.client.build",
            "win32com.client.gencache",
            "win32com.client.dynamic",
            "win32com.client.makepy",
            "win32com.shell",
            "win32com.shell.shell",
            "win32com.shell.receivers",
            "pywintypes",
            "pythoncom",
            "pywin32_bootstrap",
            "pywintypes._win32sysloader",
            "win32api",
            "win32con",
            "win32evtlog",
            "win32net",
            "win32security",
            "win32service",
            "win32ts",
            "win32wnet",
        ]
        + collect_submodules("print_collect")
        + collect_submodules("yaml")
        + collect_submodules("requests")
        + collect_submodules("urllib3")
        + collect_submodules("charset_normalizer")
        + collect_submodules("certifi")
        + collect_submodules("idna")
        + collect_submodules("colorlog")
        + collect_submodules("psutil")
        + collect_submodules("pystray")
        + collect_submodules("PIL")
        + collect_submodules("pysnmp")
        + collect_submodules("ply")
        + collect_submodules("pyasn1")
        + collect_submodules("dateutil")
        + collect_submodules("win32com")
        + collect_submodules("pywintypes")
        + collect_submodules("pythoncom")
        + collect_submodules("packaging")
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
