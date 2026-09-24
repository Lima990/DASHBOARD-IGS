import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go
import os
from sqlalchemy import create_engine

st.set_page_config(
    page_title="IGs Bahia – Diagnóstico Territorial",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# -------------------------------------------------
# NUMERAÇÃO OFICIAL DOS 27 TIs (conforme SEI)
# -------------------------------------------------
NUMERACAO_TI = {
    'Irecê': 1,
    'Velho Chico': 2,
    'Chapada Diamantina': 3,
    'Sisal': 4,
    'Litoral Sul': 5,
    'Baixo Sul': 6,
    'Extremo Sul': 7,
    'Médio Sudoeste da Bahia': 8,
    'Vale do Jiquiriçá': 9,
    'Sertão do São Francisco': 10,
    'Bacia do Rio Grande': 11,
    'Bacia do Paramirim': 12,
    'Sertão Produtivo': 13,
    'Piemonte do Paraguaçu': 14,
    'Bacia do Jacuípe': 15,
    'Piemonte da Diamantina': 16,
    'Semiárido Nordeste II': 17,
    'Litoral Norte e Agreste Baiano': 18,
    'Portal do Sertão': 19,
    'Sudoeste Baiano': 20,
    'Recôncavo': 21,
    'Médio Rio de Contas': 22,
    'Bacia do Rio Corrente': 23,
    'Itaparica': 24,
    'Piemonte Norte do Itapicuru': 25,
    'Metropolitano de Salvador': 26,
    'Costa do Descobrimento': 27,
}

def formatar_ti(nome):
    """Retorna 'NN - Nome' para exibição."""
    num = NUMERACAO_TI.get(nome)
    if num:
        return f"{num:02d} - {nome}"
    return nome

# -------------------------------------------------
TERRITORIOS_27 = [
    'Irecê','Velho Chico','Chapada Diamantina','Sisal','Litoral Sul','Baixo Sul',
    'Extremo Sul','Médio Sudoeste da Bahia','Vale do Jiquiriçá','Sertão do São Francisco',
    'Bacia do Rio Grande','Bacia do Paramirim','Sertão Produtivo','Piemonte do Paraguaçu',
    'Bacia do Jacuípe','Piemonte da Diamantina','Semiárido Nordeste II',
    'Litoral Norte e Agreste Baiano','Portal do Sertão','Sudoeste Baiano','Recôncavo',
    'Médio Rio de Contas','Bacia do Rio Corrente','Itaparica',
    'Piemonte Norte do Itapicuru','Metropolitano de Salvador','Costa do Descobrimento'
]

COLUNAS_ESPERADAS = [
    'nome_produto','territorio_identidade','municipios_abrangidos','tipo_produto',
    'modalidade_ig','status_diagnostico','singularidade','tradicao_historica',
    'vinculo_territorial','viabilidade_economica','atores_chave','geometria_espacial'
]

# -------------------------------------------------
# FUNÇÕES
# -------------------------------------------------
import re
def macro_tipo(val):
    v = str(val).lower()
    if 'ig registrada' in v: return 'IG Registrada'
    if 'artesanato' in v: return 'Artesanato'
    if any(x in v for x in ['bebida','vinho','cachaça','licor','destilado']): return 'Bebidas'
    if 'agroalimentar' in v or 'derivados' in v: return 'Agroalimentar'
    if 'agrícola' in v or 'agricola' in v: return 'Agrícola'
    if any(x in v for x in ['serviço','servico','turismo']): return 'Serviços'
    return 'Outros'

def macro_modalidade(val):
    v = str(val).lower().strip()
    if 'denominação de origem' in v or v == 'do': return 'DO'
    if 'indicação de procedência' in v or v == 'ip': return 'IP'
    return 'Potencial'

def extrair_coords(val):
    try:
        p = str(val).split(',')
        if len(p) >= 2:
            return float(p[0].strip()), float(p[1].strip())
    except:
        pass
    return None, None

# Mapeamento de correcao para nomes de territorios fora do padrao oficial
CORRECAO_TERRITORIOS = {
    'Baixo Sao Francisco': 'Sertao do Sao Francisco',
    'Baixo São Francisco': 'Sertão do São Francisco',
    'Vale do Jiquiriça': 'Vale do Jiquiriçá',
}

def normalizar_territorios(val):
    """Retorna lista com todos os territorios de uma entrada,
    inclusive multi-territoriais separados por /.
    Aplica correcoes de nomenclatura via CORRECAO_TERRITORIOS."""
    sem_parentese = str(val).split('(')[0]
    # Usa regex para aceitar tanto / quanto ; como separadores
    partes = re.split(r'[;/]', sem_parentese)
    resultado = []
    for p in partes:
        nome = p.strip()
        if nome:
            resultado.append(CORRECAO_TERRITORIOS.get(nome, nome))
    return resultado

def normalizar_territorio(val):
    return normalizar_territorios(val)[0] if normalizar_territorios(val) else str(val)

def normalizar_chave_produto(val):
    """Usa a mesma chave para agrupar e filtrar ativos, sem alterar o nome exibido."""
    return str(val).split('(')[0].strip()

def limpar(val):
    if pd.isna(val): return None
    s = str(val).strip()
    return None if s.lower() in ('nan','','none') else s


def normalizar_estudo_chave(row):
    """Cria a chave de correlação real do estudo: título + link + referência ABNT.
    Essa regra evita contagens duplicadas quando o mesmo estudo aparece em linhas
    com variações de preenchimento ou de origem.
    """
    titulo = limpar(row.get('titulo_trabalho') or row.get('nome_produto'))
    link = limpar(row.get('link'))
    abnt = limpar(row.get('referencia_abnt'))

    partes = [
        (titulo or '').strip().lower(),
        (link or '').strip().lower(),
        (abnt or '').strip().lower(),
    ]
    if not any(partes):
        return None
    return tuple(partes)


def contar_estudos_unicos(df_raw_local, nomes_produto=None):
    """Conta estudos únicos por título+link+ABNT, opcionalmente filtrados por produto."""
    if df_raw_local is None or df_raw_local.empty:
        return 0

    df = df_raw_local.copy()
    if nomes_produto is not None and len(nomes_produto):
        nomes = {normalizar_chave_produto(x) for x in nomes_produto}
        coluna_filtro = ('chave_agrupamento' if 'chave_agrupamento' in df.columns
                         else 'nome_produto')
        df = df[df[coluna_filtro].map(normalizar_chave_produto).isin(nomes)].copy()

    chaves = df['estudo_key'].dropna()
    return int(chaves.nunique()) if not chaves.empty else 0


def exibir_conteudo_ficha(row, show_criteria=True):
    """Exibe o conteúdo detalhado de uma ficha de ativo, com opção de mostrar critérios."""
    modal = row.get('macro_modalidade', '')
    tag = (f'<span class="tag-ip">IP</span>' if modal == 'IP' else
           f'<span class="tag-do">DO</span>' if modal == 'DO' else
           f'<span class="tag-pot">Potencial</span>')
    tis_exibir = normalizar_territorios(row['territorio_identidade'])
    tis_formatados = [formatar_ti(t) if t in NUMERACAO_TI else t for t in tis_exibir]

    i1, i2 = st.columns(2)
    with i1:
        st.markdown(f"**Município(s):** {row['municipios_abrangidos']}")
        st.markdown(f"**Tipo:** {row['tipo_produto']}")
        st.markdown(f"**Modalidade:** {tag} {row.get('modalidade_ig', '')}", unsafe_allow_html=True)
        st.markdown(f"**Status:** `{row.get('status_diagnostico', '')}`")
        if len(tis_exibir) > 1:
            st.markdown(f"**Territórios:** {' · '.join(tis_formatados)}")
    with i2:
        if row.get('atores_chave'):
            st.markdown(f"**Atores-chave:** {row['atores_chave']}")
        if row.get('viabilidade_economica'):
            st.info(f"💼 {row['viabilidade_economica']}")

    if show_criteria:
        st.markdown("---")
        st.markdown("**🔍 Critérios INPI:**")
        cr1, cr2, cr3, cr4 = st.columns(4)
        criterios = [
            ("Singularidade", row.get('singularidade')),
            ("Tradição Histórica", row.get('tradicao_historica')),
            ("Vínculo Territorial", row.get('vinculo_territorial')),
            ("Viab. Econômica", row.get('viabilidade_economica')),
        ]
        for col_crit, (nome_c, val_c) in zip([cr1, cr2, cr3, cr4], criterios):
            with col_crit:
                cls = 'crit-ok' if val_c else 'crit-no'
                ico = '✅' if val_c else '❌'
                st.markdown(f'<div class="{cls}">{ico} <b>{nome_c}</b></div>', unsafe_allow_html=True)
                if val_c:
                    with st.expander("ver"):
                        st.write(val_c)

    estudos = row.get('estudos') or []
    if estudos:
        st.markdown("---")
        with st.expander(f"📚 Ver {len(estudos)} {'estudo' if len(estudos) == 1 else 'estudos'}"):
            for i_e, est in enumerate(estudos, 1):
                ano_s = f" · {est['ano']}" if est.get('ano') else ''
                st.markdown(f"""<div class="estudo-card">
                    <div class="estudo-badge">Estudo {i_e}{ano_s}</div>
                    {"<div style='font-size:12px;color:#8B949E;margin-bottom:3px'><b>Fonte:</b> " + str(est.get('fonte','')) + "</div>" if est.get('fonte') else ""}
                    {"<div class='abnt-box'>" + str(est.get('referencia_abnt','')) + "</div>" if est.get('referencia_abnt') else ""}
                    {"<div style='margin-top:7px'><a href='" + str(est.get('link')) + "' target='_blank' style='color:#58a6ff;font-size:12px;'>🔗 Acessar trabalho completo</a></div>" if est.get('link') else ""}
                </div>""", unsafe_allow_html=True)

# -------------------------------------------------
# CARREGAMENTO
# -------------------------------------------------
@st.cache_resource
def obter_conexao_postgres():
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        try:
            database_url = st.secrets['DATABASE_URL']
        except Exception:
            database_url = None
    if not database_url:
        raise RuntimeError('DATABASE_URL não foi configurada.')
    return create_engine(database_url, pool_pre_ping=True)


def carregar_tabelas_postgres():
    engine = obter_conexao_postgres()
    estudos = pd.read_sql_query(
        'SELECT * FROM estudos_igs ORDER BY id', engine)
    concedidas = pd.read_sql_query(
        'SELECT * FROM igs_concedidas ORDER BY id', engine)
    return estudos, concedidas


def auditar_estudos(df_raw, df_ativos=None):
    """Resumo temporário da planilha para verificar consistência de títulos e n_estudos."""
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(columns=['nome_produto','contagem_por_titulo','soma_n_estudos_por_ativo','diverge'])

    base = df_raw.copy()
    base['nome_produto'] = base['nome_produto'].astype(str).str.strip()
    base = base[base['nome_produto'] != '']

    contagens_titulo = base.groupby('nome_produto').size().rename('contagem_por_titulo')

    if df_ativos is not None and not df_ativos.empty:
        ativos = df_ativos[['nome_produto', 'n_estudos']].copy()
        ativos['nome_produto'] = ativos['nome_produto'].astype(str).str.strip()
        ativos = ativos[ativos['nome_produto'] != '']
        soma_por_ativo = ativos.groupby('nome_produto')['n_estudos'].sum().rename('soma_n_estudos_por_ativo')
        auditoria = pd.concat([contagens_titulo, soma_por_ativo], axis=1).fillna(0).reset_index()
        auditoria = auditoria.rename(columns={'index': 'nome_produto'})
        auditoria['contagem_por_titulo'] = auditoria['contagem_por_titulo'].astype(int)
        auditoria['soma_n_estudos_por_ativo'] = auditoria['soma_n_estudos_por_ativo'].astype(int)
        auditoria['diverge'] = auditoria['contagem_por_titulo'] != auditoria['soma_n_estudos_por_ativo']
        auditoria = auditoria.sort_values(['diverge', 'nome_produto'], ascending=[False, True]).reset_index(drop=True)
        return auditoria

    resumo = contagens_titulo.reset_index().rename(columns={'index': 'nome_produto'})
    resumo['contagem_por_titulo'] = resumo['contagem_por_titulo'].astype(int)
    resumo['soma_n_estudos_por_ativo'] = 0
    resumo['diverge'] = False
    return resumo


@st.cache_data
def carregar_dados():
    try:
        df, df_of = carregar_tabelas_postgres()
        ausentes = [c for c in COLUNAS_ESPERADAS if c not in df.columns]
        if ausentes:
            st.error(f"⚠️ Colunas ausentes: {ausentes}")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        df = df[df['nome_produto'].astype(str).str.lower() != 'nome_produto'].copy()
        df = df.dropna(subset=['nome_produto']).copy()
        df[['latitude','longitude']] = df['geometria_espacial'].apply(
            lambda v: pd.Series(extrair_coords(v)))
        df['macro_tipo']       = df['tipo_produto'].apply(macro_tipo)
        df['macro_modalidade'] = df['modalidade_ig'].apply(macro_modalidade)
        df['territorio_norm']  = df['territorio_identidade'].apply(normalizar_territorio)
        if 'ano' in df.columns:
            df['ano'] = pd.to_numeric(df['ano'], errors='coerce')
        df['estudo_key'] = df.apply(normalizar_estudo_chave, axis=1)

        def agregar(grupo):
            # --- Lógica para criar um nome final descritivo ---
            # Pega o nome do grupo, que é a nossa chave de agrupamento
            nome_final = grupo.name

            # Se o nome do grupo não parece ter uma localidade, constrói um.
            # Heurística: verifica se o nome contém "de", "do", "da".
            if not any(p in nome_final.lower() for p in [' de ', ' do ', ' da ']):
                # Pega a primeira linha do grupo para extrair o município
                primeira_linha = grupo.iloc[0]
                municipios = primeira_linha.get('municipios_abrangidos', '')
                if municipios and isinstance(municipios, str):
                    # Adiciona o primeiro município ao nome para clareza
                    primeiro_municipio = municipios.split(',')[0].strip()
                    # Evita adicionar se já estiver contido (ignorando caso)
                    if primeiro_municipio.lower() not in nome_final.lower():
                        nome_final = f"{nome_final} de {primeiro_municipio}"
            # ----------------------------------------------------

            principal = grupo.copy()
            # --- Cria um score de prioridade para escolher a melhor linha base ---
            # Prioriza linhas com status oficial (Concedida > Em análise)
            def priority_score(row):
                score = row.notna().sum()
                status = str(row.get('status_diagnostico', '')).lower()
                if 'concedid' in status:
                    score += 100 # Prioridade máxima
                elif 'pedido em analise' in status or 'em analise' in status:
                    score += 50  # Prioridade média
                return score

            principal['_p'] = principal.apply(priority_score, axis=1)
            base = principal.sort_values('_p', ascending=False).iloc[0]
            estudos, vistos = [], set()
            for _, row in grupo.iterrows():
                chave = normalizar_estudo_chave(row)
                if chave is None:
                    continue

                if chave in vistos:
                    continue

                vistos.add(chave)

                ref   = limpar(row.get('referencia_abnt'))
                link  = limpar(row.get('link'))
                fonte = limpar(row.get('fonte_dados'))
                ano   = row.get('ano')
                estudos.append({'ano': int(ano) if pd.notna(ano) else None,
                                'fonte': fonte, 'link': link, 'referencia_abnt': ref,
                                'titulo_trabalho': limpar(row.get('titulo_trabalho') or row.get('nome_produto'))})
            return pd.Series({
                'nome_produto':          nome_final, # Usa o nome do grupo ou o nome construído
                'chave_agrupamento':     grupo.name,
                'territorio_identidade': base['territorio_identidade'],
                'territorio_norm':       base['territorio_norm'],
                'municipios_abrangidos': base['municipios_abrangidos'],
                'tipo_produto':          base['tipo_produto'],
                'macro_tipo':            base['macro_tipo'],
                'modalidade_ig':         base['modalidade_ig'],
                'macro_modalidade':      base['macro_modalidade'],
                'singularidade':         limpar(base.get('singularidade')),
                'tradicao_historica':    limpar(base.get('tradicao_historica')),
                'vinculo_territorial':      limpar(base.get('vinculo_territorial')),
                'viabilidade_economica': limpar(base.get('viabilidade_economica')),
                'atores_chave':          limpar(base.get('atores_chave')),
                'status_diagnostico':    limpar(base.get('status_diagnostico')),
                'latitude':              base.get('latitude'),
                'longitude':             base.get('longitude'),
                'ano':                   base.get('ano'),
                'n_estudos':             len(estudos),
                'estudos':               estudos,
            })

        # Cria uma chave de agrupamento mais inteligente
        # Remove parênteses e espaços extras para agrupar variações do mesmo nome
        df['chave_agrupamento'] = df['nome_produto'].map(normalizar_chave_produto)

        df_ag = (df.groupby('chave_agrupamento', sort=False)
                   .apply(agregar).reset_index(drop=True))

        df_of = df_of.dropna(subset=['nome_produto']).copy()
        if 'geometria_espacial' in df_of.columns:
            df_of[['latitude','longitude']] = df_of['geometria_espacial'].apply(
                lambda v: pd.Series(extrair_coords(v)))
        if 'modalidade_ig' in df_of.columns:
            df_of['macro_modalidade'] = df_of['modalidade_ig'].apply(macro_modalidade)
        if 'ano' in df_of.columns:
            df_of['ano'] = pd.to_numeric(df_of['ano'], errors='coerce')

        return df, df_ag, df_of
    except RuntimeError as e:
        st.error(f"❌ Configuração do banco: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    except Exception as e:
        st.error(f"❌ Não foi possível consultar o PostgreSQL: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

@st.cache_data
def carregar_territorios():
    url = ("https://raw.githubusercontent.com/CleitonOERocha/Shapefiles/master/"
           "Shapefiles/Territorios%20de%20Identidade_BA/Terri_iden_ba_v2.json")
    cache_file = "territorios_ba.json"
    try:
        if os.path.exists(cache_file):
            gdf = gpd.read_file(cache_file)
        else:
            gdf = gpd.read_file(url)
            gdf.to_file(cache_file, driver="GeoJSON")
        return gdf
    except Exception as e:
        st.error(f"❌ Territórios: {e}")
        return gpd.GeoDataFrame()

df_raw, df_base, df_oficial = carregar_dados()

if df_raw.empty and df_base.empty and df_oficial.empty:
    st.warning(
        "Nenhuma planilha foi carregada. A base não pôde ser acessada no repositório GitHub oficial."
    )
    st.stop()

territorios_ba = carregar_territorios()

# Calcula IGs oficiais (Concedidas) a partir da aba dedicada
# 'BD_IGs_concedida_analise', que é a fonte de verdade para esse status
igs_oficiais = df_oficial if not df_oficial.empty else pd.DataFrame()
if not igs_oficiais.empty and 'status_diagnostico' in igs_oficiais.columns:
    n_concedidas = len(igs_oficiais[igs_oficiais['status_diagnostico'].str.contains('Concedid', na=False, case=False)])
else:
    n_concedidas = 0

concedidas = pd.DataFrame()
if not igs_oficiais.empty and 'status_diagnostico' in igs_oficiais.columns:
    concedidas = igs_oficiais[igs_oficiais['status_diagnostico'].str.contains('Concedid', na=False, case=False)].copy()
    if 'nome_produto' in concedidas.columns:
        concedidas = concedidas.sort_values('nome_produto').reset_index(drop=True)

def selecionar_coluna_nome_ti(gdf):
    """Escolhe a coluna textual do nome do território, evitando códigos numéricos."""
    if gdf.empty:
        return None

    prioridades = ['NM_TI', 'NOME_TI', 'NOME', 'NM_TERRIT', 'TERRITORIO']
    for col in prioridades:
        if col in gdf.columns:
            return col

    for col in gdf.columns:
        serie = gdf[col].dropna()
        if serie.empty:
            continue
        if serie.map(lambda v: isinstance(v, str) and any(ch.isalpha() for ch in v)).any():
            return col

    return None

COLUNA_TI = None
if not territorios_ba.empty:
    COLUNA_TI = selecionar_coluna_nome_ti(territorios_ba)
    if COLUNA_TI:
        territorios_ba = territorios_ba.copy()
        territorios_ba['tooltip_ti'] = territorios_ba[COLUNA_TI].apply(
            lambda nome: formatar_ti(CORRECAO_TERRITORIOS.get(str(nome).strip(), str(nome).strip()))
        )

# -------------------------------------------------
# COBERTURA TERRITORIAL (multi-território suportado)
# -------------------------------------------------
territorios_cobertos = set()
if not df_base.empty:
    for val in df_base['territorio_identidade'].dropna():
        for t in normalizar_territorios(val):
            if t in TERRITORIOS_27:
                territorios_cobertos.add(t)
territorios_sem = [t for t in TERRITORIOS_27 if t not in territorios_cobertos]

# -------------------------------------------------
# CSS
# -------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700&family=Inter:wght@400;500&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.block-container{padding-top:1rem !important;padding-bottom:1rem !important;
    padding-left:1.5rem !important;padding-right:1.5rem !important;}
.kpi-card{background:linear-gradient(135deg,#0d1117,#161B22);padding:14px 10px !important;
    border-radius:12px;text-align:center;border-left:4px solid #F2B705;
    box-shadow:0 4px 16px rgba(0,0,0,0.3);height:96px !important;max-height:96px !important;
    overflow:hidden !important;display:flex !important;flex-direction:column;
    justify-content:center;box-sizing:border-box !important;}
.kpi-title{font-size:10px;color:#8B949E;letter-spacing:.06em;text-transform:uppercase;
    margin-bottom:4px;line-height:1.3;}
.kpi-value{font-size:28px;font-weight:700;color:#F2B705;font-family:'Sora',sans-serif;line-height:1.1;}
.kpi-sub{font-size:10px;color:#6E7681;margin-top:3px;line-height:1.3;}
.sec-title{font-family:'Sora',sans-serif;font-size:16px;font-weight:600;
    color:#E6EDF3;margin-bottom:2px;margin-top:8px;}
.tag-ip{background:#1a3a5c;color:#58a6ff;border-radius:5px;padding:2px 7px;font-size:11px;font-weight:600;}
.tag-do{background:#2d3b1e;color:#56d364;border-radius:5px;padding:2px 7px;font-size:11px;font-weight:600;}
.tag-pot{background:#3b2a0e;color:#e3b341;border-radius:5px;padding:2px 7px;font-size:11px;font-weight:600;}
.info-box{background:#161B22;border:1px solid #30363d;border-radius:10px;
    padding:12px 14px;font-size:12px;color:#ccc;line-height:1.6;}
.info-box b{color:#F2B705;}
.estudo-card{background:#0d1117;border:1px solid #30363d;border-radius:8px;
    padding:10px 14px;margin-bottom:6px;}
.estudo-badge{display:inline-block;background:#1f2937;color:#F2B705;border-radius:16px;
    padding:1px 9px;font-size:11px;font-weight:600;margin-bottom:5px;}
.abnt-box{background:#0a0e14;border-left:3px solid #30363d;padding:8px 12px;
    font-size:11px;color:#8B949E;font-style:italic;border-radius:0 6px 6px 0;margin-top:4px;}
.crit-ok{background:#0d2318;border:1px solid #2d3b1e;border-radius:8px;padding:8px 10px;
    font-size:11px;color:#56d364;}
.crit-no{background:#161B22;border:1px solid #30363d;border-radius:8px;padding:8px 10px;
    font-size:11px;color:#6E7681;}
.ig-card-ok{background:#0d1117;border:1px solid #2d3b1e;border-radius:10px;
    padding:12px 16px;margin-bottom:8px;border-left:4px solid #56d364;}
.about-box{background:#161B22;border:1px solid #30363d;border-radius:12px;
    padding:20px 24px;font-size:13px;color:#ccc;line-height:1.7;}
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# SIDEBAR (com territórios numerados)
# -------------------------------------------------
with st.sidebar:
    st.markdown("## 🔎 Filtros")
    df_filtrado = pd.DataFrame()

    if not df_base.empty:
        # Lista de territórios para o selectbox: nomes originais + formatação para exibição
        lista_ti_original = sorted(df_base['territorio_identidade'].dropna().unique().tolist())
        # Mapeia nome original -> formato com número (tenta extrair o primeiro território para formatação)
        def get_display_name(orig):
            prim = normalizar_territorios(orig)[0]
            return formatar_ti(prim) if prim in NUMERACAO_TI else orig
        lista_ti_display = [get_display_name(t) for t in lista_ti_original]
        # Cria dicionário para mapear escolha de volta ao original
        display_to_original = {d: o for d, o in zip(lista_ti_display, lista_ti_original)}
        # Adiciona "Todos" no início
        opcoes_display = ["Todos"] + lista_ti_display
        ti_sel_display = st.selectbox("Território de Identidade", opcoes_display)
        if ti_sel_display == "Todos":
            ti_sel = "Todos"
        else:
            ti_sel = display_to_original[ti_sel_display]

        lista_macro = sorted(df_base['macro_tipo'].dropna().unique().tolist())
        macro_sel   = st.multiselect("Categoria", lista_macro, default=lista_macro)

        lista_modal = sorted(df_base['macro_modalidade'].dropna().unique().tolist())
        modal_sel   = st.multiselect("Modalidade", lista_modal, default=lista_modal)

        max_est = int(df_base['n_estudos'].max()) if not df_base.empty else 1
        min_est = st.slider("Nº mínimo de estudos (0 = todos)", 0, max_est, 0) if max_est > 0 else 0

        busca = st.text_input("🔍 Buscar por nome ou município")

        df_filtrado = df_base.copy()
        if ti_sel != "Todos":
            df_filtrado = df_filtrado[df_filtrado['territorio_identidade'] == ti_sel]
        if macro_sel:
            df_filtrado = df_filtrado[df_filtrado['macro_tipo'].isin(macro_sel)]
        if modal_sel:
            df_filtrado = df_filtrado[df_filtrado['macro_modalidade'].isin(modal_sel)]
        if min_est > 0:
            df_filtrado = df_filtrado[df_filtrado['n_estudos'] >= min_est]
        if busca:
            df_filtrado = df_filtrado[
                df_filtrado['nome_produto'].astype(str).str.contains(busca,case=False,na=False) |
                df_filtrado['municipios_abrangidos'].astype(str).str.contains(busca,case=False,na=False)]

        st.divider()
        t_est = contar_estudos_unicos(df_raw, df_filtrado['chave_agrupamento'].dropna().unique()) if not df_filtrado.empty else 0
        st.caption(f"**{len(df_filtrado)}** ativos · **{t_est}** estudos")

        if st.button("🗑️ Limpar filtros"):
            st.session_state.clear()
            st.rerun()

# -------------------------------------------------
# CABEÇALHO
# -------------------------------------------------
st.markdown("""
<div style='margin-bottom:4px;'>
  <span style='font-family:Sora,sans-serif;font-size:22px;font-weight:700;color:#E6EDF3;'>
    🛡️ Diagnóstico de Indicações Geográficas – Bahia
  </span><br>
  <span style='color:#8B949E;font-size:12px;'>
    Mapeamento de potenciais IGs nos 27 Territórios de Identidade &nbsp;·&nbsp; PROFNIT / UFRB 2026
  </span>
</div>
""", unsafe_allow_html=True)
st.divider()

# -------------------------------------------------
# KPIs
# -------------------------------------------------
# --- Calcula os totais usando a contagem real de estudos trabalhados ---
# A soma por produto inflava o número porque os mesmos estudos aparecem em
# múltiplas linhas do mesmo ativo e/ou em variações de preenchimento.
total_estudos = contar_estudos_unicos(df_raw) if not df_raw.empty else 0
n_multi_estudos = len(df_base[df_base['n_estudos'] > 1]) if not df_base.empty else 0
n_ti_coberto = len(territorios_cobertos)
cobertura_pct = round(n_ti_coberto / 27 * 100)

# --- Separa os ativos por status ---
# Alguns produtos já oficializados (Concedida/Em análise) também aparecem na
# base principal com esse status descrito em texto — são excluídos aqui dos
# "potenciais" para não contar o mesmo ativo duas vezes.
if not df_base.empty:
    mask_ja_oficial_no_base = df_base['status_diagnostico'].str.contains(
        r'Concedid|em\s+an[aá]lise', na=False, case=False, regex=True)
    df_potenciais = df_base[~mask_ja_oficial_no_base]
else:
    df_potenciais = pd.DataFrame()
n_potenciais = len(df_potenciais)

# --- Detalha os potenciais por vocação ---
n_ip_pot = len(df_potenciais[df_potenciais['macro_modalidade'] == 'IP']) if not df_potenciais.empty else 0
n_do_pot = len(df_potenciais[df_potenciais['macro_modalidade'] == 'DO']) if not df_potenciais.empty else 0

# Potenciais cujo diagnóstico menciona notoriedade (reconhecimento/qualidade
# já perceptíveis, requisito relevante para IP/DO)
n_notoriedade = (len(df_potenciais[df_potenciais['status_diagnostico'].str.contains(
    'notoriedade', na=False, case=False)]) if not df_potenciais.empty else 0)
pct_notoriedade = round(n_notoriedade / n_potenciais * 100) if n_potenciais > 0 else 0

# --- Top 3 ativos (IGs) com mais estudos referenciados ---
top3_estudos = (df_base.nlargest(3, 'n_estudos')[['nome_produto', 'n_estudos']].values.tolist()
                if not df_base.empty else [])

# --- Exibição dos KPIs ---
st.markdown("##### Panorama Geral do Mapeamento")
k1, k2, k3, k4 = st.columns(4)
kpis_row1 = [
    (k1, "Potenciais Identificados", n_potenciais, "mapeados neste TCC"),
    (k2, "Potenciais com Notoriedade", n_notoriedade, f"{pct_notoriedade}% dos potenciais"),
    (k3, "Estudos Únicos Trabalhados", total_estudos, f"{n_multi_estudos} ativos com múltiplos estudos"),
    (k4, "Cobertura Territorial", f"{n_ti_coberto}/27", f"{cobertura_pct}% dos territórios"),
]
for col, titulo, valor, sub in kpis_row1:
    with col:
        st.markdown(f"""<div class="kpi-card">
            <div class="kpi-title">{titulo}</div>
            <div class="kpi-value">{valor}</div>
            <div class="kpi-sub">{sub}</div>
        </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

k5, k6, k7, k8 = st.columns(4)
pct_ip_pot = round(n_ip_pot / n_potenciais * 100) if n_potenciais > 0 else 0
pct_do_pot = round(n_do_pot / n_potenciais * 100) if n_potenciais > 0 else 0
for col, titulo, valor, sub in [
    (k5, "Potenciais para IP", n_ip_pot, f"{pct_ip_pot}% dos potenciais"),
    (k6, "Potenciais para DO", n_do_pot, f"{pct_do_pot}% dos potenciais"),
    (k7, "IGs Concedidas", n_concedidas, "registradas no INPI"),
]:
    with col:
        st.markdown(f"""<div class="kpi-card">
            <div class="kpi-title">{titulo}</div>
            <div class="kpi-value">{valor}</div>
            <div class="kpi-sub">{sub}</div>
        </div>""", unsafe_allow_html=True)

with k8:
    linhas_top3 = ""
    for i, (nome, qtd) in enumerate(top3_estudos, start=1):
        nome_curto = nome if len(nome) <= 20 else nome[:18] + "…"
        linhas_top3 += (f"<div style='display:flex;justify-content:space-between;gap:10px;"
                         f"align-items:center;font-size:10px;margin-top:2px;line-height:1.2;' title='{nome}'>"
                 f"<span style='color:#ccc;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'>{i}º · {nome_curto}</span>"
                         f"<span style='color:#F2B705;font-weight:600;flex-shrink:0;white-space:nowrap;'>· {int(qtd)} estudos</span></div>")
    if not linhas_top3:
        linhas_top3 = "<div style='font-size:10px;color:#6E7681;margin-top:2px;'>Sem dados</div>"
    st.markdown(f"""<div class="kpi-card" style="text-align:left;">
        <div class="kpi-title" style="text-align:center;margin-bottom:0;font-size:9.5px;">Top 3 IGs com Mais Estudos</div>
        {linhas_top3}
    </div>""", unsafe_allow_html=True)

st.divider()

# -------------------------------------------------
# ABAS
# -------------------------------------------------
aba1, aba2, aba3, aba4, aba5 = st.tabs([
    "🗺️ Mapa Territorial",
    "📊 Análise",
    "📋 Fichas dos Ativos",
    "🏅 IGs Registradas",
    "ℹ️ Sobre o Projeto"
])

# =================================================
# ABA 1 – MAPA
# =================================================
with aba1:
    st.markdown('<div class="sec-title">📍 Distribuição Espacial dos Ativos</div>',
                unsafe_allow_html=True)
    st.caption("🟡 Territórios com ativos filtrados (intensidade = quantidade)")

    mapa = folium.Map(
        location=[-12.5, -41.5],
        zoom_start=6,
        tiles="OpenStreetMap",
        attr="© OpenStreetMap contributors"
    )

    # Conjunto de territórios cobertos (nomes originais) para destacar
    ti_com = set()
    cont_ti = {}
    if not df_filtrado.empty:
        for _, row in df_filtrado.iterrows():
            tis = normalizar_territorios(row['territorio_identidade'])
            for t in tis:
                ti_com.add(t)
                cont_ti[t] = cont_ti.get(t, 0) + 1

    def estilo_ti(feat):
        esta, qtd = False, 0
        if COLUNA_TI and feat.get('properties'):
            nm = str(feat['properties'].get(COLUNA_TI,'')).split('(')[0].split('/')[0].strip()
            tis_nm = normalizar_territorios(nm)
            for t in tis_nm:
                if t in ti_com:
                    esta = True
                    qtd  = max(qtd, cont_ti.get(t, 0))
        if esta:
            return {"fillColor":"#F2B705","color":"#F2B705","weight":2,
                    "fillOpacity":min(0.25+qtd*0.08,0.85)}
        return {"fillColor":"#2C7BE5","color":"#cccccc","weight":0.5,"fillOpacity":0.07}

    if not territorios_ba.empty and COLUNA_TI:
        folium.GeoJson(territorios_ba, style_function=estilo_ti,
            tooltip=folium.GeoJsonTooltip(
                fields=['tooltip_ti'], aliases=["Território:"], sticky=True)
        ).add_to(mapa)

    COR = {'Agroalimentar':'green','Artesanato':'purple','Bebidas':'blue',
           'Agrícola':'orange','Serviços':'pink','Outros':'gray', 'IG Registrada': 'darkgreen'}

    if not df_filtrado.empty:
        for _, row in df_filtrado[df_filtrado['latitude'].notna() &
                                  df_filtrado['longitude'].notna()].iterrows():
            try:
                # Lógica para IGs Registradas (concedidas no INPI)
                if row['macro_tipo'] == 'IG Registrada':
                    tooltip_ig = f"⭐ {row['nome_produto']}"
                    popup_ig = f"""<div style='font-family:sans-serif;min-width:210px'>
                        <b>{tooltip_ig}</b><br>
                        <b style='color:#28a745'>{row['status_diagnostico']}</b><br>
                        Modalidade: <b>{row['macro_modalidade']}</b><br>
                        {('Concedida em: <b>'+str(row['ano'])+'</b>') if pd.notna(row.get('ano')) else ''}
                    </div>"""
                    folium.Marker(location=[row['latitude'], row['longitude']],
                                  popup=folium.Popup(popup_ig, max_width=260),
                                  tooltip=tooltip_ig,
                                  icon=folium.Icon(color='darkgreen', icon='star', prefix='glyphicon')
                    ).add_to(mapa)
                # Lógica para Potenciais IGs (da planilha)
                else:
                    n = int(row.get('n_estudos', 1))
                    cor = 'red' if n >= 3 else ('orange' if n == 2 else COR.get(row['macro_tipo'], 'gray'))
                    popup = f"""<div style='font-family:sans-serif;min-width:240px;max-width:320px'>
                        <b style='font-size:13px;color:#333'>{row['nome_produto']}</b><br>
                        <span style='color:#777;font-size:11px'>📍 {row['municipios_abrangidos']}</span><br>
                        <hr style='margin:6px 0;border-color:#eee'>
                        <b>Modalidade:</b> {row['macro_modalidade']} &nbsp; <b>Categoria:</b> {row['macro_tipo']}<br>
                    </div>"""
                    folium.Marker(location=[row['latitude'], row['longitude']],
                                  popup=folium.Popup(popup, max_width=340),
                                  tooltip=f"📌 {row['nome_produto']} · {row['macro_tipo']} · {n} {'estudos' if n > 1 else 'estudo'}",
                                  icon=folium.Icon(color=cor, icon='leaf', prefix='glyphicon')
                    ).add_to(mapa)
            except: continue

    st_folium(mapa, use_container_width=True, height=560)

    def _bolinha(cor):
        return (f"<span style='display:inline-block;width:10px;height:10px;border-radius:50%;"
                f"background:{cor};margin-right:4px;'></span>")

    st.markdown(f"""<div style='display:flex;gap:20px;flex-wrap:wrap;padding:8px 0;
        font-size:12px;color:#8B949E;border-top:1px solid #30363d;margin-top:4px;align-items:center;'>
        <span>{_bolinha('#28a745')}Agroalimentar</span>
        <span>{_bolinha('#9c27b0')}Artesanato</span>
        <span>{_bolinha('#2C7BE5')}Bebidas</span>
        <span>{_bolinha('#F2B705')}Agrícola</span>
        <span>{_bolinha('#e83e8c')}Serviços</span>
        <span>{_bolinha('#dc3545')}Alta notoriedade (3+ estudos)</span>
    </div>""", unsafe_allow_html=True)

    st.divider()

    if not df_filtrado.empty:
        gc2, gc3 = st.columns(2)
        with gc2:
            st.markdown("**Distribuição por Categoria**")
            cc = df_filtrado['macro_tipo'].value_counts().reset_index()
            cc.columns = ['Cat','Qtd']
            fig_c = px.pie(cc, names='Cat', values='Qtd', hole=0.45,
                color='Cat', template='plotly_dark',
                color_discrete_map={'Agroalimentar':'#28a745','Artesanato':'#9c27b0',
                    'Bebidas':'#2C7BE5','Agrícola':'#F2B705','Serviços':'#e83e8c','Outros':'#6c757d'})
            fig_c.update_layout(height=300, margin=dict(l=0,r=0,t=5,b=0),
                paper_bgcolor='rgba(0,0,0,0)',
                legend=dict(orientation='h',y=-0.1,font=dict(size=10)))
            st.plotly_chart(fig_c, use_container_width=True)

        with gc3:
            st.markdown("**Modalidade de Proteção**")
            mc = df_filtrado['macro_modalidade'].value_counts().reset_index()
            mc.columns = ['Modalidade','Qtd']
            total_mc = mc['Qtd'].sum()
            mc['texto'] = mc.apply(lambda r: f"{r['Qtd']} ({round(r['Qtd']/total_mc*100)}%)", axis=1)
            fig_m = px.bar(mc, x='Modalidade', y='Qtd', color='Modalidade',
                text='texto', template='plotly_dark',
                color_discrete_map={'IP':'#58a6ff','DO':'#56d364','Potencial':'#e3b341'})
            fig_m.update_traces(textposition='outside')
            fig_m.update_layout(height=300, margin=dict(l=0,r=0,t=5,b=0),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                showlegend=False, xaxis_title='', yaxis_title='Qtd', font=dict(size=11))
            st.plotly_chart(fig_m, use_container_width=True)

# =================================================
# ABA 2 – ANÁLISE
# =================================================
with aba2:
    st.markdown('<div class="sec-title">📊 Análise dos Dados</div>', unsafe_allow_html=True)
    st.divider()

    if not df_filtrado.empty:
        st.markdown("**Notoriedade — top 15 ativos por nº de estudos**")
        top_n = (df_filtrado.nlargest(15,'n_estudos')
                 [['nome_produto','n_estudos','macro_tipo']]
                 .sort_values('n_estudos',ascending=False))
        top_n['label'] = top_n['nome_produto'].apply(lambda x: x[:38]+'…' if len(x)>38 else x)
        fig_n = px.bar(top_n, x='n_estudos', y='label', orientation='h',
            color='macro_tipo', text='n_estudos',
            category_orders={'label': top_n['label'].tolist()},
            color_discrete_map={'Agroalimentar':'#28a745','Artesanato':'#9c27b0',
                'Bebidas':'#2C7BE5','Agrícola':'#F2B705','Serviços':'#dc3545','Outros':'#6c757d'},
            labels={'label':'','n_estudos':'Nº estudos','macro_tipo':'Categoria'},
            template='plotly_dark')
        fig_n.update_traces(textposition='outside')
        fig_n.update_layout(height=420, margin=dict(l=0,r=0,t=5,b=0),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            legend=dict(orientation='h',y=-0.12,font=dict(size=10)),
            xaxis_title='Nº de estudos', font=dict(size=10))
        st.plotly_chart(fig_n, use_container_width=True)

        st.divider()

        if 'ano' in df_filtrado.columns and df_filtrado['ano'].notna().any():
            st.markdown("**Estudos por Ano de Publicação**")
            ac = (df_filtrado.dropna(subset=['ano']).groupby('ano').size()
                  .reset_index(name='Qtd').sort_values('ano'))
            ac['ano'] = ac['ano'].astype(int).astype(str)
            fig_a = px.area(ac, x='ano', y='Qtd', markers=True,
                template='plotly_dark', color_discrete_sequence=['#F2B705'])
            fig_a.update_traces(line_width=2.5, marker_size=8,
                fillcolor='rgba(242,183,5,0.15)')
            fig_a.update_layout(height=200, margin=dict(l=0,r=0,t=5,b=0),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                xaxis_title='', yaxis_title='Estudos', font=dict(size=10))
            st.plotly_chart(fig_a, use_container_width=True)

            st.divider()

        st.markdown("**Cobertura dos 27 Territórios**")
        cob = pd.DataFrame({
            'Território': TERRITORIOS_27,
            'Label': [formatar_ti(t) for t in TERRITORIOS_27],
            'Status': ['✅ Mapeado' if t in territorios_cobertos else '⚠️ Sem ativo'
                       for t in TERRITORIOS_27],
            'Ativos': [
                sum(1 for _, row in df_filtrado.iterrows()
                    if t in normalizar_territorios(row['territorio_identidade']))
                if not df_filtrado.empty else 0
                for t in TERRITORIOS_27
            ]
        })
        cob_ordenado = cob.sort_values('Ativos', ascending=False)
        fig_cob = px.bar(cob_ordenado,
            x='Ativos', y='Label', orientation='h',
            color='Status', text='Ativos',
            category_orders={'Label': cob_ordenado['Label'].tolist()},
            color_discrete_map={'✅ Mapeado':'#F2B705','⚠️ Sem ativo':'#30363d'},
            template='plotly_dark')
        fig_cob.update_layout(height=650, margin=dict(l=0,r=0,t=5,b=0),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            showlegend=True, xaxis_title='Nº de ativos',
            legend=dict(orientation='h',y=-0.08), font=dict(size=9))
        st.plotly_chart(fig_cob, use_container_width=True)

# =================================================
# ABA 3 – FICHAS
# =================================================
with aba3:
    st.markdown('<div class="sec-title">📋 Fichas dos Ativos</div>', unsafe_allow_html=True)
    st.caption("Critérios do INPI · Tradição histórica · Vínculo territorial · Referências ABNT")
    st.divider()

    if not df_filtrado.empty:
        col_ord, col_pag_placeholder = st.columns([3, 1])
        with col_ord:
            ordem = st.selectbox("Ordenar por",
                                 ["Notoriedade (mais estudos primeiro)", "Nome", "Território"])

        # Lógica de AGRUPAMENTO para a visualização por Território
        if ordem == "Território":
            st.caption("Clique em um território para expandir e ver os ativos. Produtos com mais de um território aparecem em cada um deles.")

            # Mapeia cada território a todas as linhas que o mencionam (principal ou secundário)
            territorios_unicos = sorted(territorios_cobertos, key=lambda ti: NUMERACAO_TI.get(ti, 99))

            for ti in territorios_unicos:
                mask_ti = df_filtrado['territorio_identidade'].apply(
                    lambda val: ti in normalizar_territorios(val))
                df_ti = df_filtrado[mask_ti].sort_values('nome_produto')
                contagem = len(df_ti)
                if contagem == 0:
                    continue
                label_expander = f"{formatar_ti(ti)} ({contagem} {'ativo' if contagem == 1 else 'ativos'})"

                # Expander para cada Território
                with st.expander(label_expander):
                    for _, row in df_ti.iterrows():
                        n = int(row.get('n_estudos', 1))
                        badge = "🔴 Alta notoriedade" if n >= 3 else "🟡 Moderada" if n == 2 else "⚪ 1 estudo"

                        # Expander para cada Possível IG dentro do Território
                        with st.expander(f"📌 {row['nome_produto']} · {badge}"):
                            exibir_conteudo_ficha(row, show_criteria=False)
        
        # Lógica original de PAGINAÇÃO para as outras ordenações
        else:
            df_ord = (df_filtrado.sort_values('n_estudos', ascending=False) if "Notoriedade" in ordem else
                      df_filtrado.sort_values('nome_produto'))

            total = len(df_ord)
            por_pag = 8
            n_pag = max(1, -(-total // por_pag)) if total > 0 else 1
            pag = 1
            with col_pag_placeholder:
                if n_pag > 1:
                    pag = st.number_input(f"Página (1–{n_pag})", min_value=1, max_value=n_pag, value=1, step=1)

            inicio = (pag - 1) * por_pag
            st.caption(f"Mostrando {inicio+1}–{min(inicio+por_pag,total)} de {total} ativos")

            for _, row in df_ord.iloc[inicio:inicio + por_pag].iterrows():
                n = int(row.get('n_estudos', 1))
                badge = "🔴 Alta notoriedade" if n >= 3 else "🟡 Moderada" if n == 2 else "⚪ 1 estudo"
                tis_exibir = normalizar_territorios(row['territorio_identidade'])
                tis_formatados = [formatar_ti(t) if t in NUMERACAO_TI else t for t in tis_exibir]
                tis_str = " · ".join(tis_formatados)

                with st.expander(f"📌 {row['nome_produto']}  ·  {tis_str}  ·  {badge}"):
                    exibir_conteudo_ficha(row, show_criteria=True)

    st.divider()
    with st.expander("🗂️ Base de Dados Completa + Download CSV"):
        if not df_filtrado.empty:
            cols_e = ['nome_produto','territorio_identidade','municipios_abrangidos',
                      'macro_tipo','macro_modalidade','n_estudos',
                      'viabilidade_economica','status_diagnostico']
            cols_e = [c for c in cols_e if c in df_filtrado.columns]
            st.dataframe(df_filtrado[cols_e], use_container_width=True, hide_index=True)
            st.download_button("⬇️ Baixar dados filtrados (.csv)",
                data=df_filtrado[cols_e].to_csv(index=False).encode('utf-8'),
                file_name="igs_bahia_filtrado.csv", mime="text/csv")

# =================================================
# ABA 4 – IGs REGISTRADAS (com territórios numerados)
# =================================================
with aba4:
    st.markdown('<div class="sec-title">🏅 IGs Registradas na Bahia — INPI</div>',
                unsafe_allow_html=True)
    st.caption("Fonte: INPI – Instituto Nacional da Propriedade Industrial (2025)")
    st.divider()

    if concedidas.empty:
        st.info("Ainda não há registros de IGs concedidas disponíveis nessa base. Isso pode acontecer quando a aba de origem está ausente ou sem a coluna esperada.")
    else:
        st.markdown(f"### ✅ Concedidas ({len(concedidas)})")
        col_c1, col_c2 = st.columns(2)
        for i, (_, ig) in enumerate(concedidas.iterrows()):
            col_atual = col_c1 if i % 2 == 0 else col_c2
            with col_atual:
                if 'macro_modalidade' in ig.index and ig.get('macro_modalidade') == 'DO':
                    tag_m = '<span class="tag-do">DO</span>'
                else:
                    tag_m = '<span class="tag-ip">IP</span>'
                territorio = ig.get('territorio_identidade', '')
                territorio_fmt = formatar_ti(territorio) if territorio in NUMERACAO_TI else territorio
                ano_str = f"Concedida em {int(ig['ano'])}" if pd.notna(ig.get('ano')) else 'Concedida'
                st.markdown(f"""<div class="ig-card-ok">
                    <b style='color:#E6EDF3;font-size:13px'>{ig.get('nome_produto', '')}</b><br>
                    {tag_m} &nbsp;<span style='color:#6E7681;font-size:12px'>{ano_str}</span><br>
                    <span style='color:#8B949E;font-size:12px'>📍 {territorio_fmt}</span>
                </div>""", unsafe_allow_html=True)

    st.divider()
    total_pot = n_potenciais
    st.markdown("**Contexto: registradas × potenciais mapeados por este TCC**")
    fig_ctx = go.Figure(go.Bar(
        x=['IGs Concedidas','Potenciais Mapeados (TCC)'],
        y=[len(concedidas), total_pot],
        marker_color=['#56d364','#F2B705'],
        text=[len(concedidas), total_pot],
        textposition='outside', width=[0.4,0.4]
    ))
    # Calcula a razão dinamicamente a partir dos números reais exibidos no gráfico
    if len(concedidas) > 0:
        razao = total_pot / len(concedidas)
        razao_str = f"{razao:.1f}".rstrip('0').rstrip('.') if razao % 1 else f"{razao:.0f}"
        texto_razao = f"Este TCC identificou um potencial ~{razao_str}x maior que as IGs já concedidas na Bahia"
    else:
        texto_razao = "Este TCC identificou um número expressivo de potenciais ativos ainda não certificados na Bahia"

    fig_ctx.update_layout(
        template='plotly_dark', height=280,
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=0,r=0,t=20,b=40), yaxis_title='Quantidade', showlegend=False,
        annotations=[dict(
            text=texto_razao,
            xref="paper", yref="paper", x=0.5, y=-0.22,
            showarrow=False, font=dict(size=11, color='#8B949E'))]
    )
    st.plotly_chart(fig_ctx, use_container_width=True)

# =================================================
# ABA 5 – SOBRE
# =================================================
with aba5:
    st.markdown('<div class="sec-title">ℹ️ Sobre o Projeto</div>', unsafe_allow_html=True)
    st.divider()

    cs1, cs2 = st.columns([3,2])
    with cs1:
        st.markdown("""<div class="about-box">
        <b style='color:#F2B705;font-size:15px'>Mapeamento de Potenciais Indicações Geográficas
        por Território de Identidade no Estado da Bahia</b><br><br>
        Trabalho de Conclusão de Curso do <b>PROFNIT – Programa de Pós-Graduação em
        Propriedade Intelectual e Transferência de Tecnologia para Inovação</b>,
        pelo ponto focal da <b>UFRB – Universidade Federal do Recôncavo da Bahia</b>.<br><br>
        <b>Objetivo:</b> Identificar, catalogar e analisar produtos e serviços com
        características territoriais distintivas, passíveis de proteção como IGs nos 27
        Territórios de Identidade baianos, por meio de banco de dados georreferenciado
        e plataforma digital interativa.<br><br>
        <b>Metodologia:</b> Revisão sistemática e pesquisa documental, com critérios de
        seleção baseados nos 4 pilares exigidos pelo INPI: singularidade, tradição
        histórica, vínculo territorial e viabilidade econômica.<br><br>
        <b>Produto tecnológico:</b> Dashboard desenvolvida em Python (Streamlit) — ferramenta
        inédita de inteligência territorial para a gestão da PI no estado da Bahia.
        </div>""", unsafe_allow_html=True)
    with cs2:
        st.markdown("""<div class="about-box">
        <b style='color:#F2B705'>Informações Acadêmicas</b><br><br>
        👤 <b>Discente:</b> Vinícius de Jesus Almeida Lima<br>
        🎓 <b>Orientador:</b> Dr. Luís Oscar Silva Martins<br>
        🏛️ <b>Instituição:</b> UFRB / PROFNIT<br>
        📅 <b>Período:</b> 2025–2026<br>
        🔗 <b>Projeto Integrador:</b> IGs e Marcas Coletivas e Inovação Associada
        ao Desenvolvimento Sustentável<br><br>
        <b style='color:#F2B705'>Critérios de Seleção (INPI)</b><br><br>
        ⭐ Singularidade do produto<br>
        📜 Tradição histórica e cultural<br>
        📍 Vínculo territorial<br>
        💼 Viabilidade econômica<br><br>
        <b style='color:#F2B705'>Tecnologias</b><br><br>
        🐍 Python · Streamlit · Folium<br>
        📊 Plotly · GeoPandas · Pandas<br>
        ☁️ Streamlit Community Cloud
        </div>""", unsafe_allow_html=True)

    st.divider()
    st.markdown("""<div style='background:#161B22;border-radius:10px;padding:14px 18px;
        border-left:4px solid #F2B705;font-size:12px;color:#ccc;'>
        <b style='color:#F2B705'>📋 Como citar este produto tecnológico</b><br><br>
        LIMA, Vinícius de Jesus Almeida.
        <i><b>Prospecção de indicações geográficas na Bahia:<b> mapeamento por Territórios de Identidade.</i>
        Dashboard — produto tecnológico do Trabalho de Conclusão de Curso. PROFNIT/UFRB. Feira de Santana, 2026.
    </div>""", unsafe_allow_html=True)

# -------------------------------------------------
# RODAPÉ
# -------------------------------------------------
st.divider()
st.markdown(
    "<div style='text-align:center;color:#6E7681;font-size:11px;'>"
    "Projeto acadêmico <b>PROFNIT</b> – Diagnóstico Territorial de IGs | Bahia &nbsp;·&nbsp; "
    "Desenvolvido por: <b>Vinícius de Jesus Almeida Lima</b> · 2026"
    "</div>", unsafe_allow_html=True)