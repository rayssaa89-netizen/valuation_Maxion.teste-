"""Valuation Iochpe-Maxion — VPL, TIR e Payback Descontado.

Produto do Trabalho de Graduação em Administração (UNIFATEA, 2026).
Execute com:  streamlit run app.py
"""
from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from valuation import charts as C
from valuation import data_loader as DL
from valuation import model as M
from valuation import simulator as SIM

st.set_page_config(page_title="Valuation Iochpe-Maxion | TCC", page_icon="📈", layout="wide")

SAMPLE = Path(__file__).parent / "data" / "dados_historicos_iochpe_3t26.xlsx"
HIST_START, HIST_END = 2016, 2025  # período histórico do TCC


# ======================================================================================
# Formatação
# ======================================================================================
def br(value, decimals=2, prefix="", suffix=""):
    if value is None or (isinstance(value, float) and not math.isfinite(value)) or pd.isna(value):
        return "—"
    s = f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{prefix}{s}{suffix}"


def esc(text: str) -> str:
    """Evita que "R$ ... R$" seja interpretado como fórmula LaTeX no Markdown do Streamlit."""
    return text.replace("$", "\\$")


def fmt_years(years_float):
    if years_float is None:
        return "Não recuperado até o fim da projeção"
    a, m = divmod(max(0, round(years_float * 12)), 12)
    return f"{a} ano(s) e {m} mês(es)"


def style(df: pd.DataFrame, decimals=2, highlight_row=None):
    s = df.style.format({c: (lambda v, d=decimals: br(v, d)) for c in df.columns})
    if highlight_row is not None:
        s = s.apply(lambda r: ["background-color: rgba(127,167,217,.35); font-weight: 600"
                               if r.name == highlight_row else "" for _ in r], axis=1)
    return s


@st.cache_data(show_spinner=False)
def load_excel(file_bytes: bytes, filename: str):
    return DL.read_workbook(file_bytes, filename)


# ======================================================================================
# Cabeçalho
# ======================================================================================
HERO = Path(__file__).parent / "hero_maxion.html"
if HERO.exists():
    components.html(HERO.read_text(encoding="utf-8"), height=320, scrolling=False)

st.title("Valuation Iochpe-Maxion — análise de viabilidade econômica")
st.caption("VPL, TIR e Payback Descontado · Valores em R$ milhões, salvo indicação contrária.")

# ======================================================================================
# 1. Dados históricos
# ======================================================================================
st.header("1. Dados históricos")
st.write("O aplicativo já vem com a planilha de dados históricos da Iochpe-Maxion usada no trabalho. "
         "Para atualizar a análise, envie a versão mais recente da planilha, disponível na "
         "[Central de Downloads do RI da Maxion](https://www.iochpe.com.br/informacoes-ao-mercado/central-de-download/).")
up = st.file_uploader("Planilha de dados históricos da Maxion (.xlsx ou .xlsm) — opcional", type=["xlsx", "xlsm"])

try:
    if up is not None:
        co = load_excel(up.getvalue(), up.name)
        if co.profile != "iochpe":
            st.error("Esta planilha não parece ser da Iochpe-Maxion. Use a planilha de dados históricos do RI da Maxion.")
            st.stop()
        st.success(f"Planilha importada: {up.name}")
    else:
        co = load_excel(SAMPLE.read_bytes(), SAMPLE.name)
        st.caption(f"Usando a planilha do trabalho: {SAMPLE.name}")
except Exception as exc:  # noqa: BLE001
    st.error(f"Não foi possível interpretar esta planilha: {exc}")
    st.stop()

# Período histórico do TCC: demonstrações de 2016 a 2025 (projeção 2026–2030)
hist = co.hist.loc[(co.hist.index >= HIST_START) & (co.hist.index <= HIST_END)]
missing = [y for y in range(HIST_START, HIST_END + 1) if y not in hist.index]
if missing:
    st.error(f"A planilha não contém dados anuais de {', '.join(map(str, missing))}. "
             f"O trabalho usa o período de {HIST_START} a {HIST_END}.")
    st.stop()
