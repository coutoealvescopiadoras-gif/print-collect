#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WizardPareamento.py -> compila para WizardPareamento.exe (PyInstaller --onefile --console).
EXE NATIVO do Windows. Nao usa .bat, nao usa cmd.exe, NAO DA ERRO DE ASPAS,
NAO FECHA A JANELA SOZINHO (ateh usuario pressionar ENTER no final!).

Regras:
1) Acha PrintCollectAgent.exe na MESMA pasta de WizardPareamento.exe
2) Acha config.yaml em C:\\ProgramData\\PrintCollect\\config.yaml (se nao existir, cria copiando config.example.yaml da mesma pasta)
3) Executa: PrintCollectAgent.exe --config "C:\\ProgramData\\PrintCollect\\config.yaml" wizard
   (ORDEM CORRETA argparse: --config ANTES do subcomando!)
4) Captura exit_code do agente.
5) No final, imprime "FIM DO WIZARD..." e espera input do usuario (ENTER) para FECHAR.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _find_agent_exe() -> Path:
    """Acha PrintCollectAgent.exe na mesma pasta do WizardPareamento.exe (tanto rodando como .py ou como PyInstaller)."""
    if getattr(sys, "frozen", False):
        # Rodando como EXE compilado: pasta do proprio exe.
        base = Path(sys.executable).resolve().parent
    else:
        # Rodando como script dev: pasta raiz agent\
        base = Path(__file__).resolve().parent
    agent = base / "PrintCollectAgent.exe"
    if not agent.exists():
        print(f"[ERRO GRAVE] Nao encontrei PrintCollectAgent.exe em: {agent}")
        print("       (WizardPareamento.exe deve ficar NA MESMA PASTA do PrintCollectAgent.exe)")
        return Path()
    return agent


def _resolve_config_path(agent_dir: Path) -> Path:
    """Config sempre fica em C:\\ProgramData\\PrintCollect\\config.yaml (gravavel sem admin!)."""
    program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    cfg_dir = Path(program_data) / "PrintCollect"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg = cfg_dir / "config.yaml"
    if not cfg.exists():
        example = agent_dir / "config.example.yaml"
        if example.exists():
            shutil.copy2(example, cfg)
            print(f"[INFO] config.yaml nao existia. Copiei exemplo de: {example}")
            print(f"       Para: {cfg}")
        else:
            print(f"[AVISO] config.example.yaml nao encontrado em: {example}")
            print(f"       config.yaml sera criado pelo wizard em: {cfg}")
    return cfg


def main() -> int:
    print("=" * 78)
    print("   PRINT COLLECT - WIZARD DE PAREAMENTO (EXECUTAVEL NATIVO)")
    print("=" * 78)
    print()
    print("Este programa vai:")
    print("  1) Conectar no servidor oficial")
    print("  2) Pedir CÓDIGO DO CLIENTE (8 digitos, permanente) OU CÓDIGO DE PAREAMENTO (24h)")
    print("  3) Salvar token/config em C:\\ProgramData\\PrintCollect\\config.yaml")
    print("  4) Instalar inicializacao automatica (Tarefa Agendada no Windows)")
    print()

    agent = _find_agent_exe()
    if not agent:
        print()
        input("Pressione ENTER para FECHAR...")
        return 1
    agent_dir = agent.parent
    print(f"[OK] PrintCollectAgent.exe encontrado em: {agent}")

    cfg = _resolve_config_path(agent_dir)
    print(f"[OK] Arquivo de configuracao em: {cfg}")

    print()
    print("-" * 78)
    print("  INICIANDO WIZARD... (voce vai ver as perguntas abaixo)")
    print("-" * 78)
    print()

    # ORDEM CORRETA argparse: --config ANTES do subcomando wizard!
    cmd = [
        str(agent),
        "--config",
        str(cfg),
        "wizard",
    ]

    # Roda o agent MOSTRANDO TODA A SAIDA NA TELA (sem pipe, igual se rodasse manualmente)
    exit_code = 1
    try:
        completed = subprocess.run(cmd, shell=False, check=False)
        exit_code = completed.returncode
    except Exception as exc:
        print()
        print(f"[ERRO GRAVE ao executar wizard: {exc}]")
        print(f"  Comando: {' '.join(cmd)}")

    print()
    print("=" * 78)
    if exit_code == 0:
        print("   SUCESSO! Wizard terminou sem erros.")
    else:
        print(f"   ATENCAO: Wizard terminou com CODIGO DE ERRO = {exit_code}")
        print("   (Verifique as mensagens acima para entender o que aconteceu.)")
    print()
    print("   FIM DO WIZARD. PRESSIONE ENTER PARA FECHAR ESTA JANELA.")
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
        input("Pressione ENTER para fechar...")
        raise SystemExit(130)
