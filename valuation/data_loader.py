"""Leitura de dados históricos de qualquer empresa a partir de planilhas Excel.

Formatos aceitos:
1. Planilha de RI com aba de DRE rotulada por nome de conta e colunas anuais
   (ex.: "DRE- Income Statement" da Iochpe-Maxion) ou o modelo do próprio app.
2. Planilha com contas no padrão CVM (códigos 3.01, 3.02, 1.01 ... ), como as abas
   "P&L - Consolidado" e "BS - Consolidado" das planilhas de RI feitas pela MZ.

Todos os valores retornados estão em R$ milhões.
"""
from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------------------
# Campos padronizados
# --------------------------------------------------------------------------------------
DRE_LABELS = {
    "receita": "Receita líquida",
    "cpv": "Custo dos produtos vendidos (CPV)",
    "lucro_bruto": "Lucro bruto",
    "vendas": "Despesas com vendas",
    "admin": "Despesas gerais e administrativas",
    "honorarios": "Honorários da administração",
    "outros": "Outras despesas/receitas operacionais",
    "equivalencia": "Resultado de equivalência patrimonial",
    "ebit": "EBIT (lucro operacional)",
    "receitas_financeiras": "Receitas financeiras",
    "despesas_financeiras": "Despesas financeiras",
    "cambio": "Variação cambial líquida",
    "antes_ir": "Lucro antes do IR e CS",
    "imposto": "IR e CS",
    "minoritarios": "Participação de não controladores",
    "lucro_liquido": "Lucro líquido (controladores)",
    "ebitda": "EBITDA",
    "da": "Depreciação e amortização",
    "capex": "CapEx (investimentos em imobilizado e intangível)",
}
BP_LABELS = {
    "caixa": "Caixa e equivalentes de caixa",
    "aplicacoes": "Aplicações financeiras",
    "contas_receber": "Contas a receber",
    "estoques": "Estoques",
    "ativo_circulante": "Ativo circulante",
    "imobilizado": "Imobilizado",
    "ativo_total": "Ativo total",
    "fornecedores": "Fornecedores",
    "emprestimos_cp": "Empréstimos e financiamentos (CP)",
    "passivo_circulante": "Passivo circulante",
    "emprestimos_lp": "Empréstimos e financiamentos (LP)",
    "passivo_nao_circulante": "Passivo não circulante",
    "patrimonio_liquido": "Patrimônio líquido total",
    "minoritarios_pl": "Participação de não controladores no PL",
}
ALL_LABELS = {**DRE_LABELS, **BP_LABELS}