last_year = HIST_END
avg_years = list(range(HIST_START, HIST_END + 1))
st.caption(f"Período analisado: {HIST_START} a {HIST_END}, conforme o trabalho.")
fixes_period = [f for f in co.quarter_fixes if HIST_START <= f["Ano"] <= HIST_END]

if fixes_period:
    st.info(esc(f"Conferência automática: na planilha da Maxion, a coluna anual de "
                f"{', '.join(sorted({str(f['Ano']) for f in fixes_period}))} não corresponde à soma dos quatro "
                f"trimestres em {len(fixes_period)} conta(s). O aplicativo usa a soma 1T + 2T + 3T + 4T."))
    with st.expander("Ver as contas corrigidas (R$ milhões)"):
        st.dataframe(style(pd.DataFrame(fixes_period).set_index(["Ano", "Conta"]), 1), width="stretch")

with st.expander("Demonstração do Resultado (DRE) — histórico", expanded=False):
    dre_cols = [c for c in DL.DRE_LABELS if c in hist.columns]
    st.dataframe(style(hist[dre_cols].rename(columns=DL.DRE_LABELS).T, 1), width="stretch")
bp_cols = [c for c in DL.BP_LABELS if c in hist.columns]
if bp_cols:
    with st.expander("Balanço Patrimonial (BP) — histórico", expanded=False):
        st.dataframe(style(hist[bp_cols].dropna(how="all").rename(columns=DL.BP_LABELS).T, 1), width="stretch")

ratios = M.historical_ratios(hist)
c1, c2 = st.columns(2)
with c1:
    st.plotly_chart(C.bars(hist.rename(columns=DL.DRE_LABELS),
                           ["Receita líquida", "Lucro bruto", "EBIT (lucro operacional)", "Lucro líquido (controladores)"],
                           "Receita e resultados históricos (R$ milhões)"), key="hist_bars")
with c2:
    st.plotly_chart(C.lines(ratios, ["Margem bruta (%)", "Margem EBITDA (%)", "Margem EBIT (%)", "Margem líquida (%)"],
                            "Margens históricas", suffix="%"), key="hist_margins")

# ======================================================================================
# 2. Premissas
# ======================================================================================
st.header("2. Premissas editáveis")
proj_years = list(range(last_year + 1, last_year + 6))
with st.expander("Premissas macroeconômicas — editáveis", expanded=True):
    st.caption("Crescimento da receita = (1 + Maxion) × (1 + PIB) × (1 + vegetativo) ÷ [(1 + Selic) × (1 + IPCA)] − 1. "
               "Valores em %; edite as células para simular o cenário econômico do momento.")
    macro_default = M.default_macro_table(proj_years)
    macro_default.index = ["Crescimento da Maxion (%)"] + list(macro_default.index[1:])
    macro = st.data_editor(macro_default, width="stretch", key=f"macro_{last_year}")
    growth = M.growth_from_macro(macro)

c1, c2, c3 = st.columns(3)
with c1:
    base_revenue = st.number_input(f"Receita líquida de {last_year} (R$ milhões)", 0.0,
                                   value=float(round(hist.loc[last_year, "receita"], 3)), step=100.0, format="%.3f",
                                   help="Preenchida automaticamente pela DRE importada.")
    investment = st.number_input("Investimento inicial (R$ milhões)", 0.0, value=M.TCC_DEFAULTS["investment"],
                                 step=10.0, format="%.1f")
with c2:
    wacc_pct = st.number_input("TMA / WACC (%)", 0.0, 100.0, value=M.TCC_DEFAULTS["wacc"], step=0.25, format="%.2f")
    tax_pct = st.number_input("Alíquota de IR projetada (%)", 0.0, 100.0, value=M.TCC_DEFAULTS["tax"], step=1.0,
                              format="%.2f")
with c3:
    shares = st.number_input("Quantidade de ações a emitir", 1, value=int(M.TCC_DEFAULTS["shares"]), step=100_000,
                             format="%d")
    st.caption("Valor por ação = VPL ÷ quantidade de ações a emitir.")

