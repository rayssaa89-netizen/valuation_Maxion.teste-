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
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Valuation Iochpe-Maxion | TCC", layout="wide")

# ----------------------------------------------------------------------
# Paleta (a mesma do banner) e CSS — o tema base fica em .streamlit/config.toml
# ----------------------------------------------------------------------
AZUL, AZUL_ESC, VERDE, CORAL = "#4A8BEA", "#2F5AA6", "#4FD1A5", "#FF7A66"

st.markdown("""
<style>
.block-container {padding-top: 1.2rem; max-width: 1350px;}
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
div[data-testid="stDataFrame"] {border: 1px solid #223c75; border-radius: 10px; overflow: hidden;}
.stTabs [data-baseweb="tab"] {padding: 10px 22px; font-weight: 600;}
.dashboard-note {
    background: #0f1f45; border-left: 4px solid #4a8bea;
    padding: 12px 16px; border-radius: 6px; color: #dce7fa;
}
</style>
""", unsafe_allow_html=True)


def estilo(fig, titulo=None, h=360):
    """Padroniza todos os gráficos Plotly com a paleta do banner."""
    fig.update_layout(
        title=titulo, height=h, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#EEF3FB"), margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", y=1.12, x=0), hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,.07)")
    return fig


# ----------------------------------------------------------------------
# Banner (altura reduzida de 500 para 300)
# ----------------------------------------------------------------------
arquivo_hero = Path(__file__).parent / "hero_maxion.html"
if arquivo_hero.exists():
    components.html(arquivo_hero.read_text(encoding="utf-8"), height=300, scrolling=False)
else:
    st.warning("Arquivo hero_maxion.html não encontrado.")

st.title("Valuation Iochpe-Maxion — análise dinâmica")
st.caption("Os resultados são recalculados com base no arquivo histórico importado e nas premissas editáveis. Valores financeiros em R$ milhões, salvo indicação contrária.")


# ----------------------------------------------------------------------
# Funções de leitura
# ----------------------------------------------------------------------
def norm(value):
    if pd.isna(value):
        return ""
    value = str(value).strip().lower()
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
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


@st.cache_data(show_spinner="Lendo a planilha histórica...")
def read_historical_data(file_bytes):
    xls = pd.ExcelFile(BytesIO(file_bytes),
