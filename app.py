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

# --- ESTILIZAÇÃO CSS ---
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

# --- FUNÇÕES ---
def normalizar(texto):
    texto = str(texto).lower().replace(" ", "")
    for char in [("ã","a"), ("á","a"), ("é","e"), ("í","i"), ("ó","o"), ("ú","u")]:
        texto = texto.replace(char[0], char[1])
    return texto

def extrair_votos(texto):
    encontrados = re.findall(r'@[A-Za-z0-9_.-]+', texto)
    return [normalizar(v) for v in encontrados]

def salvar_no_banco(cidade, resultados_dict):
    payload = []
    cidade_clean = cidade.strip()
    for cat, top3 in resultados_dict.items():
        for _, row in top3.iterrows():
            payload.append({
                "cidade": cidade_clean, "categoria": cat,
                "candidato": row["Candidato"], "votos": int(row["Votos"])
            })
    if payload:
        try:
            supabase.table("resultados_votos").insert(payload).execute()
            st.cache_data.clear() # CRUCIAL: Limpa a lista de cidades para atualizar o menu
            return True
        except: return False
    return False

@st.cache_data(ttl=30)
def listar_cidades():
    try:
        res = supabase.table("resultados_votos").select("cidade").execute()
        return sorted(list(set([item['cidade'] for item in res.data])))
    except: return []

# --- BARRA LATERAL ---
with st.sidebar:
    st.title("🏆 Navegação")
    modo = st.radio("Acesso:", ["🔍 Ver Resultados", "⚙️ Administrador"])
    if modo == "⚙️ Administrador":
        if st.text_input("Senha", type="password") != "suasenha123": st.stop()

# --- MODO ADMIN ---
if modo == "⚙️ Administrador":
    st.header("⚙️ Upload de Resultados")
    cidade_in = st.text_input("Nome da Cidade")
    uploaded_zip = st.file_uploader("Arquivo ZIP", type=["zip"])

    if uploaded_zip and cidade_in:
        if st.button("🚀 Publicar Agora"):
            resultados = {}
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = os.path.join(tmpdir, "arq.zip")
                with open(zip_path, "wb") as f: f.write(uploaded_zip.read())
                with zipfile.ZipFile(zip_path, "r") as z: z.extractall(tmpdir)
                
                for arq in [f for f in os.listdir(tmpdir) if f.endswith((".csv", ".xlsx"))]:
                    cat = os.path.splitext(arq)[0]
                    caminho = os.path.join(tmpdir, arq)
                    try:
                        df = pd.read_csv(caminho) if arq.endswith(".csv") else pd.read_excel(caminho)
                        # Assume colunas 0 (comentário) e 1 (usuário) se não encontrar nomes
                        v_validos, users = [], set()
                        for _, row in df.iterrows():
                            v = extrair_votos(str(row.iloc[0]))
                            u = normalizar(row.iloc[1])
                            if u not in users and v:
                                v_validos.append(v[0]); users.add(u)
                        if v_validos:
                            contagem = Counter(v_validos)
                            resultados[cat] = pd.DataFrame(contagem.items(), columns=["Candidato", "Votos"]).sort_values(by="Votos", ascending=False).head(3)
                    except: continue

            if resultados and salvar_no_banco(cidade_in, resultados):
                st.success("✅ Publicado com sucesso!")
                st.rerun()

# --- MODO PÚBLICO ---
else:
    st.title("🔍 Resultados Oficiais")
    cidades = listar_cidades()
    if not cidades:
        st.info("Aguardando primeiras apurações...")
    else:
        cidade_sel = st.selectbox("Escolha a Cidade:", cidades)
        res = supabase.table("resultados_votos").select("*").eq("cidade", cidade_sel).execute()
        df_votos = pd.DataFrame(res.data)

        for cat in df_votos['categoria'].unique():
            with st.expander(f"📊 CATEGORIA: {cat.upper()}", expanded=True):
                dados = df_votos[df_votos['categoria'] == cat].sort_values(by="votos", ascending=False).head(3).reset_index(drop=True)
                
                plt.close('all')
                fig, ax = plt.subplots(figsize=(10, 10))
                fig.patch.set_facecolor('#000000'); ax.set_facecolor('#000000')
                
                # Pódio Ouro, Prata, Bronze
                ordem, cores = [1, 0, 2], ["#FFD700", "#C0C0C0", "#CD7F32"]
                total = dados['votos'].sum()

                for i, row in dados.iterrows():
                    x, h = ordem[i], [0.9, 0.7, 0.5][i]
                    ax.bar(x, h, color=cores[i], width=0.8, edgecolor='white', linewidth=1)
                    ax.text(x, h + 0.05, f"@{row['candidato']}", color=cores[i], ha='center', weight='bold', fontsize=14)
                    ax.text(x, h/2, f"{i+1}º Lugar\n{int(row['votos'])} votos", color='black', ha='center', weight='bold')

                ax.set_xlim(-0.6, 2.6); ax.set_ylim(0, 1.2); ax.axis('off')

                # --- RENDERIZAÇÃO BASE64 (MATA O ERRO DE MEDIA FILE) ---
                buf = io.BytesIO()
                fig.savefig(buf, format="png", bbox_inches='tight', facecolor='#000000')
                buf.seek(0)
                b64_img = base64.b64encode(buf.read()).decode()
                
                # Injeta a imagem diretamente no HTML
                st.markdown(f'<img src="data:image/png;base64,{b64_img}" style="width:100%; border-radius:10px;">', unsafe_allow_html=True)
                
                st.download_button("📥 Baixar Card", buf, f"resultado_{cat}.png", "image/png", key=f"dl_{cat}")
                plt.close(fig)