means = M.av_means(hist, avg_years)
with st.expander(f"Médias de análise vertical (AV) utilizadas — {avg_years[0]} a {avg_years[-1]}", expanded=False):
    st.caption("Cada conta da DRE é projetada como a média histórica do seu peso sobre a receita líquida. "
               "A coluna “Premissa” pode ser editada.")
    av_df = pd.DataFrame({"Conta": [M.AV_NAMES[k] for k in M.AV_LINES],
                          "Média histórica (%)": [means[k] * 100 for k in M.AV_LINES],
                          "Premissa (%)": [means[k] * 100 for k in M.AV_LINES]}, index=M.AV_LINES)
    av_edit = st.data_editor(av_df, width="stretch", hide_index=True, disabled=["Conta", "Média histórica (%)"],
                             column_config={"Média histórica (%)": st.column_config.NumberColumn(format="%.2f"),
                                            "Premissa (%)": st.column_config.NumberColumn(format="%.4f")},
                             key=f"av_{last_year}")
av = {k: float(v) / 100 for k, v in zip(M.AV_LINES, av_edit["Premissa (%)"])}

A = M.Assumptions(years=proj_years, growth=growth, base_revenue=base_revenue, av=av, tax=tax_pct / 100,
                  wacc=wacc_pct / 100, investment=investment, shares=shares)
proj = M.project(A)
R = M.evaluate_tcc(A, proj)

# ======================================================================================
# 3. Projeção
# ======================================================================================
st.header(f"3. Projeção financeira — {proj_years[0]} a {proj_years[-1]}")
proj_cols = ["Crescimento (%)", "Receita líquida", "CPV", "Lucro bruto", "Despesas com vendas", "Despesas G&A",
             "Honorários da administração", "Outras despesas/receitas", "Equivalência patrimonial", "EBIT",
             "Resultado financeiro", "Lucro antes do IR", "IR projetado", "Resultado após IR", "Margem após IR (%)"]
st.dataframe(style(proj[proj_cols].T, 2), width="stretch")

# ======================================================================================
# 4. Indicadores
# ======================================================================================
st.header("4. Indicadores de viabilidade")
m1, m2, m3, m4 = st.columns(4)
m1.metric("VPL", br(R["vpl"], prefix="R$ ", suffix=" mi"))
m2.metric("TIR", br(R["tir"] * 100, suffix="%") if R["tir"] is not None else "Não calculável")
m3.metric("Payback descontado", fmt_years(R["payback_desc"]))
m4.metric("VPL ÷ ações", br(R["por_acao"], prefix="R$ "))
detail = pd.DataFrame({"Fluxo usado (resultado após IR)": R["flows"], "Valor presente": R["pvs"],
                       "Acumulado descontado": R["cum"][1:]}, index=proj_years)
detail.index.name = "Ano"
st.dataframe(style(detail, 2), width="stretch")
st.caption("O fluxo usado é o resultado após IR, antes da participação de não controladores, como no trabalho.")

# ======================================================================================
# 5. Dashboards
# ======================================================================================
st.header("5. Dashboards")
st.subheader("Receita líquida: histórico e projeção")
st.plotly_chart(C.revenue_hist_proj(hist, proj), key="rev")
st.subheader("Fluxo descontado acumulado (payback)")
st.plotly_chart(C.payback_chart(proj_years, investment, R["pvs"], R["cum"], last_year), key="payback")
st.caption(esc(f"O valor final da linha ({br(R['cum'][-1], 0)}) é o próprio VPL à taxa de {br(wacc_pct)}%."))
c1, c2 = st.columns(2)
with c1:
    st.subheader(f"Da receita ao resultado, {proj_years[-1]}")
    st.plotly_chart(C.waterfall_year(proj.iloc[-1], proj_years[-1]), key="waterfall")
with c2:
    st.subheader("Resultado projetado e margem após IR")
    st.plotly_chart(C.result_margin(proj), key="result_margin")
st.caption("O resultado após IR é uma aproximação e não é um fluxo de caixa livre validado.")

