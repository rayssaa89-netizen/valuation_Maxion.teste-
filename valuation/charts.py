"""Gráficos Plotly do aplicativo."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

DARK = "#1F3B73"
LIGHT = "#7FA7D9"
GREEN = "#2E8B57"
RED = "#C0392B"
GREY = "#8C8C8C"
ORANGE = "#E08E0B"
SERIES = ["#1F3B73", "#E08E0B", "#2E8B57", "#C0392B", "#7B4EA3", "#4BA3C3", "#8C6D46"]


def _layout(fig, title=None, height=420, ytitle=None):
    fig.update_layout(
        title=title, height=height, margin=dict(l=10, r=10, t=50 if title else 20, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified", separators=",.",
    )
    if ytitle:
        fig.update_yaxes(title_text=ytitle)
    fig.update_xaxes(type="category")
    return fig


def revenue_hist_proj(hist: pd.DataFrame, proj: pd.DataFrame):
    fig = go.Figure()
    fig.add_bar(x=hist.index.astype(str), y=hist["receita"], name="Histórico", marker_color=DARK,
                hovertemplate="R$ %{y:,.1f} mi")
    fig.add_bar(x=proj.index.astype(str), y=proj["Receita líquida"], name="Projetado", marker_color=LIGHT,
                hovertemplate="R$ %{y:,.1f} mi")
    return _layout(fig, "Receita líquida: histórico e projeção (R$ milhões)", ytitle="R$ milhões")


def payback_chart(years, investment, pvs, cum, base_year):
    labels = [str(base_year)] + [str(y) for y in years]
    fig = go.Figure()
    fig.add_bar(x=labels, y=[-investment] + list(pvs), name="Fluxo descontado do ano",
                marker_color=[RED] + [LIGHT] * len(pvs), hovertemplate="R$ %{y:,.1f} mi")
    fig.add_scatter(x=labels, y=cum, name="Acumulado descontado", mode="lines+markers+text",
                    line=dict(color=DARK, width=3), text=[f"{v:,.0f}" for v in cum], textposition="top center",
                    hovertemplate="R$ %{y:,.1f} mi")
    fig.add_hline(y=0, line_dash="dot", line_color=GREY)
    return _layout(fig, "Fluxo descontado acumulado (payback descontado)", ytitle="R$ milhões")


def waterfall_year(row: pd.Series, year: int):
    oper = row["CPV"] + row["Despesas com vendas"] + row["Despesas G&A"] + row["Honorários da administração"] \
        + row["Outras despesas/receitas"] + row["Equivalência patrimonial"]
    fig = go.Figure(go.Waterfall(
        x=["Receita líquida", "Custos e despesas operacionais", "EBIT", "Resultado financeiro", "IR projetado",
           "Resultado após IR"],
        measure=["absolute", "relative", "total", "relative", "relative", "total"],
        y=[row["Receita líquida"], oper, 0, row["Resultado financeiro"], row["IR projetado"], 0],
        text=[f"{v:,.0f}" for v in [row["Receita líquida"], oper, row["EBIT"], row["Resultado financeiro"],
                                     row["IR projetado"], row["Resultado após IR"]]],
        textposition="outside", connector=dict(line=dict(color=GREY)),
        increasing=dict(marker_color=GREEN), decreasing=dict(marker_color=RED), totals=dict(marker_color=DARK),
    ))
    fig = _layout(fig, f"Da receita ao resultado — {year} (R$ milhões)", ytitle="R$ milhões")
    fig.update_layout(hovermode="closest", showlegend=False)
    return fig


def result_margin(proj: pd.DataFrame, col="Resultado após IR", margin_col="Margem após IR (%)", title=None):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(x=proj.index.astype(str), y=proj[col], name=col, marker_color=DARK,
                hovertemplate="R$ %{y:,.1f} mi", secondary_y=False)
    fig.add_scatter(x=proj.index.astype(str), y=proj[margin_col], name="Margem (%)", mode="lines+markers",
                    line=dict(color=ORANGE, width=3), hovertemplate="%{y:.2f}%", secondary_y=True)
    fig.update_yaxes(title_text="R$ milhões", secondary_y=False)
    fig.update_yaxes(title_text="Margem (%)", secondary_y=True, ticksuffix="%")
    return _layout(fig, title or "Resultado projetado e margem após IR")


def heatmap(grid: pd.DataFrame, title: str, ztitle: str):
    fig = go.Figure(go.Heatmap(
        z=grid.values, x=list(grid.columns), y=list(grid.index), colorscale="RdYlGn",
        text=[[f"{v:,.0f}" for v in row] for row in grid.values], texttemplate="%{text}",
        hovertemplate="WACC %{x}<br>IR %{y}<br>" + ztitle + ": R$ %{z:,.1f} mi<extra></extra>",
        colorbar=dict(title="R$ mi"),
    ))
    fig = _layout(fig, title, height=440)
    fig.update_layout(hovermode="closest")
    fig.update_xaxes(title_text="Taxa de desconto (WACC/TMA)")
    fig.update_yaxes(title_text="Alíquota de IR", type="category")
    return fig


def lines(df: pd.DataFrame, cols, title, ytitle=None, suffix=""):
    fig = go.Figure()
    for i, c in enumerate(cols):
        if c in df:
            fig.add_scatter(x=df.index.astype(str), y=df[c], name=c, mode="lines+markers",
                            line=dict(color=SERIES[i % len(SERIES)], width=2.5),
                            hovertemplate="%{y:,.2f}" + suffix)
    fig = _layout(fig, title, ytitle=ytitle)
    if suffix == "%":
        fig.update_yaxes(ticksuffix="%")
    return fig


def bars(df: pd.DataFrame, cols, title, ytitle="R$ milhões", barmode="group"):
    fig = go.Figure()
    for i, c in enumerate(cols):
        if c in df:
            fig.add_bar(x=df.index.astype(str), y=df[c], name=c, marker_color=SERIES[i % len(SERIES)],
                        hovertemplate="R$ %{y:,.1f} mi")
    fig.update_layout(barmode=barmode)
    return _layout(fig, title, ytitle=ytitle)


def football_field(values: dict, market_price: float | None = None):
    """Valor por ação estimado por cada modelo (barras horizontais)."""
    items = [(k, v) for k, v in values.items() if v is not None and np.isfinite(v)]
    names = [k for k, _ in items]
    vals = [v for _, v in items]
    fig = go.Figure(go.Bar(y=names, x=vals, orientation="h", marker_color=[SERIES[i % len(SERIES)] for i in range(len(vals))],
                           text=[f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") for v in vals],
                           textposition="outside", hovertemplate="%{y}: R$ %{x:,.2f}<extra></extra>", cliponaxis=False))
    if market_price:
        fig.add_vline(x=market_price, line_dash="dash", line_color=RED,
                      annotation_text=f"Cotação R$ {market_price:,.2f}".replace(".", ","), annotation_position="top")
    fig.update_layout(height=80 + 55 * len(vals), margin=dict(l=10, r=60, t=40, b=10), hovermode="closest",
                      separators=",.", title="Valor por ação estimado por modelo (R$)", showlegend=False)
    fig.update_xaxes(title_text="R$ por ação", rangemode="tozero")
    fig.update_yaxes(autorange="reversed")
    return fig


def histogram_vpl(values, base_vpl: float):
    fig = go.Figure(go.Histogram(x=values, nbinsx=60, marker_color=LIGHT, hovertemplate="VPL ≈ R$ %{x:,.0f} mi<br>%{y} cenários<extra></extra>"))
    fig.add_vline(x=0, line_color=RED, line_dash="dash", annotation_text="VPL = 0", annotation_position="top left")
    fig.add_vline(x=base_vpl, line_color=DARK, annotation_text="Cenário do TCC", annotation_position="top right")
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=50, b=10), hovermode="closest", separators=",.",
                      title="Distribuição do VPL simulado (R$ milhões)", showlegend=False, bargap=0.02)
    fig.update_xaxes(title_text="VPL (R$ milhões)")
    fig.update_yaxes(title_text="Número de cenários")
    return fig
