import streamlit as st
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import plotly.express as px
import io
import re

st.set_page_config(page_title="Mapa Corsan", layout="wide")

st.title("🗺️ Mapa das cidades Corsan")
st.markdown("Explore o mapa interativo das cidades atendidas.")

# ========= CONFIG =========
ARQUIVO_MAPA = "rs_municipios.geojson"
ARQUIVOS_PLANILHA_CANDIDATOS = [
    "Segregao_Lojas.xlsx",              # nova base
    "mapa_dados_cidades_lojas.xlsx"     # fallback base antiga
]

# Paleta base para grupos/categorias
PALETA_CATEGORIAS = [
    "#FF4D4D",  # vermelho
    "#2F80ED",  # azul
    "#27AE60",  # verde
    "#F2994A",  # laranja
    "#9B51E0",  # roxo
    "#00B8D9",  # ciano
    "#8D6E63",  # marrom
]

# ========= FUNÇÕES =========
@st.cache_data
def load_data():
    mapa = gpd.read_file(ARQUIVO_MAPA).to_crs(epsg=4326)

    planilha_encontrada = None
    for arq in ARQUIVOS_PLANILHA_CANDIDATOS:
        try:
            planilha = pd.read_excel(arq)
            planilha_encontrada = arq
            break
        except FileNotFoundError:
            continue

    if planilha_encontrada is None:
        raise FileNotFoundError(
            f"Nenhuma planilha encontrada. Esperado: {ARQUIVOS_PLANILHA_CANDIDATOS}"
        )

    return mapa, planilha, planilha_encontrada


def padronizar_nomes(serie):
    return (
        serie.astype(str)
        .str.upper()
        .str.strip()
        .str.normalize("NFKD")
        .str.encode("ascii", errors="ignore")
        .str.decode("utf-8")
    )


def detectar_coluna_categoria(df):
    # Prioriza nova base
    if "Grupo" in df.columns:
        return "Grupo", "nova"
    # Fallback base antiga
    if "DIRETORIA" in df.columns:
        return "DIRETORIA", "antiga"
    raise ValueError("Planilha sem coluna de segmentação. Esperado 'Grupo' ou 'DIRETORIA'.")


def preparar_categorias(df):
    col_categoria, modo = detectar_coluna_categoria(df)

    if modo == "nova":
        # Grupo numérico -> rótulo amigável
        grp_num = pd.to_numeric(df[col_categoria], errors="coerce")
        df["CATEGORIA"] = grp_num.apply(
            lambda x: f"Grupo {int(x)}" if pd.notna(x) else "Sem Categoria"
        )
    else:
        # Compatibilidade com base antiga
        df["CATEGORIA"] = df[col_categoria].fillna("Sem Categoria").astype(str).str.strip()
        df.loc[df["CATEGORIA"] == "", "CATEGORIA"] = "Sem Categoria"

    return df, modo


def chave_ordenacao_categoria(cat):
    # Ordena "Grupo 1", "Grupo 2", ... antes de textos genéricos
    m = re.search(r"(\d+)$", str(cat))
    return (0, int(m.group(1))) if m else (1, str(cat))


def montar_dicionario_cores(categorias_unicas):
    cores = {}
    for i, cat in enumerate(categorias_unicas):
        cores[cat] = PALETA_CATEGORIAS[i % len(PALETA_CATEGORIAS)]
    cores["Sem Categoria"] = "#E0E0E0"
    return cores


def criar_figura_mapa(rs_map, cidades_destaque, dicionario_cores, categoria_especifica=None):
    fig, ax = plt.subplots(figsize=(12, 10))
    rs_map.plot(ax=ax, color="#e0e0e0", edgecolor="white", linewidth=0.5)
    itens_legenda = []

    if categoria_especifica is None:
        for categoria, cor in dicionario_cores.items():
            if categoria == "Sem Categoria":
                continue
            subset = cidades_destaque[cidades_destaque["CATEGORIA"] == categoria]
            if not subset.empty:
                subset.plot(ax=ax, color=cor, edgecolor="black", linewidth=0.8)
                itens_legenda.append(mpatches.Patch(color=cor, label=categoria))
        if itens_legenda:
            ax.legend(handles=itens_legenda, title="Categorias", loc="lower right")
        plt.title("Distribuição das cidades por categoria", fontsize=16, fontweight="bold")
    else:
        cor = dicionario_cores.get(categoria_especifica, "#999999")
        subset = cidades_destaque[cidades_destaque["CATEGORIA"] == categoria_especifica]
        if not subset.empty:
            subset.plot(ax=ax, color=cor, edgecolor="black", linewidth=0.8)
            itens_legenda.append(mpatches.Patch(color=cor, label=categoria_especifica))
        if itens_legenda:
            ax.legend(handles=itens_legenda, title="Categoria", loc="lower right")
        plt.title(f"Categoria: {categoria_especifica}", fontsize=16, fontweight="bold")

    plt.axis("off")
    plt.tight_layout()
    return fig