# Padrões (texto normalizado, sem acento) para localizar linhas rotuladas.
# (termos que devem aparecer, termos que não podem aparecer)
LABEL_PATTERNS = {
    "receita": (["receita operacional liquida", "receita liquida", "net operating revenue", "net revenue",
                 "receita de venda de bens"], ["custo"]),
    "cpv": (["custo dos produtos vendidos", "custo dos bens", "custo das mercadorias", "custo dos servicos",
             "cost of goods sold", "(cpv)"], []),
    "lucro_bruto": (["lucro (prejuizo) bruto", "lucro bruto", "resultado bruto", "gross profit"], ["margem"]),
    "vendas": (["despesas com vendas", "com vendas", "selling expenses"], []),
    "admin": (["despesas gerais e administrativas", "gerais e administrativas", "general and administrative"], []),
    "honorarios": (["honorarios da administracao", "management fees"], []),
    "outros": (["outras despesas/receitas", "outras receitas (despesas) operacionais",
                "outras despesas e receitas operacionais", "outras receitas/despesas operacionais"], []),
    "equivalencia": (["equivalencia patrimonial", "equity income"], []),
    "ebit": (["lucro (prejuizo) operacional (ebit)", "ebit (lucro operacional)", "(ebit)",
              "resultado antes do resultado financeiro", "operating income"], ["ebitda", "margem"]),
    "receitas_financeiras": (["receitas financeiras", "financial income", "financial revenue"], []),
    "despesas_financeiras": (["despesas financeiras", "financial expenses"], []),
    "cambio": (["variacao cambial", "foreign exchange"], []),
    "antes_ir": (["antes do imp", "antes dos tributos", "antes do ir", "before income tax"], ["margem"]),
    "imposto": (["imp. de renda", "imposto de renda", "ir e cs", "income tax"], ["antes", "diferido", "margem"]),
    "minoritarios": (["participacao de nao controladores", "nao controladores", "minority", "non-controlling"],
                     ["no pl", "patrimonio"]),
    "lucro_liquido": (["lucro liquido", "lucro (prejuizo) liquido", "net income"], ["antes", "margem", "por acao"]),
    "ebitda": (["ebitda"], ["margem", "conciliacao", "reconciliation", "ajustado"]),
    "da": (["depreciacao e amortizacao", "depreciation and amortization"], []),
    "capex": (["capex"], []),
}
BP_LABEL_PATTERNS = {
    "caixa": (["caixa e equivalentes"], []),
    "aplicacoes": (["aplicacoes financeiras"], []),
    "contas_receber": (["contas a receber"], []),
    "estoques": (["estoques"], []),
    "ativo_circulante": (["ativo circulante"], ["nao circulante"]),
    "imobilizado": (["imobilizado"], []),
    "ativo_total": (["ativo total", "total do ativo"], []),
    "fornecedores": (["fornecedores"], []),
    "emprestimos_cp": (["emprestimos e financiamentos (cp)"], []),
    "passivo_circulante": (["passivo circulante"], ["nao circulante"]),
    "emprestimos_lp": (["emprestimos e financiamentos (lp)"], []),
    "passivo_nao_circulante": (["passivo nao circulante"], []),
    "patrimonio_liquido": (["patrimonio liquido total", "patrimonio liquido"], ["nao controladores"]),
    "minoritarios_pl": (["nao controladores no pl"], []),
}

# Códigos-padrão do plano de contas CVM (contas fixas, iguais para todas as empresas não financeiras)
CVM_DRE_CODES = {
    "receita": "3.01", "cpv": "3.02", "lucro_bruto": "3.03", "_desp_oper": "3.04",
    "vendas": "3.04.01", "admin": "3.04.02", "equivalencia": "3.04.06", "ebit": "3.05",
    "receitas_financeiras": "3.06.01", "despesas_financeiras": "3.06.02", "antes_ir": "3.07",
    "imposto": "3.08", "_lucro_consolidado": "3.11", "lucro_liquido": "3.11.01", "_minoritarios": "3.11.02",
    "_lpa": "3.99.01.01",
}
CVM_BP_CODES = {
    "ativo_total": "1", "ativo_circulante": "1.01", "caixa": "1.01.01", "aplicacoes": "1.01.02",
    "contas_receber": "1.01.03", "estoques": "1.01.04", "imobilizado": "1.02.03",
    "passivo_circulante": "2.01", "fornecedores": "2.01.02", "emprestimos_cp": "2.01.04",
    "passivo_nao_circulante": "2.02", "emprestimos_lp": "2.02.01", "patrimonio_liquido": "2.03",
    "minoritarios_pl": "2.03.09",
}
FINANCIAL_HINTS = ["intermediacao financeira", "seguradora", "resseguradora", "previdencia"]

UNIT_FACTORS = {"R$ mil": 1e-3, "R$ (unidades)": 1e-6, "R$ milhões": 1.0}


@dataclass
class CompanyData:
    """Dados históricos padronizados de uma empresa (R$ milhões, índice = ano)."""

    name: str
    source: str
    hist: pd.DataFrame
    shares: float | None = None
    notes: list[str] = field(default_factory=list)
    is_financial: bool = False
    profile: str = "generic"  # "iochpe" ativa as premissas do TCC
    sheets: list[str] = field(default_factory=list)
    eps_last: float | None = None
    quarter_fixes: list = field(default_factory=list)

    @property
    def last_year(self) -> int:
        return int(self.hist.index.max())

    @property
    def key(self) -> str:
        return re.sub(r"[^a-z0-9]+", "_", norm(self.name + "_" + self.source))[:60]


