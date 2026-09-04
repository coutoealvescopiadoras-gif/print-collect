"""
=============================================================================
  PrintCollect — COLETA SEGURA INDEPENDENTE de Contadores (Híbrido)
=============================================================================
  Estratégia: SQLite desenvolvimento local → PostgreSQL 16 produção Render
  Tudo via variável DATABASE_URL (os.getenv) — igual ao config.py oficial.

  O QUE ESSA TABELA FAZ (4ª CAMADA DE DEFESA, Julio pediu!):
  ┌─────────────────────────────────────────────────────────────────────┐
  │ Reading table           : Leitura BRUTA que o agente Windows envia  │
  │ historico_coletas table : Leitura VALIDADA, com STATUS auditoria,   │
  │                           travando monotonicidade, detectando picos  │
  │                           e corrigindo inchados >= 1.5x do REAL.    │
  └─────────────────────────────────────────────────────────────────────┘

  Como usar (exemplo em outro módulo Python / rotina batch / endpoint):

    from coleta_segura_independente import registrar_leitura_segura

    resultado = registrar_leitura_segura(
        ip="192.168.0.116",
        tipo_contador="PB",              # 'PB' ou 'COLOR' ou 'TOTAL'
        valor_coletado=1_850_247,        # valor vindo do agente (SNMP)
        printer_id=286,                  # opcional (FK para tabela printers)
        modelo="Brother DCP-L5652DN",    # opcional
        fabricante="Brother",            # opcional
        cliente_id=92,                   # opcional (FK clientes)
        limite_pico_paginas=5_000,       # padrão 5k por 5 min
    )
    print(resultado)
    # {'status': 'SUCESSO', 'valor_final': 1850247, 'delta': 423, ...}

  Para rodar EXEMPLO (não executa automaticamente ao importar!):
      python server/coleta_segura_independente.py --run-demo

=============================================================================
"""
import os
import re
import sys
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# 0. SANITIZAÇÃO SEGURA (iguais aos helpers oficiais routes.py / _s_ip etc)
# ---------------------------------------------------------------------------
_IPV4_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)$"
)


def _s_ip(value) -> str:
    """Sanitiza IPv4 (rejeita qualquer coisa que não seja IP válido)."""
    try:
        v = str(value or "").strip()
    except Exception:
        return "0.0.0.0"
    if not v:
        return "0.0.0.0"
    if _IPV4_RE.match(v):
        return v
    return "0.0.0.0"


def _s_strn(value, max_len: int) -> str:
    """Trunca string com segurança, remove caracteres de controle."""
    try:
        v = str(value or "").strip()
    except Exception:
        return ""
    if not v:
        return ""
    try:
        v = v.replace("\x00", "")
    except Exception:
        pass
    if len(v) > max_len:
        v = v[:max_len]
    return v


def _safe_int(v, default: int = 0) -> int:
    try:
        if v is None:
            return default
        n = int(v)
        if n < 0:
            return default
        return n
    except Exception:
        try:
            f = float(v)
            n = int(f)
            return n if n >= 0 else default
        except Exception:
            return default


# ---------------------------------------------------------------------------
# 1. CONFIGURAÇÃO HÍBRIDA (igual a Settings oficial do PrintCollect)
# ---------------------------------------------------------------------------
def _add_postgres_ssl(url: str) -> str:
    if not url.startswith("postgresql"):
        return url
    if "sslmode=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}sslmode=require"


def _normalize_driver(url: str) -> str:
    """Converte postgres:// → postgresql+psycopg:// (driver psycopg3 oficial)."""
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql+psycopg2:"):
        url = "postgresql+psycopg:" + url[len("postgresql+psycopg2:"):]
    if url.startswith("postgresql:"):
        url = "postgresql+psycopg:" + url[len("postgresql:"):]
    return url


