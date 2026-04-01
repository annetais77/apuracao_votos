import streamlit as st
import pandas as pd
import zipfile
import os
import tempfile
import re
import io
import random
from collections import Counter
import matplotlib.pyplot as plt
from supabase import create_client, Client

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Portal de Apuração Oficial", layout="wide", page_icon="🏆")

# --- CONEXÃO SUPABASE ---
# Substitua pelas suas chaves se necessário
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
    .stButton>button { width: 100%; border-radius: 5px; }
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
            st.cache_data.clear() # Limpa o cache para a nova cidade aparecer
            return True
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")
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
            st.warning("Aguardando senha...")
            st.stop()

# --- MODO ADMINISTRADOR ---
if modo == "⚙️ Administrador (Upload)":
    st.header("⚙️ Painel de Upload")
    cidade_input = st.text_input("Nome da Cidade (Ex: São Paulo)")
    uploaded_zip = st.file_uploader("ZIP com arquivos CSV/Excel", type=["zip"])

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
                        col_coment = detectar_coluna_comentario(df)
                        col_user = detectar_coluna_usuario(df)
                        votos_validos, users_voted = [], set()

                        for _, row in df.iterrows():
                            u = normalizar(row[col_user]) if col_user else None
                            votos_ext = extrair_votos(str(row[col_coment]))
                            if u and u not in users_voted and votos_ext:
                                votos_validos.append(votos_ext[0])
                                users_voted.add(u)
                        
                        if votos_validos:
                            contagem = Counter(votos_validos)
                            resultados[categoria] = pd.DataFrame(contagem.items(), columns=["Candidato", "Votos"]).sort_values(by="Votos", ascending=False).head(3)
                    except: continue

            if resultados:
                if salvar_resultados_no_banco(cidade_input, resultados):
                    st.success(f"✅ Resultados de {cidade_input} publicados!")
                    st.balloons()
                    st.rerun()
            else:
                st.error("Nenhum dado válido encontrado no ZIP.")

# --- MODO PÚBLICO (CONSULTA) ---
else:
    st.title("🔍 Resultados Oficiais")
    cidades = listar_cidades_disponiveis()
    
    if not cidades:
        st.info("Nenhum resultado disponível no momento.")
    else:
        cidade_sel = st.selectbox("Selecione a cidade:", cidades)
        if cidade_sel:
            df_votos = buscar_dados_cidade(cidade_sel)
            st.subheader(f"📍 Cidade: {cidade_sel}")

            for cat in df_votos['categoria'].unique():
                with st.expander(f"📊 CATEGORIA: {cat.upper()}", expanded=True):
                    dados_cat = df_votos[df_votos['categoria'] == cat].sort_values(by="votos", ascending=False).head(3).reset_index(drop=True)
                    
                    # --- GERAÇÃO DO GRÁFICO ---
                    plt.close('all') # Previne erro de excesso de figuras
                    fig, ax = plt.subplots(figsize=(10, 12)) 
                    fig.patch.set_facecolor('#000000')
                    ax.set_facecolor('#000000')
                    
                    ax.text(1, 1.15, cat.upper(), color='#FFD700', fontsize=32, ha='center', weight='bold')
                    for _ in range(300):
                        ax.plot(random.uniform(-0.5, 2.5), random.uniform(0, 1.3), 'w*', markersize=random.uniform(0.1, 1.5), alpha=0.3)

                    ordem_visual = [1, 0, 2] # 1º Centro, 2º Esquerda, 3º Direita
                    alturas = [0.9, 0.7, 0.5] 
                    labels_lugar = ["1º Lugar", "2º Lugar", "3º Lugar"]
                    cores_corpo = ["#FFD700", "#C0C0C0", "#CD7F32"] # Ouro, Prata, Bronze
                    cores_borda = ["#DAA520", "#A9A9A9", "#8B4513"]

                    total_v_cat = dados_cat['votos'].sum()

                    for i, row in dados_cat.iterrows():
                        if i > 2: break
                        x_pos = ordem_visual[i]
                        h = alturas[i]
                        ax.bar(x_pos, h, color=cores_corpo[i], edgecolor=cores_borda[i], linewidth=4, width=0.8, zorder=3)
                        ax.bar(x_pos, h, color='white', alpha=0.15, width=0.2, zorder=4)
                        ax.text(x_pos, h + 0.05, f"@{row['candidato']}", color=cores_corpo[i], fontsize=14, ha='center', weight='bold')
                        ax.text(x_pos, h/2 + 0.05, labels_lugar[i], color='white', fontsize=20, ha='center', weight='bold', zorder=5)
                        
                        perc = (row['votos']/total_v_cat*100) if total_v_cat > 0 else 0
                        ax.text(x_pos, h/2 - 0.05, f"{perc:.2f} %", color='white', fontsize=16, ha='center', zorder=5)

                    ax.set_xlim(-0.6, 2.6); ax.set_ylim(0, 1.3); ax.axis('off')
                    
                    # Converter gráfico para imagem (Evita erro de MediaFileHandler)
                    img_buf = io.BytesIO()
                    fig.savefig(img_buf, format="png", bbox_inches='tight', dpi=120, facecolor='#000000')
                    img_buf.seek(0)
                    
                    st.image(img_buf, width='stretch')

                    c1, c2 = st.columns(2)
                    with c1: st.button(f"VER LISTA", key=f"v_{cat}")
                    with c2:
                        st.download_button(label="📥 DOWNLOAD CARD", data=img_buf, 
                                          file_name=f"card_{cat}_{cidade_sel}.png", mime="image/png", key=f"dl_{cat}")
                    plt.close(fig)

            # --- TOP 3 GERAL DA CIDADE ---
            st.divider()
            st.header(f"👑 RANKING GERAL: {cidade_sel}")
            top3_geral = df_votos.groupby("candidato")["votos"].sum().reset_index().sort_values(by="votos", ascending=False).head(3).reset_index()
            
            cols = st.columns(3)
            for i, row in top3_geral.iterrows():
                cor = ["#FFD700", "#C0C0C0", "#CD7F32"][i]
                with cols[i]:
                    st.markdown(f"""
                        <div style="text-align: center; border: 3px solid {cor}; padding: 15px; border-radius: 15px; background-color: #0a0a0a;">
                            <h2 style="margin:0;">{["🥇","🥈","🥉"][i]}</h2>
                            <p style="font-size: 18px; font-weight: bold; margin:0;">{row['candidato']}</p>
                            <p style="font-size: 24px; color: {cor}; font-weight: bold;">{row['votos']} Votos</p>
                        </div>
                    """, unsafe_allow_html=True)
