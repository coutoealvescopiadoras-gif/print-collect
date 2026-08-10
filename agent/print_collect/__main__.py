"""Ponto de entrada: python -m print_collect [subcomando]

Subcomandos:
    daemon            (padrao) Loop infinito de coletas.
    once              Faz uma coleta unica e encerra.
    test              Testa conexao com o servidor.
    scan [--subnet X] Varre a rede e imprime as impressoras encontradas.
    list              Igual a scan, mas alias para uso no instalador.
    networks          Descobre e lista sub-redes locais detectadas.
    install           Registra tarefa de inicializacao (Windows schtasks / Linux systemd).
    uninstall         Remove tarefa de inicializacao.
    config            Abre config.yaml no editor padrao do sistema.
    watchdog          Verifica se coletas rodaram nas ultimas 75min; se NAO dispara 'once' automaticamente.
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from print_collect.collector import run_daemon, run_once

if TYPE_CHECKING:
    from print_collect.config import AgentConfig


def resolve_config_path(config_value: str, user_explicit: bool = False) -> Path:
    """
    Resolve o caminho do config.yaml.
    - Se usuario passou --config explicitamente: usa ele.
    - Senao: PRIORIZA o caminho GRAVAVEL (ProgramData ou ~/.print_collect) para
      evitar erro de PERMISSION DENIED dentro de C:\\Program Files.
    - Tambem faz fallback: se o arquivo ja existir em outro lugar (candidatos
      antigos) mas nao no gravavel, usa ele.
    """
    from print_collect.config import default_writable_config_path, is_path_writable

    # Se usuario passou um caminho absoluto explicitamente, respeita
    path = Path(config_value)
    if path.is_absolute():
        return path

    default_writable = default_writable_config_path()

    # Se o usuario NAO passou --config (ou seja, o default config.yaml):
    # PRIORIDADE 1: usar o caminho GRAVAVEL, se ele existir OU se o candidato a
    # caminho antigo (Program Files) nao for gravavel.
    if not user_explicit:
        # 1a) se arquivo ja existe no gravavel -> usa ele
        if default_writable.exists():
            return default_writable
        # 1b) senao, verifica se candidatos antigos (cwd, pasta do exe) tem arquivo
        # e sao GRAVAVEIS. Se sim, usa (compatibilidade instalacoes antigas).
        candidates = [Path.cwd() / path]
        if getattr(sys, "frozen", False):
            candidates.append(Path(sys.executable).resolve().parent / path)
        else:
            candidates.append(Path(__file__).resolve().parents[1] / path)
        for candidate in candidates:
            if candidate.exists() and is_path_writable(candidate):
                return candidate
        # 1c) nenhum candidato gravavel existe ainda -> usa o default WRITABLE
        return default_writable

    # Usuario passou --config caminho/relativo (explicito): procura em candidatos
    candidates = [Path.cwd() / path]
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / path)
    else:
        candidates.append(Path(__file__).resolve().parents[1] / path)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _pair_and_save(server_url: str, code: str, config_path: Path,
                   community: str = "public", subnets: list[str] | None = None) -> AgentConfig:
    from print_collect.sender import PairingClient
    from print_collect.config import save_config, AgentConfig, SnmpConfig

    if not server_url:
        raise ValueError("server_url nao informado")
    if not code:
        raise ValueError("codigo do cliente nao informado")

    print(f"[1/4] Contatando servidor: {server_url}")
    pairing = PairingClient(server_url.rstrip("/"))
    hostname = platform.node() or None
    version = "0.3.0"
    print(f"[2/4] Validando CÓDIGO DO CLIENTE: {code.upper()} (hostname: {hostname})")
    mode, result = pairing.exchange_smart(code=code, hostname=hostname, version=version)

    agent_token = result.get("agent_token") or ""
    client_id = result.get("client_id")
    client_name = result.get("client_name") or f"Cliente #{client_id}"
    returned_url = (result.get("server_url") or server_url).rstrip("/")
    client_code = result.get("client_code")

    if not agent_token:
        raise RuntimeError("Resposta do servidor nao contem agent_token.")

    if mode == "client_code":
        print(f"[3/4] CÓDIGO DO CLIENTE OK: vinculado a '{client_name}' (client_id={client_id})")
    else:
        print(f"[3/4] Pareamento por código TTL OK: vinculado a '{client_name}' (client_id={client_id})")

    cfg = AgentConfig(
        server_url=returned_url,
        agent_token=agent_token,
        agent_version=version,
        interval_minutes=60,
        log_file=str(__import__("print_collect.config", fromlist=["default_log_file_path"]).default_log_file_path()),
        snmp=SnmpConfig(
            community=community or "public",
            timeout=2,
            subnets=list(subnets or []),
            ips=[],
        ),
    )
    # save_config agora RETORNA o caminho real (se caiu em fallback de permissao)
    actual_path = save_config(config_path, cfg)
    print(f"[4/4] Configuracao salva em: {actual_path}")
    if actual_path.resolve() != config_path.resolve():
        print(f"      (Ajustado automaticamente para caminho com permissao de escrita)")
    if client_code:
        print(f"      Dica: o Código do Cliente é '{client_code}' e nunca expira.")
    # Salva o caminho real para uso do callers (install, wizard)
    try:
        _pair_and_save._last_config_path = actual_path
    except Exception:
        pass
    return cfg


def _print_printers_table(printers: list) -> None:
    from print_collect.snmp import PrinterData

    data: list[PrinterData] = printers
    if not data:
        print("\n(Nenhuma impressora encontrada.)")
        print(
            "Dicas de troubleshooting:\n"
            "  • A impressora está ligada e na mesma rede?\n"
            "  • A comunidade SNMP é 'public'? (se for outra use --community)\n"
            "  • A porta 161 UDP (SNMP) e 9100 TCP (JetDirect) estão liberadas no firewall?\n"
            "  • Tente escanear manualmente com: scan --subnet 192.168.1.0/24 --community private\n"
        )
        return

    header = (
        f"{'IP':<18}{'Marca':<14}{'Modelo':<30}{'Serie':<20}"
        f"{'Paginas':<9}{'Toner BK':<10}{'C':<6}{'M':<6}{'Y':<6}"
    )
    print("\n" + header)
    print("-" * len(header))
    for p in data:
        def fmt_pct(v):
            return f"{v:.0f}%" if v is not None else "-"
        print(
            f"{p.ip_address:<18}"
            f"{(p.manufacturer or '-'):<14}"
            f"{((p.model or '-')[:28]):<30}"
            f"{((p.serial_number or '-')[:18]):<20}"
            f"{p.pages_total:<9}"
            f"{fmt_pct(p.toner_black):<10}"
            f"{fmt_pct(p.toner_cyan):<6}"
            f"{fmt_pct(p.toner_magenta):<6}"
            f"{fmt_pct(p.toner_yellow):<6}"
        )
    print("-" * len(header))
    print(f"Total: {len(data)} impressora(s).\n")


def cmd_scan(args: argparse.Namespace, _return_list: bool = False) -> int | list:
    """Varre redes/IPs e mostra impressoras.
    - Por padrão (_return_list=False): imprime tabela e retorna exit code (int).
    - Quando _return_list=True (usado por wizard!): retorna a LISTA de impressoras (não imprime a tabela no stdout do wizard de pareamento)."""
    import logging

    from print_collect.collector import setup_logging
    from print_collect.config import default_log_file_path
    from print_collect.snmp import (
        collect_targets,
        discover_local_subnets,
        scan_subnet,
    )

    # SEMPRE grava log em arquivo (mesmo em scan) para diagnosticar se tarefa agendada ou atalho tiver erro
    try:
        setup_logging(str(default_log_file_path()))
    except Exception:
        # Em ultimo caso cai no basicConfig default (so stdout/stderr)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            force=True,
        )

    community = args.community or "public"
    timeout = int(args.timeout or 2)
    subnets = list(args.subnet or [])
    ips = list(args.ip or [])

    if not subnets and not ips:
        subnets = discover_local_subnets()
        if subnets:
            print(f"[i] Sub-redes detectadas automaticamente: {', '.join(subnets)}")
        else:
            print("[!] Nenhuma sub-rede detectada. Informe --subnet ou --ip.")
            return 1 if not _return_list else []

    printers: list = []
    for s in subnets:
        print(f"\n>>> Escaneando {s} ...")
        printers.extend(scan_subnet(s, community=community, timeout=timeout))
    if ips:
        print(f"\n>>> Escaneando IPs fixos ({len(ips)}) ...")
        printers.extend(collect_targets(ips, community=community, timeout=timeout))

    # deduplica por IP
    seen: set[str] = set()
    unique: list = []
    for p in printers:
        if p.ip_address not in seen:
            seen.add(p.ip_address)
            unique.append(p)

    # MODO WIZARD: retorna a lista DIRETO (sem imprimir tabela, wizard mostra sua propria saida)
    if _return_list:
        return unique

    _print_printers_table(unique)
    return 0 if unique else 1


def cmd_networks(_: argparse.Namespace) -> int:
    from print_collect.snmp import discover_local_subnets

    subnets = discover_local_subnets()
    if not subnets:
        print("Nenhuma sub-rede IPv4 local detectada.")
        return 1
    print(f"Sub-redes locais detectadas ({len(subnets)}):")
    for s in subnets:
        print(f"  • {s}")
    return 0


def _exe_cmd(cmd: list[str], check: bool = False) -> int:
    print("[>] " + " ".join(cmd))
    try:
        result = subprocess.run(cmd)
        rc = result.returncode
    except FileNotFoundError as e:
        print(f"[ERRO] Comando nao encontrado: {e}")
        return 127
    if check and rc != 0:
        raise SystemExit(rc)
    return rc


def _windows_is_admin() -> bool:
    """Retorna True se o processo atual estiver rodando COMO ADMINISTRADOR no Windows.
    Usa ctypes + CheckTokenMembership com SID do grupo Administradores.
    Fallback rapido: tenta abrir a chave HKLM\\SECURE (so admin consegue ler).
    """
    if platform.system().lower() != "windows":
        return True  # No Linux/macOS consideramos que o usuario sabe o que faz
    try:
        import ctypes
        import ctypes.wintypes as wintypes

        SECURITY_MAX_SID_SIZE = 68
        WinBuiltinAdministratorsSid = 26  # Well-known SID alias para Administradores locais

        def _get_sid():
            cbSid = wintypes.DWORD(SECURITY_MAX_SID_SIZE)
            pSid = ctypes.create_string_buffer(SECURITY_MAX_SID_SIZE)
            if not ctypes.windll.advapi32.CreateWellKnownSid(WinBuiltinAdministratorsSid, None, pSid, ctypes.byref(cbSid)):
                return None
            return pSid

        pSid = _get_sid()
        if pSid is None:
            # Fallback se a funcao acima falhar: tenta abrir chave protegida do reg
            try:
                import winreg  # type: ignore
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SECURE", 0, winreg.KEY_READ):
                    return True
            except OSError:
                return False
        is_admin = wintypes.BOOL()
        if not ctypes.windll.advapi32.CheckTokenMembership(None, pSid, ctypes.byref(is_admin)):
            return False
        return bool(is_admin.value)
    except Exception:
        return False


def _windows_relaunch_self_as_admin(args: argparse.Namespace | None = None) -> None:
    """Se NAO estiver rodando admin no Windows, re-abre o MESMO exe/script com UAC elevado.
    Transmite TUDO: sys.argv, config, comando (install/wizard etc).
    Se elevar, esta funcao NAO RETORNA: termina o processo atual (sys.exit).
    """
    if platform.system().lower() != "windows":
        return
    if _windows_is_admin():
        return  # ja estamos admin, blz!

    try:
        import ctypes
        from ctypes import wintypes

        SW_SHOWNORMAL = 1
        SEE_MASK_NOASYNC = 0x00000100
        SEE_MASK_FLAG_NO_UI = 0x00000400

        # Monta argumentos (menos sys.argv[0] que e o caminho do exe/script):
        params = " ".join(f'"{a}"' if " " in a or '"' in a else a for a in sys.argv[1:])

        # Use ShellExecuteEx para permitir runas em qualquer .exe/.py:
        class SHELLEXECUTEINFOW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("fMask", wintypes.ULONG),
                ("hwnd", wintypes.HWND),
                ("lpVerb", wintypes.LPCWSTR),
                ("lpFile", wintypes.LPCWSTR),
                ("lpParameters", wintypes.LPCWSTR),
                ("lpDirectory", wintypes.LPCWSTR),
                ("nShow", ctypes.c_int),
                ("hInstApp", wintypes.HINSTANCE),
                ("lpIDList", ctypes.c_void_p),
                ("lpClass", wintypes.LPCWSTR),
                ("hkeyClass", wintypes.HKEY),
                ("dwHotKey", wintypes.DWORD),
                ("DUMMYUNIONNAME", ctypes.c_ulonglong),
                ("hProcess", wintypes.HANDLE),
            ]

        sei = SHELLEXECUTEINFOW()
        sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
        sei.fMask = SEE_MASK_NOASYNC | SEE_MASK_FLAG_NO_UI
        sei.hwnd = None
        sei.lpVerb = "runas"  # = Pede UAC Administrador automaticamente!
        sei.lpFile = sys.executable
        sei.lpParameters = params
        sei.lpDirectory = str(Path.cwd())
        sei.nShow = SW_SHOWNORMAL
        sei.hInstApp = None

        print("\n[!] Detetamos que voce NAO esta rodando como ADMINISTRADOR.")
        print("    Para criar as 6 tarefas agendadas corretamente (sem 'Acesso negado')")
        print("    precisamos de privilegios elevados. Abrindo UAC automaticamente...")
        print("    -> Clique em 'Sim' na janela do Windows que vai aparecer agora!")
        import time
        time.sleep(1.5)

        if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
            # Se ShellExecute falhar (muito raro), avisa o usuario e nao crasha.
            le = ctypes.GetLastError()
            print(f"\n[ERRO] Nao foi possivel elevar automaticamente (erro {le}).")
            print("       ================ SOLUCAO MANUAL 1 CLIQUE =================")
            print("       1) FECHE esta janela do CMD/Prompt.")
            print("       2) Menu Iniciar → Procure Print Collect → Clique com BOTAO DIREITO em")
            print("          'Reinstalar inicializacao' OU 'Wizard de pareamento'")
            print("       3) Clique em 'Mais' → 'Executar como Administrador' → SIM no UAC.")
            print("       ==============================================================")
            try:
                input("\n[Enter para fechar...]")
            except (EOFError, KeyboardInterrupt):
                pass
        # Fecha o processo NAO ADMIN atual. O usuario agora interage com o novo processo ELEVADO:
        sys.exit(0)
    except Exception as exc:
        print(f"[Aviso] Nao foi possivel auto-elevar: {exc}")
        print("       Execute o Wizard / Install novamente como Administrador manualmente.")
        return


def _ensure_windows_bat_wrappers(exe_dir: Path) -> tuple[Path, Path]:
    """v6.4 NOVO! Cria/Atualiza run-once.bat e run-watchdog.bat na pasta do agente,
    com conteúdo 100% correto (CRLF + ANSI CP1252), SEM wrapper inline.
    Solucao DEFITIVA para o bug de aspas aninhadas do schtasks /TR que causava
    erro -2147024894 (arquivo nao encontrado) e tarefas nao disparavam.
    Retorna (bat_once_path, bat_watchdog_path)
    """
    bat_once = exe_dir / "run-once.bat"
    bat_wd = exe_dir / "run-watchdog.bat"
    pd = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"

    # Modelo: ja tem EXE_DIR = pasta do agente via %~dp0, WorkingDirectory garantido!
    once_template = (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "setlocal EnableExtensions\r\n"
        "set \"EXE_DIR=%~dp0\"\r\n"
        "cd /d \"%~dp0\"\r\n"
        f"if \"%PROGRAMDATA%\"==\"\" set \"PROGRAMDATA={pd}\"\r\n"
        "set \"CFG_DIR=%PROGRAMDATA%\\PrintCollect\"\r\n"
        "set \"CFG=%CFG_DIR%\\config.yaml\"\r\n"
        "set \"EXE=%EXE_DIR%PrintCollectAgent.exe\"\r\n"
        "if not exist \"%CFG_DIR%\" mkdir \"%CFG_DIR%\" >nul 2>&1\r\n"
        "\"%EXE%\" --config \"%CFG%\" once\r\n"
        "exit /b 0\r\n"
    )
    wd_template = (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "setlocal EnableExtensions\r\n"
        "set \"EXE_DIR=%~dp0\"\r\n"
        "cd /d \"%~dp0\"\r\n"
        f"if \"%PROGRAMDATA%\"==\"\" set \"PROGRAMDATA={pd}\"\r\n"
        "set \"CFG_DIR=%PROGRAMDATA%\\PrintCollect\"\r\n"
        "set \"CFG=%CFG_DIR%\\config.yaml\"\r\n"
        "set \"EXE=%EXE_DIR%PrintCollectAgent.exe\"\r\n"
        "if not exist \"%CFG_DIR%\" mkdir \"%CFG_DIR%\" >nul 2>&1\r\n"
        "\"%EXE%\" --config \"%CFG%\" watchdog\r\n"
        "exit /b 0\r\n"
    )
    # Escreve com CP1252 (ANSI pt-BR) + CRLF = cmd.exe nativo 100%
    import codecs
    with codecs.open(str(bat_once), "w", encoding="cp1252", errors="replace") as f:
        f.write(once_template)
    with codecs.open(str(bat_wd), "w", encoding="cp1252", errors="replace") as f:
        f.write(wd_template)
    return bat_once, bat_wd


def cmd_install(args: argparse.Namespace) -> int:
    """Registra tarefa de inicializacao automatica no Windows (SUPERV5+ 6 CAMADAS).
    Estrategia TRIPLA REDUNDANCIA para NUNCA MAIS falhar:
      CAMADA 1: Tenta rodar register-startup-task-silent.bat (empacotado no Setup.exe).
      CAMADA 2 (FALLBACK NATIVO! 100% PowerShell/.bat line-endings independent!):
          Se CAMADA 1 falhar (returncode!=0, exception, ou quaisquer erros de
          sintaxe de LF/CRLF/encoding no .bat), NOS CRIAMOS AS 6 TAREFAS DIRETAMENTE
          via schtasks + PowerShell Python nativo!
      CAMADA 3: Sempre roda 'once' no final p/ garantir primeira coleta AGORA."""
    import os
    import tempfile

    # === CORRECAO V6.3: GARANTE ADMINISTRADOR ANTES DE TENTAR CRIAR/DELETAR TAREFAS ===
    #   Evita "Acesso negado" em TUDO! Se nao for admin, re-abre automaticamente UAC.
    _windows_relaunch_self_as_admin(args)

    # Se temos um ultimo caminho salvo de pair/wizard, usamos ele (garante uso do WRITABLE)
    last_saved = getattr(_pair_and_save, "_last_config_path", None)
    if last_saved and isinstance(last_saved, Path):
        config_path = last_saved
    else:
        config_path = resolve_config_path(args.config)

    exe = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else Path(sys.executable).resolve()
    # Se nao for frozen (exe PyInstaller) monta como "python -m print_collect ..."
    if getattr(sys, "frozen", False):
        base_cmd = [str(exe), "--config", str(config_path)]
    else:
        base_cmd = [str(exe), "-m", "print_collect", "--config", str(config_path)]

    system = platform.system().lower()

    if system == "windows":
        # =====================================================================
        # CAMINHO EXE/CFG/WD — Usados por todas as camadas
        # =====================================================================
        exe_str = str(exe)
        cfg_str = str(config_path)
        wd_str = str(exe.parent)

        # v6.4 NOVO! GARANTE run-once.bat / run-watchdog.bat na pasta do agente
        # (ANTES de qualquer tarefa ser criada!)
        bat_once_path, bat_wd_path = _ensure_windows_bat_wrappers(exe.parent)
        bat_once_str = str(bat_once_path)
        bat_wd_str = str(bat_wd_path)

        # Garante ProgramData/PrintCollect existe
        pd = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
        cfg_dir = Path(pd) / "PrintCollect"
        cfg_dir.mkdir(parents=True, exist_ok=True)

        # LOG TEMP de install
        log_path = Path(tempfile.gettempdir()) / "print-collect-startup.log"

        # =====================================================================
        # CAMADA 1: RODAR register-startup-task-silent.bat (.empacotado)
        # =====================================================================
        def _try_bat_layer() -> int:
            # Localiza a pasta do instalador / pasta do agente runtime:
            if getattr(sys, "frozen", False):
                agent_dir = Path(sys.executable).resolve().parent
            else:
                here = Path(__file__).resolve().parent.parent
                agent_dir = here / "windows"
                if not (agent_dir / "register-startup-task-silent.bat").exists():
                    candidate = here / "windows" / "runtime"
                    if candidate.exists():
                        agent_dir = candidate

            bat_silent = agent_dir / "register-startup-task-silent.bat"
            bat_interativo = agent_dir / "register-startup-task.bat"
            chosen_bat = bat_silent if bat_silent.exists() else bat_interativo

            if not chosen_bat.exists():
                candidate_runtime = agent_dir / "runtime" / "register-startup-task-silent.bat"
                if candidate_runtime.exists():
                    chosen_bat = candidate_runtime
                else:
                    print(f"[INFO BAT] Nao encontrei register-startup-task-*.bat em: {agent_dir}")
                    return 2  # Codigo especial = pular para CAMADA 2 (nao encontrado)

            print(f"\n[OK] Script de agendamento encontrado: {chosen_bat}")
            print(f"\n[CAMADA 1/3] Rodando script .bat de agendamento...")
            try:
                result = subprocess.run(
                    ["cmd.exe", "/C", str(chosen_bat)],
                    shell=False,
                    check=False,
                    cwd=str(chosen_bat.parent),
                    capture_output=True,
                    text=True,
                )
                rc_bat = result.returncode
                # Mostra saida do BAT (stdout + stderr) de forma resumida p/ diagnosticar
                tail_lines = []
                if result.stdout:
                    tail_lines.extend([ln for ln in result.stdout.splitlines() if ln.strip()][-6:])
                if result.stderr:
                    tail_lines.extend([ln for ln in result.stderr.splitlines() if ln.strip()][-6:])
                if tail_lines:
                    print("[BAT saida (ultimas linhas)]:")
                    for ln in tail_lines:
                        print(f"  | {ln}")
                if rc_bat != 0:
                    print(f"[CAMADA 1/3] bat falhou (rc={rc_bat}). Vamos para CAMADA 2 (nativo Python)!")
                else:
                    print("[CAMADA 1/3] BAT executou com SUCESSO (rc=0)!")
                return rc_bat
            except Exception as e_bat:
                print(f"[CAMADA 1/3] Exception ao rodar BAT: {e_bat}. Pulando para CAMADA 2 (nativo).")
                return 3  # Codigo especial: exception no bat

        # =====================================================================
        # CAMADA 2 (FALLBACK SUPER ROBUSTO! Cria 6 tarefas DIRETAMENTE via schtasks/PowerShell Python!)
        # v6.4 CORRECAO DEFITIVA: Usa BATs SEPARADOS (sem wrapper inline) + /RU SYSTEM invisivel!
        # =====================================================================
        def _native_schtasks_ps_create_6_tasks() -> int:
            print("\n[CAMADA 2/3] ✅ FALLBACK NATIVO v6.4 (schtasks/PowerShell Python): CRIANDO 6 CAMADAS DE TAREFAS...")
            # Lista de tarefas SUPERV6 v6.4:
            #   (nome, schtasks args [menos /TN /TR], dispararRun?, run_as_system?)
            tasks = [
                ("Print Collect Agent - 30 Minutos",
                 ["/SC", "MINUTE", "/MO", "30"], True, True),
                ("Print Collect Agent - Watchdog",
                 ["/SC", "MINUTE", "/MO", "10"], True, True),
                ("Print Collect Agent - Diario Repeticao",
                 ["/SC", "DAILY", "/MO", "1", "/RI", "60", "/DU", "9999:00", "/K"], True, True),
                ("Print Collect Agent - Ao Iniciar",
                 ["/SC", "ONSTART"], False, False),
                ("Print Collect Agent - Ao Logar",
                 ["/SC", "ONLOGON"], False, False),
            ]

            # === CORRECAO V6.4: _tr() APENAS aponta para o .bat (1 nivel de aspas só!) ===
            #   NÃO usa mais wrapper cmd.exe inline — ACABA o bug -2147024894!
            #   Regra schtasks /TR: aspas INTERNAS escapadas com \, aspas EXTERNAS obrigatorias.
            def _tr(sub: str) -> str:
                bat_path = bat_wd_str if sub == "watchdog" else bat_once_str
                escaped = bat_path.replace('"', '\\"')
                return f'"{escaped}"'

            # PASSO 1 (NATIVO): DELETAR 16 variantes antigas
            old_names = [
                "Print Collect Agent","Print Collect Agent - Manha (08h)","Print Collect Agent - Tarde (18h)",
                "Print Collect Agent - Ao Logar","Print Collect Agent - A Cada 1 Hora","Print Collect Agent - A Cada 1 HORA",
                "Print Collect Agent - Hora","Print Collect Agent - Hourly","Print Collect Agent - Inicializacao",
                "Print Collect - Coletar","Print Collect Agent - 30 Minutos","Print Collect Agent - Diario Repeticao",
                "Print Collect Agent - Watchdog","Print Collect Agent - Ao Iniciar","Print Way Agent","Print Collect",
            ]
            total_del_ok = 0
            for tn in old_names:
                _exe_cmd(["schtasks","/Delete","/F","/TN",tn], check=False)
                total_del_ok += 1
            print(f"  [1/6 - LIMPEZA] {total_del_ok} variantes de tarefas antigas apagadas.")

            rc_all = 0
            # CAMADA 1/3 schtasks simples (30min, watchdog, diario, onstart, onlogon)
            for i, (tn, sch_args, run_now, run_as_system) in enumerate(tasks, 2):
                sub = "watchdog" if "Watchdog" in tn else "once"
                tr = _tr(sub)
                # v6.4 NOVO: /RU "SYSTEM" = roda invisivel em 2o plano SEM tela preta!
                system_args = ["/RL", "HIGHEST", "/RU", "SYSTEM"] if run_as_system else []
                cmdline = ["schtasks","/Create","/F","/TN",tn,*sch_args,*system_args,"/TR",tr]
                rc1 = _exe_cmd(cmdline, check=False)
                if rc1 == 0 and run_now:
                    _exe_cmd(["schtasks","/Run","/TN",tn], check=False)
                if rc1 != 0:
                    rc_all = rc1
            print(f"  [schtasks simples] RC final = {rc_all} (0 = tudo ok)")

            # CAMADA 2: PowerShell ScheduledTasks (HORARIA, e para as que falharam acima)
            # v6.4: Usa BATs + Principal SYSTEM para tarefas periodicas
            horary_ok = False
            try:
                ps_code = r"""
