import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import plotly.express as px

# -------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# -------------------------------------------------
st.set_page_config(
    page_title="IGs Bahia – Diagnóstico Territorial",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------------------------------
# COLUNAS ESPERADAS
# -------------------------------------------------
COLUNAS_ESPERADAS = [
    'nome_produto', 'territorio_identidade', 'municipios_abrangidos',
    'tipo_produto', 'modalidade_ig', 'status_diagnostico',
    'singularidade', 'viabilidade_economica', 'atores_chave',
    'geometria_espacial'
]

# -------------------------------------------------
# FUNÇÕES AUXILIARES
# -------------------------------------------------
def macro_tipo(val):
    v = str(val).lower()
    if 'artesanato' in v:
        return 'Artesanato'
    if any(x in v for x in ['bebida', 'vinho', 'cachaça', 'licor', 'destilado']):
        return 'Bebidas'
    if 'agroalimentar' in v or 'derivados' in v:
        return 'Agroalimentar'
    if 'agrícola' in v or 'agricola' in v:
        return 'Agrícola'
    return 'Outros'


def macro_modalidade(val):
    v = str(val).lower()
    if 'denominação de origem' in v:
        return 'DO'
    if 'indicação de procedência' in v or 'ip' in v:
        return 'IP'
    return 'Potencial/Indefinido'


def extrair_coords(val):
    try:
        partes = str(val).split(',')
        if len(partes) == 2:
            return float(partes[0].strip()), float(partes[1].strip())
    except Exception:
        pass
    return None, None


def normalizar_territorio(val):
    return str(val).split('(')[0].split('/')[0].strip()


# -------------------------------------------------
# CARREGAMENTO DE DADOS
# -------------------------------------------------
@st.cache_data
def carregar_dados():
    try:
        df = pd.read_excel("base_de_dados_IGs.xlsx", sheet_name="banco de dados")

        ausentes = [c for c in COLUNAS_ESPERADAS if c not in df.columns]
        if ausentes:
            st.error(f"⚠️ Colunas ausentes no Excel: {ausentes}")
            return pd.DataFrame()

        # Remove linhas de cabeçalho duplicado ou vazias
        df = df[df['nome_produto'].astype(str).str.lower() != 'nome_produto'].copy()
        df = df.dropna(subset=['nome_produto']).copy()

        # Coordenadas a partir de geometria_espacial
        df[['latitude', 'longitude']] = df['geometria_espacial'].apply(
            lambda v: pd.Series(extrair_coords(v))
        )

        # Categorias macro para visualização
        df['macro_tipo'] = df['tipo_produto'].apply(macro_tipo)
        df['macro_modalidade'] = df['modalidade_ig'].apply(macro_modalidade)
        df['territorio_norm'] = df['territorio_identidade'].apply(normalizar_territorio)

        if 'ano' in df.columns:
            df['ano'] = pd.to_numeric(df['ano'], errors='coerce')

        return df

    except FileNotFoundError:
        st.error("❌ Arquivo 'base_de_dados_IGs.xlsx' não encontrado.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ Erro ao carregar os dados: {e}")
        return pd.DataFrame()


@st.cache_data
def carregar_territorios():
    url = (
        "https://raw.githubusercontent.com/"
        "CleitonOERocha/Shapefiles/master/"
        "Shapefiles/Territorios%20de%20Identidade_BA/"
        "Terri_iden_ba_v2.json"
    )
    try:
        gdf = gpd.read_file(url)
        if gdf.empty:
            st.warning("⚠️ GeoDataFrame dos territórios está vazio.")
        return gdf
    except Exception as e:
        st.error(f"❌ Erro ao carregar territórios: {e}")
        return gpd.GeoDataFrame()


df_base = carregar_dados()
territorios_ba = carregar_territorios()

COLUNA_TI = None
if not territorios_ba.empty:
    candidatas = [c for c in territorios_ba.columns
                  if 'NM' in c.upper() or 'NOME' in c.upper() or 'TI' in c.upper()]
    if candidatas:
        COLUNA_TI = candidatas[0]

# -------------------------------------------------
# CSS
# -------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700&family=Inter:wght@400;500&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
.kpi-card {
    background: linear-gradient(135deg, #0d1117 0%, #161B22 100%);
    padding: 22px 18px; border-radius: 14px; text-align: center;
    border-left: 5px solid #F2B705; margin-bottom: 12px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.35);
}
.kpi-title { font-size: 11px; color: #8B949E; letter-spacing: 0.08em;
    text-transform: uppercase; margin-bottom: 6px; }
.kpi-value { font-size: 36px; font-weight: 700; color: #F2B705;
    font-family: 'Sora', sans-serif; line-height: 1; }
.kpi-sub { font-size: 11px; color: #6E7681; margin-top: 4px; }
.section-title { font-family: 'Sora', sans-serif; font-size: 18px;
    font-weight: 600; color: #E6EDF3; margin-bottom: 4px; }
.tag-ip { background:#1a3a5c; color:#58a6ff; border-radius:6px; padding:2px 8px; font-size:11px; font-weight:600; }
.tag-do { background:#2d3b1e; color:#56d364; border-radius:6px; padding:2px 8px; font-size:11px; font-weight:600; }
.tag-pot { background:#3b2a0e; color:#e3b341; border-radius:6px; padding:2px 8px; font-size:11px; font-weight:600; }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# SIDEBAR – FILTROS
# -------------------------------------------------
st.sidebar.markdown("## 🔎 Filtros")

df_filtrado = pd.DataFrame()

if not df_base.empty:
    lista_territorios = sorted(df_base['territorio_identidade'].dropna().unique().tolist())
    territorio_selecionado = st.sidebar.selectbox(
        "Território de Identidade", ["Todos"] + lista_territorios
    )

    lista_macro = sorted(df_base['macro_tipo'].dropna().unique().tolist())
    macro_selecionado = st.sidebar.multiselect(
        "Categoria do Produto", lista_macro, default=lista_macro
    )

    lista_modal = sorted(df_base['macro_modalidade'].dropna().unique().tolist())
    modal_selecionado = st.sidebar.multiselect(
        "Modalidade de IG", lista_modal, default=lista_modal
    )

    ano_range = None
    if 'ano' in df_base.columns and df_base['ano'].notna().any():
        ano_min = int(df_base['ano'].dropna().min())
        ano_max = int(df_base['ano'].dropna().max())
        ano_range = st.sidebar.slider("Ano do Estudo", ano_min, ano_max, (ano_min, ano_max))

    busca = st.sidebar.text_input("🔍 Buscar por nome ou município")

    df_filtrado = df_base.copy()

    if territorio_selecionado != "Todos":
        df_filtrado = df_filtrado[df_filtrado['territorio_identidade'] == territorio_selecionado]
    if macro_selecionado:
        df_filtrado = df_filtrado[df_filtrado['macro_tipo'].isin(macro_selecionado)]
    if modal_selecionado:
        df_filtrado = df_filtrado[df_filtrado['macro_modalidade'].isin(modal_selecionado)]
    if ano_range and 'ano' in df_filtrado.columns:
        df_filtrado = df_filtrado[
            df_filtrado['ano'].isna() |
            ((df_filtrado['ano'] >= ano_range[0]) & (df_filtrado['ano'] <= ano_range[1]))
        ]
    if busca:
        df_filtrado = df_filtrado[
            df_filtrado['nome_produto'].astype(str).str.contains(busca, case=False, na=False) |
            df_filtrado['municipios_abrangidos'].astype(str).str.contains(busca, case=False, na=False)
        ]

    st.sidebar.divider()
    st.sidebar.caption(f"**{len(df_filtrado)}** ativos selecionados de **{len(df_base)}** total")

# -------------------------------------------------
# CABEÇALHO
# -------------------------------------------------
st.markdown("""
<div style='margin-bottom:0.5rem;'>
    <span style='font-family:Sora,sans-serif;font-size:26px;font-weight:700;color:#E6EDF3;'>
        🛡️ Diagnóstico de Indicações Geográficas – Bahia
    </span><br>
    <span style='color:#8B949E;font-size:14px;'>
        Mapeamento de potenciais IGs nos 27 Territórios de Identidade · PROFNIT 2026
    </span>
</div>
""", unsafe_allow_html=True)
st.divider()

# -------------------------------------------------
# KPIs
# -------------------------------------------------
if not df_filtrado.empty:
    total = len(df_filtrado)
    n_territorios = df_filtrado['territorio_identidade'].nunique()
    n_ip = len(df_filtrado[df_filtrado['macro_modalidade'] == 'IP'])
    n_do = len(df_filtrado[df_filtrado['macro_modalidade'] == 'DO'])
    n_pot = len(df_filtrado[df_filtrado['macro_modalidade'] == 'Potencial/Indefinido'])
    pct_ip = round(n_ip / total * 100) if total else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    kpis = [
        ("Ativos Mapeados", total, "potenciais IGs"),
        ("Territórios", n_territorios, "de 27 no estado"),
        ("Indicação de Procedência", n_ip, f"{pct_ip}% do total"),
        ("Denominação de Origem", n_do, "ativos mapeados"),
        ("Potencial a Confirmar", n_pot, "em análise"),
    ]
    for col, (titulo, valor, sub) in zip([c1, c2, c3, c4, c5], kpis):
        with col:
            st.markdown(f"""<div class="kpi-card">
                <div class="kpi-title">{titulo}</div>
                <div class="kpi-value">{valor}</div>
                <div class="kpi-sub">{sub}</div>
            </div>""", unsafe_allow_html=True)
else:
    st.warning("Sem dados para exibir.")

st.divider()

# -------------------------------------------------
# MAPA + GRÁFICOS LATERAIS
# -------------------------------------------------
st.markdown('<div class="section-title">📍 Distribuição Espacial</div>', unsafe_allow_html=True)
st.caption("Territórios em amarelo possuem ativos filtrados. A intensidade indica quantidade. Clique nos pins para detalhes.")

col_mapa, col_graficos = st.columns([3, 2])

with col_mapa:
    mapa = folium.Map(location=[-12.9, -41.0], zoom_start=6, tiles="cartodbpositron")

    territorios_com_dados = (
        set(df_filtrado['territorio_norm'].dropna().values) if not df_filtrado.empty else set()
    )
    contagem_ti = {}
    if not df_filtrado.empty:
        contagem_ti = df_filtrado.groupby('territorio_norm').size().to_dict()

    def estilo_territorio(feature):
        esta_no_filtro = False
        qtd = 0
        if COLUNA_TI and feature.get('properties'):
            nome_raw = feature['properties'].get(COLUNA_TI, '')
            nome_norm = str(nome_raw).split('(')[0].split('/')[0].strip()
            esta_no_filtro = nome_norm in territorios_com_dados
            qtd = contagem_ti.get(nome_norm, 0)
        if esta_no_filtro:
            opacity = min(0.3 + qtd * 0.07, 0.85)
            return {"fillColor": "#F2B705", "color": "#F2B705", "weight": 2, "fillOpacity": opacity}
        return {"fillColor": "#2C7BE5", "color": "#cccccc", "weight": 0.5, "fillOpacity": 0.08}

    if not territorios_ba.empty and COLUNA_TI:
        folium.GeoJson(
            territorios_ba,
            name="Territórios de Identidade",
            style_function=estilo_territorio,
            tooltip=folium.GeoJsonTooltip(fields=[COLUNA_TI], aliases=["Território:"], sticky=True)
        ).add_to(mapa)

    COR_MACRO = {
        'Agroalimentar': 'green', 'Artesanato': 'purple',
        'Bebidas': 'blue', 'Agrícola': 'orange', 'Outros': 'gray'
    }

    if not df_filtrado.empty:
        df_com_coords = df_filtrado[df_filtrado['latitude'].notna() & df_filtrado['longitude'].notna()]
        for _, row in df_com_coords.iterrows():
            try:
                cor = COR_MACRO.get(row.get('macro_tipo', 'Outros'), 'gray')
                sing = str(row.get('singularidade', ''))
                sing_trunc = sing[:180] + '...' if len(sing) > 180 else sing
                popup_html = f"""<div style='font-family:sans-serif;min-width:220px'>
                    <b style='font-size:13px'>{row['nome_produto']}</b><br>
                    <span style='color:#555'>{row['municipios_abrangidos']}</span><br><br>
                    <b>Território:</b> {row['territorio_identidade']}<br>
                    <b>Categoria:</b> {row['macro_tipo']} | <b>Modalidade:</b> {row['macro_modalidade']}<br><br>
                    <i>{sing_trunc}</i></div>"""
                folium.Marker(
                    location=[row['latitude'], row['longitude']],
                    popup=folium.Popup(popup_html, max_width=320),
                    tooltip=f"📌 {row['nome_produto']}",
                    icon=folium.Icon(color=cor, icon='leaf', prefix='glyphicon')
                ).add_to(mapa)
            except Exception:
                continue

    st_folium(mapa, use_container_width=True, height=460)
    st.markdown("""<div style='display:flex;gap:16px;flex-wrap:wrap;margin-top:4px;font-size:12px;color:#8B949E;'>
        <span>🟢 Agroalimentar</span><span>🟣 Artesanato</span>
        <span>🔵 Bebidas</span><span>🟠 Agrícola</span><span>⚫ Outros</span>
    </div>""", unsafe_allow_html=True)

with col_graficos:
    if not df_filtrado.empty:
        # Gráfico 1: Top territórios
        st.markdown("**Ativos por Território (top 10)**")
        top_ti = (
            df_filtrado.groupby('territorio_identidade').size()
            .reset_index(name='Qtd').sort_values('Qtd', ascending=True).tail(10)
        )
        fig_bar = px.bar(top_ti, x='Qtd', y='territorio_identidade', orientation='h',
            color='Qtd', color_continuous_scale=['#1e3a5f', '#F2B705'],
            labels={'territorio_identidade': '', 'Qtd': ''}, template='plotly_dark')
        fig_bar.update_layout(height=240, margin=dict(l=0,r=0,t=5,b=5),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            showlegend=False, coloraxis_showscale=False, font=dict(size=10))
        st.plotly_chart(fig_bar, use_container_width=True)

        # Gráfico 2: Modalidade (rosca)
        st.markdown("**Modalidade de Proteção**")
        modal_counts = df_filtrado['macro_modalidade'].value_counts().reset_index()
        modal_counts.columns = ['Modalidade', 'Qtd']
        fig_pie = px.pie(modal_counts, names='Modalidade', values='Qtd',
            color='Modalidade', hole=0.5, template='plotly_dark',
            color_discrete_map={'IP': '#58a6ff', 'DO': '#56d364', 'Potencial/Indefinido': '#e3b341'})
        fig_pie.update_layout(height=200, margin=dict(l=0,r=0,t=5,b=5),
            paper_bgcolor='rgba(0,0,0,0)', legend=dict(orientation='h', y=-0.15),
            font=dict(size=10))
        st.plotly_chart(fig_pie, use_container_width=True)

st.divider()

# -------------------------------------------------
# GRÁFICOS ANALÍTICOS
# -------------------------------------------------
st.markdown('<div class="section-title">📊 Análise dos Dados</div>', unsafe_allow_html=True)

if not df_filtrado.empty:
    cg1, cg2 = st.columns(2)

    with cg1:
        st.markdown("**Distribuição por Categoria**")
        cat_counts = df_filtrado['macro_tipo'].value_counts().reset_index()
        cat_counts.columns = ['Categoria', 'Qtd']
        fig_cat = px.bar(cat_counts, x='Categoria', y='Qtd', color='Categoria',
            text='Qtd', template='plotly_dark',
            color_discrete_sequence=['#F2B705','#2C7BE5','#28a745','#9c27b0','#6c757d'])
        fig_cat.update_traces(textposition='outside')
        fig_cat.update_layout(height=280, margin=dict(l=0,r=0,t=10,b=5),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            showlegend=False, xaxis_title='', yaxis_title='Quantidade')
        st.plotly_chart(fig_cat, use_container_width=True)

    with cg2:
        if 'ano' in df_filtrado.columns and df_filtrado['ano'].notna().any():
            st.markdown("**Estudos por Ano de Publicação**")
            ano_counts = (df_filtrado.dropna(subset=['ano'])
                .groupby('ano').size().reset_index(name='Qtd').sort_values('ano'))
            ano_counts['ano'] = ano_counts['ano'].astype(int).astype(str)
            fig_ano = px.line(ano_counts, x='ano', y='Qtd', markers=True,
                template='plotly_dark', color_discrete_sequence=['#F2B705'])
            fig_ano.update_traces(line_width=2.5, marker_size=8)
            fig_ano.update_layout(height=280, margin=dict(l=0,r=0,t=10,b=5),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                xaxis_title='Ano', yaxis_title='Estudos')
            st.plotly_chart(fig_ano, use_container_width=True)
        else:
            st.markdown("**Categoria × Modalidade**")
            cross = pd.crosstab(df_filtrado['macro_tipo'], df_filtrado['macro_modalidade'])
            fig_heat = px.imshow(cross, text_auto=True, color_continuous_scale='YlOrBr',
                template='plotly_dark')
            fig_heat.update_layout(height=280, margin=dict(l=0,r=0,t=10,b=5),
                paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_heat, use_container_width=True)

st.divider()

# -------------------------------------------------
# FICHAS DOS ATIVOS (COM PAGINAÇÃO)
# -------------------------------------------------
st.markdown('<div class="section-title">📋 Fichas dos Ativos</div>', unsafe_allow_html=True)

if not df_filtrado.empty:
    total = len(df_filtrado)
    por_pagina = 10
    n_paginas = max(1, -(-total // por_pagina))

    pagina = 1
    if n_paginas > 1:
        pagina = st.number_input(f"Página (1–{n_paginas})", min_value=1,
                                  max_value=n_paginas, value=1, step=1)

    inicio = (pagina - 1) * por_pagina
    df_pagina = df_filtrado.iloc[inicio:inicio + por_pagina]

    for _, row in df_pagina.iterrows():
        modal = row.get('macro_modalidade', '')
        if modal == 'IP':
            tag = '<span class="tag-ip">IP</span>'
        elif modal == 'DO':
            tag = '<span class="tag-do">DO</span>'
        else:
            tag = '<span class="tag-pot">Potencial</span>'

        with st.expander(f"📌 {row['nome_produto']}  —  {row['territorio_identidade']}"):
            cA, cB = st.columns(2)
            with cA:
                st.markdown(f"**Município(s):** {row['municipios_abrangidos']}")
                st.markdown(f"**Tipo:** {row['tipo_produto']}")
                st.markdown(f"**Modalidade:** {tag} {row.get('modalidade_ig', '')}", unsafe_allow_html=True)
                if pd.notna(row.get('ano')):
                    st.markdown(f"**Ano do Estudo:** {int(row['ano'])}")
            with cB:
                sing = str(row.get('singularidade', ''))
                if sing and sing != 'nan':
                    st.markdown(f"**Singularidade:** {sing}")
                atores = str(row.get('atores_chave', ''))
                if atores and atores != 'nan':
                    st.markdown(f"**Atores-chave:** {atores}")

            viab = str(row.get('viabilidade_economica', ''))
            if viab and viab != 'nan':
                st.info(f"💼 **Viabilidade Econômica:** {viab}")

            st.markdown(f"**Status:** `{row.get('status_diagnostico', '')}`")
            link = row.get('link') if 'link' in row.index else None
            if link and pd.notna(link):
                st.markdown(f"🔗 [Acessar Estudo Completo]({link})")

    st.caption(f"Mostrando {inicio+1}–{min(inicio+por_pagina, total)} de {total} ativos")
else:
    st.info("Nenhum ativo encontrado com os filtros selecionados.")

# -------------------------------------------------
# TABELA COMPLETA + DOWNLOAD
# -------------------------------------------------
st.divider()
with st.expander("🗂️ Ver Base de Dados Completa"):
    if not df_filtrado.empty:
        cols_exibir = ['nome_produto', 'territorio_identidade', 'municipios_abrangidos',
                       'macro_tipo', 'macro_modalidade', 'viabilidade_economica', 'status_diagnostico']
        cols_exibir = [c for c in cols_exibir if c in df_filtrado.columns]
        st.dataframe(df_filtrado[cols_exibir], use_container_width=True, hide_index=True)
        st.download_button(
            label="⬇️ Baixar dados filtrados (.csv)",
            data=df_filtrado[cols_exibir].to_csv(index=False).encode('utf-8'),
            file_name="igs_bahia_filtrado.csv",
            mime="text/csv"
        )

# -------------------------------------------------
# RODAPÉ
# -------------------------------------------------
st.divider()
st.markdown(
    "<div style='text-align:center;color:#6E7681;font-size:13px;'>"
    "Projeto acadêmico <b>PROFNIT</b> – Diagnóstico Territorial de Indicações Geográficas | Bahia<br>"
    "Desenvolvido por: <b>Vinícius de Jesus Almeida Lima</b> · 2026"
    "</div>",
    unsafe_allow_html=True
)