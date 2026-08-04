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
    config            Abre o config.yaml no editor padrao do sistema.
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
        interval_minutes=720,
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

    from print_collect.snmp import (
        collect_targets,
        discover_local_subnets,
        scan_subnet,
    )

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


def cmd_install(args: argparse.Namespace) -> int:
    """Registra tarefa de inicializacao automatica.
    NO WINDOWS: estrategia MAIS SEGURA de todas:
      (1) APAGA as tarefas antigas (08h/18h legado) se existirem.
      (2) CRIA 'Print Collect Agent - A Cada 1 HORA (repeticao INFINITA).
      (3) CRIA 'Print Collect Agent - Ao Logar' (coleta no login).
      Tudo isso feito VIA register-startup-task-silent.bat (nao tem erro de aspas, 100% testado!)."""
    import os

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
        # ESTRATEGIA 100% CONFIÁVEL: RODAR OS .BAT (que nós já codamos!)
        # - register-startup-task-silent.bat (mesma pasta do EXE)
        #   O que .bat faz (100% testado!):
        #   [0/4] APAGA tarefas antigas: 08h e 18h (legado)
        #   [1/4] Cria  Print Collect Agent - A Cada 1 HORA (PT1H INFINITO)
        #   [2/4] Cria  Print Collect Agent - Ao Logar
        #   [3/4] Roda once agora (teste!)
        #   [4/4] Mensagem sucesso.
        # =====================================================================

        # Localiza a pasta do instalador / pasta do agente runtime:
        #   -> Se EXE compilado (PyInstaller): pasta do proprio exe
        #   -> Se script dev: agent/windows/runtime (local)
        if getattr(sys, "frozen", False):
            agent_dir = Path(sys.executable).resolve().parent
        else:
            # Dev: assumimos que o modulo esta em <repo>/agent/print_collect/__main__.py
            # E os .bat em <repo>/agent/windows/runtime  e <repo>/agent/windows
            here = Path(__file__).resolve().parent.parent
            agent_dir = here / "windows"
            if not (agent_dir / "register-startup-task-silent.bat").exists():
                # fallback: runtime/
                candidate = here / "windows" / "runtime"
                if candidate.exists():
                    agent_dir = candidate

        # 1) Tentar SILENT.bat primeiro (sem pausa), se nao existir tenta o interativo (com pause)
        bat_silent = agent_dir / "register-startup-task-silent.bat"
        bat_interativo = agent_dir / "register-startup-task.bat"
        chosen_bat = bat_silent if bat_silent.exists() else bat_interativo

        if not chosen_bat.exists():
            # Fallback: tentar pasta runtime se agente colocaram em outra subpasta
            candidate_runtime = agent_dir / "runtime" / "register-startup-task-silent.bat"
            if candidate_runtime.exists():
                chosen_bat = candidate_runtime
            else:
                print(f"[ERRO GRAVE] Nao encontrei register-startup-task-silent.bat nem em: {agent_dir}")
                print(f"      Conteudo da pasta: {list(agent_dir.glob('*.bat'))}")
                # Ultimo recurso: rodar uma vez 'once' mas nao agenda (agendamento falhou)
                print("\n[!] Nao agendou, mas coletando UMA VEZ para testar...")
                base_cmd_once = base_cmd + ["once"]
                _exe_cmd(base_cmd_once)
                return 1

        print(f"\n[OK] Script de agendamento encontrado: {chosen_bat}")

        # Copia o config.yaml para o local esperado pelo bat (C:\ProgramData\PrintCollect\config.yaml)
        # Garantir que o agente e o config estao presentes (o bat ja copia de qualquer forma)
        print(f"\n[1/2] Rodando script de instalacao (tarefas agendadas 1/HORA)...")
        try:
            # RODAR O .BAT (sem shell=True p/ .bat
            result = subprocess.run(
                ["cmd.exe", "/C", str(chosen_bat)],
                shell=False,
                check=False,
                cwd=str(chosen_bat.parent),
            )
            rc_install = result.returncode
        except Exception as e_bat:
            print(f"[ERRO] Falha ao rodar bat de agendamento: {e_bat}")
            rc_install = 1

        # Roda uma vez 'once' uma vez agora para confirmar (passo 3/4 do .bat ja deve ter rodado):
        print("\n[2/2] Rodando coleta UMA VEZ agora p/ testar...")
        base_cmd_once = base_cmd + ["once"]
        _exe_cmd(base_cmd_once)

        print("\n[DICA] Para ver as tarefas no Windows:")
        print("       Painel de Controle > Ferramentas Administrativas > Agendador de Tarefas")
        print("       OU: schtasks /Query | findstr 'Print Collect'")
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
    try:
        class _InstArgs:
            system = False
            config = str(actual_config_path)
        rc = cmd_install(_InstArgs)
        if rc == 0:
            instalou_ok = True
            print("[OK] Inicializacao automatica instalada com sucesso!")
            print("     (Agente inicia sozinho toda vez que ligar o PC!)")
    except Exception as e:
        print(f"[AVISO] Nao foi possivel instalar inicializacao: {e}")
        print("     (Voce pode instalar depois pelo atalho: Reinstalar inicializacao)")

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
        print(f" · Auto inicializa  : ✅ INSTALADA (inicia com o Windows!)")
    else:
        print(f" · Auto inicializa  : ⚠️  Instale depois pelo atalho")
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
