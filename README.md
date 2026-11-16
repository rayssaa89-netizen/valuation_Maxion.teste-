# Valuation Iochpe-Maxion — VPL, TIR e Payback Descontado

Aplicativo Streamlit desenvolvido como produto do Trabalho de Graduação
*“Valuation da Iochpe-Maxion: Estudo de Análise da Viabilidade Econômica por meio de VPL, TIR e PBD”*
(Administração — UNIFATEA, 2026).

## O que o app mostra

1. **Dados históricos** (2016–2025): DRE, balanço e margens, lidos da planilha de dados históricos da Maxion.
   O app já vem com a planilha do trabalho (`data/`) e aceita o envio de uma versão mais recente.
2. **Premissas editáveis**: crescimento da Maxion, PIB, Selic, IPCA, crescimento vegetativo, TMA, IR,
   investimento inicial, quantidade de ações a emitir e médias de análise vertical.
3. **Projeção 2026–2030** da DRE.
4. **Indicadores**: VPL, TIR, payback descontado e VPL ÷ ações.
5. **Dashboards**: receita histórica e projetada, payback, cascata de 2030, resultado e margem após IR.
6. **Sensibilidade do VPL**: mapa de calor WACC × IR e tabela por taxa de desconto.

Com as premissas do trabalho, os resultados são: **VPL R$ 381,50 mi · TIR 32,30% · R$ 16,48 por ação** (TMA 13%).

**Conferência dos dados:** na planilha da Maxion (3T26), a coluna anual de 2025 soma apenas 1T a 3T em
14 contas (a receita soma os 4 trimestres). O app usa a soma 1T + 2T + 3T + 4T e mostra as contas corrigidas.

## Rodar localmente

```bash
pip install -r requirements.txt
streamlit run "app 2.py"
```

## Publicar no Streamlit Community Cloud

Substitua os arquivos do repositório ligado a `valuation-iochpe-maxion2026.streamlit.app` por estes
(`app 2.py`, `valuation/`, `data/`, `requirements.txt`, `.streamlit/`). O app é atualizado automaticamente.

*Resultados acadêmicos, condicionados às premissas. Não constituem recomendação de investimento.*
