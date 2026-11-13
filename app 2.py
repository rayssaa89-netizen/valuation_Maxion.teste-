from html import escape
from io import BytesIO
import math
import re
import unicodedata

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="AutoValuation | VPL · TIR · Payback", layout="wide")

# ======================================================================
# PALETA E CSS
# ======================================================================
AZUL, AZUL_ESC, VERDE, CORAL = "#4A8BEA", "#2F5AA6", "#4FD1A5", "#FF7A66"

CSS = """
<style>
.stApp {background: #08122b;}
section[data-testid="stSidebar"] {background: #0f1f45;}
.block-container {padding-top: 1.2rem; max-width: 1350px;}
h1, h2, h3 {color: #eef3fb;}
h2 {border-left: 4px solid #4a8bea; padding-left: 12px; margin-top: 1.2rem;}

.hero {
    background: linear-gradient(120deg, #0f2a5e 0%, #1d4a96 55%, #2f78d6 100%);
    border: 1px solid #2f5aa6; border-radius: 16px;
    padding: 26px 32px; margin-bottom: 14px;
    box-shadow: 0 8px 28px rgba(0,0,0,.4);
}
.hero .tag {
    display: inline-block; background: rgba(255,255,255,.14);
    color: #dce7fa !important; font-size: .78rem; font-weight: 600;
    letter-spacing: .08em; text-transform: uppercase;
    padding: 4px 12px; border-radius: 20px; margin-bottom: 10px;
}
.hero h1 {margin: 0 0 6px 0; font-size: 2.3rem; color: #fff !important;}
.hero p {margin: 0; color: #dce7fa !important; font-size: 1.02rem;}

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
div[data-testid="stMetricValue"] > div {
    white-space: normal !important; overflow: visible !important;
    text-overflow: clip !important; font-size: 1.55rem !important;
}
div[data-testid="stDataFrame"] {
    border: 1px solid #223c75; border-radius: 10px; overflow: hidden;
}
.tbl-wrap {
    overflow-x: auto; border: 1px solid #223c75;
    border-radius: 12px; margin: 6px 0 14px 0;
}
table.tbl {width: 100%; border-collapse: collapse; font-size: .88rem; color: #eef3fb;}
table.tbl th {
    background: linear-gradient(180deg, #1d4a96, #163a78);
    color: #fff; font-weight: 600; text-align: right;
    padding: 10px 12px; white-space: nowrap; border-bottom: 2px solid #4a8bea;
}
table.tbl th:first-child, table.tbl td:first-child {text-align: left; position: sticky; left: 0;}
table.tbl td {
    padding: 9px 12px; text-align: right; white-space: nowrap;
    border-bottom: 1px solid #1a2f5e; font-variant-numeric: tabular-nums;
}
table.tbl tbody tr:nth-child(odd) td  {background: #0f1f45;}
table.tbl tbody tr:nth-child(even) td {background: #0b1a3b;}
table.tbl tbody tr:hover td {background: #1a3470;}
table.tbl tbody tr.hl td {background: #1d4a96; font-weight: 700;}

.dashboard-note {
    background: #0f1f45; border-left: 4px solid #4a8bea;
    padding: 12px 16px; border-radius: 6px; color: #dce7fa;
}
.verdict {
    border-radius: 12px; padding: 14px 18px; margin: 8px 0 14px 0;
    font-size: 1.02rem; border: 1px solid;
}
.verdict.ok  {background: rgba(79,209,165,.12); border-color: #4fd1a5;}
.verdict.bad {background: rgba(255,122,102,.12); border-color: #ff7a66;}
.stTabs [data-baseweb="tab"] {font-weight: 600;}

.stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp p, .stApp label,
[data-testid="stMarkdownContainer"],
[data-testid="stWidgetLabel"] p {color: #eef3fb !important;}
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p {color: #93a8cc !important;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def estilo(fig, titulo=None, h=360):
    fig.update_layout(
        title=titulo, height=h, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#EEF3FB"), margin=dict(l=10, r=10, t=55, b=10),
        legend=dict(orientation="h", y=1.14, x=0), hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,.07)")
    return fig


def br(value, decimals=2):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(value):
        return "—"
    txt = f"{value:,.{decimals}f}"
    return txt.replace(",", "X").replace(".", ",").replace("X", ".")


def n2(v):
    return br(v) if pd.notna(v) else "—"


def pct(v):
    return br(v) + "%" if pd.notna(v) else "—"


def tabela_html(df, fmt=None, cor_cols=None, destaque=None, render=True):
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
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )
    if render:
        st.markdown(html, unsafe_allow_html=True)
    return html


# ======================================================================
# DADOS DO EXEMPLO (Iochpe-Maxion, DRE 2016-2025 do TCC, R$ milhões)
# ======================================================================
MAXION_TCC = pd.DataFrame(
    columns=["Ano", "receita", "custo", "despesas_op", "resultado_fin", "ebt", "imposto"],
    data=[
        [2016, 6816.454, -5844.666, -512.54, -324.416, 134.832, -45.702],
        [2017, 7487.94, -6332.962, -666.166, -339.464, 149.348, -69.139],
        [2018, 9616.299, -8298.023, -616.783, -220.819, 480.674, -279.349],
        [2019, 10016.395, -8831.177, -508.963, -169.904, 506.351, -84.936],
        [2020, 8760.568, -8195.255, -750.034, -232.986, -417.707, -2.207],
        [2021, 13688.367, -11984.244, -422.638, -324.617, 956.868, -329.93],
        [2022, 16947.869, -15139.227, -562.958, -617.664, 628.02, -223.848],
        [2023, 14955.22, -13446.975, -757.337, -486.208, 264.7, -158.809],
        [2024, 15331.813, -13510.38, -800.397, -435.573, 585.463, -205.379],
        [2025, 15366.537, -13515.765, -908.858, -578.276, 363.638, -146.504],
    ],
)


MACRO_ROWS = [
    "Crescimento da empresa (%)",
    "Crescimento do PIB (%)",
    "Efeito da Selic sobre vendas (%)",
    "Efeito da inflação (IPCA) sobre vendas (%)",
    "Crescimento vegetativo (%)",
]
MAXION_MACRO = [
    [4.00, 4.50, 4.20, 4.00, 3.80],
    [1.80, 2.00, 2.00, 2.00, 2.00],
    [-2.00, 2.00, 1.9607843137, 1.9230769231, 1.8867924528],
    [4.50, 0, 0, 0, 0],
    [0.36, 0.34, 0.32, 0.31, 0.29],
]


# ======================================================================
# LEITURA FLEXÍVEL DE PLANILHAS
# ======================================================================
def norm(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    value = str(value).strip().lower()
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", value)


def clean_cell(x):
    """Converte textos numéricos (1.234,56 / (1.234) / R$ 10) em número."""
    if not isinstance(x, str):
        return x
    t = x.strip().replace("R$", "").replace(" ", "").replace("%", "")
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    if re.fullmatch(r"-?[\d\.,]+", t) and re.search(r"\d", t):
        if "," in t:
            t = t.replace(".", "").replace(",", ".")
        elif t.count(".") > 1:
            t = t.replace(".", "")
        try:
            v = float(t)
            return -v if neg else v
        except ValueError:
            return x
    return x


def parse_year(v):
    if v is None:
        return None
    if isinstance(v, (int, float, np.integer, np.floating)):
        if pd.notna(v) and float(v).is_integer() and 1990 <= v <= 2100:
            return int(v)
        return None
    m = re.fullmatch(r"\s*((?:19|20)\d{2})\s*[AaEe]?\s*", str(v))
    return int(m.group(1)) if m else None


def detect_header(raw):
    for r in range(min(15, len(raw))):
        found = {}
        for c, v in enumerate(raw.iloc[r].tolist()):
            y = parse_year(v)
            if y is not None and y not in found:
                found[y] = c
        if len(found) >= 3:
            return r, found
    return None, {}


def pick_label_col(raw, header_row, year_cols):
    first = min(year_cols.values())
    best, best_n = 0, -1
    for c in range(min(first, 4)):
        n = raw.iloc[header_row + 1:, c].map(
            lambda x: isinstance(x, str) and x.strip() != ""
        ).sum()
        if n > best_n:
            best, best_n = c, n
    return best


def candidate_rows(raw, label_col, header_row, year_cols):
    rows = []
    cols = list(year_cols.values())
    for i in range(header_row + 1, len(raw)):
        lab = raw.iloc[i, label_col]
        if not isinstance(lab, str) or not lab.strip():
            continue
        vals = pd.to_numeric(raw.iloc[i, cols], errors="coerce")
        if vals.notna().sum() >= 2:
            rows.append((i, lab.strip()))
    return rows


def suggest(rows, kws, multi=False, exclude=()):
    labs = [(i, norm(lab)) for i, lab in rows]
    if multi:
        return [
            i for i, lab in labs
            if any(k in lab for k in kws) and not any(e in lab for e in exclude)
        ]
    for k in kws:
        for i, lab in labs:
            if k in lab and not any(e in lab for e in exclude):
                return i
    return None


KW = {
    "receita": ["receita operacional liquida", "receita liquida", "vendas liquidas",
                "net operating revenue", "net revenue", "receita"],
    "lb": ["lucro (prejuizo) bruto", "lucro bruto", "gross profit"],
    "custo": ["cpv", "custo dos produtos", "custo das vendas", "cost of goods"],
    "desp": ["com vendas", "selling expenses", "gerais e administrativas",
             "general and administrative", "despesas administrativas",
             "despesas comerciais", "despesas gerais", "honorarios",
             "outras despesas/receitas", "equivalencia patrimonial"],
    "fin": ["receitas financeiras", "despesas financeiras", "variacao cambial",
            "financial revenue", "financial expenses", "foreing exchange",
            "foreign exchange", "resultado financeiro"],
    "ebt": ["antes do imp", "antes do ir", "earnings after financial", "lucro antes"],
    "imposto": ["provisao de ir", "imp. de renda / contrib", "imposto de renda",
                "income tax"],
}


def guess_unit(raw, receita_idx, year_cols):
    for r in range(min(10, len(raw))):
        for v in raw.iloc[r].tolist():
            t = norm(v)
            if "r$ mil" in t and "milh" not in t:
                return "R$ mil"
            if "milh" in t:
                return "R$ milhões"
    if receita_idx is not None:
        vals = pd.to_numeric(raw.iloc[receita_idx, list(year_cols.values())],
                             errors="coerce").dropna().abs()
        if len(vals):
            med = float(vals.median())
            if med >= 1e9:
                return "R$ (unidade)"
            if med >= 1e6:
                return "R$ mil"
    return "R$ milhões"


UNIT_DIV = {"R$ (unidade)": 1e6, "R$ mil": 1e3, "R$ milhões": 1.0}


def build_hist(raw, year_cols, m, unit_div, invert):
    def serie(idxs):
        if not idxs:
            return None
        df = pd.DataFrame({
            y: pd.to_numeric(raw.iloc[idxs, c], errors="coerce").values
            for y, c in year_cols.items()
        })
        return df.sum(axis=0, min_count=1) / unit_div

    rec = serie([m["receita"]])
    lb = serie([m["lb"]]) if m["lb"] is not None else None
    custo = serie(m["custo"])
    desp = serie(m["desp"])
    fin = serie(m["fin"])
    ebt = serie([m["ebt"]]) if m["ebt"] is not None else None
    imp = serie([m["imposto"]]) if m["imposto"] is not None else None
    if invert:
        custo = -custo if custo is not None else None
        desp = -desp if desp is not None else None
        imp = -imp if imp is not None else None
        lb = lb  # lucro bruto já é resultado
    if custo is None and lb is not None:
        custo = lb - rec
    if ebt is None:
        if custo is not None and desp is not None and fin is not None:
            ebt = rec + custo + desp + fin
        else:
            raise ValueError(
                "Informe o 'Lucro antes do IR' ou preencha custos, "
                "despesas operacionais e resultado financeiro."
            )
    hist = pd.DataFrame({
        "Ano": rec.index, "receita": rec.values,
        "custo": custo.values if custo is not None else np.nan,
        "despesas_op": desp.values if desp is not None else np.nan,
        "resultado_fin": fin.values if fin is not None else np.nan,
        "ebt": ebt.values,
        "imposto": imp.values if imp is not None else np.nan,
    })
    hist = hist[hist["receita"].notna() & (hist["receita"] != 0) & hist["ebt"].notna()]
    hist = hist.sort_values("Ano").reset_index(drop=True)
    if len(hist) < 3:
        raise ValueError("Preciso de pelo menos 3 anos com receita e resultado.")
    return hist


def load_upload():
    """Importa planilha, detecta anos/contas e deixa o usuário ajustar."""
    up = st.file_uploader(
        "Envie a DRE da empresa (Excel .xlsx/.xlsm ou CSV)",
        type=["xlsx", "xlsm", "csv"], key="upload_dre",
        help="Anos nas colunas e contas nas linhas (formato padrão de DRE).",
    )
    if up is None:
        st.info("Aguardando a planilha. Dica: DREs da B3/CVM, RI das empresas "
                "ou o Status Invest exportados em Excel funcionam.")
        return None
    data = up.getvalue()
    if up.name.lower().endswith(".csv"):
        try:
            raw = pd.read_csv(BytesIO(data), header=None, sep=None,
                              engine="python", encoding="utf-8")
        except Exception:
            raw = pd.read_csv(BytesIO(data), header=None, sep=None,
                              engine="python", encoding="latin-1")
        raw = raw.apply(lambda col: col.map(clean_cell))
        sheets = {"CSV": raw}
    else:
        xls = pd.ExcelFile(BytesIO(data), engine="openpyxl")
        sheets = {s: pd.read_excel(xls, sheet_name=s, header=None)
                  for s in xls.sheet_names}

    def score(name, raw):
        hr, yc = detect_header(raw)
        if not yc:
            return -1
        s = len(yc)
        lc = pick_label_col(raw, hr, yc)
        labs = " | ".join(norm(x) for x in raw.iloc[:, lc].tolist())
        if any(k in labs for k in ("receita", "vendas liquidas", "revenue")):
            s += 50
        if any(k in labs for k in ("lucro liquido", "net income", "antes do imp")):
            s += 40
        if any(k in norm(name) for k in ("dre", "income", "resultado", "demonstra")):
            s += 30
        if "(av)" in norm(name):
            s -= 100
        return s

    names = list(sheets)
    scores = [score(n, sheets[n]) for n in names]
    default_i = int(np.argmax(scores))
    if max(scores) < 0:
        st.error("Não encontrei uma linha de cabeçalho com anos (ex.: 2021, "
                 "2022, 2023). Confira se os anos estão nas colunas.")
        return None
    sheet = st.selectbox("Aba com a DRE", names, index=default_i,
                         key=f"sheet_{up.name}") if len(names) > 1 else names[0]
    raw = sheets[sheet]
    hr, yc = detect_header(raw)
    if not yc:
        st.error("Essa aba não tem cabeçalho de anos. Escolha outra aba.")
        return None
    lc = pick_label_col(raw, hr, yc)
    rows = candidate_rows(raw, lc, hr, yc)
    labmap = {i: lab for i, lab in rows}
    ds_id = f"up_{up.name}_{sheet}"
    st.success(f"Detectei {len(yc)} anos ({min(yc)}–{max(yc)}) e "
               f"{len(rows)} linhas de contas na aba '{sheet}'.")

    sug = {
        "receita": suggest(rows, KW["receita"]),
        "lb": suggest(rows, KW["lb"]),
        "custo": suggest(rows, KW["custo"], multi=True, exclude=("lucro",)),
        "desp": suggest(rows, KW["desp"], multi=True, exclude=("financeir",)),
        "fin": suggest(rows, KW["fin"], multi=True),
        "ebt": suggest(rows, KW["ebt"]),
        "imposto": suggest(rows, KW["imposto"],
                           exclude=("antes", "before", "after financial")),
    }
    opts = [i for i, _ in rows]
    fmt = lambda i: f"{labmap[i]}  (linha {i + 1})"
    fmt1 = lambda i: "— não usar —" if i is None else fmt(i)

    with st.expander("Mapeamento de contas (já sugerido automaticamente — ajuste se precisar)", expanded=True):
        u1, u2 = st.columns(2)
        unit_guess = guess_unit(raw, sug["receita"], yc)
        unit = u1.selectbox("Unidade dos valores", list(UNIT_DIV),
                            index=list(UNIT_DIV).index(unit_guess),
                            key=f"unit_{ds_id}")
        invert = u2.checkbox(
            "Custos, despesas e impostos estão como números positivos",
            key=f"inv_{ds_id}",
            help="Marque se a planilha mostra custos sem sinal negativo.",
        )
        a, b = st.columns(2)
        sel = {}
        with a:
            o1 = [None] + opts
            sel["receita"] = st.selectbox(
                "Receita líquida *", opts,
                index=opts.index(sug["receita"]) if sug["receita"] in opts else 0,
                format_func=fmt, key=f"m_rec_{ds_id}")
            sel["ebt"] = st.selectbox(
                "Lucro antes do IR", o1,
                index=o1.index(sug["ebt"]) if sug["ebt"] in o1 else 0,
                format_func=fmt1, key=f"m_ebt_{ds_id}")
            sel["imposto"] = st.selectbox(
                "Imposto de renda / CSLL (opcional)", o1,
                index=o1.index(sug["imposto"]) if sug["imposto"] in o1 else 0,
                format_func=fmt1, key=f"m_imp_{ds_id}")
            sel["lb"] = st.selectbox(
                "Lucro bruto (opcional)", o1,
                index=o1.index(sug["lb"]) if sug["lb"] in o1 else 0,
                format_func=fmt1, key=f"m_lb_{ds_id}")
        with b:
            sel["custo"] = st.multiselect(
                "Custos (CPV) — opcional", opts, default=sug["custo"],
                format_func=fmt, key=f"m_cpv_{ds_id}")
            sel["desp"] = st.multiselect(
                "Despesas operacionais — opcional", opts, default=sug["desp"],
                format_func=fmt, key=f"m_dsp_{ds_id}")
            sel["fin"] = st.multiselect(
                "Resultado financeiro — opcional", opts, default=sug["fin"],
                format_func=fmt, key=f"m_fin_{ds_id}")
        st.caption("Você pode selecionar várias linhas nos campos de custos, "
                   "despesas e resultado financeiro: o app soma por ano. "
                   "Se o lucro antes do IR não for informado, ele é calculado.")
    try:
        hist = build_hist(raw, yc, sel, UNIT_DIV[unit], invert)
    except Exception as exc:
        st.error(f"Não consegui montar a DRE: {exc}")
        return None
    return hist, ds_id, re.sub(r"\.(xlsx|xlsm|csv)$", "", up.name, flags=re.I)


# ======================================================================
# MOTOR FINANCEIRO
# ======================================================================
def flows_matrix(rev0, g, marg, tax, da_pct, capex_pct):
    """g: (S,H) crescimento; marg: (S,1) margem antes do IR."""
    revs = rev0 * np.cumprod(1 + g, axis=1)
    ebt = revs * marg
    tax_amt = -np.maximum(ebt, 0.0) * tax
    net = ebt + tax_amt
    flow = net + revs * (da_pct - capex_pct) / 100.0
    return revs, ebt, tax_amt, net, flow


def vpl_vec(flow, inv, w, tv_g):
    S, H = flow.shape
    disc = (1 + w) ** np.arange(1, H + 1)
    v = -inv + (flow / disc).sum(axis=1)
    if tv_g is not None and w > tv_g:
        v = v + flow[:, -1] * (1 + tv_g) / (w - tv_g) / (1 + w) ** H
    return v


def irr_calc(cfs):
    def f(r):
        return sum(c / (1 + r) ** t for t, c in enumerate(cfs))
    lo, hi = -0.99, 10.0
    flo, fhi = f(lo), f(hi)
    if not (math.isfinite(flo) and math.isfinite(fhi)) or flo * fhi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = f(mid)
        if flo * fm <= 0:
            hi = mid
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


def payback_calc(flows, inv, rate):
    acc = -inv
    for i, f in enumerate(flows, 1):
        pv = f / (1 + rate) ** i
        before = acc
        acc += pv
        if acc >= 0 and pv > 0:
            return (i - 1) + (-before / pv)
    return None


def payback_txt(p, curto=False):
    if p is None:
        return "Não recupera no horizonte"
    a = int(p)
    resto = (p - a) * 12
    m = int(resto)
    d = int((resto - m) * 30)
    return f"{a}a {m}m {d}d" if curto else f"{a} ano(s), {m} mês(es) e {d} dia(s)"


def wacc_capm(rf, beta, erp, kd, peso_div, ir):
    ke = rf + beta * erp
    return (1 - peso_div) * ke + peso_div * kd * (1 - ir), ke


def interpretar(vpl, irr, pbd, wacc, horizonte, inv):
    out = []
    if vpl >= 0:
        out.append(
            f"O VPL de R$ {br(vpl)} milhões é positivo: descontados a "
            f"{br(wacc * 100)}% ao ano, os fluxos superam o investimento de "
            f"R$ {br(inv)} milhões, o que indica viabilidade econômica."
        )
    else:
        out.append(
            f"O VPL de R$ {br(vpl)} milhões é negativo: descontados a "
            f"{br(wacc * 100)}% ao ano, os fluxos não cobrem o investimento "
            f"de R$ {br(inv)} milhões, o que indica inviabilidade."
        )
    if irr is not None:
        comp = "supera" if irr > wacc else "fica abaixo d"
        comp = "supera" if irr > wacc else "não supera"
        out.append(
            f"A TIR de {br(irr * 100)}% {comp} a taxa mínima de atratividade "
            f"de {br(wacc * 100)}%."
        )
    else:
        out.append("A TIR não pôde ser calculada com esses fluxos.")
    if pbd is None:
        out.append(f"O investimento não é recuperado em {horizonte} anos "
                   "(payback descontado).")
    else:
        out.append(f"O investimento é recuperado, em valores descontados, em "
                   f"{payback_txt(pbd)}.")
    return out


# ======================================================================
# INTERFACE
# ======================================================================
st.markdown(
    '<div class="hero"><span class="tag">TCC · Análise de viabilidade econômica</span>'
    "<h1>AutoValuation</h1>"
    "<p>VPL, TIR e Payback para qualquer empresa: importe a DRE, defina as "
    "premissas e compare cenários, risco e empresas em minutos.</p></div>",
    unsafe_allow_html=True,
)

t_dados, t_prem, t_proj, t_viab, t_risco, t_comp, t_rel = st.tabs([
    "1 · Dados", "2 · Premissas", "3 · Projeção", "4 · Viabilidade",
    "5 · Cenários e risco", "6 · Comparar empresas", "7 · Relatório",
])

# ---------------------------------------------------------------- 1. DADOS
with t_dados:
    st.subheader("Fonte dos dados")
    fonte = st.radio(
        "De onde vêm os dados históricos?",
        ["Exemplo pronto: Iochpe-Maxion (TCC)",
         "Importar a planilha de outra empresa (Excel ou CSV)"],
        horizontal=True, key="fonte",
    )
    if fonte.startswith("Exemplo"):
        ds_id, is_ex, company_default = "ex", True, "Iochpe-Maxion"
        hist_all = MAXION_TCC.copy()
        st.caption(
            "DRE 2016–2025 da Iochpe-Maxion usada no TCC (R$ milhões). Com as "
            "premissas padrão o resultado é o do trabalho: VPL R$ 381,50 mi, "
            "TIR 32,30% e R$ 16,48 por ação."
        )
    else:
        loaded = load_upload()
        if loaded is None:
            st.stop()
        hist_all, ds_id, company_default = loaded
        is_ex = False
    with st.expander("Conferir a DRE histórica padronizada (R$ milhões)"):
        show = hist_all.rename(columns={
            "receita": "Receita líquida", "custo": "Custos (CPV)",
            "despesas_op": "Despesas operacionais",
            "resultado_fin": "Resultado financeiro",
            "ebt": "Lucro antes do IR", "imposto": "IR / CSLL",
        })
        st.dataframe(show, width="stretch", hide_index=True)

# -------------------------------------------------------------- 2. PREMISSAS
with t_prem:
    st.subheader("Empresa e período histórico")
    p1, p2 = st.columns(2)
    company = p1.text_input("Nome da empresa", value=company_default,
                            key=f"nome_{ds_id}")
    anos_hist = [int(a) for a in hist_all["Ano"]]
    lo, hi = p2.select_slider(
        "Período histórico analisado", options=anos_hist,
        value=(anos_hist[0], anos_hist[-1]), key=f"per_{ds_id}",
    )
    hist = hist_all[(hist_all["Ano"] >= lo) & (hist_all["Ano"] <= hi)]
    hist = hist.reset_index(drop=True)
    if len(hist) < 3:
        st.error("Selecione um período com pelo menos 3 anos.")
        st.stop()

    s1, s2 = st.columns(2)
    janela = s1.radio("Anos usados nas médias de margem",
                      ["Todo o período", "Últimos N anos"],
                      horizontal=True, key=f"jan_{ds_id}")
    if janela == "Todo o período":
        n_win = len(hist)
    else:
        n_win = s1.slider("N anos", 2, len(hist), min(5, len(hist)),
                          key=f"nw_{ds_id}_{len(hist)}")
    how = s2.radio("Estatística das margens", ["Média", "Mediana"],
                   horizontal=True, key=f"how_{ds_id}")
    hw = hist.tail(n_win)

    def stat(col):
        if hw[col].notna().sum() == 0:
            return None
        s = (hw[col] / hw["receita"]).replace([np.inf, -np.inf], np.nan)
        return float(s.median() if how == "Mediana" else s.mean())

    av = {k: stat(k) for k in ["custo", "resultado_fin", "ebt", "imposto"]}
    has_custo = av["custo"] is not None
    has_det = (has_custo and av["resultado_fin"] is not None
               and hist["despesas_op"].notna().any())
    pos = hist[hist["ebt"] > 0]
    ef_hist = (float(-pos["imposto"].sum() / pos["ebt"].sum())
               if hist["imposto"].notna().any() and len(pos) and pos["ebt"].sum() > 0
               else None)

    st.subheader("Crescimento da receita")
    H = st.slider("Horizonte da projeção (anos)", 3, 10, 5, key=f"h_{ds_id}")
    anos_proj = [hi + 1 + i for i in range(H)]
    cols_names = [str(a) for a in anos_proj]
    rev_hist = hist["receita"]
    cagr = (rev_hist.iloc[-1] / rev_hist.iloc[0]) ** (1 / (len(hist) - 1)) - 1
    cagr_def = round(float(np.clip(cagr * 100, 0, 8)), 2)
    modos = ["Modelo macro do TCC (empresa, PIB, Selic, IPCA, vegetativo)",
             "Crescimento direto (% ao ano)"]
    modo = st.radio("Como projetar a receita", modos,
                    index=0 if is_ex else 1, horizontal=True,
                    key=f"modo_{ds_id}")
    if modo.startswith("Modelo"):
        def extend(v):
            return (list(v) + [v[-1]] * H)[:H]
        if is_ex:
            vals = [extend(r) for r in MAXION_MACRO]
        else:
            vals = [[cagr_def] * H, [2.0] * H, [0.0] * H, [0.0] * H, [0.0] * H]
        dfm = pd.DataFrame(vals, index=MACRO_ROWS, columns=cols_names)
        ed = st.data_editor(
            dfm, key=f"ed_m_{ds_id}_{H}_{hi}", width="stretch",
            column_config={c: st.column_config.NumberColumn(format="%.4f")
                           for c in cols_names},
        )
        e = ed.fillna(0.0).to_numpy(float) / 100.0
        den = (1 + e[2]) * (1 + e[3])
        den = np.where(den == 0, 1.0, den)
        growths = (1 + e[0]) * (1 + e[1]) * (1 + e[4]) / den - 1
    else:
        dfd = pd.DataFrame([[cagr_def] * H], columns=cols_names,
                           index=["Crescimento da receita (%)"])
        ed = st.data_editor(
            dfd, key=f"ed_d_{ds_id}_{H}_{hi}", width="stretch",
            column_config={c: st.column_config.NumberColumn(format="%.4f")
                           for c in cols_names},
        )
        growths = ed.fillna(0.0).to_numpy(float)[0] / 100.0
    st.caption(
        f"CAGR histórico {lo}–{hi}: {pct(cagr * 100)}. Crescimento projetado "
        "a.a.: " + " · ".join(f"{a}: {pct(g * 100)}" for a, g in zip(anos_proj, growths))
    )

    st.subheader("Projeto e retorno exigido")
    k1, k2, k3 = st.columns(3)
    rev_last = float(hist["receita"].iloc[-1])
    rev0 = k1.number_input(f"Receita-base de {hi} (R$ milhões)", min_value=0.0,
                           value=rev_last, step=100.0, format="%.3f",
                           key=f"rev_{ds_id}_{hi}")
    inv = k1.number_input("Investimento inicial (R$ milhões)", min_value=0.0,
                          value=722.1 if is_ex else round(rev_last * 0.05, 1),
                          step=10.0, format="%.3f", key=f"invest_{ds_id}_{hi}")
    tax = k2.number_input("Alíquota de IR projetada (%)", 0.0, 100.0,
                          35.0 if is_ex else 34.0, 1.0, format="%.2f",
                          key=f"tax_{ds_id}") / 100.0
    if ef_hist is not None:
        k2.caption(f"Alíquota efetiva histórica: {pct(ef_hist * 100)}.")
    metodo_w = k3.radio("Taxa de desconto", ["Informar TMA / WACC",
                                             "Calcular pelo CAPM"],
                        key=f"mw_{ds_id}")
    if metodo_w.startswith("Informar"):
        wacc = k3.number_input("TMA / WACC (%)", 0.0, 100.0, 13.0, 0.25,
                               format="%.2f", key=f"w_{ds_id}") / 100.0
    else:
        c = st.columns(5)
        rf = c[0].number_input("Taxa livre de risco (%)", 0.0, 50.0, 10.0, 0.25, key=f"rf_{ds_id}") / 100
        beta = c[1].number_input("Beta", 0.0, 5.0, 1.10, 0.05, key=f"beta_{ds_id}")
        erp = c[2].number_input("Prêmio de risco (%)", 0.0, 30.0, 6.0, 0.25, key=f"erp_{ds_id}") / 100
        kd = c[3].number_input("Custo da dívida (%)", 0.0, 50.0, 11.0, 0.25, key=f"kd_{ds_id}") / 100
        wd = c[4].number_input("Dívida / capital (%)", 0.0, 100.0, 40.0, 5.0, key=f"wd_{ds_id}") / 100
        wacc, ke = wacc_capm(rf, beta, erp, kd, wd, tax)
        st.caption(f"Custo do capital próprio (CAPM) = {pct(ke * 100)} · "
                   f"WACC resultante = {pct(wacc * 100)}.")

    with st.expander("Avançado: valor terminal, caixa e ações (opcional)"):
        a1, a2, a3 = st.columns(3)
        tv_on = a1.checkbox("Incluir valor terminal (perpetuidade)",
                            key=f"tv_{ds_id}")
        tv_g = a1.number_input("Crescimento na perpetuidade (%)", 0.0, 10.0, 3.0,
                               0.25, key=f"tvg_{ds_id}") / 100.0
        da_pct = a2.number_input("Depreciação e amortização (% da receita)",
                                 0.0, 50.0, 0.0, 0.25, key=f"da_{ds_id}")
        capex_pct = a2.number_input("Investimentos recorrentes / capex (% da receita)",
                                    0.0, 50.0, 0.0, 0.25, key=f"cx_{ds_id}")
        shares = a3.number_input("Quantidade de ações (0 = não usar)", 0,
                                 value=23143771 if is_ex else 0,
                                 step=100000, format="%d", key=f"sh_{ds_id}")
        st.caption("Com D&A e capex em 0% e sem valor terminal, o fluxo é o "
                   "lucro após IR, como no TCC.")
    tvg = tv_g if tv_on else None

    st.subheader("Cenários")
    cenario = st.radio("Cenário ativo", ["Base", "Otimista", "Pessimista"],
                       horizontal=True, key=f"cen_{ds_id}")
    with st.expander("Ajustes dos cenários (p.p. sobre o caso base)"):
        q1, q2 = st.columns(2)
        og = q1.number_input("Otimista: crescimento (p.p. ao ano)", value=1.5, step=0.25, key="og")
        om = q1.number_input("Otimista: margem antes do IR (p.p.)", value=0.5, step=0.25, key="om")
        pg = q2.number_input("Pessimista: crescimento (p.p. ao ano)", value=-1.5, step=0.25, key="pg")
        pm = q2.number_input("Pessimista: margem antes do IR (p.p.)", value=-0.5, step=0.25, key="pm")
    SCEN = {"Base": (0.0, 0.0), "Otimista": (og, om), "Pessimista": (pg, pm)}
    gd_act, md_act = SCEN[cenario]


# ------------------------------------------------------------ CÁLCULOS
def modelo(gd=0.0, md=0.0, tax_r=None):
    g = (np.array(growths, dtype=float) + gd / 100.0)[None, :]
    marg = np.array([[av["ebt"] + md / 100.0]])
    revs, ebt, taxa, net, flow = flows_matrix(
        rev0, g, marg, tax if tax_r is None else tax_r, da_pct, capex_pct)
    return {"g": g[0], "revs": revs[0], "ebt": ebt[0], "tax": taxa[0],
            "net": net[0], "flow": flow[0], "marg": marg[0, 0]}


def indicadores(r, w=None):
    ww = wacc if w is None else w
    cf = [-inv] + [float(x) for x in r["flow"]]
    if tvg is not None and ww > tvg:
        cf[-1] += r["flow"][-1] * (1 + tvg) / (ww - tvg)
    v = float(vpl_vec(r["flow"][None, :], inv, ww, tvg)[0])
    return v, irr_calc(cf), payback_calc(r["flow"], inv, ww)


res = modelo(gd_act, md_act)
vpl, irr_v, pbd = indicadores(res)
pbs = payback_calc(res["flow"], inv, 0.0)
vp_fluxos = vpl + inv
il = vp_fluxos / inv if inv > 0 else None

detail_rows, acc = [], -inv
for i, a in enumerate(anos_proj, 1):
    pv = float(res["flow"][i - 1]) / (1 + wacc) ** i
    acc += pv
    detail_rows.append({"Ano": a, "Fluxo usado (R$ mi)": float(res["flow"][i - 1]),
                        "Valor presente (R$ mi)": pv,
                        "Acumulado descontado (R$ mi)": acc})
df_detail = pd.DataFrame(detail_rows)

proj_rows = []
for i, a in enumerate(anos_proj):
    r_ = float(res["revs"][i])
    row = {"Ano": a, "Crescimento (%)": float(res["g"][i]) * 100,
           "Receita líquida": r_}
    ebt_i = float(res["ebt"][i])
    custo_i = r_ * av["custo"] if has_custo else None
    fin_i = r_ * av["resultado_fin"] if has_det else None
    if has_custo:
        row["Custos (CPV)"] = custo_i
        row["Lucro bruto"] = r_ + custo_i
    if has_det:
        row["Despesas operacionais"] = ebt_i - (r_ + custo_i + fin_i)
        row["Resultado financeiro"] = fin_i
    elif has_custo:
        row["Demais despesas e resultado financeiro"] = ebt_i - (r_ + custo_i)
    row["Lucro antes do IR"] = ebt_i
    row["IR projetado"] = float(res["tax"][i])
    row["Lucro líquido (após IR)"] = float(res["net"][i])
    if da_pct or capex_pct:
        row["Ajuste de caixa (D&A − capex)"] = r_ * (da_pct - capex_pct) / 100.0
    row["Fluxo usado"] = float(res["flow"][i])
    proj_rows.append(row)
proj_df = pd.DataFrame(proj_rows)

# ------------------------------------------------------------- 3. PROJEÇÃO
with t_proj:
    st.subheader(f"Diagnóstico histórico — {lo} a {hi}")
    dh = pd.DataFrame({
        "Ano": hist["Ano"], "Receita líquida": hist["receita"],
        "Crescimento (%)": hist["receita"].pct_change() * 100,
    })
    if has_custo:
        dh["Margem bruta (%)"] = (hist["receita"] + hist["custo"]) / hist["receita"] * 100
    dh["Margem antes do IR (%)"] = hist["ebt"] / hist["receita"] * 100
    if hist["imposto"].notna().any():
        dh["Alíquota efetiva (%)"] = np.where(
            hist["ebt"] > 0, -hist["imposto"] / hist["ebt"] * 100, np.nan)
        dh["Margem líquida (%)"] = (hist["ebt"] + hist["imposto"]) / hist["receita"] * 100
    fmt_h = {c: pct for c in dh.columns if c.endswith("(%)")}
    fmt_h["Receita líquida"] = n2
    fmt_h["Ano"] = lambda v: str(int(v))
    tabela_html(dh, fmt_h)

    st.subheader(f"Projeção financeira — {anos_proj[0]} a {anos_proj[-1]} "
                 f"(cenário {cenario.lower()})")
    fmt_p = {c: n2 for c in proj_df.columns if c not in ("Ano", "Crescimento (%)")}
    fmt_p["Ano"] = lambda v: str(int(v))
    fmt_p["Crescimento (%)"] = pct
    tabela_html(proj_df, fmt_p,
                ["Lucro antes do IR", "IR projetado", "Lucro líquido (após IR)", "Fluxo usado"])
    with st.expander("Médias de análise vertical usadas na projeção"):
        avr = [("Lucro antes do IR", av["ebt"])]
        if has_custo:
            avr.insert(0, ("Custos (CPV)", av["custo"]))
        if has_det:
            avr.insert(1, ("Resultado financeiro", av["resultado_fin"]))
        if av["imposto"] is not None:
            avr.append(("IR / CSLL (histórico)", av["imposto"]))
        tabela_html(pd.DataFrame(
            [{"Conta": k, f"{how} sobre a receita (%)": v * 100} for k, v in avr]),
            {f"{how} sobre a receita (%)": pct})
        st.caption(f"Base: {n_win} ano(s) · {how.lower()}. Despesas "
                   "operacionais são o ajuste que fecha o lucro antes do IR.")

# ----------------------------------------------------------- 4. VIABILIDADE
fig_rev = fig_acc = None
with t_viab:
    ok = vpl >= 0
    msg = ("✅ Projeto <b>economicamente viável</b>" if ok
           else "⚠️ Projeto <b>inviável</b> nas premissas atuais")
    st.markdown(
        f'<div class="verdict {"ok" if ok else "bad"}">{msg} — {escape(company)}'
        f" · cenário {cenario.lower()} · VPL R$ {br(vpl)} mi</div>",
        unsafe_allow_html=True)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("VPL", f"R$ {br(vpl)} mi",
              delta="VPL positivo" if ok else "-VPL negativo")
    if irr_v is not None:
        m2.metric("TIR", f"{br(irr_v * 100)}%",
                  delta=f"{(irr_v - wacc) * 100:+.2f} p.p. vs WACC".replace(".", ","))
    else:
        m2.metric("TIR", "Não calculável")
    m3.metric("Payback descontado", payback_txt(pbd, curto=True),
              help=payback_txt(pbd))
    if shares > 0:
        m4.metric("VPL por ação", f"R$ {br(vpl * 1e6 / shares)}",
                  help="VPL ÷ ações. Não é preço-alvo: não considera dívida líquida.")
    else:
        m4.metric("Índice de lucratividade", br(il) if il is not None else "—",
                  help="Valor presente dos fluxos ÷ investimento inicial.")
    st.caption(
        f"WACC/TMA {pct(wacc * 100)} · payback simples: "
        f"{payback_txt(pbs, curto=True)} · índice de lucratividade: "
        f"{br(il) if il is not None else '—'}"
        + (" · valor terminal incluído" if tvg is not None else ""))
    interp = interpretar(vpl, irr_v, pbd, wacc, H, inv)
    for line in interp:
        st.markdown(f"- {line}")
    tabela_html(df_detail,
                {"Ano": lambda v: str(int(v)),
                 "Fluxo usado (R$ mi)": n2, "Valor presente (R$ mi)": n2,
                 "Acumulado descontado (R$ mi)": n2},
                ["Fluxo usado (R$ mi)", "Valor presente (R$ mi)",
                 "Acumulado descontado (R$ mi)"])

    left, right = st.columns([1.15, 1])
    with left:
        h_ = pd.DataFrame({"Ano": hist["Ano"], "Receita": hist["receita"],
                           "Tipo": "Histórico"})
        p_ = pd.DataFrame({"Ano": proj_df["Ano"], "Receita": proj_df["Receita líquida"],
                           "Tipo": "Projetado"})
        fig_rev = px.bar(pd.concat([h_, p_]), x="Ano", y="Receita", color="Tipo",
                         text_auto=",.0f",
                         color_discrete_map={"Histórico": AZUL_ESC, "Projetado": AZUL})
        fig_rev.update_traces(textposition="outside")
        fig_rev.update_xaxes(dtick=1)
        st.plotly_chart(estilo(fig_rev, "Receita líquida — histórico e projeção (R$ mi)"),
                        width="stretch")
    with right:
        acum = [-inv] + df_detail["Acumulado descontado (R$ mi)"].tolist()
        anos_l = ["Inv."] + [str(a) for a in anos_proj]
        fig_acc = go.Figure(go.Bar(
            x=anos_l, y=acum,
            marker_color=[VERDE if v >= 0 else CORAL for v in acum],
            text=[f"{v:,.0f}" for v in acum], textposition="outside"))
        fig_acc.add_hline(y=0, line_color="#93a8cc")
        st.plotly_chart(estilo(fig_acc, "Fluxo descontado acumulado — payback (R$ mi)"),
                        width="stretch")

# ---------------------------------------------------- 5. CENÁRIOS E RISCO
scen_rows = []
for nome, (gd_, md_) in SCEN.items():
    r_ = modelo(gd_, md_)
    v_, i_, p_ = indicadores(r_)
    scen_rows.append({"Cenário": nome, "Crescimento (p.p.)": gd_,
                      "Margem (p.p.)": md_, "Receita final": float(r_["revs"][-1]),
                      "VPL (R$ mi)": v_,
                      "TIR (%)": i_ * 100 if i_ is not None else np.nan,
                      "Payback (anos)": p_ if p_ is not None else np.nan})
scen_df = pd.DataFrame(scen_rows)

mc_stats = None
with t_risco:
    st.subheader("Comparação de cenários")
    tabela_html(
        scen_df,
        {"Crescimento (p.p.)": n2, "Margem (p.p.)": n2, "Receita final": n2,
         "VPL (R$ mi)": n2, "TIR (%)": pct, "Payback (anos)": n2},
        ["VPL (R$ mi)"],
        destaque=["Base", "Otimista", "Pessimista"].index(cenario))
    fig_sc = go.Figure(go.Bar(
        x=scen_df["Cenário"], y=scen_df["VPL (R$ mi)"],
        marker_color=[VERDE if v >= 0 else CORAL for v in scen_df["VPL (R$ mi)"]],
        text=[f"{v:,.0f}" for v in scen_df["VPL (R$ mi)"]], textposition="outside"))
    fig_sc.add_hline(y=0, line_color="#93a8cc")
    st.plotly_chart(estilo(fig_sc, "VPL por cenário (R$ mi)", h=320), width="stretch")

    st.subheader("Sensibilidade do VPL")
    waccs = [max(wacc + d, 0.001) for d in (-0.03, -0.02, -0.01, 0, 0.01, 0.02, 0.03)]
    taxes = sorted(set([0.25, 0.30, 0.34, 0.40, round(tax, 4)]))
    h1, h2 = st.columns(2)
    with h1:
        z = []
        for w in waccs:
            linha = []
            for t_ in taxes:
                r_ = modelo(gd_act, md_act, tax_r=t_)
                linha.append(float(vpl_vec(r_["flow"][None, :], inv, w, tvg)[0]))
            z.append(linha)
        fig = go.Figure(go.Heatmap(
            z=z, x=[f"{t * 100:.0f}%" for t in taxes],
            y=[f"{w * 100:.1f}%" for w in waccs], zmid=0, colorscale="RdYlGn",
            text=[[f"{v:,.0f}" for v in r] for r in z], texttemplate="%{text}",
            hovertemplate="WACC %{y} · IR %{x}<br>VPL R$ %{z:,.0f} mi<extra></extra>"))
        fig.update_xaxes(title="Alíquota de IR")
        fig.update_yaxes(title="WACC")
        st.plotly_chart(estilo(fig, "VPL: WACC × alíquota de IR (R$ mi)", h=400),
                        width="stretch")
    with h2:
        dgs, dms = [-4, -2, 0, 2, 4], [-1.5, -1.0, -0.5, 0, 0.5, 1.0, 1.5]
        z2 = []
        for dm in dms:
            linha = []
            for dg in dgs:
                r_ = modelo(gd_act + dg, md_act + dm)
                linha.append(float(vpl_vec(r_["flow"][None, :], inv, wacc, tvg)[0]))
            z2.append(linha)
        fig = go.Figure(go.Heatmap(
            z=z2, x=[f"{d:+d} p.p." for d in dgs], y=[f"{m:+.1f} p.p." for m in dms],
            zmid=0, colorscale="RdYlGn",
            text=[[f"{v:,.0f}" for v in r] for r in z2], texttemplate="%{text}",
            hovertemplate="Cresc. %{x} · Margem %{y}<br>VPL R$ %{z:,.0f} mi<extra></extra>"))
        fig.update_xaxes(title="Variação do crescimento anual")
        fig.update_yaxes(title="Variação da margem antes do IR")
        st.plotly_chart(estilo(fig, "VPL: crescimento × margem (R$ mi)", h=400),
                        width="stretch")

    st.subheader("Simulação de Monte Carlo")
    st.write("Sorteia variações de crescimento e margem para estimar a "
             "probabilidade de o projeto ter VPL positivo.")
    mc1, mc2, mc3 = st.columns(3)
    n_sim = mc1.select_slider("Número de simulações", [1000, 2000, 5000, 10000],
                              value=2000, key="n_sim")
    sd_g = mc2.number_input("Desvio-padrão do crescimento (p.p.)", 0.0, 20.0, 2.0, 0.25, key="sd_g")
    sd_m = mc3.number_input("Desvio-padrão da margem (p.p.)", 0.0, 10.0, 0.8, 0.1, key="sd_m")
    rng = np.random.default_rng(42)
    gd_s = rng.normal(0.0, sd_g, n_sim)
    md_s = rng.normal(0.0, sd_m, n_sim)
    g_s = np.array(growths)[None, :] + (gd_act + gd_s)[:, None] / 100.0
    marg_s = (av["ebt"] + (md_act + md_s) / 100.0)[:, None]
    _, _, _, _, flow_s = flows_matrix(rev0, g_s, marg_s, tax, da_pct, capex_pct)
    vpl_s = vpl_vec(flow_s, inv, wacc, tvg)
    mc_stats = {"prob": float((vpl_s > 0).mean()), "media": float(vpl_s.mean()),
                "p5": float(np.percentile(vpl_s, 5)),
                "p95": float(np.percentile(vpl_s, 95))}
    q1_, q2_, q3_, q4_ = st.columns(4)
    q1_.metric("Prob. de VPL > 0", pct(mc_stats["prob"] * 100))
    q2_.metric("VPL médio", f"R$ {br(mc_stats['media'], 0)} mi")
    q3_.metric("Pior caso (P5)", f"R$ {br(mc_stats['p5'], 0)} mi")
    q4_.metric("Melhor caso (P95)", f"R$ {br(mc_stats['p95'], 0)} mi")
    fig = go.Figure(go.Histogram(x=vpl_s, nbinsx=50, marker_color=AZUL))
    fig.add_vline(x=0, line_color=CORAL, line_dash="dash")
    fig.update_xaxes(title="VPL (R$ mi)")
    st.plotly_chart(estilo(fig, "Distribuição do VPL simulado", h=340), width="stretch")

# ----------------------------------------------------- 6. COMPARAR EMPRESAS
with t_comp:
    st.subheader("Comparar empresas")
    st.write("Analise uma empresa, clique em adicionar, troque a planilha na "
             "aba 1 e repita. A tabela abaixo compara todas.")
    st.session_state.setdefault("comparacao", [])
    nome_cmp = st.text_input("Nome na comparação", value=company, key=f"nc_{ds_id}")
    b1, b2 = st.columns([1, 1])
    if b1.button("➕ Adicionar esta análise à comparação"):
        ml = ((hist["ebt"] + hist["imposto"]) / hist["receita"]).mean() \
            if hist["imposto"].notna().any() else np.nan
        st.session_state["comparacao"] = [
            c for c in st.session_state["comparacao"] if c["Empresa"] != nome_cmp
        ] + [{
            "Empresa": nome_cmp, "Cenário": cenario,
            "Horizonte (anos)": H, "CAGR histórico (%)": cagr * 100,
            "Margem antes do IR (%)": av["ebt"] * 100,
            "WACC (%)": wacc * 100, "Investimento (R$ mi)": inv,
            "VPL (R$ mi)": vpl,
            "VPL / investimento": (vpl / inv) if inv > 0 else np.nan,
            "TIR (%)": irr_v * 100 if irr_v is not None else np.nan,
            "Payback (anos)": pbd if pbd is not None else np.nan,
        }]
    if b2.button("Limpar comparação"):
        st.session_state["comparacao"] = []
    comp = pd.DataFrame(st.session_state["comparacao"])
    if comp.empty:
        st.info("Nenhuma empresa adicionada ainda.")
    else:
        fm = {c: n2 for c in comp.columns if c not in ("Empresa", "Cenário", "Horizonte (anos)")}
        fm["Horizonte (anos)"] = lambda v: str(int(v))
        tabela_html(comp, fm, ["VPL (R$ mi)"])
        figc = px.bar(comp, x="Empresa", y="VPL / investimento",
                      text_auto=".2f", color_discrete_sequence=[AZUL])
        st.plotly_chart(estilo(figc, "Criação de valor: VPL ÷ investimento", h=320),
                        width="stretch")
        st.caption("Compare empresas pelo VPL ÷ investimento, que ajusta pelo tamanho do projeto.")

# ---------------------------------------------------------- 7. RELATÓRIO
def build_excel():
    buf = BytesIO()
    prem = pd.DataFrame([
        ["Empresa", company], ["Período histórico", f"{lo}-{hi}"],
        ["Horizonte (anos)", H], ["Cenário", cenario],
        ["Receita-base (R$ mi)", rev0], ["Investimento (R$ mi)", inv],
        ["Alíquota de IR (%)", tax * 100], ["WACC / TMA (%)", wacc * 100],
        ["Valor terminal", "sim" if tvg is not None else "não"],
        ["D&A (% receita)", da_pct], ["Capex (% receita)", capex_pct],
        ["Estatística das margens", f"{how} de {n_win} ano(s)"],
    ], columns=["Premissa", "Valor"])
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        prem.to_excel(w, sheet_name="Premissas", index=False)
        hist.to_excel(w, sheet_name="Historico", index=False)
        proj_df.to_excel(w, sheet_name="Projecao", index=False)
        df_detail.to_excel(w, sheet_name="Fluxos e VPL", index=False)
        scen_df.to_excel(w, sheet_name="Cenarios", index=False)
        if st.session_state.get("comparacao"):
            pd.DataFrame(st.session_state["comparacao"]).to_excel(
                w, sheet_name="Comparacao", index=False)
    return buf.getvalue()


def build_html():
    def tb(df, fmt):
        return tabela_html(df, fmt, render=False)
    fp = {c: n2 for c in proj_df.columns if c not in ("Ano", "Crescimento (%)")}
    fp["Ano"] = lambda v: str(int(v))
    fp["Crescimento (%)"] = pct
    fd = {"Ano": lambda v: str(int(v)), "Fluxo usado (R$ mi)": n2,
          "Valor presente (R$ mi)": n2, "Acumulado descontado (R$ mi)": n2}
    fs = {"Crescimento (p.p.)": n2, "Margem (p.p.)": n2, "Receita final": n2,
          "VPL (R$ mi)": n2, "TIR (%)": pct, "Payback (anos)": n2}
    graficos = ""
    for f_ in (fig_rev, fig_acc):
        if f_ is not None:
            f_.update_layout(template="plotly_white", paper_bgcolor="white",
                             plot_bgcolor="white", font=dict(color="#222"))
            graficos += f_.to_html(full_html=False, include_plotlyjs="cdn")
    mc_txt = ""
    if mc_stats:
        mc_txt = (f"<p>Simulação de Monte Carlo ({n_sim} rodadas): probabilidade de "
                  f"VPL positivo de {br(mc_stats['prob'] * 100)}%; faixa P5–P95 de "
                  f"R$ {br(mc_stats['p5'], 0)} a R$ {br(mc_stats['p95'], 0)} mi.</p>")
    interp_html = "".join(f"<li>{escape(x)}</li>" for x in interp)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Relatório de viabilidade — {escape(company)}</title>
<style>
body{{font-family:Arial,Helvetica,sans-serif;color:#1b2a4a;max-width:980px;margin:30px auto;padding:0 18px}}
h1{{color:#1d4a96}} h2{{border-left:5px solid #4a8bea;padding-left:10px;margin-top:30px}}
table.tbl{{border-collapse:collapse;width:100%;font-size:12px}}
table.tbl th{{background:#1d4a96;color:#fff;padding:6px 8px;text-align:right}}
table.tbl td{{padding:5px 8px;text-align:right;border-bottom:1px solid #d6def0}}
table.tbl th:first-child,table.tbl td:first-child{{text-align:left}}
.kpi{{display:flex;gap:12px;flex-wrap:wrap}} .kpi div{{background:#eef3fb;border-top:3px solid #4a8bea;padding:10px 16px;border-radius:8px}}
.kpi b{{display:block;font-size:20px}}
</style></head><body>
<h1>Relatório de viabilidade econômica — {escape(company)}</h1>
<p>Cenário {escape(cenario.lower())} · histórico {lo}–{hi} · projeção {anos_proj[0]}–{anos_proj[-1]} · valores em R$ milhões.</p>
<div class="kpi"><div>VPL<b>R$ {br(vpl)} mi</b></div>
<div>TIR<b>{br(irr_v * 100) + '%' if irr_v is not None else '—'}</b></div>
<div>Payback descontado<b>{payback_txt(pbd, True)}</b></div>
<div>WACC / TMA<b>{br(wacc * 100)}%</b></div></div>
<h2>Interpretação</h2><ul>{interp_html}</ul>
<h2>Premissas</h2><p>Investimento inicial R$ {br(inv)} mi · alíquota de IR {br(tax * 100)}% · receita-base R$ {br(rev0)} mi · margens: {escape(how.lower())} de {n_win} ano(s).</p>
<h2>Projeção</h2>{tb(proj_df, fp)}
<h2>Fluxos e payback</h2>{tb(df_detail, fd)}
<h2>Cenários</h2>{tb(scen_df, fs)}{mc_txt}
<h2>Gráficos</h2>{graficos}
<p style="margin-top:30px;font-size:12px;color:#556">Resultado após IR usado como aproximação do fluxo de caixa. Valide dívida líquida, número de ações e premissas antes de usar como valor justo.</p>
</body></html>"""


with t_rel:
    st.subheader("Relatório e exportação")
    st.write("Baixe o relatório (abra no navegador e use Imprimir → Salvar como PDF) "
             "ou a planilha completa com premissas, projeção e fluxos.")
    r1, r2 = st.columns(2)
    r1.download_button("📄 Baixar relatório (HTML / PDF)", data=build_html(),
                       file_name=f"Relatorio_{re.sub(r'[^A-Za-z0-9]+', '_', company)}.html",
                       mime="text/html", key="dl_html")
    r2.download_button("⬇️ Baixar análise em Excel", data=build_excel(),
                       file_name=f"Valuation_{re.sub(r'[^A-Za-z0-9]+', '_', company)}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       key="dl_xlsx")
    st.markdown(
        '<div class="dashboard-note"><strong>Nota metodológica:</strong> o fluxo '
        "usado é o lucro após IR (mais D&A e menos capex, se informados). Sem valor "
        "terminal e sem dívida líquida, o VPL é uma medida de viabilidade do projeto, "
        "não o valor justo da empresa. Valide premissas e dados antes de decidir.</div>",
        unsafe_allow_html=True)
