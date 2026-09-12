# -*- mode: python ; coding: utf-8 -*-
# PrintCollectAgent.spec v6.9.6+ (atualizado!) — CAMINHOS RELATIVOS + TODOS hiddenimports obrigatórios
# (evita ModuleNotFoundError: 'yaml'/'charset_normalizer'/'pysnmp' que quebrou Wizard na v6.9.3!)

a = Analysis(
    ['agent\\print_collect\\__main__.py'],
    pathex=['agent', 'agent\\.pydeps'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'yaml', 'yaml.loader', 'yaml.constructor', 'yaml.parser',
        'requests', 'requests.exceptions', 'requests.auth',
        'charset_normalizer', 'charset_normalizer.api', 'charset_normalizer.md',
        'pysnmp', 'pysnmp.hlapi', 'pysnmp.hlapi.asyncio',
        'pysnmp.proto', 'pysnmp.proto.rfc1902', 'pysnmp.proto.rfc1905',
        'pysnmp.entity', 'pysnmp.entity.rfc3413', 'pysnmp.entity.rfc3413.oneliner',
        'pysnmp.carrier', 'pysnmp.carrier.asyncio', 'pysnmp.carrier.asyncio.dgram',
        'pyasn1', 'pyasn1.type', 'pyasn1.type.univ', 'pyasn1.type.namedtype',
        'pyasn1.type.constraint', 'pyasn1.type.tag', 'pyasn1.type.tagmap',
        'pyasn1.codec', 'pyasn1.codec.ber', 'pyasn1.codec.ber.encoder',
        'pyasn1.codec.ber.decoder', 'pyasn1.codec.cer', 'pyasn1.codec.der',
        'urllib3', 'urllib3.util', 'urllib3.util.retry', 'urllib3.poolmanager',
        'idna', 'certifi', 'tzdata', 'zoneinfo', 'backports.zoneinfo',
        'platformdirs',
    ],
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
    name='PrintCollectAgent',
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