# ======================================================================================
# 6. Sensibilidade
# ======================================================================================
st.header("Sensibilidade do VPL")
waccs = [w / 100 for w in range(10, 17)]
taxes = [0.25, 0.30, 0.35, 0.40]
grid = M.sensitivity_grid(A, waccs, taxes, "tcc")
st.plotly_chart(C.heatmap(grid, "VPL (R$ mi): WACC × alíquota de IR", "VPL"), key="heatmap")
st.caption(esc(f"VPL de R$ {br(np.nanmin(grid.values), 0)} mi a R$ {br(np.nanmax(grid.values), 0)} mi. ")
           + ("O VPL é positivo em todas as combinações." if np.nanmin(grid.values) > 0
              else "Há combinações com VPL negativo."))
st.subheader("VPL e indicador por ação por taxa de desconto")
st.caption("O modelo não inclui valor terminal.")
rt = M.rate_table(A, sorted(set(np.round(waccs + [A.wacc], 4))), "tcc")
rt["Taxa de desconto (%)"] = rt["Taxa de desconto (%)"].round(2)
rt = rt.set_index("Taxa de desconto (%)")
st.dataframe(style(rt, 2, highlight_row=round(A.wacc * 100, 2)), width="stretch")

# ======================================================================================
# 7. Simulador de modelos de valuation (complementar — não altera os resultados do TCC)
# ======================================================================================
st.header("Simulador de modelos de valuation")
st.write("Seção complementar ao trabalho: compara o valor da Iochpe-Maxion por outros modelos de valuation. "
         "Os resultados do TCC acima (VPL, TIR, payback e VPL ÷ ações) **não são alterados** por esta seção.")
cx = pd.read_csv(Path(__file__).parent / "data" / "dados_complementares_cvm.csv", sep=";").set_index("ano")
cx = cx.loc[HIST_START:HIST_END]
h = hist
mino_pl = float(h["minoritarios_pl"].iloc[-1]) if "minoritarios_pl" in h else 0.0
nd_series = M.net_debt_series(h)
nd_last = float(nd_series.iloc[-1]) if nd_series is not None else 0.0

c1, c2, c3, c4 = st.columns(4)
shares_out = c1.number_input("Ações em circulação", 1, value=149_770_000, step=100_000, format="%d",
                             help="DFP 2025 (CVM): 153,72 milhões de ações menos 3,95 milhões em tesouraria. "
                                  "Diferente das ações a emitir do modelo do TCC.")
ke = c2.number_input("Taxa de desconto dos modelos (%)", 0.0, 60.0, value=float(wacc_pct), step=0.25, format="%.2f",
                     help="Por padrão, igual à TMA do trabalho.") / 100
g_perp = c3.number_input("Crescimento na perpetuidade g (%)", -5.0, 15.0, 3.5, 0.25, format="%.2f",
                         help="Crescimento de longo prazo, próximo da inflação.") / 100
price_mkt = c4.number_input("Cotação atual (R$, opcional)", 0.0, value=0.0, step=0.1, format="%.2f",
                            help="Se informada, o app mostra a diferença entre o valor estimado e a cotação.")

t_cmp, t_fcff, t_div, t_gra, t_mult, t_mc = st.tabs(["📊 Comparação", "FCFF (DCF)", "Dividendos: Gordon e Bazin",
                                                     "Graham", "Múltiplos", "🎲 Monte Carlo"])

