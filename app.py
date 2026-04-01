import streamlit as st
import pandas as pd
import zipfile
import os
import tempfile
import re
import io
import random
import base64
import numpy as np
from collections import Counter
import matplotlib.pyplot as plt
from supabase import create_client, Client

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Portal de Apuração", layout="wide", page_icon="🏆")

# --- CONEXÃO SUPABASE ---
SUPABASE_URL = "https://nualgtyikfijnjzmybsg.supabase.co"
SUPABASE_KEY = "sb_publishable_e9RRmaN-2XIryrki_lpWhA_uC5sHZ1K"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ESTILO ---
st.markdown("<style>.main {background-color: #000; color: #fff;}</style>", unsafe_allow_html=True)

# --- FUNÇÕES ---
def normalizar(texto):
    return str(texto).lower().strip().replace(" ", "")

def extrair_votos(texto):
    return [normalizar(v) for v in re.findall(r'@[A-Za-z0-9_.-]+', str(texto))]

@st.cache_data(ttl=0)
def listar_cidades(key):
    try:
        res = supabase.table("resultados_votos").select("cidade").execute()
        return sorted(list(set([item['cidade'] for item in res.data])))
    except: return []

# --- MENU LATERAL ---
with st.sidebar:
    st.title("🏆 Painel")
    modo = st.radio("Acesso:", ["🔍 Ver Resultados", "⚙️ Administrador"])
    if modo == "⚙️ Administrador":
        if st.text_input("Senha", type="password") != "suasenha123": st.stop()

# --- MODO ADMINISTRADOR ---
if modo == "⚙️ Administrador":
    tab1, tab2 = st.tabs(["🚀 Novo Upload", "✏️ Gerenciar Cidades"])
    
    with tab1:
        st.header("Upload de Dados")
        cidade_in = st.text_input("Nome da Cidade para o novo arquivo")
        uploaded_zip = st.file_uploader("Arquivo ZIP", type=["zip"])

        if uploaded_zip and cidade_in and st.button("PUBLICAR"):
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = os.path.join(tmpdir, "arq.zip")
                with open(zip_path, "wb") as f: f.write(uploaded_zip.read())
                with zipfile.ZipFile(zip_path, "r") as z: z.extractall(tmpdir)
                
                payload = []
                for arq in [f for f in os.listdir(tmpdir) if f.endswith((".csv", ".xlsx"))]:
                    cat = os.path.splitext(arq)[0]
                    df = pd.read_csv(os.path.join(tmpdir, arq)) if arq.endswith(".csv") else pd.read_excel(os.path.join(tmpdir, arq))
                    col_txt = "commentText" if "commentText" in df.columns else df.columns[3]
                    col_usr = "userName" if "userName" in df.columns else df.columns[1]

                    v_validos, users = [], set()
                    for _, row in df.iterrows():
                        votos = extrair_votos(row[col_txt]); u = normalizar(row[col_usr])
                        if u not in users and votos:
                            v_validos.append(votos[0]); users.add(u)
                    
                    if v_validos:
                        for cand, qtd in Counter(v_validos).items():
                            payload.append({"cidade": cidade_in.strip(), "categoria": cat, "candidato": cand, "votos": qtd})
                
                if payload:
                    supabase.table("resultados_votos").insert(payload).execute()
                    st.success("✅ Publicado!"); st.rerun()

    with tab2:
        st.header("Editar ou Excluir")
        cidades_existentes = listar_cidades(random.random())
        if cidades_existentes:
            cid_edit = st.selectbox("Selecione a cidade para gerenciar:", cidades_existentes)
            
            col_ren, col_del = st.columns(2)
            with col_ren:
                novo_nome = st.text_input("Novo nome:")
                if st.button("Confirmar Renomeação"):
                    supabase.table("resultados_votos").update({"cidade": novo_nome}).eq("cidade", cid_edit).execute()
                    st.success("Renomeado!"); st.rerun()
            
            with col_del:
                st.warning("Zona de Perigo")
                if st.button("EXCLUIR CIDADE COMPLETA"):
                    supabase.table("resultados_votos").delete().eq("cidade", cid_edit).execute()
                    st.error("Excluído!"); st.rerun()

# --- MODO PÚBLICO ---
else:
    st.title("🔍 Resultados")
    cidades = listar_cidades(random.random())
    if cidades:
        cidade_sel = st.selectbox("Cidade:", cidades)
        res = supabase.table("resultados_votos").select("*").eq("cidade", cidade_sel).execute()
        df_votos = pd.DataFrame(res.data)

        for cat in df_votos['categoria'].unique():
            with st.container():
                st.subheader(f"📊 {cat.upper()}")
                dados_cat = df_votos[df_votos['categoria'] == cat]
                total_votos = dados_cat['votos'].sum()
                dados = dados_cat.sort_values(by="votos", ascending=False).head(3).reset_index(drop=True)
                
                plt.close('all')
                fig, ax = plt.subplots(figsize=(10, 6))
                fig.patch.set_facecolor('#000000'); ax.set_facecolor('#000000')
                
                # --- PONTOS LUMINOSOS (GRID DE FUNDO) ---
                for _ in range(100):
                    ax.scatter(random.uniform(-0.5, 2.5), random.uniform(0, 1.2), 
                               alpha=random.uniform(0.1, 0.4), s=random.randint(2, 15), color="white")

                ordem, cores = [1, 0, 2], ["#FFD700", "#C0C0C0", "#CD7F32"]
                for i, row in dados.iterrows():
                    if i >= len(ordem): break
                    x, h = ordem[i], [0.9, 0.7, 0.5][i]
                    p_val = round((row['votos'] / total_votos * 100), 1) if total_votos > 0 else 0
                    
                    ax.bar(x, h, color=cores[i], width=0.8, edgecolor='white', zorder=3)
                    ax.text(x, h + 0.05, f"@{row['candidato']}", color=cores[i], ha='center', weight='bold', fontsize=12)
                    ax.text(x, h/2, f"{p_val}%", color='black', ha='center', weight='bold', fontsize=18, zorder=4)

                ax.axis('off')
                buf = io.BytesIO()
                fig.savefig(buf, format="png", bbox_inches='tight', facecolor='#000000')
                encoded = base64.b64encode(buf.getvalue()).decode()
                st.write(f'<img src="data:image/png;base64,{encoded}" style="width:100%;">', unsafe_allow_html=True)
                
                st.download_button("📥 Baixar", buf.getvalue(), f"{cat}.png", "image/png", key=f"d_{cat}_{random.randint(0,9)}")
                st.divider()