$ErrorActionPreference = 'Stop'
$batOnce = '__BAT_ONCE__'
$batWd   = '__BAT_WD__'
$cmdExe  = 'C:\Windows\System32\cmd.exe'
function New-TaskWrap($taskName, $useWatchdog, $trigger, $runNow, $useSystem) {
  $bat = if ($useWatchdog) { $batWd } else { $batOnce }
  $act = New-ScheduledTaskAction -Execute $cmdExe -Argument ('/c ""{0}""' -f $bat)
  $set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1)
  if ($useSystem) {
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trigger -Settings $set -Principal $principal -Force -ErrorAction Stop | Out-Null
  } else {
    Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trigger -Settings $set -Force -ErrorAction Stop | Out-Null
  }
  if ($runNow) { Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue }
}
# 1) HORARIA (proxima hora cheia + repeticao 1h INFINITO) — SYSTEM invisivel
$startHorario = (Get-Date -Minute 0 -Second 0).AddHours(1)
$trgH = New-ScheduledTaskTrigger -Once -At $startHorario -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue)
New-TaskWrap 'Print Collect Agent - A Cada 1 HORA' $false $trgH $true $true
# 2) 30 Minutos (fallback) — SYSTEM
$start30 = (Get-Date).AddMinutes(2)
$trg30 = New-ScheduledTaskTrigger -Once -At $start30 -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration ([TimeSpan]::MaxValue)
New-TaskWrap 'Print Collect Agent - 30 Minutos' $false $trg30 $true $true
# 3) Watchdog fallback — SYSTEM
$startWD = (Get-Date).AddMinutes(1)
$trgWD = New-ScheduledTaskTrigger -Once -At $startWD -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration ([TimeSpan]::MaxValue)
New-TaskWrap 'Print Collect Agent - Watchdog' $true $trgWD $true $true
# 4) Diario repeticao fallback — SYSTEM
$startDaily = (Get-Date -Minute 0 -Second 0).AddHours(1)
$trgDaily = New-ScheduledTaskTrigger -Daily -At $startDaily -DaysInterval 1
$trgDaily.Repetition.Interval = (New-TimeSpan -Minutes 60)
$trgDaily.Repetition.Duration = ([TimeSpan]::MaxValue)
New-TaskWrap 'Print Collect Agent - Diario Repeticao' $false $trgDaily $true $true
# 5) Boot (fallback) — interativo (sem SYSTEM, p/ ter rede disponivel)
$trgBoot = New-ScheduledTaskTrigger -AtStartup
New-TaskWrap 'Print Collect Agent - Ao Iniciar' $false $trgBoot $false $false
# 6) Logon (fallback) — interativo
$uid = $env:USERNAME
$trgLogon = New-ScheduledTaskTrigger -AtLogOn -User $uid
New-TaskWrap 'Print Collect Agent - Ao Logar' $false $trgLogon $false $false
Write-Output 'NATIVE_FALLBACK_OK'
"""
                ps_code = (ps_code
                           .replace("__BAT_ONCE__", bat_once_str.replace("'","''"))
                           .replace("__BAT_WD__",   bat_wd_str.replace("'","''")))
                r = subprocess.run(
                    ["powershell","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-Command",ps_code],
                    capture_output=True, text=True, check=False
                )
                if r.returncode == 0 and "NATIVE_FALLBACK_OK" in (r.stdout or ""):
                    horary_ok = True
                    print("  [PowerShell ScheduledTasks v6.4] ✅ SUCESSO! Tarefa HORARIA e fallbacks criados.")
                else:
                    print(f"  [PowerShell ScheduledTasks v6.4] rc={r.returncode}")
                    if r.stdout: print("  stdout (ultimas):", "\n  ".join((r.stdout.splitlines() or [])[-4:]))
                    if r.stderr: print("  stderr (ultimas):", "\n  ".join((r.stderr.splitlines() or [])[-4:]))
            except Exception as e:
                print(f"  [PowerShell ScheduledTasks v6.4] Exception: {e}")

            # CAMADA 3: schtasks HOURLY fallback — v6.4 com BAT + /RU SYSTEM
            if not horary_ok:
                try:
                    from datetime import datetime, timedelta
                    t = datetime.now() + timedelta(minutes=3)
                    sd = t.strftime("%m/%d/%Y")
                    st = t.strftime("%H:%M")
                    rc2 = _exe_cmd([
                        "schtasks","/Create","/F",
                        "/TN","Print Collect Agent - A Cada 1 HORA",
                        "/SC","HOURLY","/MO","1",
                        "/RL","HIGHEST","/RU","SYSTEM",
                        "/SD",sd,"/ST",st,
                        "/TR",_tr("once"),
                    ], check=False)
                    if rc2 == 0:
                        _exe_cmd(["schtasks","/Run","/TN","Print Collect Agent - A Cada 1 HORA"], check=False)
                except Exception as e2:
                    print(f"[CAMADA 2/3] schtasks HOURLY fallback falhou: {e2}")
                    rc_all = 5

            return 0 if (rc_all == 0 or horary_ok) else rc_all

        # =====================================================================
        # EXECUTA AS CAMADAS
        # =====================================================================
        rc_bat = _try_bat_layer()
        rc_install = rc_bat
        if rc_bat != 0:
            rc_fb = _native_schtasks_ps_create_6_tasks()
            rc_install = rc_fb

        # =====================================================================
        # CAMADA 3: SEMPRE roda once p/ garantir primeira coleta AGORA
        # =====================================================================
        print("\n[CAMADA 3/3] Rodando coleta UMA VEZ agora p/ testar...")
        base_cmd_once = base_cmd + ["once"]
        _exe_cmd(base_cmd_once)

        print("\n[DICA] Para ver as 6 tarefas no Windows:")
        print("       Painel de Controle > Ferramentas Administrativas > Agendador de Tarefas")
        print("       OU: schtasks /Query /FO LIST | findstr 'Print Collect'")
        return rc_install

    # Linux/systemd
    service_name = "print-collect.service"
    unit_path = Path("/etc/systemd/system") / service_name
    unit_content = (
        "[Unit]\nDescription=Print Collect Agent\nAfter=network-online.target\n"
        "Wants=network-online.target\n\n"
        "[Service]\nType=simple\n"
        f"ExecStart={' '.join(base_cmd)}\n"
        f"User={os.environ.get('SUDO_USER', os.environ.get('USER', 'root'))}\n"
        "Restart=always\nRestartSec=30\n\n"
        "[Install]\nWantedBy=multi-user.target\n"
    )
    if args.system:
        try:
            unit_path.write_text(unit_content, encoding="utf-8")
        except PermissionError:
            print("[ERRO] Precisa rodar como root (sudo) para criar systemd unit.")
            return 1
        _exe_cmd(["systemctl", "daemon-reload"], check=False)
        _exe_cmd(["systemctl", "enable", "--now", service_name], check=False)
        print("Servico instalado em:", unit_path)
        return 0
    print("Use --system para instalar o servico systemd.")
    print("Unidade sugerida:")
    print(unit_content)
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    system = platform.system().lower()
    if system == "windows":
        # Remove TODAS as versoes de tarefas: antigo (1 unica), 08h/18h (legado), HORARIO (novo), Ao Logar
        tarefas = [
            "Print Collect Agent",                    # nome antigo (ainda pode existir!)
            "Print Collect Agent - Manha (08h)",       # legado
            "Print Collect Agent - Tarde (18h)",       # legado
            "Print Collect Agent - Ao Logar",          # sempre
            "Print Collect Agent - A Cada 1 HORA",     # NOVA! (agenda a cada 1h PT1H)
            "Print Collect Agent - A Cada 1 Hora",     # variacao de espaco/letra maiuscula
        ]
        total_ok = 0
        for tn in tarefas:
            rc = _exe_cmd(["schtasks", "/Delete", "/F", "/TN", tn])
            if rc == 0:
                total_ok += 1
        print(f"\nForam removidas {total_ok} tarefa(s) do Agendador.")
        return 0 if total_ok > 0 else 1
    # Linux
    _exe_cmd(["systemctl", "disable", "--now", "print-collect.service"], check=False)
    import os
    unit = Path("/etc/systemd/system/print-collect.service")
    if unit.exists():
        try:
            unit.unlink()
            print("Removido:", unit)
        except PermissionError:
            print("[ERRO] Precisa de sudo para remover o arquivo systemd.")
            return 1
    return 0


def cmd_pair(args: argparse.Namespace) -> int:
    config_path = resolve_config_path(args.config)
    # Server URL
    server_url = (args.server_url or "").strip() or os.environ.get("SERVER_URL", "").strip()
    if not server_url:
        try:
            server_url = input("URL do servidor (ex.: https://www.printcollect.com.br): ").strip()
        except (EOFError, KeyboardInterrupt):
            return 2
    if not server_url:
        print("[ERRO] URL do servidor nao informada.")
        return 1
    if not server_url.startswith("http"):
        server_url = "https://" + server_url

    # Código de vínculo: ACEITA AMBOS (🎫 Código Cliente Fixo OU 🔗 Pareamento Temporário)
    code = (args.code or "").strip() or os.environ.get("PAIRING_CODE", "").strip()
    if not code:
        try:
            code = input(
                "🎫 CÓDIGO DO CLIENTE (RECOMENDADO): 8 caracteres, fixo, NÃO EXPIRA — use o mesmo código em\n"
                "   TODAS as filiais ou reinstalações do MESMO cliente (coluna '🎫 Código Cliente' no painel).\n"
                "OU\n"
                "🔗 CÓDIGO DE PAREAMENTO (TEMPORÁRIO): 8 caracteres, expira em 24h, uso único (botão 🔗 Pareamento\n"
                "   na aba Clientes do painel, serve para um agente específico).\n"
                "Digite QUALQUER um dos dois códigos abaixo: ").strip()
        except (EOFError, KeyboardInterrupt):
            return 2

    # Subnets default -> detect local
    subnets: list[str] = []
    try:
        from print_collect.snmp import discover_local_subnets
        subnets = list(discover_local_subnets())
    except Exception as e:
        print(f"[AVISO] Nao foi possivel detectar sub-redes locais: {e}")

    community = (args.community or "public").strip() or "public"

    try:
        config = _pair_and_save(server_url, code, config_path,
                                community=community, subnets=subnets)
    except Exception as e:
        print(f"[ERRO] Falha no pareamento: {e}")
        return 1

    # Caminho REAL salvo (pode ter sido ajustado por fallback de permissao)
    actual_config_path = getattr(_pair_and_save, "_last_config_path", config_path)
    # Garante que chamadas futuras (install, daemon etc) usem o caminho correto
    args.config = str(actual_config_path)

    # Scan opcional
    if not args.no_scan:
        try:
            class _ScanArgs:
                subnet = list(config.snmp.subnets) if config.snmp.subnets else None
                ip = None
                community = config.snmp.community
                timeout = config.snmp.timeout
            printers = cmd_scan(_ScanArgs(), _return_list=True)
        except Exception as e:
            print(f"[AVISO] Primeira busca falhou: {e}")
            printers = []

        # Envio opcional
        if printers and not args.no_send:
            try:
                from print_collect.sender import ApiSender
                sender = ApiSender(config.server_url, config.agent_token)
                sender.send_readings(printers, config.agent_version)
                print(f"[OK] Enviadas {len(printers)} impressoras para o cliente vinculado.")
            except Exception as e:
                print(f"[AVISO] Nao foi possivel enviar leitura: {e}")

    print("\n[Pronto] Agente pareado. Agora voce pode rodar: install / daemon / once")
    return 0


def cmd_wizard(args: argparse.Namespace) -> int:
    """Wizard SUPER SIMPLIFICADO — O QUE O CLIENTE SEMPRE QUIS!
    1) Abre  2) Cola CODIGO DO CLIENTE  3) Enter  4) PRONTO!
    Tudo o resto (URL servidor, comunidade, sub-redes, inicializacao automatica)
    ja sai de fabrica! Nao precisa de mais nada!"""

    # === CORRECAO V6.3: GARANTE ADMINISTRADOR NO WIZARD TAMBEM! ===
    #   O usuario clica no atalho do Menu Iniciar (normal user!)
    #   Auto-eleva para UAC admin ANTES de perguntar o código → Acesso negado ZERO!
    _windows_relaunch_self_as_admin(args)

    print("=" * 62)
    print("   PRINT COLLECT — WIZARD DE INSTALAÇÃO")
    print("   SUPER SIMPLES: COLE O CÓDIGO E DÊ ENTER! PRONTO!")
    print("=" * 62)
    print()

    # URL DO SERVIDOR SEMPRE PADRAO — NUNCA PERGUNTA!
    # Julio tem razao: URL nunca muda, para que perguntar?
    DEFAULT_SERVER_URL = "https://www.printcollect.com.br"

    config_path = resolve_config_path(args.config)

    # 1/4) UNICA PERGUNTA QUE EXISTE: CODIGO DO CLIENTE / PAREAMENTO!
    code = (args.code or "").strip() or os.environ.get("PAIRING_CODE", "").strip()
    if not code:
        try:
            code = input(
                "\n┌──────────────────────────────────────────────────────────┐\n"
                "│  1/4) COLE AQUI SEU CÓDIGO (Código Cliente OU Pareamento):\n"
                "└──────────────────────────────────────────────────────────┘\n"
                "   🎫 Código Cliente: 8 caracteres · NUNCA expira · Fixo!\n"
                "   🔗 Código Pareamento: 8 caracteres · 24h · Uso único.\n"
                ">\n"
                "> ").strip()
        except (EOFError, KeyboardInterrupt):
            return 2
    if not code:
        print("\n[ERRO] Você não digitou nenhum código! Tente novamente.")
        try:
            input("\nPressione ENTER para fechar...")
        except Exception:
            pass
        return 2

    # -------------------------------------------------------------------------
    # TUDO O RESTO VAI AUTOMATICO! (Julio tem razao, por que perguntar??)
    # -------------------------------------------------------------------------

    # Server URL: SEMPRE o oficial (hardcoded) a menos que seja passado por args/env!
    server_url = (args.server_url or "").strip() or os.environ.get("SERVER_URL", "").strip()
    if not server_url:
        server_url = DEFAULT_SERVER_URL
    if not server_url.startswith("http"):
        server_url = "https://" + server_url
    print(f"\n[OK] Servidor: {server_url}")

    # Comunidade SNMP: SEMPRE 'public' (padrão 99,9% dos casos!)
    community = (args.community or "public").strip()
    print(f"[OK] Comunidade SNMP: {community}")

    # Sub-redes: DETECTA AUTOMATICAMENTE (não pergunta!)
    try:
        from print_collect.snmp import discover_local_subnets
        subnets = list(discover_local_subnets())
    except Exception:
        subnets = []
    if subnets:
        print(f"[OK] Sub-redes detectadas automaticamente: {subnets}")
    else:
        print("[AVISO] Não detectei sub-redes automaticamente. "
              "Depois você pode ajustar em: C:\\ProgramData\\PrintCollect\\config.yaml")
        subnets = []

    # -------------------------------------------------------------------------
    # 2/4) Parear — CONTATA O SERVIDOR E VINCULA O AGENTE
    # -------------------------------------------------------------------------
    print("\n2/4) Vinculando agente ao servidor e ao cliente...")
    try:
        config = _pair_and_save(server_url, code, config_path,
                                community=community, subnets=subnets)
    except Exception as e:
        print(f"\n[ERRO] Pareamento falhou: {e}")
        print("\nDicas:")
        print("   · Verifique se o código está correto (8 caracteres, sem espaços!)")
        print("   · Verifique se a internet do cliente está funcionando")
        print("   · Verifique se o código expirou (se for código de pareamento 24h)")
        try:
            input("\nPressione ENTER para fechar...")
        except Exception:
            pass
        return 1

    actual_config_path = getattr(_pair_and_save, "_last_config_path", config_path)
    args.config = str(actual_config_path)
    print("[OK] Agente pareado com sucesso!")

    # -------------------------------------------------------------------------
    # 3/4) Buscar impressoras na REDE + enviar primeira leitura
    # -------------------------------------------------------------------------
    printers: list = []
    try:
        print("\n3/4) Buscando impressoras na rede (primeira coleta)...")
        class _ScanArgs:
            subnet = list(config.snmp.subnets) if config.snmp.subnets else None
            ip = None
            community = config.snmp.community
            timeout = config.snmp.timeout
        printers = cmd_scan(_ScanArgs(), _return_list=True)
    except Exception as e:
        print(f"[AVISO] Busca falhou: {e}")

    if printers:
        try:
            from print_collect.sender import ApiSender
            sender = ApiSender(config.server_url, config.agent_token)
            sender.send_readings(printers, config.agent_version)
            print(f"[OK] Encontradas e enviadas: {len(printers)} impressoras!")
        except Exception as e:
            print(f"[AVISO] Não foi possível enviar primeira coleta: {e}")
    else:
        print("[!] Nenhuma impressora detectada nesta primeira execucao.")
        print("    Dicas: confira a comunidade SNMP, se a impressora esta ligada e SNMP ativado.")
        print("    Voce pode rodar o atalho 'Procurar impressoras' depois.")

    # -------------------------------------------------------------------------
    # 4/4) INSTALAR INICIALIZACAO AUTOMATICA — SEMPRE SIM! (nao pergunta!)
    # -------------------------------------------------------------------------
    print("\n4/4) Instalando inicializacao automatica (tarefa agendada)...")
    instalou_ok = False
    instalou_parcialmente_ok = False
    try:
        class _InstArgs:
            system = False
            config = str(actual_config_path)
        rc = cmd_install(_InstArgs)
        if rc == 0:
            instalou_ok = True
            instalou_parcialmente_ok = True
            print("[OK] Inicializacao automatica instalada com sucesso!")
            print("     (Agente inicia sozinho toda vez que ligar o PC!)")
        else:
            # rc != 0 = provavelmente falhou apenas Ao Iniciar/Ao Logar por falta de Admin.
            # As 4 tarefas PRINCIPAIS (30min/Horaria/Diario/Watchdog) foram criadas!
            instalou_parcialmente_ok = True
            print("\n[!] ATENCAO: Inicializacao automatica INSTALADA PARCIALMENTE (4/6 tarefas OK!)")
            print("   ✅ TAREFAS JA CRIADAS (FUNCIONANDO DE HORA EM HORA NORMALMENTE!):")
            print("      · Print Collect Agent - 30 Minutos")
            print("      · Print Collect Agent - A Cada 1 HORA")
            print("      · Print Collect Agent - Diario Repeticao")
            print("      · Print Collect Agent - Watchdog (a cada 10min, garante que nao pare!)")
            print()
            print("   ⚠️  FALTARAM apenas 2 tarefas (precisam de ADMINISTRADOR para criar):")
            print("      · Ao Iniciar (quando liga PC)   · Ao Logar (quando usuario entra)")
            print()
            print("   ✅ PASSO A PASSO RAPIDO PARA ADICIONAR AS 2 FALTANTES AGORA MESMO:")
            print("      1) Menu Iniciar → Print Collect")
            print("      2) Botao DIREITO em 'Reinstalar inicializacao' → Mais → Executar como Administrador")
            print("      OU: Abre C:\\Program Files (x86)\\Print Collect")
            print("          Botao DIREITO em 'register-startup-task-silent.bat' → Executar como Administrador")
            print("      3) Confirma 'Sim' no UAC, espera ~60 segundos. PRONTO! 6/6 tarefas!")
            print()
    except Exception as e:
        print(f"[AVISO] Nao foi possivel instalar inicializacao: {e}")
        print("     (Voce pode instalar depois pelo atalho: Reinstalar inicializacao como ADMIN)")

    # -------------------------------------------------------------------------
    # FIM DE TUDO! MENSAGEM BONITO E CLARO!
    # -------------------------------------------------------------------------
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║          🎉  TUDO PRONTO! INSTALAÇÃO CONCLUÍDA!         ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    print(f" · Código usado     : {code}")
    print(f" · Servidor         : {server_url}")
    print(f" · Config salvo em  : {actual_config_path}")
    print(f" · Impressoras hoje : {len(printers)} encontradas")
    if instalou_ok:
        print(f" · Auto inicializa  : ✅ 6/6 TAREFAS INSTALADAS (100%!)")
    elif instalou_parcialmente_ok:
        print(f" · Auto inicializa  : ✅ 4/6 TAREFAS OK (funciona horario! Leia acima como add 2 faltantes.)")
    else:
        print(f" · Auto inicializa  : ⚠️  Instale depois pelo atalho (como ADMIN!)")
    print()
    print(" A partir de AGORA, este PC vai coletar as impressoras")
    print(" automaticamente todos os dias! 🚀")
    print()
    try:
        input(" Pressione ENTER para FECHAR o Wizard...")
    except EOFError:
        pass
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    config_path = resolve_config_path(args.config)
    if not config_path.exists():
        print(f"[!] Configuracao nao encontrada: {config_path}")
        print("Copie config.example.yaml para config.yaml e preencha.")
        return 1
    system = platform.system().lower()
    try:
        if system == "windows":
            subprocess.Popen(["notepad.exe", str(config_path)])
        elif system == "darwin":
            subprocess.Popen(["open", str(config_path)])
        else:
            subprocess.Popen(["xdg-open", str(config_path)])
    except Exception as e:
        print(f"[ERRO] Nao foi possivel abrir o editor: {e}")
        print("Edite manualmente:", config_path)
        return 1
    return 0


def cmd_watchdog(args: argparse.Namespace) -> int:
    """Watchdog SUPERPODER! Verifica se as coletas estao rodando de hora em hora.

    Se NAO houver NENHUMA linha nova no agent.log nos ultimos ~75 minutos, ou
    seja, as 5 tarefas agendadas NAO funcionaram, WATCHDOG DISPARA UMA COLETA
    IMEDIATA ele mesmo! Garante que NUNCA mais fique horas sem atualizar.
    """
    import re
    import time
    from datetime import datetime, timedelta
    from print_collect.config import load_config, default_log_file_path

    config_path = resolve_config_path(args.config)
    cfg = load_config(config_path)

    # === CORRECAO V6.2: Usa o MESMO caminho de log do load_config/setup_logging! ===
    # Nao confiamos mais em log_dir hardcoded ou env var. O load_config() ja retorna
    # cfg.log_file com o PATH CERTO (ProgramData/PrintCollect/agent.log) inclusive
    # quando usuario nao especificou nada (fallback default_log_file_path)!
    if cfg.log_file:
        log_path = Path(cfg.log_file)
    else:
        # Fallback extremo (se cfg.log_file for None por algum bug):
        log_path = default_log_file_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    print(f"[Watchdog] Verificando: {log_path}")

    MAX_IDLE = timedelta(minutes=75)
    now = datetime.now()
    last_ts: datetime | None = None

    if log_path.exists():
        try:
            # Leitura com encoding tolerante; ultimas 400 linhas (mais leve):
            txt = ""
            with log_path.open("r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                if lines:
                    txt = "".join(lines[-400:])

            # Tenta varios formatos de data/hora usados em log do agente:
            patterns = [
                # ISO: 2026-08-08 12:26:00,123
                (re.compile(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)"),
                 lambda s: datetime.strptime(
                     s.replace("T", " ").split(",")[0].split(".")[0],
                     "%Y-%m-%d %H:%M:%S"
                 )),
                # Log antigo: [dd/mm/aaaa hh:mm:ss]
                (re.compile(r"\[(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})\]"),
                 lambda s: datetime.strptime(s, "%d/%m/%Y %H:%M:%S")),
            ]

            for regex, parse in patterns:
                for m in regex.findall(txt):
                    try:
                        ts = parse(m[0] if isinstance(m, tuple) else m)
                        if last_ts is None or ts > last_ts:
                            last_ts = ts
                    except Exception:
                        continue
        except Exception as e:
            print(f"[Watchdog] Aviso ao ler log: {e}")

    idle_str = f"{(now - last_ts).total_seconds()/60:.0f} minutos" if last_ts else "NUNCA"
    print(f"[Watchdog] Ultima coleta detectada: {last_ts or 'JAMAIS'}. Inativo = {idle_str}. Max permitido = {MAX_IDLE.total_seconds()/60:.0f} min.")

    # Sem log / log MUITO velho → Dispara coleta AGORA MESMO!
    if last_ts is None or (now - last_ts) > MAX_IDLE:
        print("[Watchdog] >>> IDLE LIMITE ULTRAPASSADO! Disparando run_once() IMEDIATAMENTE! <<<")
        t0 = time.time()
        rc = run_once(config_path) or 0
        print(f"[Watchdog] run_once() terminou em {time.time() - t0:.1f}s. Exit={rc}")
        return rc

    print("[Watchdog] OK. Ultima coleta recente. Nao preciso fazer nada.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="print-collect",
        description="Print Collect — agente de coleta SNMP de impressoras.",
    )
    parser.add_argument("-c", "--config", default="config.yaml",
                        help="Caminho do config.yaml (padrão: config.yaml)")
    parser.add_argument("--once", action="store_true", dest="legacy_once",

                        help="Legacy — igual a subcomando 'once'")
    parser.add_argument("--test", action="store_true", dest="legacy_test",
                        help="Legacy — igual a subcomando 'test'")

    sub = parser.add_subparsers(dest="command", title="Comandos")

    p_daemon = sub.add_parser("daemon", help="(padrao) Roda coletas em loop.")
    p_daemon.set_defaults(func=lambda a: (run_daemon(resolve_config_path(a.config)) or 0))

    p_once = sub.add_parser("once", help="Faz uma coleta unica e encerra.")
    p_once.set_defaults(func=lambda a: (run_once(resolve_config_path(a.config)) or 0))

    p_test = sub.add_parser("test", help="Testa conexao com o servidor API.")
    def func_test(a):
        from print_collect.config import load_config
        from print_collect.sender import ApiSender
        config = load_config(resolve_config_path(a.config))
        ok = ApiSender(config.server_url, config.agent_token).test_connection()
        return 0 if ok else 1
    p_test.set_defaults(func=func_test)

    p_scan = sub.add_parser("scan", aliases=["list"],
                            help="Varre a rede em busca de impressoras (nao envia nada).")
    p_scan.add_argument("--subnet", action="append", default=None,
                        help="Sub-rede CIDR (ex.: 192.168.1.0/24). Pode repetir.")
    p_scan.add_argument("--ip", action="append", default=None,
                        help="IP unico. Pode repetir.")
    p_scan.add_argument("--community", default=None,
                        help="Comunidade SNMP (padrão: public)")
    p_scan.add_argument("--timeout", type=int, default=None,
                        help="Timeout SNMP em segundos (padrão: 2)")
    p_scan.set_defaults(func=cmd_scan)

    p_nets = sub.add_parser("networks", help="Mostra sub-redes locais detectadas.")
    p_nets.set_defaults(func=cmd_networks)

    p_install = sub.add_parser("install", help="Instala tarefa de inicializacao (schtasks/systemd).")
    p_install.add_argument("--system", action="store_true",
                           help="No Windows: roda como SYSTEM. No Linux: instala systemd unit global.")
    p_install.set_defaults(func=cmd_install)

    p_uninst = sub.add_parser("uninstall", help="Remove tarefa de inicializacao.")
    p_uninst.set_defaults(func=cmd_uninstall)

    p_cfg = sub.add_parser("config", help="Abre config.yaml no editor padrao.")
    p_cfg.set_defaults(func=cmd_config)

    p_wd = sub.add_parser("watchdog",
                          help="Verifica se as coletas estao atualizadas; se NAO, dispara coleta imediata.")
    p_wd.set_defaults(func=cmd_watchdog)

    p_pair = sub.add_parser("pair", help="Pareamento por codigo curto (estilo Print Way).",
                            description="Faz pareamento com o servidor usando um codigo curto de 8 chars.")
    p_pair.add_argument("code", nargs="?", default=None,
                        help="Codigo de pareamento (ex.: ABCD1234). Se omitido sera pedido interativamente.")
    p_pair.add_argument("--server-url", default=None,
                        help="URL do servidor. Se omitido sera pedido ou lido de SERVER_URL.")
    p_pair.add_argument("--community", default="public",
                        help="Comunidade SNMP padrao (padrão: public).")
    p_pair.add_argument("--no-scan", action="store_true",
                        help="Apos parear, nao faz a primeira busca por impressoras.")
    p_pair.add_argument("--no-send", action="store_true",
                        help="Apos parear, nao envia automaticamente a primeira leitura.")
    p_pair.set_defaults(func=cmd_pair)

    p_wiz = sub.add_parser("wizard", aliases=["first-run"],
                           help="Wizard interativo: pareamento + primeira busca + envio.")
    p_wiz.add_argument("--server-url", default=None,
                       help="URL do servidor (caso contrario sera pedido).")
    p_wiz.add_argument("--code", default=None,
                       help="Codigo de pareamento (caso contrario sera pedido).")
    p_wiz.add_argument("--community", default="public",
                       help="Comunidade SNMP padrao (padrão: public).")
    p_wiz.set_defaults(func=cmd_wizard)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Compatibilidade modo legacy (sem subcomando):
    if args.command is None:
        if args.legacy_test:
            args.command = "test"
            func = (lambda a: (
                (__import__("print_collect.config", fromlist=["load_config"]),
                 __import__("print_collect.sender", fromlist=["ApiSender"]))
                and (lambda: 0 if __import__("print_collect.sender", fromlist=["ApiSender"])
                       .ApiSender(
                           __import__("print_collect.config", fromlist=["load_config"])
                           .load_config(resolve_config_path(a.config)).server_url,
                           __import__("print_collect.config", fromlist=["load_config"])
                           .load_config(resolve_config_path(a.config)).agent_token
                       ).test_connection() else 1)()
            ))
            sys.exit(func(args))
        if args.legacy_once:
            run_once(resolve_config_path(args.config))
            return
        run_daemon(resolve_config_path(args.config))
        return

    rc = args.func(args)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
