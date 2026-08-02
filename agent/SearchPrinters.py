#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SearchPrinters.py  ->  compila para SearchPrinters.exe (PyInstaller onefile console).
EXE NATIVO. Nao usa .bat, nao fecha sozinho, tem input() no final!

Funcionalidade:
1) Acha PrintCollectAgent.exe na mesma pasta.
2) Acha config.yaml em C:\\ProgramData\\PrintCollect\\config.yaml (mesma regra do WizardPareamento).
3) Pergunta OPCIONALMENTE: Comunidade SNMP (enter = usar do config.yaml ou public).
4) Pergunta OPCIONALMENTE: Sub-rede CIDR (ex: 192.168.1.0/24) OU IP UNICO (ex: 192.168.1.50)
   - Se ENTER: usa sub-redes detectadas automaticamente / lidas do config.yaml
5) Executa: PrintCollectAgent.exe --config "..."  list  (ou scan)
6) Mostra resultados e input() no final (nao fecha sozinho!).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _find_agent_exe() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent
    agent = base / "PrintCollectAgent.exe"
    if not agent.exists():
        print(f"[ERRO GRAVE] Nao encontrei PrintCollectAgent.exe em: {agent}")
        return Path()
    return agent


def _resolve_config_path(agent_dir: Path) -> Path:
    program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    cfg_dir = Path(program_data) / "PrintCollect"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg = cfg_dir / "config.yaml"
    if not cfg.exists():
        example = agent_dir / "config.example.yaml"
        if example.exists():
            import shutil
            shutil.copy2(example, cfg)
            print(f"[INFO] config.yaml nao existia. Copiei exemplo para: {cfg}")
    return cfg


def main() -> int:
    print("=" * 78)
    print("   PRINT COLLECT - PROCURAR IMPRESSORAS (EXECUTAVEL NATIVO)")
    print("   (Janela NAO fecha sozinho! Feche apertando ENTER no final.)")
    print("=" * 78)
    print()

    agent = _find_agent_exe()
    if not agent:
        input("\nPressione ENTER para fechar...")
        return 1
    agent_dir = agent.parent
    print(f"[OK] PrintCollectAgent.exe em: {agent}")

    cfg = _resolve_config_path(agent_dir)
    print(f"[OK] Config em: {cfg}")
    print()

    # --- Pergunta 1: Comunidade SNMP (enter = usa a do config ou public) ---
    try:
        comunity = input(
            "1) Comunidade SNMP (ENTER = usar 'public' ou a do config.yaml):\n> "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        comunity = ""

    # --- Pergunta 2: Sub-rede ou IP unico ---
    try:
        alvo = input(
            "\n2) Informe SUA REDE (CIDR, ex: 192.168.1.0/24)\n"
            "   OU informe UM IP DE IMPRESSORA (ex: 192.168.1.50)\n"
            "   OU apenas ENTER para DETECTAR/AUTOMATICO (usa sub-redes do config.yaml):\n> "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        alvo = ""

    print()
    print("-" * 78)
    print("  INICIANDO BUSCA POR IMPRESSORAS NA REDE...")
    print("-" * 78)
    print()

    # Monta comando
    cmd = [str(agent), "--config", str(cfg), "list"]

    # Se informou comunidade, adiciona --community
    if comunity:
        cmd += ["--community", comunity]
    # Se informou IP/CIDR:
    if alvo:
        # Verifica se é IP/CIDR com barra (subnet) ou IP unico
        if "/" in alvo:
            cmd += ["--subnet", alvo]
        else:
            cmd += ["--ip", alvo]

    print(f"> Comando: {' '.join(cmd)}")
    print()

    exit_code = 1
    try:
        completed = subprocess.run(cmd, shell=False, check=False)
        exit_code = completed.returncode
    except Exception as exc:
        print(f"\n[ERRO GRAVE ao executar busca: {exc}]")
        print(f"  Comando: {' '.join(cmd)}")

    print()
    print("=" * 78)
    if exit_code == 0:
        print("   BUSCA TERMINOU (sem erros de execucao).")
    else:
        print(f"   ATENCAO: Busca terminou com codigo de erro = {exit_code}")
    print()
    print("   (Verifique as linhas ACIMA para ver as impressoras encontradas!)")
    print()
    print("   FIM. PRESSIONE ENTER PARA FECHAR ESTA JANELA.")
    print("=" * 78)
    try:
        input()
    except EOFError:
        pass
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelado pelo usuario.")
        try:
            input("Pressione ENTER para fechar...")
        except Exception:
            pass
        raise SystemExit(130)
