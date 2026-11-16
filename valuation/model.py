"""Motor de cálculo: médias históricas, projeção, VPL, TIR, payback e sensibilidade."""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
import numpy_financial as npf
import pandas as pd

# Linhas da DRE projetadas como % da receita (análise vertical)
AV_LINES = ["cpv", "vendas", "admin", "honorarios", "outros", "equivalencia",
            "receitas_financeiras", "despesas_financeiras", "cambio"]
AV_NAMES = {
    "cpv": "CPV", "vendas": "Despesas com vendas", "admin": "Despesas gerais e administrativas",
    "honorarios": "Honorários da administração", "outros": "Outras despesas/receitas operacionais",
    "equivalencia": "Equivalência patrimonial", "receitas_financeiras": "Receitas financeiras",
    "despesas_financeiras": "Despesas financeiras", "cambio": "Variação cambial líquida",
}
OPERATING = ["cpv", "vendas", "admin", "honorarios", "outros", "equivalencia"]
FINANCIAL = ["receitas_financeiras", "despesas_financeiras", "cambio"]

MACRO_ROWS = [
    "Crescimento da empresa/setor (%)",
    "Crescimento do PIB (%)",
    "Efeito da Selic sobre vendas (%)",
    "Efeito da inflação (IPCA) sobre vendas (%)",
    "Crescimento vegetativo (%)",
]
# Premissas usadas no TCC (2026-2030)
TCC_MACRO = {
    MACRO_ROWS[0]: [4.00, 4.50, 4.20, 4.00, 3.80],
    MACRO_ROWS[1]: [1.80, 2.00, 2.00, 2.00, 2.00],
    MACRO_ROWS[2]: [-2.00, 2.00, 1.9607843137, 1.9230769231, 1.8867924528],
    MACRO_ROWS[3]: [4.50, 0.0, 0.0, 0.0, 0.0],
    MACRO_ROWS[4]: [0.36, 0.34, 0.32, 0.31, 0.29],
}
TCC_DEFAULTS = {"wacc": 13.0, "tax": 35.0, "investment": 722.1, "shares": 23_143_771}


def growth_from_macro(table: pd.DataFrame) -> list[float]:
    """Fórmula do TCC: (1+empresa)(1+PIB)(1+vegetativo) / ((1+Selic)(1+IPCA)) - 1. Entradas em %."""
    out = []
    for col in table.columns:
        v = table[col].astype(float).fillna(0.0) / 100.0
        m, pib, selic, ipca, veg = (v.iloc[i] for i in range(5))
        den = (1 + selic) * (1 + ipca)
        out.append(((1 + m) * (1 + pib) * (1 + veg) / den) - 1 if den else 0.0)
    return out


def default_macro_table(years: list[int]) -> pd.DataFrame:
    data = {}
    for i, y in enumerate(years):
        data[str(y)] = [vals[min(i, len(vals) - 1)] for vals in TCC_MACRO.values()]
    return pd.DataFrame(data, index=MACRO_ROWS)


# --------------------------------------------------------------------------------------
# Médias históricas
# --------------------------------------------------------------------------------------
def vertical_analysis(hist: pd.DataFrame) -> pd.DataFrame:
    rev = hist["receita"]
    av = pd.DataFrame({k: hist[k] / rev for k in AV_LINES if k in hist}, index=hist.index)
    return av.replace([np.inf, -np.inf], np.nan)


def av_means(hist: pd.DataFrame, years: list[int], method: str = "media") -> dict:
    av = vertical_analysis(hist.loc[[y for y in years if y in hist.index]])
    out = {}
    for k in AV_LINES:
        s = av[k].dropna() if k in av else pd.Series(dtype=float)
        if s.empty:
            out[k] = 0.0
        elif method == "mediana":
            out[k] = float(s.median())
        else:
            out[k] = float(s.mean())
    return out


