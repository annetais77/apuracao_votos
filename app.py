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
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE PROCESSAMENTO ---
def detectar_coluna_comentario(df):
    for col in ["commentText", "CommentText", "comment", "Comment", "text"]:
        if col in df.columns: return col
    return df.columns[0]

def detectar_coluna_usuario(df):
    for col in ["userName", "username", "UserName"]:
        if col in df.columns: return col
    return None

def normalizar(texto):
    texto = str(texto).lower().replace(" ", "")
    for char in [("ã","a"), ("á","a"), ("é","e"), ("í","i"), ("ó","o"), ("ú","u")]:
        texto = texto.replace(char[0], char[1])
    return texto

def extrair_votos(texto):
    encontrados = re.findall(r'@[A-Za-z0-9_.-]+', texto)
    return [normalizar(v) for v in encontrados]

# --- FUNÇÕES DE BANCO DE DADOS ---
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
            st.cache_data.clear() # Limpa cache da lista de cidades
            return True
        except Exception as e:
            st.error(f"Erro no Supabase: {e}")
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
            st.stop()

# --- MODO ADMINISTRADOR ---
if modo == "⚙️ Administrador (Upload)":
    st.header("⚙️ Painel de Upload")
    cidade_input = st.text_input("Nome da Cidade")
    uploaded_zip = st.file_uploader("ZIP com arquivos", type=["zip"])

    if uploaded_zip and cidade_input:
        if st.button("🚀 Processar e Publicar"):
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
                        col_coment, col_user = detectar_coluna_comentario(df), detectar_coluna_usuario(df)
                        votos_validos, users_voted = [], set()
                        for _, row in df.iterrows():
                            u = normalizar(row[col_user]) if col_user else None
                            v_ext = extrair_votos(str(row[col_coment]))
                            if u and u not in users_voted and v_ext:
                                votos_validos.append(v_ext[0]); users_voted.add(u)
                        if votos_validos:
                            contagem = Counter(votos_validos)
                            resultados[categoria] = pd.DataFrame(contagem.items(), columns=["Candidato", "Votos"]).sort_values(by="Votos", ascending=False).head(3)
                    except: continue

            if resultados:
                if salvar_resultados_no_banco(cidade_input, resultados):
                    st.success(f"✅ Publicado: {cidade_input}")
                    st.balloons()
                    st.rerun() # Força atualização da lista de cidades

# --- MODO PÚBLICO (CONSULTA) ---
else:
    st.title("🔍 Resultados Oficiais")
    cidades = listar_cidades_disponiveis()
    
    if not cidades:
        st.info("Nenhum resultado disponível.")
    else:
        cidade_sel = st.selectbox("Selecione a cidade:", cidades)
        if cidade_sel:
            df_votos = buscar_dados_cidade(cidade_sel)
            for cat in df_votos['categoria'].unique():
                with st.expander(f"📊 CATEGORIA: {cat.upper()}", expanded=True):
                    dados_cat = df_votos[df_votos['categoria'] == cat].sort_values(by="votos", ascending=False).head(3).reset_index(drop=True)
                    
                    # --- GRÁFICO SEGURO ---
                    plt.close('all')
                    fig, ax = plt.subplots(figsize=(10, 12)) 
                    fig.patch.set_facecolor('#000000'); ax.set_facecolor('#000000')
                    ax.text(1, 1.15, cat.upper(), color='#FFD700', fontsize=32, ha='center', weight='bold')
                    
                    for _ in range(200):
                        ax.plot(random.uniform(-0.5, 2.5), random.uniform(0, 1.3), 'w*', markersize=random.uniform(0.1, 1.2), alpha=0.3)

                    ordem, alturas = [1, 0, 2], [0.9, 0.7, 0.5]
                    cores = ["#FFD700", "#C0C0C0", "#CD7F32"]
                    total_v = dados_cat['votos'].sum()

                    for i, row in dados_cat.iterrows():
                        if i < 3:
                            x, h = ordem[i], alturas[i]
                            ax.bar(x, h, color=cores[i], width=0.8, zorder=3)
                            ax.text(x, h + 0.05, f"@{row['candidato']}", color=cores[i], fontsize=14, ha='center', weight='bold')
                            ax.text(x, h/2, f"{i+1}º LUGAR\n{((row['votos']/total_v)*100):.1f}%", color='white', fontsize=18, ha='center', weight='bold', zorder=5)

                    ax.set_xlim(-0.6, 2.6); ax.set_ylim(0, 1.3); ax.axis('off')
                    
                    # --- CONVERSÃO PARA BASE64 (ESTABILIDADE TOTAL) ---
                    buf = io.BytesIO()
                    fig.savefig(buf, format="png", bbox_inches='tight', dpi=100, facecolor='#000000')
                    buf.seek(0)
                    b64 = base64.b64encode(buf.read()).decode()
                    
                    # Exibe HTML puro para evitar erro de arquivo ausente
                    st.markdown(f'<img src="data:image/png;base64,{b64}" width="100%">', unsafe_allow_html=True)

                    st.download_button("📥 BAIXAR CARD", buf, f"card_{cat}.png", "image/png", key=f"dl_{cat}")
                    plt.close(fig)

            # TOP 3 GERAL
            st.divider()
            top3_geral = df_votos.groupby("candidato")["votos"].sum().reset_index().sort_values(by="votos", ascending=False).head(3).reset_index()
            cols = st.columns(3)
            for i, row in top3_geral.iterrows():
                cor = ["#FFD700", "#C0C0C0", "#CD7F32"][i]
                with cols[i]:
                    st.markdown(f'<div style="text-align: center; border: 2px solid {cor}; padding: 10px; border-radius: 10px;"><h3>{["🥇","🥈","🥉"][i]}</h3><p>{row["candidato"]}</p><h2 style="color:{cor}">{row["votos"]}</h2></div>', unsafe_allow_html=True)
