from io import BytesIO
import math
import re
import unicodedata

import numpy as np
import numpy_financial as npf
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Valuation Iochpe-Maxion | TCC", layout="wide")
st.title("Valuation Iochpe-Maxion — análise dinâmica")
st.caption("Os resultados são recalculados com base no arquivo histórico importado e nas premissas editáveis. Valores financeiros em R$ milhões, salvo indicação contrária.")


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


def read_historical_data(file_bytes):
    xls = pd.ExcelFile(BytesIO(file_bytes), engine="openpyxl")
    sheet = find_dre_sheet(xls)
    if sheet is None:
        raise ValueError("Não encontrei uma aba de DRE/Income Statement. Use a planilha histórica oficial da Maxion.")
    raw = pd.read_excel(xls, sheet_name=sheet, header=None)
    if raw.shape[0] < 5 or raw.shape[1] < 5:
        raise ValueError("A aba de DRE parece vazia ou tem uma estrutura diferente da esperada.")

    # Na planilha histórica da Maxion, a linha de cabeçalho contém colunas anuais (2016...2025)
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
        raise ValueError("Não consegui identificar os cabeçalhos anuais da DRE. Confira se a planilha está no formato original.")

    years = [y for y in range(2016, 2026) if y in year_cols]
    if not years:
        years = sorted(year_cols)
    label_col = 0
    labels = raw.iloc[:, label_col].map(norm)

    def row_index(contains, exclude=None):
        exclude = exclude or []
        for idx, label in labels.items():
            if label and any(term in label for term in contains) and not any(term in label for term in exclude):
                return idx
        return None

    revenue_idx = row_index(["receita operacional liquida", "net operating revenue"])
    gross_idx = row_index(["lucro (prejuizo) bruto", "gross profit"])
    ebit_idx = row_index(["lucro (prejuizo) operacional (ebit)", "operating income (ebit)"])
    if revenue_idx is None:
        revenue_idx = row_index(["receita liquida", "net revenue"])
    if revenue_idx is None or gross_idx is None:
        raise ValueError("Não encontrei Receita Operacional Líquida e Lucro Bruto na DRE. Não vou calcular usando números fixos.")

    # Linhas da DRE são identificadas pelo nome; valores anuais são lidos do arquivo importado.
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
        rec = {"Ano": year, "Receita líquida (R$ milhões)": float(revenue) / 1000.0}
        for key, idx in indices.items():
            if key == "receita":
                continue
            val = num_at(idx, year) if idx is not None else np.nan
            rec[key] = float(val) / 1000.0 if pd.notna(val) else np.nan
        # CPV é derivado da identidade da DRE: lucro bruto = receita líquida + CPV.
        rec["cpv"] = (float(num_at(indices["lucro_bruto"], year)) - float(revenue)) / 1000.0
        records.append(rec)
    hist = pd.DataFrame(records).sort_values("Ano")
    if hist.empty or hist["Ano"].max() < 2024:
        raise ValueError("A DRE importada não contém dados anuais suficientes (é esperado pelo menos até 2024/2025).")
    return hist, sheet, xls.sheet_names


def br(value, decimals=2):
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "—"
    return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


st.header("1. Importar planilha histórica")
st.write("Selecione a planilha oficial de dados históricos da Maxion (.xlsx ou .xlsm). O aplicativo vai localizar a aba de DRE e usar os valores anuais para formar as médias históricas.")
uploaded_file = st.file_uploader(
    "Escolha o arquivo Excel da Maxion",
    type=["xlsx", "xlsm"],
    accept_multiple_files=False,
    key="historical_workbook_upload",
    help="Clique em Procurar arquivos ou arraste o arquivo para esta área. A planilha não precisa estar na pasta do aplicativo."
)
if uploaded_file is None:
    st.info("Aguardando a planilha histórica. Se clicar na área e a janela não abrir no Safari, atualize a página ou abra o endereço local do Streamlit no Google Chrome; o seletor de arquivos é controlado pelo navegador.")
    st.stop()

try:
    hist, dre_sheet, all_sheets = read_historical_data(uploaded_file.getvalue())
    st.success(f"Arquivo importado: {uploaded_file.name} · DRE identificada na aba '{dre_sheet}' · {len(hist)} anos lidos.")
    with st.expander("Conferir dados históricos importados", expanded=False):
        st.dataframe(hist, width="stretch", hide_index=True)
        st.caption("Os valores monetários foram convertidos de R$ mil para R$ milhões, conforme o cabeçalho da DRE histórica.")
except Exception as exc:
    st.error(f"Não foi possível interpretar esta planilha: {exc}")
    st.stop()

# Ajuste de participação de não controladores:
# A linha "minoritarios" costuma vir negativa na DRE. Como o valuation solicitado
# usa o resultado antes dessa participação, somamos seu valor absoluto ao lucro líquido.
# A coluna original é preservada para conferência.
hist["lucro_liquido_ajustado"] = hist["lucro_liquido"] - hist["minoritarios"]