def historical_ratios(hist: pd.DataFrame) -> pd.DataFrame:
    """Indicadores históricos de margem, crescimento, liquidez, endividamento e rentabilidade."""
    h = hist
    r = pd.DataFrame(index=h.index)
    r["Crescimento da receita (%)"] = h["receita"].pct_change() * 100
    r["Margem bruta (%)"] = h["lucro_bruto"] / h["receita"] * 100
    r["Margem EBIT (%)"] = h["ebit"] / h["receita"] * 100
    if "ebitda" in h:
        r["Margem EBITDA (%)"] = h["ebitda"] / h["receita"] * 100
    r["Margem líquida (%)"] = h["lucro_liquido"] / h["receita"] * 100
    if "imposto" in h:
        r["Alíquota efetiva de IR (%)"] = (-h["imposto"] / h["antes_ir"]).where(h["antes_ir"] > 0) * 100
    if {"ativo_circulante", "passivo_circulante"} <= set(h.columns):
        r["Liquidez corrente (x)"] = h["ativo_circulante"] / h["passivo_circulante"]
    debt = net_debt_series(h)
    if debt is not None:
        r["Dívida líquida (R$ mi)"] = debt
        if "ebitda" in h:
            r["Dívida líquida / EBITDA (x)"] = debt / h["ebitda"]
    if {"patrimonio_liquido", "ativo_total"} <= set(h.columns):
        pl_ctrl = h["patrimonio_liquido"] - h.get("minoritarios_pl", 0).fillna(0) if "minoritarios_pl" in h else h["patrimonio_liquido"]
        r["ROE (%)"] = h["lucro_liquido"] / pl_ctrl * 100
        r["ROA (%)"] = h["lucro_liquido"] / h["ativo_total"] * 100
        r["Endividamento geral (%)"] = (h["ativo_total"] - h["patrimonio_liquido"]) / h["ativo_total"] * 100
    if {"contas_receber", "estoques", "fornecedores"} <= set(h.columns):
        r["Capital de giro operacional (% receita)"] = nwc_series(h) / h["receita"] * 100
    return r


def net_debt_series(h: pd.DataFrame):
    if not {"emprestimos_cp", "emprestimos_lp", "caixa"} <= set(h.columns):
        return None
    return (h["emprestimos_cp"].fillna(0) + h["emprestimos_lp"].fillna(0)
            - h["caixa"].fillna(0) - h.get("aplicacoes", pd.Series(0, index=h.index)).fillna(0)).where(h["caixa"].notna())


def nwc_series(h: pd.DataFrame):
    return h["contas_receber"] + h["estoques"] - h["fornecedores"]


def cagr(series: pd.Series, years: int) -> float | None:
    s = series.dropna()
    if len(s) <= years or s.iloc[-1 - years] <= 0 or s.iloc[-1] <= 0:
        return None
    return (s.iloc[-1] / s.iloc[-1 - years]) ** (1 / years) - 1


# --------------------------------------------------------------------------------------
# Premissas e projeção
# --------------------------------------------------------------------------------------
@dataclass
class Assumptions:
    years: list
    growth: list            # crescimento da receita por ano (decimal)
    base_revenue: float     # R$ mi
    av: dict                # % da receita por linha (decimal; custos negativos)
    tax: float              # alíquota IR (decimal)
    wacc: float             # decimal
    investment: float       # investimento inicial (R$ mi) — modelo TCC
    shares: float           # quantidade de ações a emitir