def _detect_database_url() -> str:
    candidates = [
        os.getenv("POSTGRES_URL"),
        os.getenv("POSTGRES_URL_NON_POOLING"),
        os.getenv("POSTGRES_PRISMA_URL"),
        os.getenv("DATABASE_URL"),
        os.getenv("DIRECT_URL"),
    ]
    for c in candidates:
        if c:
            c = str(c).strip()
            c = _normalize_driver(c)
            return _add_postgres_ssl(c)
    return "sqlite:///./historico_coletas_dev.db"


DATABASE_URL_FINAL = _detect_database_url()

# ---------------------------------------------------------------------------
# 2. SQLAlchemy: Engine + Session + Base
# ---------------------------------------------------------------------------
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    BigInteger,
    Index,
    Text,
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import desc as sqla_desc

_engine_kwargs: Dict[str, Any] = {}
if DATABASE_URL_FINAL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs["pool_pre_ping"] = True
    _engine_kwargs["pool_recycle"] = 300  # 5 min
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 10

engine = create_engine(DATABASE_URL_FINAL, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


# ---------------------------------------------------------------------------
# 3. MODELO DA TABELA historico_coletas (corrigido 4 underlines!)
# ---------------------------------------------------------------------------
class HistoricoColeta(Base):
    """Registro de leitura VALIDADA (4ª camada de defesa)."""

    __tablename__ = "historico_coletas"

    # PK
    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)

    # Identificadores — indexados para buscas rápidas
    printer_id = Column(Integer, nullable=True, index=True)
    cliente_id = Column(Integer, nullable=True, index=True)
    ip_impressora = Column(String(50), nullable=False, index=True)
    fabricante = Column(String(100), nullable=True)
    modelo = Column(String(200), nullable=True)

    # Contador
    tipo_contador = Column(String(20), nullable=False, index=True)  # 'PB' | 'COLOR' | 'TOTAL'
    valor_contador = Column(BigInteger().with_variant(Integer, "sqlite"), nullable=False)

    # Status de auditoria (4 estados, mais ricos que 3 do exemplo)
    status_coleta = Column(
        String(40),
        nullable=False,
        default="SUCESSO",
        index=True,
    )  # SUCESSO | ERRO_DECRESCIMO | PICO_PENDENTE | INCHADO_CORRIGIDO

    # Métricas de auditoria (Julio cobrança 100%)
    valor_anterior = Column(BigInteger().with_variant(Integer, "sqlite"), nullable=True)
    delta_paginas = Column(Integer, nullable=True)  # (valor_atual - valor_anterior)
    observacao = Column(Text, nullable=True)  # texto livre do porquê do status

    # Horários (com timezone UTC lazy!)
    data_registro = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        Index(
            "ix_historico_printer_tipo_data",
            "printer_id",
            "tipo_contador",
            "data_registro",
        ),
        Index(
            "ix_historico_ip_tipo_data",
            "ip_impressora",
            "tipo_contador",
            "data_registro",
        ),
    )


# Cria as tabelas SE NÃO EXISTIREM (100% seguro — idempotente).
try:
    Base.metadata.create_all(bind=engine)
except Exception as _create_err:
    logging.critical(
        "[coleta_segura] Falha ao criar tabelas historico_coletas: %s",
        str(_create_err)[:300],
    )