def gerar_buffer_download(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight", transparent=True)
    buf.seek(0)
    return buf


def nome_arquivo_seguro(txt):
    txt = str(txt).strip().lower()
    txt = re.sub(r"\s+", "_", txt)
    txt = re.sub(r"[^a-z0-9_]+", "", txt)
    return txt or "categoria"


# ========= CARGA =========
with st.spinner("Carregando base de dados e mapas..."):
    try:
        rs_map, df, arquivo_usado = load_data()
    except FileNotFoundError as e:
        st.error(f"⚠️ {e}")
        st.stop()
    except Exception as e:
        st.error(f"⚠️ Erro ao carregar dados: {e}")
        st.stop()

st.caption(f"📁 Base carregada: **{arquivo_usado}**")

# ========= PADRONIZAÇÃO =========
if "CIDADE" not in df.columns:
    st.error("⚠️ A planilha precisa ter a coluna 'CIDADE'.")
    st.stop()

if "name_muni" not in rs_map.columns:
    st.error("⚠️ O GeoJSON precisa ter a coluna 'name_muni'.")
    st.stop()

df, modo_base = preparar_categorias(df)

df["CIDADE_TRATADA"] = padronizar_nomes(df["CIDADE"])
rs_map["name_muni_tratado"] = padronizar_nomes(rs_map["name_muni"])
rs_map["name_muni"] = rs_map["name_muni"].astype(str).str.strip()

# Evita duplicatas no mapa (uma categoria por cidade)
df_mapa = (
    df[["CIDADE_TRATADA", "CATEGORIA"]]
    .dropna(subset=["CIDADE_TRATADA"])
    .drop_duplicates(subset=["CIDADE_TRATADA"])
)

mapa_categorias = rs_map.merge(
    df_mapa, how="left", left_on="name_muni_tratado", right_on="CIDADE_TRATADA"
)
mapa_categorias["CATEGORIA"] = mapa_categorias["CATEGORIA"].fillna("Sem Categoria")
cidades_destaque = mapa_categorias[mapa_categorias["CATEGORIA"] != "Sem Categoria"]

categorias_unicas = sorted(
    [c for c in df_mapa["CATEGORIA"].dropna().unique() if c != "Sem Categoria"],
    key=chave_ordenacao_categoria
)
dicionario_cores = montar_dicionario_cores(categorias_unicas)

# ========= ABAS =========
nomes_abas = ["📍 Mapa Interativo", "Visão Geral (Download)"] + categorias_unicas
abas = st.tabs(nomes_abas)

# ==========================================
# ABA 0: MAPA INTERATIVO (PLOTLY)
# ==========================================
with abas[0]:
    st.subheader("Busca e Exploração Interativa")

    lista_cidades = sorted(cidades_destaque["name_muni"].unique())

    if "cidade_selecionada" not in st.session_state:
        st.session_state.cidade_selecionada = None
    if "map_key" not in st.session_state:
        st.session_state.map_key = 0

    index_selecionado = None
    if st.session_state.cidade_selecionada in lista_cidades:
        index_selecionado = lista_cidades.index(st.session_state.cidade_selecionada)

    col1, col2 = st.columns([4, 1])

    with col1:
        nova_selecao = st.selectbox(
            "🔍 Digite, selecione ou clique no mapa para destacar uma cidade:",
            lista_cidades,
            index=index_selecionado,
            placeholder="Escolha uma cidade..."
        )

        # Endereço/Horário
        if nova_selecao:
            cidade_tratada_selecionada = padronizar_nomes(pd.Series([nova_selecao])).iloc[0]
            dados_cidade = df[df["CIDADE_TRATADA"] == cidade_tratada_selecionada]

            col_end = "ENDERECO" if "ENDERECO" in df.columns else None
            col_hor = "HORARIO" if "HORARIO" in df.columns else None

            if col_end:
                colunas_filtro = [col_end, col_hor] if col_hor else [col_end]
                lojas = dados_cidade[colunas_filtro].dropna(subset=[col_end]).drop_duplicates()
                lojas = lojas[
                    ~lojas[col_end].astype(str).str.strip().str.lower().isin(["nan", "none", ""])
                ]

                if not lojas.empty:
                    st.markdown("##### 🏢 Lojas de Atendimento")
                    for _, loja in lojas.iterrows():
                        end = str(loja[col_end]).strip()
                        texto_loja = f"📍 **Endereço:** {end}"

                        if col_hor:
                            hor = str(loja[col_hor]).strip()
                            if hor.lower() not in ["nan", "none", ""]:
                                texto_loja += f"  \n🕒 **Horário:** {hor}"

                        st.info(texto_loja)

    with col2:
        st.write("")
        st.write("")
        if st.button("🗑️ Limpar Seleção", use_container_width=True):
            nova_selecao = None

    if nova_selecao != st.session_state.cidade_selecionada:
        st.session_state.cidade_selecionada = nova_selecao
        if nova_selecao is None:
            st.session_state.map_key += 1
        st.rerun()

    cidade_atual = st.session_state.cidade_selecionada
    mapa_interativo = mapa_categorias.copy()

    mapa_zoom = 6.2
    mapa_centro = {"lat": -30.0, "lon": -53.5}

    if cidade_atual is None:
        mapa_interativo["Status_Cor"] = mapa_interativo["CATEGORIA"]
        cores_plotly = dicionario_cores.copy()
        cores_plotly["Sem Categoria"] = "#E0E0E0"
    else:
        categoria_alvo = mapa_interativo.loc[
            mapa_interativo["name_muni"] == cidade_atual, "CATEGORIA"
        ].values[0]

        def definir_destaque(row):
            if row["name_muni"] == cidade_atual:
                return "📍 Cidade Selecionada"
            elif row["CATEGORIA"] == categoria_alvo:
                return f"Categoria: {categoria_alvo}"
            else:
                return "Outras Categorias"

        mapa_interativo["Status_Cor"] = mapa_interativo.apply(definir_destaque, axis=1)

        cores_plotly = {
            "📍 Cidade Selecionada": "#FF0000",
            f"Categoria: {categoria_alvo}": dicionario_cores.get(categoria_alvo, "#777777"),
            "Outras Categorias": "#F0F0F0",
        }

        geometria_cidade = mapa_interativo.loc[
            mapa_interativo["name_muni"] == cidade_atual, "geometry"
        ].iloc[0]
        centroide = geometria_cidade.centroid
        mapa_centro = {"lat": centroide.y, "lon": centroide.x}
        mapa_zoom = 8.0

    mapa_interativo = mapa_interativo.set_index("name_muni")

    fig_interativa = px.choropleth_mapbox(
        mapa_interativo,
        geojson=mapa_interativo.geometry,
        locations=mapa_interativo.index,
        color="Status_Cor",
        color_discrete_map=cores_plotly,
        mapbox_style="carto-positron",
        zoom=mapa_zoom,
        center=mapa_centro,
        opacity=0.8,
        hover_name=mapa_interativo.index,
        hover_data={"CATEGORIA": True, "Status_Cor": False},
        height=750,
    )

    fig_interativa.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})

    evento_mapa = st.plotly_chart(
        fig_interativa,
        use_container_width=True,
        on_select="rerun",
        selection_mode="points",
        config={"scrollZoom": True},
        key=f"mapa_interativo_{st.session_state.map_key}",
    )

    if evento_mapa and len(evento_mapa.selection["points"]) > 0:
        cidade_clicada = evento_mapa.selection["points"][0]["location"]
        if cidade_clicada != st.session_state.cidade_selecionada:
            st.session_state.cidade_selecionada = cidade_clicada
            st.rerun()

# ==========================================
# ABA 1: VISÃO GERAL + DOWNLOAD
# ==========================================
with abas[1]:
    with st.spinner("Gerando mapa geral para download..."):
        fig_geral = criar_figura_mapa(rs_map, cidades_destaque, dicionario_cores)
        st.pyplot(fig_geral)
        st.download_button(
            "📥 Baixar Mapa Geral (PNG)",
            data=gerar_buffer_download(fig_geral),
            file_name="mapa_geral.png",
            mime="image/png",
        )

# ==========================================
# ABAS POR CATEGORIA
# ==========================================
for i, categoria in enumerate(categorias_unicas):
    with abas[i + 2]:
        with st.spinner(f"Gerando mapa da categoria {categoria}..."):
            fig_ind = criar_figura_mapa(
                rs_map, cidades_destaque, dicionario_cores, categoria_especifica=categoria
            )
            st.pyplot(fig_ind)
            st.download_button(
                f"📥 Baixar Mapa {categoria} (PNG)",
                data=gerar_buffer_download(fig_ind),
                file_name=f"mapa_{nome_arquivo_seguro(categoria)}.png",
                mime="image/png",
            )