# Base histórica: receita do último ano disponível e médias AV anuais calculadas do arquivo importado.
last_year = int(hist["Ano"].max())
last_row = hist.loc[hist["Ano"] == last_year].iloc[-1]
revenue_last = float(last_row["Receita líquida (R$ milhões)"])
ratio_keys = ["cpv", "lucro_bruto", "vendas", "admin", "honorarios", "outros", "equivalencia", "receitas_financeiras", "despesas_financeiras", "cambio"]
ratio_labels = {
    "cpv": "CPV", "lucro_bruto": "Lucro bruto", "vendas": "Despesas com vendas",
    "admin": "Despesas gerais e administrativas", "honorarios": "Honorários da administração",
    "outros": "Outras despesas/receitas", "equivalencia": "Equivalência patrimonial",
    "receitas_financeiras": "Receitas financeiras", "despesas_financeiras": "Despesas financeiras",
    "cambio": "Variação cambial líquida"
}
for key in ratio_keys:
    hist[key + "_av"] = hist[key] / hist["Receita líquida (R$ milhões)"]
    hist[key + "_av"] = hist[key + "_av"].replace([np.inf, -np.inf], np.nan)
av_means = {key: float(hist[key + "_av"].mean(skipna=True)) if hist[key + "_av"].notna().any() else 0.0 for key in ratio_keys}

