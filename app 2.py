from html import escape
from io import BytesIO
from pathlib import Path
import math
import re
import unicodedata

import numpy as np
import numpy_financial as npf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Valuation Iochpe-Maxion | TCC", layout="wide")

# ======================================================================
# PALETA E CSS (único bloco — cores do banner Maxion)
# ======================================================================
AZUL, AZUL_ESC, VERDE, CORAL = "#4A8BEA", "#2F5AA6", "#4FD1A5", "#FF7A66"

CSS = """
<style>
.stApp {background: #08122b;}
section[data-testid="stSidebar"] {background: #0f1f45;}
.block-container {padding-top: 1.2rem; max-width: 1350px;}
h1, h2, h3 {color: #eef3fb;}
h2 {border-left: 4px solid #4a8bea; padding-left: 12px; margin-top: 1.6rem;}

div[data-testid="stMetric"] {
    background: linear-gradient(145deg, #0f1f45, #0a1836);
    border: 1px solid #223c75;
    border-top: 3px solid #4a8bea;
    border-radius: 12px;
    padding: 16px 18px;
    box-shadow: 0 4px 18px rgba(0, 0, 0, .35);
}
div[data-testid="stMetricLabel"] {color: #93a8cc !important; font-weight: 600;}
div[data-testid="stMetricValue"] {color: #eef3fb !important; font-weight: 700;}

div[data-testid="stDataFrame"] {
    border: 1px solid #223c75; border-radius: 10px; overflow: hidden;
}

.tbl-wrap {
    overflow-x: auto; border: 1px solid #223c75;
    border-radius: 12px; margin: 6px 0 14px 0;
}
table.tbl {
    width: 100%; border-collapse: collapse;
    font-size: .88rem; color: #eef3fb;
}
table.tbl th {
    background: linear-gradient(180deg, #1d4a96, #163a78);
    color: #fff; font-weight: 600; text-align: right;
    padding: 10px 12px; white-space: nowrap;
    border-bottom: 2px solid #4a8bea;
}
table.tbl th:first-child, table.tbl td:first-child {
    text-align: left; position: sticky; left: 0;
}
table.tbl td {
    padding: 9px 12px; text-align: right; white-space: nowrap;
    border-bottom: 1px solid #1a2f5e;
    font-variant-numeric: tabular-nums;
}
table.tbl tbody tr:nth-child(odd) td  {background: #0f1f45;}
table.tbl tbody tr:nth-child(even) td {background: #0b1a3b;}
table.tbl tbody tr:hover td {background: #1a3470;}
table.tbl tbody tr.hl td {background: #1d4a96; font-weight: 700;}

.dashboard-note {
    background: #0f1f45; border-left: 4px solid #4a8bea;
    padding: 12px 16px; border-radius: 6px; color: #dce7fa;
}
.stTabs [data-baseweb="tab"] {font-weight: 600;}

.stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp p, .stApp label,
[data-testid="stMarkdownContainer"],
[data-testid="stWidgetLabel"] p {
    color: #eef3fb !important;
}
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p {
    color: #93a8cc !important;
}
div[data-testid="stMetricValue"] > div {
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    font-size: 1.6rem !important;
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def estilo(fig, titulo=None, h=360):
    """Padroniza os gráficos Plotly com a paleta do banner."""
    fig.update_layout(
        title=titulo, height=h, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#EEF3FB"), margin=dict(l=10, r=10, t=55, b=10),
        legend=dict(orientation="h", y=1.14, x=0), hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,.07)")
    return fig


def tabela_html(df, fmt=None, cor_cols=None, destaque=None):
    """Tabela estilizada (o st.dataframe ignora estilos de tabela)."""
    fmt = fmt or {}
    cor_cols = cor_cols or []
    head = "".join(f"<th>{escape(str(c))}</th>" for c in df.columns)
    body = ""
    for i, (_, row) in enumerate(df.reset_index(drop=True).iterrows()):
        cells = ""
        for c in df.columns:
            v = row[c]
            txt = fmt[c](v) if c in fmt else str(v)
            style = ""
            if c in cor_cols:
                try:
                    n = float(v)
                    if n < 0:
                        style = ' style="color:#ff8b8b;font-weight:600"'
                    elif n > 0:
                        style = ' style="color:#75dcff;font-weight:600"'
                except (TypeError, ValueError):
                    pass
            cells += f"<td{style}>{escape(txt)}</td>"
        cls = "hl" if destaque == i else ""
        body += f'<tr class="{cls}">{cells}</tr>'
    html = (
        '<div class="tbl-wrap"><table class="tbl">'
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
    )
    st.markdown(html, unsafe_allow_html=True)


# ======================================================================
# CABEÇALHO
# ======================================================================
arquivo_hero = Path(__file__).parent / "hero_maxion.html"

if arquivo_hero.exists():
    components.html(
        arquivo_hero.read_text(encoding="utf-8"),
        height=320,
        scrolling=False,
    )
else:
    st.warning("Arquivo hero_maxion.html não encontrado.")

st.title("Valuation Iochpe-Maxion — análise dinâmica")
st.caption(
    "Os resultados são recalculados com base no arquivo histórico "
    "importado e nas premissas editáveis. "
    "Valores financeiros em R$ milhões, salvo indicação contrária."
)


# ======================================================================
# FUNÇÕES DE LEITURA (lógica inalterada)
# ======================================================================
def norm(value):
    if pd.isna(value):
        return ""
    value = str(value).strip().lower()
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", value)


def find_dre_sheet(xls):
    for name in xls.sheet_names:
        n = norm(name)
        if "dre" in n and "income statement" in n:
            return name
    for name in xls.sheet_names:
        n = norm(name)
        if "dre" in n or "income statement" in n:
            return name
    return None


def read_historical_data(file_bytes):
    xls = pd.ExcelFile(BytesIO(file_bytes), engine="openpyxl")
    sheet = find_dre_sheet(xls)
    if sheet is None:
        raise ValueError(
            "Não encontrei uma aba de DRE/Income Statement. "
            "Use a planilha histórica oficial da Maxion."
        )
    raw = pd.read_excel(xls, sheet_name=sheet, header=None)
    if raw.shape[0] < 5 or raw.shape[1] < 5:
        raise ValueError(
            "A aba de DRE parece vazia ou tem uma estrutura "
            "diferente da esperada."
        )

    header_row = None
    year_cols = {}
    for r in range(min(8, len(raw))):
        found = {}
        for c, value in enumerate(raw.iloc[r].tolist()):
            try:
                y = int(float(value))
                if 2010 <= y <= 2035:
                    found[y] = c
            except (TypeError, ValueError):
                pass
        if len(found) >= 3:
            header_row, year_cols = r, found
            break
    if header_row is None:
        raise ValueError(
            "Não consegui identificar os cabeçalhos anuais da DRE. "
            "Confira se a planilha está no formato original."
        )

    years = [y for y in range(2016, 2026) if y in year_cols]
    if not years:
        years = sorted(year_cols)
    labels = raw.iloc[:, 0].map(norm)

    def row_index(contains, exclude=None):
        exclude = exclude or []
        for idx, label in labels.items():
            if not label:
                continue
            if any(t in label for t in contains) and not any(t in label for t in exclude):
                return idx
        return None

    revenue_idx = row_index(["receita operacional liquida", "net operating revenue"])
    gross_idx = row_index(["lucro (prejuizo) bruto", "gross profit"])
    ebit_idx = row_index(["lucro (prejuizo) operacional (ebit)", "operating income (ebit)"])
    if revenue_idx is None:
        revenue_idx = row_index(["receita liquida", "net revenue"])
    if revenue_idx is None or gross_idx is None:
        raise ValueError(
            "Não encontrei Receita Operacional Líquida e Lucro Bruto "
            "na DRE. Não vou calcular usando números fixos."
        )

    patterns = {
        "receita": (["receita operacional liquida", "net operating revenue", "net revenue"], []),
        "lucro_bruto": (["lucro (prejuizo) bruto", "gross profit"], []),
        "vendas": (["com vendas", "selling expenses"], []),
        "admin": (["gerais e administrativas", "general and administrative"], []),
        "honorarios": (["honorarios da administracao", "management fees"], []),
        "outros": (["outras despesas/receitas", "other"], ["outras despesas operacionais"]),
        "equivalencia": (["resultado de equivalencia patrimonial", "equity income"], []),
        "ebit": (["lucro (prejuizo) operacional (ebit)", "operating income (ebit)"], []),
        "receitas_financeiras": (["receitas financeiras", "financial revenue"], ["despesas financeiras"]),
        "despesas_financeiras": (["despesas financeiras", "financial expenses"], []),
        "cambio": (["variacao cambial liquida", "foreign exchange gains"], []),
        "antes_ir": (["lucro (prejuizo) antes do imp. de renda", "earnings after financial results"], []),
        "imposto_historico": (["imp. de renda / contrib. social", "income taxes"], []),
        "minoritarios": (["participacao de nao controladores", "minority shareholders"], []),
        "lucro_liquido": (["lucro liquido (prejuizo)", "net income (loss)"], []),
        "ebitda": (["ebitda"], ["conciliação", "reconciliation"]),
    }
    indices = {}
    for key, (terms, exclude) in patterns.items():
        indices[key] = row_index(terms, exclude)
    indices["receita"] = revenue_idx
    indices["lucro_bruto"] = gross_idx
    indices["ebit"] = ebit_idx if ebit_idx is not None else indices["ebit"]

    def num_at(idx, year):
        if idx is None:
            return np.nan
        val = raw.iloc[idx, year_cols[year]]
        return pd.to_numeric(pd.Series([val]), errors="coerce").iloc[0]

    records = []
    for year in years:
        revenue = num_at(indices["receita"], year)
        if pd.isna(revenue) or revenue == 0:
            continue
        rec = {
            "Ano": year,
            "Receita líquida (R$ milhões)": float(revenue) / 1000.0,
        }
        for key, idx in indices.items():
            if key == "receita":
                continue
            val = num_at(idx, year) if idx is not None else np.nan
            rec[key] = float(val) / 1000.0 if pd.notna(val) else np.nan
        gross_val = float(num_at(indices["lucro_bruto"], year))
        rec["cpv"] = (gross_val - float(revenue)) / 1000.0
        records.append(rec)
    hist = pd.DataFrame(records).sort_values("Ano")
    if hist.empty or hist["Ano"].max() < 2024:
        raise ValueError(
            "A DRE importada não contém dados anuais suficientes "
            "(é esperado pelo menos até 2024/2025)."
        )
    return hist, sheet, xls.sheet_names


def br(value, decimals=2):
    if value is None:
        return "—"
    if isinstance(value, float) and not math.isfinite(value):
        return "—"
    txt = f"{value:,.{decimals}f}"
    return txt.replace(",", "X").replace(".", ",").replace("X", ".")


def n2(v):
    return br(float(v)) if pd.notna(v) else "—"


def pct(v):
    return br(float(v)) + "%" if pd.notna(v) else "—"


# ======================================================================
# 1. IMPORTAR PLANILHA
# ======================================================================
st.header("1. Importar planilha histórica")
st.write(
    "Selecione a planilha oficial de dados históricos da Maxion "
    "(.xlsx ou .xlsm). O aplicativo vai localizar a aba de DRE e "
    "usar os valores anuais para formar as médias históricas."
)
uploaded_file = st.file_uploader(
    "Escolha o arquivo Excel da Maxion",
    type=["xlsx", "xlsm"],
    accept_multiple_files=False,
    key="historical_workbook_upload",
    help=(
        "Clique em Procurar arquivos ou arraste o arquivo para esta "
        "área. A planilha não precisa estar na pasta do aplicativo."
    ),
)
if uploaded_file is None:
    st.info(
        "Aguardando a planilha histórica. Se a janela não abrir no "
        "Safari, atualize a página ou use o Google Chrome."
    )
    st.stop()

try:
    hist, dre_sheet, all_sheets = read_historical_data(uploaded_file.getvalue())
    st.success(
        f"Arquivo importado: {uploaded_file.name} · DRE identificada "
        f"na aba '{dre_sheet}' · {len(hist)} anos lidos."
    )
    with st.expander("Conferir dados históricos importados", expanded=False):
        st.dataframe(hist, width="stretch", hide_index=True)
        st.caption(
            "Os valores monetários foram convertidos de R$ mil para "
            "R$ milhões, conforme o cabeçalho da DRE histórica."
        )
except Exception as exc:
    st.error(f"Não foi possível interpretar esta planilha: {exc}")
    st.stop()

# Ajuste de participação de não controladores (coluna original preservada).
hist["lucro_liquido_ajustado"] = hist["lucro_liquido"] - hist["minoritarios"]

last_year = int(hist["Ano"].max())
last_row = hist.loc[hist["Ano"] == last_year].iloc[-1]
revenue_last = float(last_row["Receita líquida (R$ milhões)"])
ratio_keys = [
    "cpv", "lucro_bruto", "vendas", "admin", "honorarios", "outros",
    "equivalencia", "receitas_financeiras", "despesas_financeiras", "cambio",
]
ratio_labels = {
    "cpv": "CPV",
    "lucro_bruto": "Lucro bruto",
    "vendas": "Despesas com vendas",
    "admin": "Despesas gerais e administrativas",
    "honorarios": "Honorários da administração",
    "outros": "Outras despesas/receitas",
    "equivalencia": "Equivalência patrimonial",
    "receitas_financeiras": "Receitas financeiras",
    "despesas_financeiras": "Despesas financeiras",
    "cambio": "Variação cambial líquida",
}
for key in ratio_keys:
    hist[key + "_av"] = hist[key] / hist["Receita líquida (R$ milhões)"]
    hist[key + "_av"] = hist[key + "_av"].replace([np.inf, -np.inf], np.nan)
av_means = {}
for key in ratio_keys:
    serie = hist[key + "_av"]
    av_means[key] = float(serie.mean(skipna=True)) if serie.notna().any() else 0.0

# ======================================================================
# 2. PREMISSAS EDITÁVEIS
# ======================================================================
st.header("2. Premissas editáveis")
years_proj = [2026, 2027, 2028, 2029, 2030]
defaults = {
    "Crescimento da Maxion (%)": [4.00, 4.50, 4.20, 4.00, 3.80],
    "Crescimento do PIB (%)": [1.80, 2.00, 2.00, 2.00, 2.00],
    "Efeito da Selic sobre vendas (%)": [
        -2.00, 2.00, 1.9607843137, 1.9230769231, 1.8867924528,
    ],
    "Efeito da inflação (IPCA) sobre vendas (%)": [4.50, 0, 0, 0, 0],
    "Crescimento vegetativo (%)": [0.36, 0.34, 0.32, 0.31, 0.29],
}
assumptions = {}
with st.expander("Premissas macroeconômicas — editáveis", expanded=True):
    for label, values in defaults.items():
        st.markdown(f"**{label}**")
        cols = st.columns(5)
        assumptions[label] = []
        for col, year, default in zip(cols, years_proj, values):
            with col:
                valor = st.number_input(
                    str(year),
                    value=float(default),
                    step=0.1,
                    format="%.4f",
                    key=f"{label}_{year}",
                )
                assumptions[label].append(valor / 100.0)

c1, c2, c3 = st.columns(3)
with c1:
    revenue_override = st.number_input(
        f"Receita líquida de {last_year} (R$ milhões)",
        min_value=0.0, value=float(revenue_last), step=100.0, format="%.3f",
        help="Preenchido pela DRE importada; pode ser ajustado.",
    )
    investment = st.number_input(
        "Investimento inicial (R$ milhões)",
        min_value=0.0, value=722.1, step=10.0, format="%.3f",
    )
with c2:
    wacc_pct = st.number_input(
        "TMA / WACC (%)",
        min_value=0.0, max_value=100.0, value=13.0, step=0.25, format="%.2f",
    )
    tax_pct = st.number_input(
        "Alíquota de IR projetada (%)",
        min_value=0.0, max_value=100.0, value=35.0, step=1.0, format="%.2f",
    )
with c3:
    shares = st.number_input(
        "Quantidade de ações (unidades)",
        min_value=1, value=23143771, step=100000, format="%d",
    )
    st.caption(
        "Preço por ação calculado como VPL ÷ quantidade de ações. "
        "Confirme essa convenção com o modelo do TCC."
    )

# ----------------------------------------------------------------------
# Base das médias de análise vertical (AV)
# ----------------------------------------------------------------------
st.subheader("Base das médias de análise vertical (AV)")
modo_av = st.radio(
    "Fonte das médias AV usadas na projeção",
    [
        "TCC — médias da Tabela 3 (editáveis)",
        "Planilha importada (calculadas da DRE)",
    ],
    horizontal=True,
    key="modo_av",
)
usar_tcc = modo_av.startswith("TCC")

# Médias da Tabela 3/6 do TCC, em % da receita líquida.
TCC_AV_PCT = {
    "lucro_bruto": 11.880614,
    "admin": -4.916767,
    "vendas": -0.911925,
    "despesas_financeiras": -3.970031,
    "gerais": -0.079407,
    "receitas_financeiras": 0.788424,
}
TCC_LABELS = {
    "lucro_bruto": "Lucro bruto",
    "admin": "Despesas administrativas",
    "vendas": "Despesas comerciais",
    "despesas_financeiras": "Despesas financeiras",
    "gerais": "Despesas gerais",
    "receitas_financeiras": "Receitas financeiras",
}
tcc_av = {k: v / 100.0 for k, v in TCC_AV_PCT.items()}

if usar_tcc:
    tcc_df = pd.DataFrame({
        "Conta": [TCC_LABELS[k] for k in TCC_AV_PCT],
        "Média AV (%)": [TCC_AV_PCT[k] for k in TCC_AV_PCT],
    })
    tcc_edit = st.data_editor(
        tcc_df,
        hide_index=True,
        disabled=["Conta"],
        key="tcc_av_editor",
        width="stretch",
        column_config={
            "Média AV (%)": st.column_config.NumberColumn(format="%.4f"),
        },
    )
    for k, v in zip(TCC_AV_PCT, tcc_edit["Média AV (%)"].tolist()):
        tcc_av[k] = float(v) / 100.0
    st.caption(
        "Resultado antes do IR = lucro bruto + despesas administrativas, "
        "comerciais, financeiras e gerais + receitas financeiras, como na "
        "Tabela 6 do TCC. Com as premissas padrão, o modelo reproduz "
        "VPL R$ 381,50 mi, TIR 32,30% e R$ 16,48 por ação."
    )

with st.expander("Comparar com as médias calculadas da planilha importada"):
    comp_planilha = {
        "lucro_bruto": av_means["lucro_bruto"],
        "admin": av_means["admin"],
        "vendas": av_means["vendas"],
        "despesas_financeiras": (
            av_means["despesas_financeiras"] + av_means["cambio"]
        ),
        "gerais": (
            av_means["honorarios"] + av_means["outros"]
            + av_means["equivalencia"]
        ),
        "receitas_financeiras": av_means["receitas_financeiras"],
    }
    comp_rows = []
    for k in TCC_AV_PCT:
        pl = comp_planilha[k] * 100
        comp_rows.append({
            "Conta": TCC_LABELS[k],
            "TCC (%)": TCC_AV_PCT[k],
            "Planilha (%)": pl,
            "Diferença (p.p.)": pl - TCC_AV_PCT[k],
        })
    tabela_html(
        pd.DataFrame(comp_rows),
        {
            "TCC (%)": n2,
            "Planilha (%)": n2,
            "Diferença (p.p.)": n2,
        },
        ["Diferença (p.p.)"],
    )
    st.caption(
        "Se a diferença não for próxima de zero, a planilha importada "
        "não tem a mesma estrutura ou os mesmos anos da tabela do TCC."
    )

# Projeção de receita por premissas.
growth_factors = []
for i in range(5):
    m = assumptions["Crescimento da Maxion (%)"][i]
    pib = assumptions["Crescimento do PIB (%)"][i]
    selic = assumptions["Efeito da Selic sobre vendas (%)"][i]
    ipca = assumptions["Efeito da inflação (IPCA) sobre vendas (%)"][i]
    veg = assumptions["Crescimento vegetativo (%)"][i]
    denominator = (1 + selic) * (1 + ipca)
    if denominator:
        growth_factors.append(((1 + m) * (1 + pib) * (1 + veg) / denominator) - 1)
    else:
        growth_factors.append(0.0)

revenues = []
prev = revenue_override
for growth in growth_factors:
    prev *= 1 + growth
    revenues.append(prev)

ebit_ratio = hist["ebit"] / hist["Receita líquida (R$ milhões)"]
ebit_ratio = ebit_ratio.replace([np.inf, -np.inf], np.nan)
if hist["ebit"].notna().any():
    ebit_av = ebit_ratio.mean(skipna=True)
else:
    ebit_av = np.nan

projection = []
net_income = []
for i, year in enumerate(years_proj):
    rev = revenues[i]
    if usar_tcc:
        lb = rev * tcc_av["lucro_bruto"]
        adm = rev * tcc_av["admin"]
        com = rev * tcc_av["vendas"]
        ger = rev * tcc_av["gerais"]
        fin = rev * tcc_av["despesas_financeiras"]
        rec = rev * tcc_av["receitas_financeiras"]
        values = {
            "cpv": lb - rev,
            "lucro_bruto": lb,
            "vendas": com,
            "admin": adm,
            "honorarios": 0.0,
            "outros": ger,
            "equivalencia": 0.0,
        }
        ebit = lb + adm + com + ger
        financial_result = fin + rec
    else:
        values = {key: rev * av_means[key] for key in ratio_keys}
        if pd.notna(ebit_av):
            ebit = rev * float(ebit_av)
        else:
            ebit = rev * (
                av_means["lucro_bruto"] + av_means["vendas"]
                + av_means["admin"] + av_means["honorarios"]
                + av_means["outros"] + av_means["equivalencia"]
            )
        financial_result = (
            values["receitas_financeiras"]
            + values["despesas_financeiras"]
            + values["cambio"]
        )
    pretax = ebit + financial_result
    tax = -max(pretax, 0.0) * tax_pct / 100.0
    minorities = 0.0
    net = pretax + tax
    net_income.append(net)
    projection.append({
        "Ano": year,
        "Crescimento projetado (%)": growth_factors[i] * 100,
        "Receita líquida": rev,
        "CPV": values["cpv"],
        "Lucro bruto": values["lucro_bruto"],
        "Despesas com vendas": values["vendas"],
        "Despesas G&A": values["admin"],
        "Honorários da administração": values["honorarios"],
        "Outras despesas/receitas": values["outros"],
        "Equivalência patrimonial": values["equivalencia"],
        "EBIT projetado": ebit,
        "Resultado financeiro": financial_result,
        "Lucro antes do IR": pretax,
        "IR projetado": tax,
        "Participação de não controladores considerada no valuation": minorities,
        "Resultado após IR, antes de não controladores": net,
    })

# ======================================================================
# 3. PROJEÇÃO FINANCEIRA
# ======================================================================
st.header("3. Projeção financeira — 2026 a 2030")
st.caption(
    f"Receita-base e médias AV derivadas da aba '{dre_sheet}' da "
    f"planilha carregada. Média AV calculada sobre os anos disponíveis "
    f"de 2016 a {last_year}; altere premissas para recalcular."
)
proj_df = pd.DataFrame(projection)

COL_RES = "Resultado após IR, antes de não controladores"
fmt_proj = {}
for c in proj_df.columns:
    if c not in ["Ano", "Crescimento projetado (%)"]:
        fmt_proj[c] = n2
fmt_proj["Ano"] = lambda v: str(int(v))
fmt_proj["Crescimento projetado (%)"] = pct
cor_proj = ["Resultado financeiro", "Lucro antes do IR", "IR projetado", COL_RES]
tabela_html(proj_df, fmt_proj, cor_proj)

with st.expander("Médias de análise vertical (AV) utilizadas", expanded=False):
    av_table = pd.DataFrame([
        {
            "Conta histórica": ratio_labels[k],
            "Média AV sobre receita líquida (%)": av_means[k] * 100,
        }
        for k in ratio_keys
    ])
    tabela_html(
        av_table,
        {"Média AV sobre receita líquida (%)": pct},
        ["Média AV sobre receita líquida (%)"],
    )

# ======================================================================
# 4. INDICADORES DE VIABILIDADE
# ======================================================================
st.header("4. Indicadores de viabilidade — recalculados")
wacc = wacc_pct / 100.0
cashflows = [-float(investment)] + [float(x) for x in net_income]
vpl = sum(cf / ((1 + wacc) ** t) for t, cf in enumerate(cashflows))
try:
    irr = npf.irr(cashflows)
    if irr is not None and math.isfinite(float(irr)):
        irr_pct = float(irr * 100)
    else:
        irr_pct = None
except Exception:
    irr_pct = None

COL_FLUXO = "Fluxo usado (após IR, antes de não controladores; R$ mi)"
COL_VP = "Valor presente (R$ mi)"
COL_ACUM = "Acumulado descontado (R$ mi)"

acc = -float(investment)
pbd = None
detail = []
for i, (year, flow) in enumerate(zip(years_proj, net_income), start=1):
    pv = flow / ((1 + wacc) ** i)
    before = acc
    acc += pv
    detail.append({"Ano": year, COL_FLUXO: flow, COL_VP: pv, COL_ACUM: acc})
    if pbd is None and acc >= 0 and pv > 0:
        pbd = (i - 1) + (-before / pv)
price = (vpl * 1_000_000) / shares
if pbd is None:
    payback_text = "Não recuperado até 2030"
else:
    anos_p = int(pbd)
    resto_m = (pbd - anos_p) * 12
    meses_p = int(resto_m)
    dias_p = int(round((resto_m - meses_p) * 30))
    payback_text = f"{anos_p} ano(s), {meses_p} mês(es) e {dias_p} dia(s)"

m1, m2, m3, m4 = st.columns(4)
m1.metric(
    "VPL", f"R$ {br(vpl)} mi",
    delta="VPL positivo" if vpl >= 0 else "-VPL negativo",
)
if irr_pct is not None:
    delta_tir = f"{irr_pct - wacc_pct:+.2f} p.p. vs WACC".replace(".", ",")
    m2.metric("TIR", f"{br(irr_pct)}%", delta=delta_tir)
else:
    m2.metric("TIR", "Não calculável")
m3.metric("Payback descontado", payback_text)
m4.metric("VPL ÷ ações", f"R$ {br(price)}")
if usar_tcc:
    st.caption(
        "Referência do TCC: VPL R$ 381,50 mi · TIR 32,30% · "
        "R$ 16,48 por ação (com as premissas padrão)."
    )

df_detail = pd.DataFrame(detail)
colunas_valores = [COL_FLUXO, COL_VP, COL_ACUM]
fmt_detail = {c: n2 for c in colunas_valores}
fmt_detail["Ano"] = lambda v: str(int(v))
tabela_html(df_detail, fmt_detail, colunas_valores)

# ======================================================================
# 5. DASHBOARD EXECUTIVO
# ======================================================================
st.header("5. Dashboard executivo")
st.caption(
    "Painéis dinâmicos calculados a partir da planilha histórica "
    "importada e das premissas acima."
)

rev_final = float(proj_df["Receita líquida"].iloc[-1])
if revenue_override > 0:
    cagr = (rev_final / revenue_override) ** (1 / len(years_proj)) - 1
else:
    cagr = float("nan")
margem_liq = proj_df[COL_RES] / proj_df["Receita líquida"]
resultado_acum = float(proj_df[COL_RES].sum())

k1, k2, k3, k4 = st.columns(4)
k1.metric(f"Receita {years_proj[-1]}", f"R$ {br(rev_final, 0)} mi")
k2.metric(
    "Crescimento anual da receita (CAGR)", pct(cagr * 100),
    help=f"De {last_year} (base) até {years_proj[-1]}.",
)
k3.metric("Margem média após IR", pct(float(margem_liq.mean()) * 100))
k4.metric(
    "Resultado acumulado 2026–2030", f"R$ {br(resultado_acum, 0)} mi",
)

st.write("")

# ---- Linha 1: receita e payback
left, right = st.columns([1.15, 1])

with left:
    h = hist[["Ano", "Receita líquida (R$ milhões)"]]
    h = h.set_axis(["Ano", "Receita"], axis=1).assign(Tipo="Histórico")
    p = proj_df[["Ano", "Receita líquida"]]
    p = p.set_axis(["Ano", "Receita"], axis=1).assign(Tipo="Projetado")
    fig = px.bar(
        pd.concat([h, p]), x="Ano", y="Receita", color="Tipo",
        text_auto=",.0f",
        color_discrete_map={"Histórico": AZUL_ESC, "Projetado": AZUL},
    )
    fig.update_traces(textposition="outside")
    fig.update_xaxes(dtick=1)
    st.plotly_chart(
        estilo(fig, "Receita líquida — histórico e projeção (R$ mi)"),
        width="stretch",
    )

with right:
    acum = [-float(investment)] + df_detail[COL_ACUM].tolist()
    anos = ["Inv."] + [str(a) for a in years_proj]
    cores = [VERDE if v >= 0 else CORAL for v in acum]
    fig = go.Figure(go.Bar(
        x=anos, y=acum, marker_color=cores,
        text=[f"{v:,.0f}" for v in acum], textposition="outside",
    ))
    fig.add_hline(y=0, line_color="#93a8cc")
    st.plotly_chart(
        estilo(fig, "Fluxo descontado acumulado — payback (R$ mi)"),
        width="stretch",
    )

# ---- Linha 2: cascata e resultado + margem
left2, right2 = st.columns([1.15, 1])

with left2:
    u = proj_df.iloc[-1]
    fig = go.Figure(go.Waterfall(
        x=[
            "Receita", "Custos e desp. operacionais",
            "Resultado financeiro", "IR", "Resultado após IR",
        ],
        measure=["absolute", "relative", "relative", "relative", "total"],
        y=[
            u["Receita líquida"],
            u["EBIT projetado"] - u["Receita líquida"],
            u["Resultado financeiro"],
            u["IR projetado"],
            0,
        ],
        increasing_marker_color=VERDE,
        decreasing_marker_color=CORAL,
        totals_marker_color=AZUL,
        texttemplate="%{y:,.0f}",
    ))
    st.plotly_chart(
        estilo(fig, f"Da receita ao resultado — {int(u['Ano'])} (R$ mi)"),
        width="stretch",
    )

with right2:
    res = proj_df[COL_RES]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=proj_df["Ano"], y=res, name="Resultado após IR (R$ mi)",
            marker_color=AZUL,
            text=[f"{v:,.0f}" for v in res], textposition="outside",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=proj_df["Ano"], y=margem_liq * 100, name="Margem (%)",
            mode="lines+markers", line=dict(color=VERDE, width=3),
        ),
        secondary_y=True,
    )
    fig.update_xaxes(dtick=1)
    fig.update_yaxes(title_text="R$ mi", secondary_y=False)
    fig.update_yaxes(title_text="Margem (%)", secondary_y=True, showgrid=False)
    st.plotly_chart(
        estilo(fig, "Resultado projetado e margem após IR"),
        width="stretch",
    )
    st.caption(
        "O resultado após IR é a aproximação usada atualmente; "
        "não é fluxo de caixa livre validado."
    )

# ---- Linha 3: sensibilidade
st.divider()
st.subheader("Sensibilidade do VPL")
st.write(
    "Como o VPL muda quando a TMA/WACC e a alíquota de IR variam. "
    "O modelo atual não inclui valor terminal por perpetuidade."
)

pretax_arr = proj_df["Lucro antes do IR"].to_numpy()
waccs = [max(wacc + d, 0.001) for d in (-0.03, -0.02, -0.01, 0, 0.01, 0.02, 0.03)]
taxes = sorted(set([0.25, 0.30, tax_pct / 100.0, 0.40]))


def vpl_calc(w, t):
    flows = pretax_arr - np.maximum(pretax_arr, 0) * t
    desc = sum(f / (1 + w) ** i for i, f in enumerate(flows, 1))
    return -float(investment) + desc


hl, hr = st.columns([1.2, 1])

with hl:
    z = [[vpl_calc(w, t) for t in taxes] for w in waccs]
    fig = go.Figure(go.Heatmap(
        z=z,
        x=[f"{t * 100:.0f}%" for t in taxes],
        y=[f"{w * 100:.1f}%" for w in waccs],
        zmid=0,
        colorscale="RdYlGn",
        text=[[f"{v:,.0f}" for v in r] for r in z],
        texttemplate="%{text}",
        hovertemplate=(
            "WACC %{y} · IR %{x}<br>"
            "VPL R$ %{z:,.0f} mi<extra></extra>"
        ),
    ))
    fig.update_xaxes(title="Alíquota de IR")
    fig.update_yaxes(title="WACC")
    st.plotly_chart(
        estilo(fig, "VPL por WACC × alíquota de IR (R$ mi)", h=420),
        width="stretch",
    )

with hr:
    st.markdown("**VPL e indicador por ação por taxa de desconto**")
    rows = []
    for w in waccs:
        v = sum(cf / ((1 + w) ** t) for t, cf in enumerate(cashflows))
        rows.append({
            "TMA / WACC": pct(w * 100),
            "VPL (R$ mi)": v,
            "Indicador por ação (R$)": (v * 1_000_000) / shares,
        })
    sens_df = pd.DataFrame(rows)
    base_idx = int(np.argmin([abs(w - wacc) for w in waccs]))
    tabela_html(
        sens_df,
        {"VPL (R$ mi)": n2, "Indicador por ação (R$)": n2},
        ["VPL (R$ mi)", "Indicador por ação (R$)"],
        destaque=base_idx,
    )
    st.caption(
        "Linha destacada = WACC-base. Análise de sensibilidade, não "
        "um Football Field completo: comparar FCD, múltiplos "
        "EV/EBITDA, P/L e cotações exige dados específicos."
    )

# ======================================================================
# RODAPÉ — um aviso e um download
# ======================================================================
st.divider()
NOTA = (
    '<div class="dashboard-note"><strong>Nota metodológica:</strong> '
    "a participação de não controladores é preservada na tabela "
    "histórica para conferência e não altera os fluxos do valuation. "
    "O resultado após IR é usado como aproximação do fluxo de caixa. "
    "Antes de interpretar os resultados como valor justo da "
    "Iochpe-Maxion, valide o fluxo de caixa, a dívida líquida, o "
    "número de ações e a metodologia do Excel original do TCC.</div>"
)
st.markdown(NOTA, unsafe_allow_html=True)

export_buffer = BytesIO()
with pd.ExcelWriter(export_buffer, engine="openpyxl") as writer:
    hist.to_excel(writer, sheet_name="Historico importado", index=False)
    proj_df.to_excel(writer, sheet_name="Projecao 2026-2030", index=False)
    av_table.to_excel(writer, sheet_name="Medias AV", index=False)
    df_detail.to_excel(writer, sheet_name="Fluxos e VPL", index=False)

st.write("")
st.download_button(
    label="⬇️ Baixar análise calculada em Excel",
    data=export_buffer.getvalue(),
    file_name="Valuation_Iochpe_Maxion_calculado.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    key="download_valuation_calculado",
)