# ---------------------------------------------------------------------------
# 4. DETECTOR DE P&B IGUAL AO _is_color_printer_real (inline, sem import routes)
# ---------------------------------------------------------------------------
def _pb_confirmado_pelo_modelo(fabricante: Optional[str], modelo: Optional[str]) -> bool:
    """Mesmas regras do helper oficial PASSO -1 do routes.py. Se retorna True = 100% PB."""
    m = _s_strn(modelo, 400).lower()
    f = _s_strn(fabricante, 200).lower()
    mf = ((f + " ") if f else "") + m

    if not mf:
        return False

    # Ricoh MP/SP/IM SEM C no modelo = PB
    if ("ricoh" in mf or "lanier" in mf or "savin" in mf):
        if re.search(r"(?:^|[\s_-])(mp|sp|im)[\s_-]?\d{3,6}(?!.*c\d{3,5})", mf):
            return True

    # Brother sem L3/L8/L9/L35/L37/L82/L83/L84/L92/L94/L96 = PB
    if "brother" in mf:
        if re.search(r"(?:^|[\s_-])(?:l[389]\d{2,5}|mfc-l[389]\d{2,5}|dcp-l[389]\d{2,5}|hl-l[389]\d{2,5})", mf):
            return False
        if re.search(r"brother\s*(dcp|hl|mfc|fax)-?(?!l[389])\w*", mf):
            return True

    # Epson WorkForce SEM WF-C = PB
    if "epson" in mf and "workforce" in mf and "wf-c" not in mf and "et-" not in mf:
        return True
    if "epson" in mf and re.search(r"l\s*\d{3,5}(?!\s*w)", mf):
        return True  # Epson EcoTank PB (L3210 etc)

    # Samsung M series = PB (Xpress M, ProXpress M, SL-M)
    if ("samsung" in mf or "xpress" in mf or "proxpress" in mf or "sl-" in mf) and re.search(
        r"\sm\d{3,5}", mf
    ):
        if "clp-" in mf or "clx-" in mf or re.search(r"(?:xpress\s+c|proxpress\s+c)", mf):
            return False
        return True

    # Konica Minolta bizhub NUMÉRICO SEM C = PB (bizhub 284e, 224e etc)
    if "konica" in mf or "minolta" in mf or "bizhub" in mf:
        if re.search(r"bizhub[\s_-]*\d{3,4}[a-z]?\b", mf):
            if re.search(r"bizhub[\s_-]*c\d{3,4}", mf):
                return False
            return True

    # Canon imageRunner/LBP/Satera SEM regras de cor = PB
    if "canon" in mf and ("imagerunner" in mf or " lb" in mf or "satera" in mf or "mf" in mf):
        if re.search(r"[\s_-]c\d{3,5}", mf) or "c13250" in mf or "irc" in mf:
            return False
        return True

    # HP LaserJet PB (sem Color LaserJet / CP1025 / M479 / MFP color)
    if "hp" in mf or "hewlett" in mf:
        if (
            "laserjet" in mf
            and "color" not in mf
            and "clj" not in mf
            and "cp1025" not in mf
            and "m479" not in mf
            and "m283" not in mf
            and "m454" not in mf
        ):
            return True

    return False


