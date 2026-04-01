import streamlit as st
import pandas as pd
import zipfile
import os
import tempfile
import re
import io
import random
import base64
from collections import Counter
import matplotlib.pyplot as plt
from supabase import create_client, Client

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Portal de Apuração Oficial", layout="wide", page_icon="🏆")

# --- CONEXÃO SUPABASE ---
SUPABASE_URL = "https://nualgtyikfijnjzmybsg.supabase.co"
SUPABASE_KEY = "sb_publishable_e9RRmaN-2XIryrki_lpWhA_uC5sHZ1K"

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"Erro ao conectar ao banco de dados: {e}")

# --- ESTILIZAÇÃO CSS (MODO NOTURNO TOTAL) ---
st.markdown("""
    <style>
    .main, .stApp { background-color: #000000; color: white; }
    .stExpander { border: 1px solid #333; border-radius: 10px; background-color: #0a0a0a; margin-bottom: 20px; }
    h1, h2, h3, p, label, .stMarkdown { color: white !important; }
    div[data-testid="stMetricValue"] { color: #FFD700 !important; }
    .stTextInput>div>div>input, .stSelectbox>div>div>div {
        background-color: #1a1a1a !important; color: white !important; border-color: #333 !important;
    }
    .stButton>button { width: 100%; border-radius: 5px; background-color: #1a1a1a; color: white; border: 1px solid #333; }
    .stButton>button:hover { border-color: #FFD700; color: #FFD700; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE APOIO ---
def normalizar(texto):
    texto = str(texto).lower().replace(" ", "")
    for char in [("ã","a"), ("á","a"), ("é","e"), ("í","i"), ("ó","o"), ("ú","u")]:
        texto = texto.replace(char[0], char[1])
    return texto

def extrair_votos(texto):
    encontrados = re.findall(r'@[A-Za-z0-9_.-]+', texto)
    return [normalizar(v) for v in encontrados]

def salvar_resultados_no_banco(cidade, resultados_dict):
    payload = []
    cidade_clean = cidade.strip()
    for categoria, top3 in resultados_dict.items():
        for _, row in top3.iterrows():
            payload.append({
                "cidade": cidade_clean,
                "categoria": categoria,
                "candidato": row["Candidato"],
                "votos": int(row["Votos"])
            })
    if payload:
        try:
            supabase.table("resultados_votos").insert(payload).execute()
            # LIMPANDO O CACHE PARA FORÇAR A ATUALIZAÇÃO DA LISTA DE CIDADES
            st.cache_data.clear() 
            return True
        except Exception as e:
            st.error(f"Erro ao salvar no banco: {e}")
            return False
    return False

@st.cache_data(ttl=60)
def listar_cidades_disponiveis():
    try:
        res = supabase.table("resultados_votos").select("cidade").execute()
        return sorted(list(set([item['cidade'] for item in res.data])))
    except: return []

def buscar_dados_cidade(cidade_nome):
    res = supabase.table("resultados_votos").select("*").eq("cidade", cidade_nome).execute()
    return pd.DataFrame(res.data)

# --- BARRA LATERAL ---
with st.sidebar:
    st.title("🏆 Navegação")
    modo = st.radio("Escolha o acesso:", ["🔍 Ver Resultados", "⚙️ Administrador (Upload)"])
    st.divider()
    if modo == "⚙️ Administrador (Upload)":
        senha = st.text_input("Senha de acesso", type="password")
        if senha != "suasenha123":
            st.warning("Aguardando senha correta...")
            st.stop()

# --- MODO ADMINISTRADOR (UPLOAD) ---
if modo == "⚙️ Administrador (Upload)":
    st.header("⚙️ Painel de Publicação")
    cidade_input = st.text_input("Nome da Cidade (ex: Afogados da Ingazeira)")
    uploaded_zip = st.file_uploader("Envie o ZIP com os arquivos CSV/Excel", type=["zip"])

    if uploaded_zip and cidade_input:
        if st.button("🚀 PROCESSAR E PUBLICAR RESULTADOS"):
            resultados = {}
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = os.path.join(tmpdir, "arquivos.zip")
                with open(zip_path, "wb") as f: f.write(uploaded_zip.read())
                with zipfile.ZipFile(zip_path, "r") as zip_ref: zip_ref.extractall(tmpdir)
                
                arquivos = [f for f in os.listdir(tmpdir) if f.endswith((".csv", ".xlsx"))]
                for arquivo in arquivos:
                    categoria = os.path.splitext(arquivo)[0]
                    caminho = os.path.join(tmpdir, arquivo)
                    try:
                        df = pd.read_csv(caminho) if arquivo.endswith(".csv") else pd.read_excel(caminho)
                        # Identifica colunas dinamicamente (Comentário e Usuário)
                        votos_validos, users_voted = [], set()
                        for _, row in df.iterrows():
                            v_ext = extrair_votos(str(row.iloc[0]))
                            u = normalizar(row.iloc[1])
                            if u not in users_voted and v_ext:
                                votos_validos.append(v_ext[0])
                                users_voted.add(u)
                        if votos_validos:
                            contagem = Counter(votos_validos)
                            resultados[categoria] = pd.DataFrame(contagem.items(), columns=["Candidato", "Votos"]).sort_values(by="Votos", ascending=False).head(3)
                    except: continue

            if resultados:
                if salvar_resultados_no_banco(cidade_input, resultados):
                    st.success(f"✅ Resultados de '{cidade_input}' publicados com sucesso!")
                    st.balloons()
                    # ATUALIZA A PÁGINA PARA A CIDADE APARECER NO SELECTBOX
                    st.rerun()
            else:
                st.error("Nenhum dado válido encontrado. Verifique o formato dos arquivos.")

# --- MODO PÚBLICO (CONSULTA) ---
else:
    st.title("🔍 Resultados Oficiais")
    cidades = listar_cidades_disponiveis()
    
    if not cidades:
        st.info("Nenhum resultado disponível no momento.")
    else:
        cidade_sel = st.selectbox("Selecione a cidade desejada:", cidades)
        if cidade_sel:
            df_votos = buscar_dados_cidade(cidade_sel)
            st.subheader(f"📍 Exibindo resultados de: {cidade_sel}")

            for cat in df_votos['categoria'].unique():
                with st.expander(f"📊 CATEGORIA: {cat.upper()}", expanded=True):
                    dados_cat = df_votos[df_votos['categoria'] == cat].sort_values(by="votos", ascending=False).head(3).reset_index(drop=True)
                    
                    # --- GERAÇÃO DO GRÁFICO ---
                    plt.close('all')
                    fig, ax = plt.subplots(figsize=(10, 12)) 
                    fig.patch.set_facecolor('#000000'); ax.set_facecolor('#000000')
                    
                    ax.text(1, 1.15, cat.upper(), color='#FFD700', fontsize=32, ha='center', weight='bold')
                    for _ in range(200):
                        ax.plot(random.uniform(-0.5, 2.5), random.uniform(0, 1.3), 'w*', 
                                markersize=random.uniform(0.1, 1.2), alpha=0.3)

                    ordem, alturas = [1, 0, 2], [0.9, 0.7, 0.5]
                    cores = ["#FFD700", "#C0C0C0", "#CD7F32"] # Ouro, Prata, Bronze
                    total_v = dados_cat['votos'].sum()

                    for i, row in dados_cat.iterrows():
                        if i < 3:
                            x, h = ordem[i], alturas[i]
                            ax.bar(x, h, color=cores[i], width=0.8, zorder=3, edgecolor='white', linewidth=0.5)
                            ax.text(x, h + 0.05, f"@{row['candidato']}", color=cores[i], fontsize=14, ha='center', weight='bold')
                            ax.text(x, h/2, f"{i+1}º LUGAR\n{int(row['votos'])} Votos", color='white', fontsize=18, ha='center', weight='bold', zorder=5)

                    ax.set_xlim(-0.6, 2.6); ax.set_ylim(0, 1.3); ax.axis('off')
                    
                    # --- CONVERSÃO PARA BASE64 (MATA ERRO DE MÍDIA) ---
                    img_buf = io.BytesIO()
                    fig.savefig(img_buf, format="png", bbox_inches='tight', dpi=100, facecolor='#000000')
                    img_buf.seek(0)
                    b64_img = base64.b64encode(img_buf.read()).decode()
                    
                    # Injeta a imagem diretamente no HTML para estabilidade total
                    st.markdown(f'<img src="data:image/png;base64,{b64_img}" style="width:100%; border-radius:10px;">', unsafe_allow_html=True)

                    # Botões de ação
                    c1, c2 = st.columns(2)
                    with c1:
                        st.button(f"VER LISTA COMPLETA", key=f"btn_{cat}")
                    with c2:
                        st.download_button(label="📥 BAIXAR CARD", data=img_buf, 
                                          file_name=f"resultado_{cat}.png", mime="image/png", key=f"dl_{cat}")
                    plt.close(fig)

            # --- RANKING GERAL ---
            st.divider()
            st.header(f"👑 TOP 3 GERAL: {cidade_sel}")
            top3_geral = df_votos.groupby("candidato")["votos"].sum().reset_index().sort_values(by="votos", ascending=False).head(3).reset_index()
            
            cols = st.columns(3)
            for i, row in top3_geral.iterrows():
                cor = ["#FFD700", "#C0C0C0", "#CD7F32"][i]
                with cols[i]:
                    st.markdown(f"""
                        <div style="text-align: center; border: 2px solid {cor}; padding: 20px; border-radius: 15px; background-color: #0a0a0a;">
                            <h1 style="margin:0;">{["🥇","🥈","🥉"][i]}</h1>
                            <h3 style="color:white; margin:10px 0;">{row['candidato']}</h3>
                            <h2 style="color:{cor}; margin:0;">{int(row['votos'])} Votos</h2>
                        </div>
                    """, unsafe_allow_html=True)
