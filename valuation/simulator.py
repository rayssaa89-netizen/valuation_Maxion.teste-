"""Simulador de modelos de valuation (complementar ao modelo do TCC).

Modelos: FCFF (DCF) com valor terminal, Gordon (dividendos), Bazin, Graham, múltiplos e Monte Carlo do VPL.
Valores monetários em R$ milhões; valores por ação em R$.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .model import FINANCIAL, OPERATING, Assumptions, project


# --------------------------------------------------------------------------------------
# FCFF (fluxo de caixa livre da firma) + valor terminal de Gordon
# --------------------------------------------------------------------------------------
def fcff(a: Assumptions, da_pct: float, capex_pct: float, nwc_pct: float, wacc: float, g: float,
         net_debt: float, minorities: float, shares: float) -> dict:
    proj = project(a)
    rev = proj["Receita líquida"]
    ebit = proj["EBIT"]
    nopat = ebit - ebit.clip(lower=0) * a.tax
    da = rev * da_pct
    capex = rev * capex_pct
    nwc = rev * nwc_pct
    d_nwc = nwc.diff()
    d_nwc.iloc[0] = nwc.iloc[0] - a.base_revenue * nwc_pct
    flows = nopat + da - capex - d_nwc
    t = np.arange(1, len(flows) + 1)
    pv = flows / (1 + wacc) ** t
    tv = flows.iloc[-1] * (1 + g) / (wacc - g) if wacc > g else float("nan")
    pv_tv = tv / (1 + wacc) ** len(flows)
    ev = pv.sum() + pv_tv
    equity = ev - net_debt - minorities
    table = pd.DataFrame({"EBIT": ebit, "NOPAT (EBIT × (1 − IR))": nopat, "(+) D&A": da, "(−) CapEx": -capex,
                          "(−) Variação do capital de giro": -d_nwc, "FCFF": flows, "Valor presente": pv})
    return {"table": table, "ev": ev, "tv": tv, "pv_tv": pv_tv, "equity": equity,
            "per_share": equity * 1e6 / shares if shares else None,
            "tv_share": pv_tv / ev if ev else None}


# --------------------------------------------------------------------------------------
# Modelos de preço justo por ação
# --------------------------------------------------------------------------------------
def gordon(dpa: float, ke: float, g: float) -> float | None:
    """Modelo de Gordon (dividendos descontados): P = D1 / (ke − g)."""
    if ke <= g or dpa <= 0:
        return None
    return dpa * (1 + g) / (ke - g)


def bazin(dpa: float, min_yield: float = 0.06) -> float | None:
    """Método Bazin: preço-teto = dividendo por ação ÷ rendimento mínimo (6%)."""
    return dpa / min_yield if dpa > 0 and min_yield > 0 else None


def graham(lpa: float, vpa: float) -> float | None:
    """Número de Graham: √(22,5 × LPA × VPA)."""
    if lpa <= 0 or vpa <= 0:
        return None
    return math.sqrt(22.5 * lpa * vpa)


def by_pe(pe: float, lpa: float) -> float | None:
    return pe * lpa if lpa > 0 else None


def by_ev_ebitda(multiple: float, ebitda: float, net_debt: float, minorities: float, shares: float) -> float | None:
    if not shares:
        return None
    return (multiple * ebitda - net_debt - minorities) * 1e6 / shares


# --------------------------------------------------------------------------------------
# Monte Carlo do VPL do modelo do TCC
# --------------------------------------------------------------------------------------
def monte_carlo(a: Assumptions, n: int = 5000, sd_growth: float = 0.02, sd_margin: float = 0.01,
                sd_rate: float = 0.015, seed: int = 42) -> np.ndarray:
    """Sorteia choques normais no crescimento anual, na margem EBIT e na TMA e recalcula o VPL.

    Com desvios iguais a zero, reproduz exatamente o VPL do modelo do TCC.
    """
    rng = np.random.default_rng(seed)
    h = len(a.years)
    g = np.array(a.growth)[None, :] + rng.normal(0, sd_growth, (n, h))
    rev = a.base_revenue * np.cumprod(1 + g, axis=1)
    ebit_m = 1 + sum(a.av.get(k, 0.0) for k in OPERATING) + rng.normal(0, sd_margin, (n, 1))
    fin_m = sum(a.av.get(k, 0.0) for k in FINANCIAL)
    pretax = rev * (ebit_m + fin_m)
    net = pretax - np.clip(pretax, 0, None) * a.tax
    r = np.clip(a.wacc + rng.normal(0, sd_rate, (n, 1)), 0.0, None)
    disc = (1 + r) ** np.arange(1, h + 1)[None, :]
    return -a.investment + (net / disc).sum(axis=1)