with t_fcff:
    st.caption("Fluxo de Caixa Livre da Firma (Damodaran): FCFF = EBIT × (1 − IR) + D&A − CapEx − Δ capital de giro, "
               "descontado pela taxa e somado ao valor terminal de Gordon. A receita e o EBIT são os mesmos da projeção do TCC.")
    da_def = float(((h["ebitda"] - h["ebit"]) / h["receita"]).mean() * 100)
    capex_def = float((cx["capex_rs_mil"] / 1000 / h["receita"]).mean() * 100)
    nwc_def = float((M.nwc_series(h) / h["receita"]).mean() * 100) if "fornecedores" in h else 0.0
    c1, c2, c3 = st.columns(3)
    da_p = c1.number_input("D&A (% da receita)", 0.0, 30.0, round(da_def, 2), 0.1,
                           help=f"Média {HIST_START}–{HIST_END} de (EBITDA − EBIT) ÷ receita.") / 100
    capex_p = c2.number_input("CapEx (% da receita)", 0.0, 30.0, round(capex_def, 2), 0.1,
                              help=f"Média {HIST_START}–{HIST_END}: aquisição de imobilizado e intangível (DFC, CVM).") / 100
    nwc_p = c3.number_input("Capital de giro (% da receita)", -20.0, 60.0, round(nwc_def, 2), 0.5,
                            help="(Contas a receber + estoques − fornecedores) ÷ receita, média histórica.") / 100
    c1, c2 = st.columns(2)
    nd_in = c1.number_input(f"Dívida líquida {HIST_END} (R$ mi)", value=round(nd_last, 1), step=10.0,
                            help="Empréstimos CP + LP − caixa − aplicações (balanço da planilha).")
    mino_in = c2.number_input("Não controladores no PL (R$ mi)", value=round(mino_pl, 1), step=10.0)
    F = SIM.fcff(A, da_p, capex_p, nwc_p, ke, g_perp, nd_in, mino_in, shares_out)
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Enterprise value", br(F["ev"], 1, "R$ ", " mi"))
    f2.metric("Valor do acionista", br(F["equity"], 1, "R$ ", " mi"))
    f3.metric("Valor por ação", br(F["per_share"], prefix="R$ "))
    f4.metric("Peso do valor terminal", br((F["tv_share"] or 0) * 100, 1, suffix="%"))
    st.dataframe(style(F["table"].T, 1), width="stretch")
    st.caption(esc(f"Valor terminal em {proj_years[-1]}: R$ {br(F['tv'], 1)} mi (valor presente R$ {br(F['pv_tv'], 1)} mi). "
                   f"Valor do acionista = EV − dívida líquida − não controladores."))

with t_div:
    st.caption("Dividendos pagos aos acionistas controladores (Demonstração dos Fluxos de Caixa, CVM).")
    div_hist = pd.DataFrame({"Dividendos pagos (R$ mi)": cx["dividendos_pagos_controladores_rs_mil"] / 1000,
                             "Por ação (R$)": cx["dividendos_pagos_controladores_rs_mil"] * 1000 / shares_out})
    st.dataframe(style(div_hist.T, 3), width="stretch")
    c1, c2 = st.columns(2)
    base_div = c1.radio("Dividendo por ação usado", [f"Média {HIST_END - 4}–{HIST_END}", f"Último ano ({HIST_END})"],
                        horizontal=True, help="A média reduz o efeito de anos sem dividendos, como 2021.")
    dpa_default = float(div_hist["Por ação (R$)"].loc[HIST_END - 4:HIST_END].mean() if base_div.startswith("Média")
                        else div_hist["Por ação (R$)"].loc[HIST_END])
    dpa = c1.number_input("Dividendo por ação (R$)", 0.0, value=round(dpa_default, 4), step=0.01, format="%.4f",
                          key=f"dpa_{base_div}")
    min_yield = c2.number_input("Rendimento mínimo de Bazin (%)", 0.5, 30.0, 6.0, 0.5, format="%.1f") / 100
    v_gordon, v_bazin = SIM.gordon(dpa, ke, g_perp), SIM.bazin(dpa, min_yield)
    d1, d2 = st.columns(2)
    d1.metric("Gordon: D₁ ÷ (ke − g)", br(v_gordon, prefix="R$ ") if v_gordon else "ke precisa ser maior que g")
    d2.metric(f"Bazin: dividendo ÷ {br(min_yield * 100, 1)}%", br(v_bazin, prefix="R$ "))
    st.caption("O modelo de Gordon supõe que os dividendos crescem a uma taxa constante g para sempre; "
               "o método Bazin define um preço-teto para que o dividendo renda pelo menos 6% ao ano.")

