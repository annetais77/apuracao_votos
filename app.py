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
    st.error(f"Erro de conexão: {e}")

# --- ESTILIZAÇÃO CSS ---
st.markdown("""
    <style>
    .main { background-color: #000000; color: white; }
    .stExpander { border: 1px solid #333; background-color: #0a0a0a; border-radius: 10px; }
    h1, h2, h3, p, label { color: white !important; }
    .stButton>button { width: 100%; background-color: #1a1a1a; color: white; border: 1px solid #333; }
    .stButton>button:hover { border-color: #FFD700; color: #FFD700; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE SUPORTE ---
def normalizar(texto):
    texto = str(texto).lower().strip().replace(" ", "")
    for c in [("ã","a"),("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u")]:
        texto = texto.replace(c[0], c[1])
    return texto

def extrair_votos(texto):
    return [normalizar(v) for v in re.findall(r'@[A-Za-z0-9_.-]+', str(texto))]

def salvar_no_banco(cidade, resultados_dict):
    payload = []
    for cat, top3 in resultados_dict.items():
        for _, row in top3.iterrows():
            payload.append({
                "cidade": cidade.strip(), "categoria": cat,
                "candidato": row["Candidato"], "votos": int(row["Votos"])
            })
    if payload:
        try:
            supabase.table("resultados_votos").insert(payload).execute()
            st.cache_data.clear()
            return True
        except: return False
    return False

@st.cache_data(ttl=30)
def listar_cidades():
    try:
        res = supabase.table("resultados_votos").select("cidade").execute()
        return sorted(list(set([item['cidade'] for item in res.data])))
    except: return []

# --- INTERFACE ---
with st.sidebar:
    st.title("🏆 Menu")
    modo = st.radio("Acesso:", ["🔍 Ver Resultados", "⚙️ Administrador"])
    if modo == "⚙️ Administrador":
        if st.text_input("Senha", type="password") != "suasenha123": st.stop()

# --- MODO ADMIN ---
if modo == "⚙️ Administrador":
    st.header("⚙️ Publicar Novos Dados")
    cidade_in = st.text_input("Nome da Cidade (ex: Afogados)")
    uploaded_zip = st.file_uploader("Arquivo ZIP (CSVs dentro)", type=["zip"])

    if uploaded_zip and cidade_in and st.button("🚀 PROCESSAR E PUBLICAR"):
        resultados = {}
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "temp.zip")
            with open(zip_path, "wb") as f: f.write(uploaded_zip.read())
            with zipfile.ZipFile(zip_path, "r") as z: z.extractall(tmpdir)
            
            for arq in [f for f in os.listdir(tmpdir) if f.endswith((".csv", ".xlsx"))]:
                cat = os.path.splitext(arq)[0]
                try:
                    df = pd.read_csv(os.path.join(tmpdir, arq)) if arq.endswith(".csv") else pd.read_excel(os.path.join(tmpdir, arq))
                    v_validos, users = [], set()
                    
                    # Identifica colunas pelo seu padrão (userName e commentText)
                    col_txt = "commentText" if "commentText" in df.columns else df.columns[min(3, len(df.columns)-1)]
                    col_usr = "userName" if "userName" in df.columns else df.columns[min(1, len(df.columns)-1)]

                    for _, row in df.iterrows():
                        votos = extrair_votos(row[col_txt])
                        u = normalizar(row[col_usr])
                        if u not in users and votos:
                            v_validos.append(votos[0])
                            users.add(u)
                    
                    if v_validos:
                        count = Counter(v_validos)
                        resultados[cat] = pd.DataFrame(count.items(), columns=["Candidato", "Votos"]).sort_values(by="Votos", ascending=False).head(3)
                except: continue

        if resultados and salvar_no_banco(cidade_in, resultados):
            st.success("✅ Publicado com sucesso!"); st.balloons(); st.rerun()
        else:
            st.error("❌ Nenhum dado válido encontrado no ZIP.")

# --- MODO PÚBLICO ---
else:
    st.title("🔍 Resultados Oficiais")
    cidades = listar_cidades()
    if not cidades:
        st.info("Aguardando publicação de resultados...")
    else:
        cidade_sel = st.selectbox("Selecione a cidade:", cidades)
        res = supabase.table("resultados_votos").select("*").eq("cidade", cidade_sel).execute()
        df_votos = pd.DataFrame(res.data)

        for cat in df_votos['categoria'].unique():
            with st.expander(f"📊 CATEGORIA: {cat.upper()}", expanded=True):
                dados = df_votos[df_votos['categoria'] == cat].sort_values(by="votos", ascending=False).head(3).reset_index(drop=True)
                
                # --- GERAÇÃO DO GRÁFICO (MEMÓRIA LIMPA) ---
                plt.close('all'); plt.clf()
                fig, ax = plt.subplots(figsize=(10, 8))
                fig.patch.set_facecolor('#000000'); ax.set_facecolor('#000000')
                
                # Estrelas de fundo
                for _ in range(50):
                    ax.plot(random.uniform(-0.5, 2.5), random.uniform(0, 1.2), 'w*', markersize=1, alpha=0.3)

                ordem, cores = [1, 0, 2], ["#FFD700", "#C0C0C0", "#CD7F32"]
                for i, row in dados.iterrows():
                    x, h = ordem[i], [0.9, 0.7, 0.5][i]
                    ax.bar(x, h, color=cores[i], width=0.7, edgecolor='white', linewidth=0.5)
                    ax.text(x, h + 0.05, f"@{row['candidato']}", color=cores[i], fontsize=12, ha='center', weight='bold')
                    ax.text(x, h/2, f"{int(row['votos'])}\nVOTOS", color='black', fontsize=14, ha='center', weight='bold')

                ax.set_xlim(-0.6, 2.6); ax.set_ylim(0, 1.2); ax.axis('off')
                
                # --- CONVERSÃO PARA BASE64 E DOWNLOAD ---
                buf = io.BytesIO()
                fig.savefig(buf, format="png", bbox_inches='tight', dpi=150, facecolor='#000000')
                img_data = buf.getvalue()
                b64 = base64.b64encode(img_data).decode()
                
                # Exibição
                st.markdown(f'<img src="data:image/png;base64,{b64}" style="width:100%; border-radius:10px; border: 1px solid #333;">', unsafe_allow_html=True)
                
                # Botão de Download (Usa os dados do buffer)
                st.download_button(
                    label="📥 BAIXAR CARD (PNG)",
                    data=img_data,
                    file_name=f"resultado_{cat}_{cidade_sel}.png",
                    mime="image/png",
                    key=f"dl_{cat}"
                )
                plt.close(fig)

        # TOP 3 GERAL (RODAPÉ)
        st.divider()
        st.subheader(f"🏆 TOP 3 VOTAÇÃO TOTAL: {cidade_sel}")
        geral = df_votos.groupby("candidato")["votos"].sum().reset_index().sort_values(by="votos", ascending=False).head(3)
        cols = st.columns(3)
        for i, (idx, row) in enumerate(geral.iterrows()):
            with cols[i]:
                st.metric(label=f"{i+1}º Lugar Geral", value=f"@{row['candidato']}", delta=f"{int(row['votos'])} votos")