st.header("2. Premissas editáveis")
years_proj = [2026, 2027, 2028, 2029, 2030]
defaults = {
    "Crescimento da Maxion (%)": [4.00, 4.50, 4.20, 4.00, 3.80],
    "Crescimento do PIB (%)": [1.80, 2.00, 2.00, 2.00, 2.00],
    "Efeito da Selic sobre vendas (%)": [-2.00, 2.00, 1.9607843137, 1.9230769231, 1.8867924528],
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
                assumptions[label].append(st.number_input(str(year), value=float(default), step=0.1, format="%.4f", key=f"{label}_{year}") / 100.0)

c1, c2, c3 = st.columns(3)
with c1:
    revenue_override = st.number_input(f"Receita líquida de {last_year} (R$ milhões)", min_value=0.0, value=float(revenue_last), step=100.0, format="%.3f", help="Valor preenchido automaticamente pela DRE importada; pode ser ajustado se necessário.")
    investment = st.number_input("Investimento inicial (R$ milhões)", min_value=0.0, value=722.1, step=10.0, format="%.3f")
with c2:
    wacc_pct = st.number_input("TMA / WACC (%)", min_value=0.0, max_value=100.0, value=13.0, step=0.25, format="%.2f")
    tax_pct = st.number_input("Alíquota de IR projetada (%)", min_value=0.0, max_value=100.0, value=35.0, step=1.0, format="%.2f")
with c3:
    shares = st.number_input("Quantidade de ações (unidades)", min_value=1, value=23143771, step=100000, format="%d")
    st.caption("Preço por ação calculado como VPL ÷ quantidade de ações. Confirme essa convenção com o modelo do TCC.")

# Projeção de receita por premissas e de despesas/margens pelas médias AV anuais do Excel importado.
growth_factors = []
for i in range(5):
    m = assumptions["Crescimento da Maxion (%)"][i]
    pib = assumptions["Crescimento do PIB (%)"][i]
    selic = assumptions["Efeito da Selic sobre vendas (%)"][i]
    ipca = assumptions["Efeito da inflação (IPCA) sobre vendas (%)"][i]
    veg = assumptions["Crescimento vegetativo (%)"][i]
    denominator = (1 + selic) * (1 + ipca)
    growth_factors.append(((1 + m) * (1 + pib) * (1 + veg) / denominator) - 1 if denominator else 0.0)

revenues = []
prev = revenue_override
for growth in growth_factors:
    prev *= 1 + growth
    revenues.append(prev)

projection = []
net_income = []
for i, year in enumerate(years_proj):
    rev = revenues[i]
    values = {key: rev * av_means[key] for key in ratio_keys}
    # Prefer EBIT calculado a partir da margem histórica disponível; fallback à soma das rubricas operacionais.
    ebit_av = (hist["ebit"] / hist["Receita líquida (R$ milhões)"]).replace([np.inf, -np.inf], np.nan).mean(skipna=True) if "ebit" in hist and hist["ebit"].notna().any() else np.nan
    if pd.notna(ebit_av):
        ebit = rev * float(ebit_av)
    else:
        ebit = rev * (av_means["lucro_bruto"] + av_means["vendas"] + av_means["admin"] + av_means["honorarios"] + av_means["outros"] + av_means["equivalencia"])
    financial_result = values["receitas_financeiras"] + values["despesas_financeiras"] + values["cambio"]
    pretax = ebit + financial_result
    tax = -max(pretax, 0.0) * tax_pct / 100.0
    # A participação de não controladores não é projetada nem aplicada como despesa.
    # O fluxo usado no valuation é o resultado após IR, antes dessa participação.
    minorities = 0.0
    net = pretax + tax
    net_income.append(net)
    projection.append({
        "Ano": year, "Crescimento projetado (%)": growth_factors[i] * 100,
        "Receita líquida": rev, "CPV": values["cpv"], "Lucro bruto": values["lucro_bruto"],
        "Despesas com vendas": values["vendas"], "Despesas G&A": values["admin"],
        "Honorários da administração": values["honorarios"], "Outras despesas/receitas": values["outros"],
        "Equivalência patrimonial": values["equivalencia"], "EBIT projetado": ebit,
        "Resultado financeiro": financial_result, "Lucro antes do IR": pretax,
        "IR projetado": tax, "Participação de não controladores considerada no valuation": minorities,
        "Resultado após IR, antes de não controladores": net
    })

st.header("3. Projeção financeira — 2026 a 2030")
st.caption(f"Receita-base e médias AV derivadas da aba '{dre_sheet}' da planilha carregada. Média AV calculada sobre os anos disponíveis de 2016 a {last_year}; altere premissas para recalcular os resultados.")
proj_df = pd.DataFrame(projection)
format_cols = {col: "{:,.2f}" for col in proj_df.columns if col not in ["Ano", "Crescimento projetado (%)"]}
format_cols["Crescimento projetado (%)"] = "{:.2f}%"
st.dataframe(proj_df.style.format(format_cols), width="stretch", hide_index=True)

with st.expander("Médias de análise vertical (AV) utilizadas", expanded=False):
    av_table = pd.DataFrame([{"Conta histórica": ratio_labels[k], "Média AV sobre receita líquida (%)": av_means[k] * 100} for k in ratio_keys])
    st.dataframe(av_table.style.format({"Média AV sobre receita líquida (%)": "{:.2f}%"}), width="stretch", hide_index=True)

st.header("4. Indicadores de viabilidade — recalculados")
wacc = wacc_pct / 100.0
cashflows = [-float(investment)] + [float(x) for x in net_income]
vpl = sum(cf / ((1 + wacc) ** t) for t, cf in enumerate(cashflows))
try:
    irr = npf.irr(cashflows)
    irr_pct = float(irr * 100) if irr is not None and math.isfinite(float(irr)) else None
except Exception:
    irr_pct = None
acc = -float(investment)
pbd = None
detail = []
for i, (year, flow) in enumerate(zip(years_proj, net_income), start=1):
    pv = flow / ((1 + wacc) ** i)
    before = acc
    acc += pv
    detail.append({"Ano": year, "Fluxo usado (após IR, antes de não controladores; R$ mi)": flow, "Valor presente (R$ mi)": pv, "Acumulado descontado (R$ mi)": acc})
    if pbd is None and acc >= 0 and pv > 0:
        pbd = (i - 1) + (-before / pv)
price = (vpl * 1_000_000) / shares
m1, m2, m3, m4 = st.columns(4)
m1.metric("VPL", f"R$ {br(vpl)} mi")
m2.metric("TIR", f"{br(irr_pct)}%" if irr_pct is not None else "Não calculável")
if pbd is None:
    payback_text = "Não recuperado até 2030"
else:
    total_months = max(0, round(pbd * 12))
    payback_text = f"{total_months // 12} ano(s) e {total_months % 12} mês(es)"
m3.metric("Payback descontado", payback_text)
m4.metric("VPL ÷ ações", f"R$ {br(price)}")
st.dataframe(pd.DataFrame(detail).style.format({"Fluxo usado (após IR, antes de não controladores; R$ mi)": "{:,.2f}", "Valor presente (R$ mi)": "{:,.2f}", "Acumulado descontado (R$ mi)": "{:,.2f}"}), width="stretch", hide_index=True)

st.warning('A participação de não controladores é preservada na tabela histórica para conferência, e a coluna "lucro_liquido_ajustado" calcula lucro líquido menos a linha de minoritários (quando negativa, isso equivale a somá-la de volta). Na projeção, a participação não é incluída como rubrica nem altera os fluxos usados no valuation. O resultado após IR ainda é usado como aproximação do fluxo de caixa; confirme a metodologia do Excel original antes de tratar os indicadores como equivalentes.')

export_buffer = BytesIO()
with pd.ExcelWriter(export_buffer, engine="openpyxl") as writer:
    hist.to_excel(writer, sheet_name="Historico importado", index=False)
    proj_df.to_excel(writer, sheet_name="Projecao 2026-2030", index=False)
    av_table.to_excel(writer, sheet_name="Medias AV", index=False)
    pd.DataFrame(detail).to_excel(writer, sheet_name="Fluxos e VPL", index=False)
st.download_button(
    "Baixar análise calculada em Excel",
    data=export_buffer.getvalue(),
    file_name="Valuation_Iochpe_Maxion_calculado.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