with t_gra:
    st.caption("Número de Graham: preço justo = √(22,5 × LPA × VPA), que combina P/L de 15 e P/VP de 1,5.")
    lpa_series = h["lucro_liquido"] * 1e6 / shares_out
    c1, c2 = st.columns(2)
    base_lpa = c1.radio("Lucro por ação usado", [f"Último ano ({HIST_END})", f"Média {HIST_END - 2}–{HIST_END}"],
                        horizontal=True)
    lpa_default = float(lpa_series.loc[HIST_END] if base_lpa.startswith("Último") else lpa_series.loc[HIST_END - 2:HIST_END].mean())
    lpa = c1.number_input("LPA (R$)", value=round(lpa_default, 4), step=0.01, format="%.4f", key=f"lpa_{base_lpa}",
                          help="Lucro líquido dos controladores ÷ ações em circulação.")
    vpa_default = float((h["patrimonio_liquido"].iloc[-1] - mino_pl) * 1e6 / shares_out)
    vpa = c2.number_input("VPA (R$)", value=round(vpa_default, 4), step=0.1, format="%.4f",
                          help="Patrimônio líquido dos controladores ÷ ações em circulação.")
    v_graham = SIM.graham(lpa, vpa)
    st.metric("Preço justo de Graham", br(v_graham, prefix="R$ ") if v_graham else "Requer LPA e VPA positivos")

with t_mult:
    st.caption("Avaliação relativa: aplica múltiplos de referência (de empresas comparáveis do setor) aos números da Iochpe-Maxion. "
               "Os múltiplos abaixo são ilustrativos — ajuste com a média de comparáveis como Randon, Tupy e Marcopolo.")
    ebitda_last = float(h["ebitda"].iloc[-1])
    c1, c2 = st.columns(2)
    pe = c1.number_input("P/L de referência (x)", 0.0, 60.0, 8.0, 0.5, format="%.1f")
    eveb = c2.number_input("EV/EBITDA de referência (x)", 0.0, 30.0, 4.5, 0.25, format="%.2f")
    v_pe = SIM.by_pe(pe, lpa)
    v_eveb = SIM.by_ev_ebitda(eveb, ebitda_last, nd_in, mino_in, shares_out)
    m1_, m2_ = st.columns(2)
    m1_.metric("Pelo P/L", br(v_pe, prefix="R$ ") if v_pe else "LPA negativo", help=f"P/L × LPA ({br(lpa, 3)})")
    m2_.metric("Pelo EV/EBITDA", br(v_eveb, prefix="R$ "),
               help=esc(f"(Múltiplo × EBITDA {HIST_END} de R$ {br(ebitda_last, 1)} mi − dívida líquida − não controladores) ÷ ações"))

with t_mc:
    st.caption("Simulação de Monte Carlo sobre o modelo do TCC: sorteia milhares de cenários variando o crescimento da "
               "receita, a margem EBIT e a TMA em torno das premissas do trabalho, e mostra a distribuição do VPL.")
    c1, c2, c3, c4 = st.columns(4)
    n_sim = c1.select_slider("Cenários", [1000, 2000, 5000, 10000, 20000], value=5000)
    sd_g = c2.number_input("Desvio do crescimento (p.p./ano)", 0.0, 10.0, 2.0, 0.25, format="%.2f")
    sd_m = c3.number_input("Desvio da margem EBIT (p.p.)", 0.0, 5.0, 0.5, 0.1, format="%.2f")
    sd_r = c4.number_input("Desvio da TMA (p.p.)", 0.0, 10.0, 1.5, 0.25, format="%.2f")
    sims = SIM.monte_carlo(A, n_sim, sd_g / 100, sd_m / 100, sd_r / 100)
    p5, p50, p95 = np.percentile(sims, [5, 50, 95])
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Probabilidade de VPL > 0", br((sims > 0).mean() * 100, 1, suffix="%"))
    k2.metric("VPL mediano", br(p50, 1, "R$ ", " mi"))
    k3.metric("Pessimista (5%)", br(p5, 1, "R$ ", " mi"))
    k4.metric("Otimista (95%)", br(p95, 1, "R$ ", " mi"))
    st.plotly_chart(C.histogram_vpl(sims, R["vpl"]), key="mc_hist")
    st.caption(esc(f"Em 90% dos cenários, o VPL fica entre R$ {br(p5, 0)} mi e R$ {br(p95, 0)} mi. "
                   "Com desvios iguais a zero, a simulação reproduz exatamente o VPL do trabalho."))