# ---------------------------------------------------------------------------
# 5. FUNÇÃO DE SALVAMENTO (Julio — 100% segura cobrança)
# ---------------------------------------------------------------------------
def registrar_leitura_segura(
    ip: str,
    tipo_contador: str,
    valor_coletado: int,
    printer_id: Optional[int] = None,
    cliente_id: Optional[int] = None,
    modelo: Optional[str] = None,
    fabricante: Optional[str] = None,
    limite_pico_paginas: int = 5_000,
    regra_anti_inchado_pb: bool = True,
) -> Dict[str, Any]:
    """
    Registra uma coleta VALIDADA na tabela historico_coletas.

    Retorna dict com:
        status: SUCESSO | ERRO_DECRESCIMO | PICO_PENDENTE | INCHADO_CORRIGIDO
        valor_final: int (valor que realmente foi gravado)
        valor_anterior: int
        delta: int
        observacao: str
        registro_id: int (pk inserida)
    """
    # --- SANITIZAÇÃO TUDO ANTES (nunca confiar em entrada!) ---
    ip_s = _s_ip(ip)
    tipo_s = _s_strn(tipo_contador, 20).upper() or "TOTAL"
    if tipo_s not in {"PB", "COLOR", "TOTAL"}:
        tipo_s = "TOTAL"
    valor_novo: int = _safe_int(valor_coletado, 0)
    pid: Optional[int] = _safe_int(printer_id, 0) or None
    cid: Optional[int] = _safe_int(cliente_id, 0) or None
    modelo_s = _s_strn(modelo, 200) or None
    fab_s = _s_strn(fabricante, 100) or None
    limite: int = _safe_int(limite_pico_paginas, 1) or 1

    # --- DETECÇÃO AUTOMÁTICA P&B (trava color=0 e bw=total!) ---
    pb_ok: bool = bool(_pb_confirmado_pelo_modelo(fab_s, modelo_s))
    observacoes: list[str] = []
    if pb_ok and tipo_s == "COLOR":
        tipo_s = "PB"
        valor_novo = 0
        observacoes.append("FORCADO PB: impressora modelo confirmado P&B (helper oficial)")

    status = "SUCESSO"
    valor_final = valor_novo
    delta = None
    valor_anterior: int = 0
    db = SessionLocal()
    try:
        # ----- PASSO 1: busca a última leitura VÁLIDA desta impressora/tipo -----
        _q = db.query(HistoricoColeta)
        if pid is not None:
            _q = _q.filter(HistoricoColeta.printer_id == pid)
        _q = _q.filter(
            HistoricoColeta.ip_impressora == ip_s,
            HistoricoColeta.tipo_contador == tipo_s,
            HistoricoColeta.status_coleta.in_(["SUCESSO", "INCHADO_CORRIGIDO"]),
        )
        ultima = _q.order_by(sqla_desc(HistoricoColeta.data_registro), sqla_desc(HistoricoColeta.id)).first()
        valor_anterior = int(ultima.valor_contador or 0) if ultima else 0

        # ----- PASSO 2: (ANTES DE TUDO!) REGRINHA ESPECIAL ANTI-INCHADO PB 04/09 — Julio cobrança! -----
        #    Raciocínio: salvo >= 1.5x o SNMP REAL novo = cálculo falso do bug dia 02/09 (bw+color dobrava).
        #    O contador FÍSICO REAL tem PRIORIDADE MÁXIMA. Substituímos o salvo antigo pelo novo REAL.
        #    FAZEMOS ISSO ANTES do decrescimo, para não travar o 4M infinitamente.
        anti_inchado_aplicou = False
        if (
            regra_anti_inchado_pb
            and pb_ok
            and tipo_s in {"PB", "TOTAL"}
            and valor_anterior > 0
            and valor_novo > 0
            and valor_anterior >= int(1.5 * valor_novo)
        ):
            status = "INCHADO_CORRIGIDO"
            anti_inchado_aplicou = True
            observacoes.append(
                f"INCHADO >= 1.5x REAL detectado (bug 02/09). salvo_anterior={valor_anterior} >= 1.5x SNMP={valor_novo}. "
                "Valor real SNMP FISICO usado (prioridade máxima cobrança!)."
            )
            logging.warning(
                "[%s] INCHADO_CORRIGIDO IP=%s printer_id=%s salvo=%s >= 1.5x REAL_NOVO=%s | USANDO REAL NOVO.",
                tipo_s, ip_s, pid, valor_anterior, valor_novo,
            )
            # Não podemos apagar o histórico. Ajustamos o "valor_anterior considerado" para o cálculo delta,
            # mas o valor real do salvo anterior fica PRESERVADO em observacao + coluna valor_anterior.
            valor_final = valor_novo

        # ----- PASSO 3: TRAVA DE DECRESCIMENTO (apenas se NÃO aplicamos anti-inchado!) -----
        if not anti_inchado_aplicou and valor_novo < valor_anterior and valor_anterior > 0:
            status = "ERRO_DECRESCIMO"
            observacoes.append(
                f"DECRESCIMO DETECTADO: fisico={valor_novo} < banco={valor_anterior}. "
                "Valor mantido (monotonicidade)."
            )
            logging.critical(
                "[%s] DECRESCIMO IP=%s | printer_id=%s | FISICO=%s < BANCO=%s",
                tipo_s, ip_s, pid, valor_novo, valor_anterior,
            )
            valor_final = valor_anterior  # NUNCA reduz contador!

        # ----- PASSO 4: PICO ABSURDO (>5000 páginas) -----
        if status == "SUCESSO" and valor_anterior > 0:
            delta_raw = valor_final - valor_anterior
            if delta_raw > limite:
                status = "PICO_PENDENTE"
                observacoes.append(
                    f"PICO detectado: delta={delta_raw} > limite={limite}. "
                    "Retido para aprovação manual (não cobra cliente)."
                )
                logging.warning(
                    "[%s] PICO IP=%s | printer_id=%s | SALTO %s → %s (delta=%s > %s).",
                    tipo_s, ip_s, pid, valor_anterior, valor_final, delta_raw, limite,
                )
        # ----- PASSO 4b: Valor novo ZERO (impressora desligada / bug transitório) -----
        if valor_novo == 0 and valor_anterior > 0 and status == "SUCESSO":
            status = "PICO_PENDENTE"
            observacoes.append("ZERO reportado mas já temos valor anterior. Retido (impressora offline provavel).")

        # ----- PASSO 4: CALCULA DELTA -----
        delta = None
        if valor_anterior > 0 and valor_final >= valor_anterior:
            delta = int(valor_final - valor_anterior)

        # ----- PASSO 5: P&B FORÇA color=0 / bw=total (mais 1 defesa!) -----
        if pb_ok and tipo_s == "TOTAL":
            # Não temos contador color separado, mas gravamos observação.
            observacoes.append("PB_CONFIRMADO: NÃO HÁ páginas coloridas neste equipamento (helper oficial).")
        if pb_ok and tipo_s == "COLOR":
            valor_final = 0
            observacoes.append("PB_CONFIRMADO: pages_color = 0 forçado.")

        # ----- PASSO 6: GRAVA NO BANCO (SQLite OU Postgres 16) -----
        novo_registro = HistoricoColeta(
            printer_id=pid,
            cliente_id=cid,
            ip_impressora=ip_s,
            fabricante=fab_s,
            modelo=modelo_s,
            tipo_contador=tipo_s,
            valor_contador=int(valor_final),
            status_coleta=status,
            valor_anterior=(int(valor_anterior) if valor_anterior else None),
            delta_paginas=int(delta) if delta is not None else None,
            observacao=" | ".join(observacoes) if observacoes else None,
        )
        db.add(novo_registro)
        db.flush()  # pega pk id sem commit
        _pk_registro = int(novo_registro.id or 0)
        db.commit()
        db.refresh(novo_registro)

        logging.info(
            "[%s] REGISTRO status=[%s] IP=%s printer_id=%s | anterior=%s → final=%s | delta=%s",
            tipo_s, status, ip_s, pid, valor_anterior, valor_final, (delta or 0),
        )
        return {
            "ok": True,
            "status": status,
            "tipo": tipo_s,
            "valor_final": int(valor_final),
            "valor_anterior": int(valor_anterior),
            "delta_paginas": (int(delta) if delta is not None else 0),
            "observacao": (" | ".join(observacoes) if observacoes else ""),
            "registro_id": _pk_registro,
            "data_registro_utc": str(
                getattr(novo_registro, "data_registro") or datetime.now(timezone.utc)
            ),
            "printer_id": pid,
            "ip": ip_s,
        }

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logging.error("[coleta_segura] Erro DB: %s", str(e)[:400], exc_info=True)
        return {
            "ok": False,
            "status": "ERRO_BANCO",
            "tipo": tipo_s,
            "valor_final": 0,
            "valor_anterior": int(valor_anterior),
            "delta_paginas": 0,
            "observacao": f"EXCECAO: {str(e)[:500]}",
            "registro_id": 0,
            "error": str(e)[:500],
        }
    finally:
        try:
            db.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 6. FUNÇÕES AUXILIARES ÚTEIS (Julio — cobrança!)
