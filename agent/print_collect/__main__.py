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


def resolve_config_path(config_value: str) -> Path:
    path = Path(config_value)
    if path.is_absolute():
        return path

    candidates = [Path.cwd() / path]

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / path)
    else:
        candidates.append(Path(__file__).resolve().parents[1] / path)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


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


def cmd_scan(args: argparse.Namespace) -> int:
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
            return 1

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
    Por padrao roda como USUARIO LOGADO (melhor acesso a rede e AD compartilhadas).
    Use --system para rodar como SYSTEM (antes o padrao do instalador antigo)."""
    import os

    config_path = resolve_config_path(args.config)
    exe = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else Path(sys.executable).resolve()
    # Se nao for frozen (exe PyInstaller) monta como "python -m print_collect ..."
    if getattr(sys, "frozen", False):
        base_cmd = [str(exe), "--config", str(config_path)]
    else:
        base_cmd = [str(exe), "-m", "print_collect", "--config", str(config_path)]

    system = platform.system().lower()
    task_name = "Print Collect Agent"

    if system == "windows":
        schtasks = ["schtasks", "/Create", "/F", "/TN", task_name, "/SC", "ONLOGON", "/TR", " ".join(f'"{x}"' for x in base_cmd)]
        if args.system:
            schtasks.extend(["/RU", "SYSTEM", "/RL", "HIGHEST", "/SC", "ONSTART"])
        rc = _exe_cmd(schtasks)
        if rc == 0:
            print("\n[OK] Tarefa agendada criada. Iniciando agora...")
            _exe_cmd(["schtasks", "/Run", "/TN", task_name])
        return rc

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
    task_name = "Print Collect Agent"
    system = platform.system().lower()
    if system == "windows":
        return _exe_cmd(["schtasks", "/Delete", "/F", "/TN", task_name])
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
        interval_minutes=15,
        snmp=SnmpConfig(
            community=community or "public",
            timeout=2,
            subnets=list(subnets or []),
            ips=[],
        ),
    )
    save_config(config_path, cfg)
    print(f"[4/4] Configuracao salva em: {config_path}")
    if client_code:
        print(f"      Dica: o Código do Cliente é '{client_code}' e nunca expira.")
    return cfg


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
    """Wizard interativo de first run. Pergunta server_url, CÓDIGO DE VÍNCULO
    (aceita 🎫 Código Cliente Fixo OU 🔗 Código de Pareamento Temporário),
    community, faz pareamento, scan, envia primeira leitura, e pergunta se
    quer instalar startup."""

    print("=" * 62)
    print("   PRINT COLLECT — WIZARD DE INSTALAÇÃO")
    print("=" * 62)
    print()

    config_path = resolve_config_path(args.config)

    # Server URL
    server_url = (args.server_url or "").strip() or os.environ.get("SERVER_URL", "").strip()
    if not server_url:
        try:
            server_url = input(
                "1/5) URL do seu servidor Print Collect (padrão: https://www.printcollect.com.br):\n"
                "> ").strip()
        except (EOFError, KeyboardInterrupt):
            return 2
    if not server_url:
        server_url = "https://www.printcollect.com.br"
    if not server_url.startswith("http"):
        server_url = "https://" + server_url
    print(f"     → URL do servidor: {server_url}")

    # CÓDIGO DE VÍNCULO: ACEITA AMBOS (🎫 Código Cliente Fixo OU 🔗 Pareamento Temporário)
    code = (args.code or "").strip() or os.environ.get("PAIRING_CODE", "").strip()
    if not code:
        try:
            code = input(
                "\n2/5) Informe o CÓDIGO DE VÍNCULO para este agente — ACEITAMOS 2 TIPOS DE CÓDIGO:\n"
                "     🎫 OPÇÃO 1 (RECOMENDADO): CÓDIGO DO CLIENTE (coluna '🎫 Código Cliente' na aba Clientes)\n"
                "         · 8 caracteres · NÃO EXPIRA · mesmo código em matriz e TODAS as filiais do mesmo cliente\n"
                "     🔗 OPÇÃO 2: CÓDIGO DE PAREAMENTO (gerado no botão 🔗 Pareamento na aba Clientes)\n"
                "         · 8 caracteres · expira em 24h · uso único (serve para UM agente específico)\n"
                "     Digite QUALQUER um dos dois códigos abaixo:\n"
                "> ").strip()
        except (EOFError, KeyboardInterrupt):
            return 2

    # Community
    community = (args.community or "public").strip()
    try:
        resposta = input(f"\n3/5) Comunidade SNMP (padrão: {community}). Enter para aceitar:\n> ").strip()
        if resposta:
            community = resposta or community
    except (EOFError, KeyboardInterrupt):
        pass

    # Sub-redes
    try:
        from print_collect.snmp import discover_local_subnets
        subnets = list(discover_local_subnets())
    except Exception:
        subnets = []
    if not subnets:
        try:
            extra = input("\nSub-redes locais nao detectadas automaticamente. "
                          "Informe CIDR (ex.: 192.168.1.0/24) ou Enter para pular:\n> ").strip()
            if extra:
                subnets.append(extra)
        except (EOFError, KeyboardInterrupt):
            pass

    # 4) Pair
    try:
        config = _pair_and_save(server_url, code, config_path,
                                community=community, subnets=subnets)
    except Exception as e:
        print(f"\n[ERRO] Pareamento falhou: {e}")
        return 1

    # 5) Scan + envio
    printers: list = []
    try:
        print("\n4/5) Buscando impressoras na rede (primeira coleta)...")
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
            print(f"[OK] Enviadas {len(printers)} impressoras.")
        except Exception as e:
            print(f"[AVISO] Nao foi possivel enviar: {e}")
    else:
        print("[!] Nenhuma impressora detectada nesta primeira execucao.")
        print("    Dicas: confira a comunidade SNMP, se a impressora esta ligada e SNMP ativado.")
        print("    Voce pode rodar 'scan' manualmente depois.")

    # 6) (opcional) Instalar inicializacao automatica
    print("\n5/5) Deseja instalar a inicializacao automatica do agente?")
    try:
        instalar = input("    Digite S para SIM (tarefa agendada no login) ou Enter para NAO:\n> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        instalar = ""
    if instalar in ("s", "sim", "y", "yes", "1"):
        try:
            class _InstArgs:
                system = False
                config = args.config
            rc = cmd_install(_InstArgs)
            if rc == 0:
                print("[OK] Inicializacao automatica instalada.")
        except Exception as e:
            print(f"[AVISO] Nao foi possivel instalar inicializacao: {e}")

    print("\n" + "=" * 62)
    print("   WIZARD CONCLUIDO.")
    print("=" * 62)
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