def project(a: Assumptions) -> pd.DataFrame:
    rows = []
    rev_prev = a.base_revenue
    for i, year in enumerate(a.years):
        rev = rev_prev * (1 + a.growth[i])
        lines = {k: rev * a.av.get(k, 0.0) for k in AV_LINES}
        gross = rev + lines["cpv"]
        ebit = gross + sum(lines[k] for k in OPERATING if k != "cpv")
        fin = sum(lines[k] for k in FINANCIAL)
        pretax = ebit + fin
        tax = -max(pretax, 0.0) * a.tax
        net = pretax + tax
        rows.append({
            "Ano": year, "Crescimento (%)": a.growth[i] * 100, "Receita líquida": rev,
            "CPV": lines["cpv"], "Lucro bruto": gross, "Despesas com vendas": lines["vendas"],
            "Despesas G&A": lines["admin"], "Honorários da administração": lines["honorarios"],
            "Outras despesas/receitas": lines["outros"], "Equivalência patrimonial": lines["equivalencia"],
            "EBIT": ebit, "Receitas financeiras": lines["receitas_financeiras"],
            "Despesas financeiras": lines["despesas_financeiras"], "Variação cambial": lines["cambio"],
            "Resultado financeiro": fin, "Lucro antes do IR": pretax, "IR projetado": tax,
            "Resultado após IR": net, "Margem após IR (%)": net / rev * 100 if rev else np.nan,
        })
        rev_prev = rev
    return pd.DataFrame(rows).set_index("Ano")


def _irr(cashflows):
    try:
        v = npf.irr(cashflows)
        return float(v) if v is not None and math.isfinite(float(v)) else None
    except Exception:
        return None


def discounted_payback(investment, flows, rate):
    acc = -investment
    for i, f in enumerate(flows, start=1):
        pv = f / (1 + rate) ** i
        before = acc
        acc += pv
        if acc >= 0 and pv > 0:
            return (i - 1) + (-before / pv)
    return None


def simple_payback(investment, flows):
    acc = -investment
    for i, f in enumerate(flows, start=1):
        before = acc
        acc += f
        if acc >= 0 and f > 0:
            return (i - 1) + (-before / f)
    return None


def evaluate_tcc(a: Assumptions, proj: pd.DataFrame | None = None) -> dict:
    """Modelo do TCC: VPL = -investimento + Σ resultado após IR descontado pela TMA/WACC."""
    proj = project(a) if proj is None else proj
    flows = proj["Resultado após IR"].tolist()
    r = a.wacc
    pvs = [f / (1 + r) ** t for t, f in enumerate(flows, start=1)]
    vpl = -a.investment + sum(pvs)
    cfs = [-a.investment] + flows
    acc, cum = -a.investment, [-a.investment]
    for pv in pvs:
        acc += pv
        cum.append(acc)
    return {
        "vpl": vpl, "tir": _irr(cfs) if a.investment > 0 else None,
        "payback_desc": discounted_payback(a.investment, flows, r) if a.investment > 0 else None,
        "payback_simples": simple_payback(a.investment, flows) if a.investment > 0 else None,
        "por_acao": vpl * 1e6 / a.shares if a.shares else None,
        "flows": flows, "pvs": pvs, "cum": cum,
    }



# --------------------------------------------------------------------------------------
# Sensibilidade e cenários
# --------------------------------------------------------------------------------------
def sensitivity_grid(a: Assumptions, waccs, taxes, method: str = "tcc") -> pd.DataFrame:
    """VPL para cada combinação de taxa de desconto e alíquota de IR."""
    out = pd.DataFrame(index=[f"{t*100:.0f}%" for t in taxes], columns=[f"{w*100:.1f}%" for w in waccs], dtype=float)
    for t in taxes:
        for w in waccs:
            b = replace(a, wacc=w, tax=t)
            out.loc[f"{t*100:.0f}%", f"{w*100:.1f}%"] = evaluate_tcc(b)["vpl"]
    out.index.name = "Alíquota de IR"
    return out


def rate_table(a: Assumptions, waccs, method: str = "tcc") -> pd.DataFrame:
    rows = []
    for w in waccs:
        b = replace(a, wacc=w)
        res = evaluate_tcc(b)
        rows.append({"Taxa de desconto (%)": w * 100, "VPL (R$ mi)": res["vpl"], "Indicador por ação (R$)": res["por_acao"]})
    return pd.DataFrame(rows)