# ---------------------------------------------------------------------------
def pegar_ultimo_contador_valido(
    ip: str,
    tipo_contador: str,
    printer_id: Optional[int] = None,
) -> int:
    """Retorna o último valor VÁLIDO de contador (pra mostrar na UI ou cálculo fatura)."""
    ip_s = _s_ip(ip)
    tipo_s = _s_strn(tipo_contador, 20).upper() or "TOTAL"
    pid: Optional[int] = _safe_int(printer_id, 0) or None
    db = SessionLocal()
    try:
        q = db.query(HistoricoColeta).filter(
            HistoricoColeta.ip_impressora == ip_s,
            HistoricoColeta.tipo_contador == tipo_s,
            HistoricoColeta.status_coleta.in_(["SUCESSO", "INCHADO_CORRIGIDO"]),
        )
        if pid is not None:
            q = q.filter(HistoricoColeta.printer_id == pid)
        ult = q.order_by(sqla_desc(HistoricoColeta.data_registro), sqla_desc(HistoricoColeta.id)).first()
        return int(ult.valor_contador or 0) if ult else 0
    except Exception:
        return 0
    finally:
        try:
            db.close()
        except Exception:
            pass


def exportar_historico_csv(
    caminho_saida: str,
    printer_id: Optional[int] = None,
    cliente_id: Optional[int] = None,
    status_coleta: Optional[str] = None,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    limit: int = 50_000,
) -> Dict[str, Any]:
    """
    Exporte CSV da tabela historico_coletas via CLI Python (sem passar pela API).
    Ideal para agendar no Agendador de Tarefas do Windows e mandar por email!

    data_inicio / data_fim formato: 'YYYY-MM-DD'
    """
    import csv as _csv

    caminho_saida = str(caminho_saida).strip() or (
        f"historico_coletas_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    )
    db = SessionLocal()
    q = db.query(HistoricoColeta)
    pid = _safe_int(printer_id, 0) or None
    cid = _safe_int(cliente_id, 0) or None
    if pid:
        q = q.filter(HistoricoColeta.printer_id == pid)
    if cid:
        q = q.filter(HistoricoColeta.cliente_id == cid)
    if status_coleta and str(status_coleta).strip():
        q = q.filter(HistoricoColeta.status_coleta == str(status_coleta).strip().upper())
    try:
        if data_inicio:
            q = q.filter(
                HistoricoColeta.data_registro
                >= datetime.strptime(str(data_inicio), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            )
    except Exception:
        pass
    try:
        if data_fim:
            _fim = datetime.strptime(str(data_fim), "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
            q = q.filter(HistoricoColeta.data_registro < _fim)
    except Exception:
        pass
    rows = (
        q.order_by(sqla_desc(HistoricoColeta.data_registro), sqla_desc(HistoricoColeta.id))
        .limit(int(limit) or 50000)
        .all()
    )
    try:
        with open(caminho_saida, "w", newline="", encoding="utf-8-sig") as f:
            w = _csv.writer(f, delimiter=";", quoting=_csv.QUOTE_MINIMAL)
            w.writerow([
                "ID Registro", "Data (UTC)", "Printer ID", "Cliente ID", "IP Impressora",
                "Fabricante", "Modelo", "Tipo Contador", "Valor Contador",
                "Status", "Valor Anterior", "Delta Páginas", "Observação",
            ])
            for r in rows or []:
                try:
                    _data = ""
                    d = getattr(r, "data_registro", None)
                    if d:
                        try:
                            if d.tzinfo is None:
                                d = d.replace(tzinfo=timezone.utc)
                            _data = d.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                        except Exception:
                            _data = str(d)[:19]
                    w.writerow([
                        int(getattr(r, "id", 0) or 0),
                        _data,
                        (int(getattr(r, "printer_id", 0)) if getattr(r, "printer_id", None) else ""),
                        (int(getattr(r, "cliente_id", 0)) if getattr(r, "cliente_id", None) else ""),
                        _safe_str(getattr(r, "ip_impressora", None), default=""),
                        _safe_str(getattr(r, "fabricante", None), default=""),
                        _safe_str(getattr(r, "modelo", None), default=""),
                        _safe_str(getattr(r, "tipo_contador", None), default=""),
                        int(getattr(r, "valor_contador", 0) or 0),
                        _safe_str(getattr(r, "status_coleta", None), default=""),
                        (int(getattr(r, "valor_anterior", 0)) if getattr(r, "valor_anterior", None) is not None else ""),
                        (int(getattr(r, "delta_paginas", 0)) if getattr(r, "delta_paginas", None) is not None else ""),
                        _safe_str(getattr(r, "observacao", None), default=""),
                    ])
                except Exception:
                    continue
        return {
            "ok": True,
            "arquivo": os.path.abspath(caminho_saida),
            "total_linhas": int(len(rows or [])),
        }
    except Exception as e:
        logging.error("[exportar_historico_csv] %s", str(e)[:400], exc_info=True)
        return {"ok": False, "arquivo": caminho_saida, "total_linhas": 0, "error": str(e)[:500]}
    finally:
        try:
            db.close()
        except Exception:
            pass


def _safe_str(v, default: str = "") -> str:
    try:
        s = str(v or "").strip()
    except Exception:
        return default
    return s if s else default


# ---------------------------------------------------------------------------
# 7. EXEMPLO DE EXECUÇÃO — SÓ RODA SE CHAMAR python server/coleta_segura_independente.py
#    NÃO executa no import! (corrige erro colateral do exemplo).
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    run_demo = "--run-demo" in sys.argv
    if run_demo:
        print("=" * 72)
        print("  DEMO — Coleta Segura Independente (PrintCollect)")
        print("=" * 72)
        print(f"  Banco conectado : {DATABASE_URL_FINAL.split('@')[-1] if '@' in DATABASE_URL_FINAL else DATABASE_URL_FINAL}")
        print()

        r1 = registrar_leitura_segura(
            ip="192.168.1.100", tipo_contador="PB", valor_coletado=10500,
            modelo="Brother DCP-L5652DN", fabricante="Brother",
            printer_id=1, cliente_id=10, limite_pico_paginas=5000,
        )
        print(f"  [Passo 1 — Coleta normal PB]: {r1}")

        r2 = registrar_leitura_segura(
            ip="192.168.1.100", tipo_contador="PB", valor_coletado=9000,
            modelo="Brother DCP-L5652DN", fabricante="Brother", printer_id=1,
        )
        print(f"  [Passo 2 — Tentativa de fraude/bug (menor)]: status={r2['status']} valor_final={r2['valor_final']}")

        r3 = registrar_leitura_segura(
            ip="192.168.1.100", tipo_contador="PB", valor_coletado=10800,
            modelo="Brother DCP-L5652DN", fabricante="Brother", printer_id=1,
        )
        print(f"  [Passo 3 — Coleta normal (sobe)]: delta={r3['delta_paginas']} status={r3['status']}")

        r4 = registrar_leitura_segura(
            ip="192.168.1.100", tipo_contador="PB", valor_coletado=5_400,  # inchado salvo = ~9.000 (1.6x real!)
            modelo="Brother DCP-L5652DN", fabricante="Brother", printer_id=1,
        )
        print(f"  [Passo 4 — Anti-inchado >= 1.5x]: status={r4['status']} obs={r4['observacao'][:80]}")

        ultimo = pegar_ultimo_contador_valido(ip="192.168.1.100", tipo_contador="PB", printer_id=1)
        print(f"  [Consulta] Último contador PB VÁLIDO (para cobrança): {ultimo}")
    else:
        print(
            "[coleta_segura_independente.py] Módulo importado OK. Use:\n"
            "  • registrar_leitura_segura(...) → gravar nova coleta validada\n"
            "  • pegar_ultimo_contador_valido(...) → último valor seguro p/ cobrança\n\n"
            "Rodar DEMO: python server/coleta_segura_independente.py --run-demo\n"
            f"Banco em uso: {DATABASE_URL_FINAL[:120]}"
        )
