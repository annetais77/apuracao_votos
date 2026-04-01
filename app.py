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
    for cat, top3 in resultados_dict.items():
        for _, row in top3.iterrows():
            payload.append({"cidade": cidade.strip(), "categoria": cat, "candidato": row["Candidato"], "votos": int(row["Votos"])})
    if payload:
        try:
            supabase.table("resultados_votos").insert(payload).execute()
            st.cache_data.clear()
            return True
        except: return False
    return False

@st.cache_data(ttl=60)
def listar_cidades():
    try:
        res = supabase.table("resultados_votos").select("cidade").execute()
        return sorted(list(set([i['cidade'] for i in res.data])))
    except: return []

# --- BARRA LATERAL ---
with st.sidebar:
    st.title("🏆 Navegação")
    modo = st.radio("Escolha:", ["🔍 Ver Resultados", "⚙️ Administrador"])
    if modo == "⚙️ Administrador":
        if st.text_input("Senha", type="password") != "suasenha123": st.stop()

# --- LOGICA DE EXIBIÇÃO ---
if modo == "⚙️ Administrador":
    st.header("⚙️ Painel Admin")
    cidade_in = st.text_input("Cidade")
    file_zip = st.file_uploader("ZIP", type=["zip"])
    if file_zip and cidade_in and st.button("🚀 Publicar"):
        # Lógica de processamento simplificada para o exemplo
        st.success("Publicado!") 
        st.rerun()

else:
    st.title("🔍 Resultados Oficiais")
    cidades = listar_cidades()
    if cidades:
        cidade_sel = st.selectbox("Cidade:", cidades)
        res = supabase.table("resultados_votos").select("*").eq("cidade", cidade_sel).execute()
        df_votos = pd.DataFrame(res.data)

        if not df_votos.empty:
            for cat in df_votos['categoria'].unique():
                with st.expander(f"📊 {cat.upper()}", expanded=True):
                    dados = df_votos[df_votos['categoria'] == cat].sort_values(by="votos", ascending=False).head(3).reset_index(drop=True)
                    
                    # Limpeza de memória Matplotlib
                    plt.close('all')
                    fig, ax = plt.subplots(figsize=(10, 12))
                    fig.patch.set_facecolor('#000000'); ax.set_facecolor('#000000')
                    
                    # Desenho do Pódio (simplificado para estabilidade)
                    ordem, alturas, cores = [1, 0, 2], [0.9, 0.7, 0.5], ["#FFD700", "#C0C0C0", "#CD7F32"]
                    ax.text(1, 1.15, cat.upper(), color='#FFD700', fontsize=30, ha='center', weight='bold')
                    
                    total = dados['votos'].sum()
                    for i, row in dados.iterrows():
                        if i < 3:
                            x, h = ordem[i], alturas[i]
                            ax.bar(x, h, color=cores[i], width=0.8, zorder=3)
                            ax.text(x, h + 0.05, f"@{row['candidato']}", color=cores[i], fontsize=14, ha='center', weight='bold')
                            ax.text(x, h/2, f"{i+1}º\n{(row['votos']/total*100):.1f}%", color='white', fontsize=18, ha='center', weight='bold', zorder=5)

                    ax.set_xlim(-0.6, 2.6); ax.set_ylim(0, 1.3); ax.axis('off')

                    # --- SOLUÇÃO DEFINITIVA PARA O ERRO ---
                    tmp_buf = io.BytesIO()
                    fig.savefig(tmp_buf, format="png", bbox_inches='tight', dpi=100, facecolor='#000000')
                    tmp_buf.seek(0)
                    
                    # Transformamos a imagem em Base64 para não depender de arquivos no servidor
                    b64 = base64.b64encode(tmp_buf.read()).decode()
                    st.markdown(f'<img src="data:image/png;base64,{b64}" style="width:100%;">', unsafe_allow_html=True)
                    
                    st.download_button("📥 Baixar Card", tmp_buf, f"card_{cat}.png", "image/png", key=f"dl_{cat}")
                    plt.close(fig)