with t_cmp:
    model_values = {"FCFF (DCF)": F["per_share"], "Gordon (dividendos)": v_gordon, "Bazin": v_bazin,
                    "Graham": v_graham, "Múltiplo P/L": v_pe, "Múltiplo EV/EBITDA": v_eveb}
    st.plotly_chart(C.football_field(model_values, price_mkt or None), key="football")
    valid = [v for v in model_values.values() if v is not None and np.isfinite(v)]
    sim_df = pd.DataFrame({"Valor por ação (R$)": list(model_values.values())}, index=list(model_values))
    sim_df.index.name = "Modelo"
    if price_mkt:
        sim_df["Diferença vs. cotação (%)"] = (sim_df["Valor por ação (R$)"] / price_mkt - 1) * 100
    st.dataframe(style(sim_df, 2), width="stretch")
    if valid:
        st.markdown(esc(f"Média dos modelos: **R$ {br(float(np.mean(valid)))}** · mediana: **R$ {br(float(np.median(valid)))}** "
                        f"· faixa: R$ {br(min(valid))} a R$ {br(max(valid))} por ação."))
    st.caption("Os valores por ação desta seção usam as ações em circulação e avaliam a empresa inteira. "
               "O “VPL ÷ ações” do TCC (R$ 16,48) divide o VPL do investimento pelas ações a emitir, por isso não é "
               "comparável diretamente. Cada modelo responde a uma pergunta diferente; a dispersão entre eles é normal.")

# ======================================================================================
# Exportação e metodologia
# ======================================================================================
buf = BytesIO()
with pd.ExcelWriter(buf, engine="openpyxl") as w:
    pd.DataFrame({"Indicador": ["VPL (R$ mi)", "TIR (%)", "Payback descontado (anos)", "VPL ÷ ações (R$)"],
                  "Valor": [R["vpl"], R["tir"] * 100 if R["tir"] is not None else None, R["payback_desc"],
                            R["por_acao"]]}).to_excel(w, sheet_name="Resultados", index=False)
    macro.to_excel(w, sheet_name="Premissas macro")
    hist.rename(columns=DL.ALL_LABELS).T.to_excel(w, sheet_name="Historico importado")
    av_edit.to_excel(w, sheet_name="Medias AV", index=False)
    proj[proj_cols].T.to_excel(w, sheet_name=f"Projecao {proj_years[0]}-{proj_years[-1]}")
    detail.to_excel(w, sheet_name="Fluxos e VPL")
    grid.to_excel(w, sheet_name="Sensibilidade")
    sim_df.to_excel(w, sheet_name="Simulador de modelos")
    F["table"].T.to_excel(w, sheet_name="Simulador FCFF")
st.download_button("⬇️ Baixar análise calculada em Excel", buf.getvalue(), "Valuation_Iochpe_Maxion_calculado.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with st.expander("Metodologia"):
    st.markdown("A receita é projetada pelos fatores macroeconômicos; as demais contas, pela média da análise vertical "
                f"de {avg_years[0]} a {avg_years[-1]}. O IR incide sobre o lucro antes do IR positivo.")
    st.latex(r"VPL = -I_0 + \sum_{t=1}^{5} \frac{FC_t}{(1+TMA)^t} \qquad \sum_{t=0}^{5}\frac{FC_t}{(1+TIR)^t}=0")
    st.markdown("O payback descontado é o tempo até o acumulado dos fluxos descontados igualar o investimento inicial. "
                "Referências: Assaf Neto, Damodaran, Iudícibus e Marion.")
st.caption("ANSELMO, Rayssa Pfaffenzeller. Valuation da Iochpe-Maxion: Estudo de Análise da Viabilidade Econômica por "
           "meio de VPL, TIR e PBD. Trabalho de Graduação (Administração) — Centro Universitário Teresa D’Ávila, Lorena, "
           "2026. Resultados acadêmicos condicionados às premissas; não constituem recomendação de investimento.")