# --------------------------------------------------------------------------------------
# Utilitários
# --------------------------------------------------------------------------------------
def norm(value) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    value = str(value).strip().lower()
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", value)


def to_number(value) -> float:
    if value is None:
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    s = str(value).strip()
    if s in {"", "-", "–", "—", "n/a", "nd"}:
        return np.nan
    s = s.replace("R$", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return np.nan


def _year_of(value) -> int | None:
    if isinstance(value, (pd.Timestamp, datetime)):
        return None
    try:
        y = float(value)
    except (TypeError, ValueError):
        return None
    if y.is_integer() and 2000 <= y <= 2040:
        return int(y)
    return None


def _as_date(value):
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.Timestamp(value)
    if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}", value.strip()):
        try:
            return pd.Timestamp(value.strip()[:10])
        except ValueError:
            return None
    if isinstance(value, str) and re.match(r"^\d{2}/\d{2}/\d{4}$", value.strip()):
        return pd.to_datetime(value.strip(), dayfirst=True)
    return None


def normalize_code(value) -> str | None:
    """Converte '3.01', 3.01, 1, '1.01.01' em código CVM textual."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, (int, np.integer)):
        s = str(int(value))
    elif isinstance(value, (float, np.floating)):
        s = str(int(value)) if float(value).is_integer() else repr(float(value))
    else:
        s = str(value).strip()
    if not re.fullmatch(r"[1-9](\.\d{1,2})*", s):
        return None
    parts = s.split(".")
    parts = [parts[0]] + [p if len(p) == 2 else p + "0" for p in parts[1:]]
    return ".".join(parts)


def detect_unit(texts: list[str]) -> str | None:
    joined = " ".join(norm(t) for t in texts if t)
    if re.search(r"r\$ ?mil(?!h)|thousand|\(mil\)|em milhares", joined):
        return "R$ mil"
    if re.search(r"r\$ ?milh|million|em milhoes", joined):
        return "R$ milhões"
    return None


def is_iochpe(text: str) -> bool:
    t = norm(text)
    return "iochpe" in t or "maxion" in t


# --------------------------------------------------------------------------------------
# Formato 1: DRE rotulada com colunas anuais
# --------------------------------------------------------------------------------------
def _find_year_header(raw: pd.DataFrame):
    for r in range(min(12, len(raw))):
        found = {}
        for c, value in enumerate(raw.iloc[r].tolist()):
            y = _year_of(value)
            if y is not None and y not in found:
                found[y] = c
        if len(found) >= 3:
            return r, found
    return None, {}


def _label_column(raw: pd.DataFrame, header_row: int) -> int:
    best, best_count = 0, -1
    for c in range(min(4, raw.shape[1])):
        col = raw.iloc[header_row + 1:, c]
        count = sum(isinstance(v, str) and len(v.strip()) > 2 for v in col)
        if count > best_count:
            best, best_count = c, count
    return best


def _parse_labeled(raw: pd.DataFrame, patterns: dict, check_quarters: bool = False) -> tuple[pd.DataFrame, str | None]:
    header_row, year_cols = _find_year_header(raw)
    if header_row is None:
        return pd.DataFrame(), None
    label_col = _label_column(raw, header_row)
    labels = raw.iloc[:, label_col].map(norm)
    years = sorted(year_cols)
    unit = detect_unit([str(v) for v in raw.iloc[: header_row + 1].values.ravel() if isinstance(v, str)])

    def has_data(idx):
        return any(pd.notna(to_number(raw.iat[idx, year_cols[y]])) for y in years)

    data = {}
    used = set()
    for key, (terms, exclude) in patterns.items():
        for idx, label in labels.items():
            if idx <= header_row or idx in used or not label:
                continue
            if any(t in label for t in terms) and not any(e in label for e in exclude) and has_data(idx):
                data[key] = {y: to_number(raw.iat[idx, year_cols[y]]) for y in years}
                used.add(idx)
                break
    df = pd.DataFrame(data)
    if not df.empty:
        df.index.name = "Ano"
    df.attrs["quarter_fixes"] = []
    if check_quarters and not df.empty:
        df = _reconcile_quarters(raw, header_row, labels, df, patterns, used)
    return df, unit


def _reconcile_quarters(raw, header_row, labels, df, patterns, used_rows):
    """Confere a coluna anual com a soma dos 4 trimestres (1T..4T). Se divergir, usa a soma."""
    qcols: dict[int, list[int]] = {}
    for c, v in enumerate(raw.iloc[header_row].tolist()):
        m = re.fullmatch(r"([1-4])\s*[tTqQ]\s*(\d{2})", str(v).strip()) if isinstance(v, str) else None
        if m:
            qcols.setdefault(2000 + int(m.group(2)), []).append(c)
    qcols = {y: cs for y, cs in qcols.items() if len(cs) == 4}
    if not qcols:
        return df
    row_of = {}
    for key, (terms, exclude) in patterns.items():
        for idx in used_rows:
            label = labels[idx]
            if any(t in label for t in terms) and not any(e in label for e in exclude):
                row_of.setdefault(key, idx)
    fixes = []
    for key, idx in row_of.items():
        if key not in df:
            continue
        for y, cs in qcols.items():
            if y not in df.index:
                continue
            qs = [to_number(raw.iat[idx, c]) for c in cs]
            if any(pd.isna(q) for q in qs):
                continue
            qsum, annual = float(np.sum(qs)), df.at[y, key]
            if pd.isna(annual) or abs(qsum - annual) > max(1.0, 0.005 * abs(qsum)):
                fixes.append({"Ano": y, "Conta": key, "Coluna anual da planilha": annual, "Soma 1T-4T": qsum})
                df.at[y, key] = qsum
    df.attrs["quarter_fixes"] = fixes
    return df


# --------------------------------------------------------------------------------------
# Formato 2: plano de contas CVM (códigos)
# --------------------------------------------------------------------------------------
def _parse_coded(raw: pd.DataFrame):
    """Retorna (tipo, {codigo: {ano: valor}}, {codigo: descricao}) ou None."""
    code_col, best = None, 0
    for c in range(min(4, raw.shape[1])):
        n = sum(normalize_code(v) is not None for v in raw.iloc[:, c])
        if n > best:
            code_col, best = c, n
    if code_col is None or best < 8:
        return None
    codes = raw.iloc[:, code_col].map(normalize_code)
    code_set = set(codes.dropna())
    if {"3.01", "3.05"} <= code_set:
        kind = "dre"
    elif {"1.01", "2.03"} <= code_set:
        kind = "bp"
    elif "6.01" in code_set:
        kind = "dfc"
    else:
        return None
    first_code_row = int(codes.first_valid_index())
    desc_col = code_col + 1 if code_col + 1 < raw.shape[1] else code_col
    descs = {codes[i]: str(raw.iat[i, desc_col]) for i in codes.dropna().index}

    # Cabeçalhos de cada coluna de dados
    col_info = {}
    for c in range(raw.shape[1]):
        if c in (code_col, desc_col):
            continue
        header = raw.iloc[:first_code_row, c].tolist()
        date = next((d for d in (_as_date(v) for v in header) if d is not None), None)
        year = next((y for y in (_year_of(v) for v in header) if y is not None), None)
        text = " ".join(norm(v) for v in header if isinstance(v, str))
        if date is None and year is None:
            continue
        col_info[c] = {"date": date, "year": year, "text": text,
                       "quarterly": bool(re.search(r"\b[1-4][tq]\d{2}\b", text)),
                       "acum": "acum" in text}

    annual = {}  # ano -> lista de colunas a somar
    years = sorted({(i["date"].year if i["date"] is not None else i["year"]) for i in col_info.values()})
    for y in years:
        cols_y = [c for c, i in col_info.items()
                  if (i["date"] is not None and i["date"].year == y) or (i["date"] is None and i["year"] == y)]
        dec = [c for c in cols_y if col_info[c]["date"] is not None and col_info[c]["date"].month == 12]
        no_date = [c for c in cols_y if col_info[c]["date"] is None and not col_info[c]["quarterly"]]
        if kind == "bp":
            if dec:
                annual[y] = [dec[0]]
            elif no_date:
                annual[y] = [no_date[0]]
            continue
        acum = [c for c in dec if col_info[c]["acum"]]
        if acum:
            annual[y] = [acum[0]]
        elif no_date:
            annual[y] = [no_date[0]]
        elif dec and not col_info[dec[0]]["quarterly"]:
            annual[y] = [dec[0]]
        else:
            quarters = [c for c in cols_y if col_info[c]["quarterly"] and not col_info[c]["acum"]]
            if len(quarters) == 4:
                annual[y] = quarters

    values = {}
    for i in codes.dropna().index:
        code = codes[i]
        if code in values:
            continue
        row = {}
        for y, cols in annual.items():
            nums = [to_number(raw.iat[i, c]) for c in cols]
            row[y] = np.nansum(nums) if any(pd.notna(n) for n in nums) else np.nan
        values[code] = row
    return kind, values, descs


def dre_from_codes(values: dict, descs: dict) -> pd.DataFrame:
    def get(code):
        return pd.Series(values.get(code, {}), dtype=float)

    df = pd.DataFrame({k: get(c) for k, c in CVM_DRE_CODES.items() if c in values})
    if df.empty or "receita" not in df:
        return pd.DataFrame()
    for col in ["vendas", "admin", "equivalencia", "_desp_oper"]:
        if col not in df:
            df[col] = 0.0
    df["outros"] = df["_desp_oper"].fillna(0) - df[["vendas", "admin", "equivalencia"]].fillna(0).sum(axis=1)
    df["honorarios"] = 0.0
    df["cambio"] = 0.0
    if "lucro_liquido" not in df or df["lucro_liquido"].isna().all():
        df["lucro_liquido"] = df.get("_lucro_consolidado")
    df["minoritarios"] = -df["_minoritarios"] if "_minoritarios" in df else 0.0
    df.index.name = "Ano"
    return df


def bp_from_codes(values: dict) -> pd.DataFrame:
    df = pd.DataFrame({k: pd.Series(values.get(c, {}), dtype=float) for k, c in CVM_BP_CODES.items() if c in values})
    df.index.name = "Ano"
    return df


def dfc_from_codes(values: dict, descs: dict) -> pd.DataFrame:
    da, capex = {}, {}
    for code, row in values.items():
        d = norm(descs.get(code, ""))
        if code.startswith("6.01.01.") and re.search(r"deprecia|amortiza|exaust", d) and "juros" not in d:
            for y, v in row.items():
                da[y] = da.get(y, 0.0) + (0 if pd.isna(v) else v)
        if (code.startswith("6.02.") and re.search(r"imobilizado|intang", d)
                and not re.search(r"venda|aliena|receb|baixa|resgate", d)):
            for y, v in row.items():
                if pd.notna(v) and v < 0:
                    capex[y] = capex.get(y, 0.0) - v
    df = pd.DataFrame({"da": pd.Series(da, dtype=float), "capex": pd.Series(capex, dtype=float)})
    df.index.name = "Ano"
    return df


# --------------------------------------------------------------------------------------
# Pós-processamento comum
# --------------------------------------------------------------------------------------
def finalize_hist(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().sort_index()
    df = df[[c for c in df.columns if not str(c).startswith("_")]]
    if "receita" not in df:
        raise ValueError("Não encontrei a Receita Líquida.")
    df = df[df["receita"].notna() & (df["receita"] != 0)]
    if "lucro_bruto" in df and df["lucro_bruto"].notna().any():
        df["cpv"] = df["lucro_bruto"] - df["receita"]
    elif "cpv" in df:
        df["cpv"] = -df["cpv"].abs()
        df["lucro_bruto"] = df["receita"] + df["cpv"]
    else:
        raise ValueError("Não encontrei Lucro Bruto nem CPV na DRE.")
    for col in ["vendas", "admin", "honorarios", "outros", "equivalencia", "receitas_financeiras",
                "despesas_financeiras", "cambio", "minoritarios"]:
        if col not in df:
            df[col] = 0.0
        df[col] = df[col].fillna(0.0)
    if "ebit" not in df or df["ebit"].isna().all():
        df["ebit"] = df[["lucro_bruto", "vendas", "admin", "honorarios", "outros", "equivalencia"]].sum(axis=1)
    else:
        # Fecha a identidade da DRE: diferenças entre EBIT reportado e a soma das linhas vão para "outros"
        soma = df[["lucro_bruto", "vendas", "admin", "honorarios", "outros", "equivalencia"]].sum(axis=1)
        diff = (df["ebit"] - soma).fillna(0)
        df["outros"] = df["outros"] + diff
    if "antes_ir" not in df or df["antes_ir"].isna().all():
        df["antes_ir"] = df["ebit"] + df["receitas_financeiras"] + df["despesas_financeiras"] + df["cambio"]
    if "da" not in df and "ebitda" in df:
        df["da"] = df["ebitda"] - df["ebit"]
    if "da" in df and ("ebitda" not in df or df["ebitda"].isna().all()):
        df["ebitda"] = df["ebit"] + df["da"]
    # CPV, despesas e IR como números negativos (convenção da DRE)
    for col in ["despesas_financeiras"]:
        df[col] = -df[col].abs()
    if "imposto" in df:
        df["imposto"] = df["imposto"].fillna(0.0)
    order = [c for c in ALL_LABELS if c in df.columns]
    return df[order]


def _scale(df: pd.DataFrame, factor: float) -> pd.DataFrame:
    return df.astype(float) * factor


# --------------------------------------------------------------------------------------
# Leitura de planilha
# --------------------------------------------------------------------------------------
def read_workbook(file_bytes: bytes, filename: str = "", unit_override: str | None = None,
                  fix_quarters: bool = True) -> CompanyData:
    xls = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")
    notes: list[str] = []
    info = _read_info_sheet(xls)
    sheets = {name: pd.read_excel(xls, sheet_name=name, header=None) for name in xls.sheet_names}

    def priority(name):
        n = norm(name)
        if "dre" in n or "income" in n or "resultado" in n:
            return 0
        if "p&l" in n or "pl " in n:
            return 1
        return 2

    dre, dre_unit, dre_sheet = pd.DataFrame(), None, None
    bp, dfc = pd.DataFrame(), pd.DataFrame()
    coded_dre = None
    bp_coded = False
    financial = False

    for name in sorted(sheets, key=priority):
        raw = sheets[name]
        if raw.shape[0] < 4 or raw.shape[1] < 3:
            continue
        coded = _parse_coded(raw)
        if coded:
            kind, values, descs = coded
            if kind == "dre" and coded_dre is None:
                coded_dre = (name, values, descs)
                d301 = norm(descs.get("3.01", ""))
                financial = any(h in d301 for h in FINANCIAL_HINTS)
            elif kind == "bp" and not bp_coded:
                bp, bp_coded = bp_from_codes(values), True
                notes.append(f"Balanço patrimonial lido da aba '{name}' (plano de contas CVM).")
            elif kind == "dfc" and dfc.empty:
                dfc = dfc_from_codes(values, descs)
            continue
        n = norm(name)
        if dre.empty and "kpi" not in n and "indicador" not in n:
            parsed, unit = _parse_labeled(raw, LABEL_PATTERNS, check_quarters=fix_quarters)
            if not parsed.empty and "receita" in parsed and ("lucro_bruto" in parsed or "cpv" in parsed):
                if priority(name) == 0 or len(parsed.columns) >= 6:
                    dre, dre_unit, dre_sheet = parsed, unit, name
        if bp.empty and ("balan" in n or "balance" in n):
            parsed_bp, _ = _parse_labeled(raw, BP_LABEL_PATTERNS)
            if {"ativo_total", "patrimonio_liquido"} <= set(parsed_bp.columns):
                bp = parsed_bp

    unit = unit_override or info.get("unidade") or dre_unit or "R$ mil"
    factor = UNIT_FACTORS.get(unit, 1e-3)
    fixes = []
    if not dre.empty:
        notes.insert(0, f"DRE lida da aba '{dre_sheet}' (contas identificadas pelo nome). Unidade: {unit}.")
        fixes = [{**f, "Coluna anual da planilha": f["Coluna anual da planilha"] * factor, "Soma 1T-4T": f["Soma 1T-4T"] * factor,
                  "Conta": ALL_LABELS.get(f["Conta"], f["Conta"])} for f in dre.attrs.get("quarter_fixes", [])]
        if fixes:
            anos = sorted({f["Ano"] for f in fixes})
            notes.append(f"Conferência trimestral: a coluna anual de {', '.join(map(str, anos))} não bate com a soma "
                         f"de 1T a 4T em {len(fixes)} conta(s). O app usou a soma dos trimestres.")
    elif coded_dre is not None:
        name, values, descs = coded_dre
        dre = dre_from_codes(values, descs)
        notes.insert(0, f"DRE lida da aba '{name}' (plano de contas CVM). Unidade: {unit}.")
    else:
        raise ValueError(
            "Não encontrei uma DRE reconhecível. Use uma planilha de RI com aba de DRE anual, "
            "uma aba no padrão CVM (contas 3.01, 3.02...) ou o modelo de planilha do aplicativo."
        )

    hist = _scale(dre, factor)
    if not dfc.empty:
        dfc_s = _scale(dfc, factor)
        for col in ["da", "capex"]:
            if col in dfc_s and (col not in hist or hist[col].isna().all()):
                hist[col] = dfc_s[col]
    if not bp.empty:
        bp_s = _scale(bp, factor)
        hist = hist.join(bp_s, how="left")
    hist = finalize_hist(hist)
    if len(hist) < 3:
        raise ValueError("A DRE tem menos de 3 anos com receita. São necessários mais anos para formar médias.")

    company = info.get("empresa") or _guess_name(filename, xls.sheet_names, sheets)
    profile = "iochpe" if is_iochpe(company) or is_iochpe(filename) else "generic"
    if profile == "iochpe":
        company = "Iochpe-Maxion"
    return CompanyData(
        name=company, source=f"Planilha: {filename or 'upload'}", hist=hist, shares=info.get("acoes"),
        notes=notes, is_financial=financial, profile=profile, sheets=list(xls.sheet_names),
        quarter_fixes=fixes,
    )


def _read_info_sheet(xls) -> dict:
    out = {}
    for name in xls.sheet_names:
        if norm(name) not in {"info", "informacoes", "empresa"}:
            continue
        raw = pd.read_excel(xls, sheet_name=name, header=None)
        for _, row in raw.iterrows():
            key, val = norm(row.iloc[0]), row.iloc[1] if raw.shape[1] > 1 else None
            if pd.isna(val) if not isinstance(val, str) else not val.strip():
                continue
            if key.startswith("empresa"):
                out["empresa"] = str(val).strip()
            elif key.startswith("unidade"):
                v = norm(val)
                out["unidade"] = "R$ milhões" if "milh" in v else ("R$ (unidades)" if "unid" in v else "R$ mil")
            elif "acoes" in key:
                n = to_number(val)
                if pd.notna(n) and n > 0:
                    out["acoes"] = n
    return out


def _guess_name(filename: str, sheet_names, sheets) -> str:
    if is_iochpe(filename) or any(is_iochpe(s) for s in sheet_names):
        return "Iochpe-Maxion"
    for raw in list(sheets.values())[:3]:
        for v in raw.iloc[:6, :4].values.ravel():
            if isinstance(v, str) and is_iochpe(v):
                return "Iochpe-Maxion"
    base = re.sub(r"\.(xlsx|xlsm|xls)$", "", filename or "Empresa", flags=re.I)
    base = re.sub(r"[_\-]+", " ", base).strip()
    return base.title() if base else "Empresa"
