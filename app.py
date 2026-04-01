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
st.set_page_config(page_title="Portal de Apuração", layout="wide", page_icon="🏆")

# --- CONEXÃO SUPABASE ---
SUPABASE_URL = "https://nualgtyikfijnjzmybsg.supabase.co"
SUPABASE_KEY = "sb_publishable_e9RRmaN-2XIryrki_lpWhA_uC5sHZ1K"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ESTILO ---
st.markdown("<style>.main {background-color: #000; color: #fff;}</style>", unsafe_allow_html=True)

# --- FUNÇÕES DE APOIO ---
def normalizar(texto):
    return str(texto).lower().strip().replace(" ", "")

def extrair_votos(texto):
    return [normalizar(v) for v in re.findall(r'@[A-Za-z0-9_.-]+', str(texto))]

def salvar_no_banco(cidade, resultados_dict):
    payload = []
    for cat, df_cat in resultados_dict.items():
        for _, row in df_cat.iterrows():
            payload.append({
                "cidade": cidade.strip(), 
                "categoria": cat,
                "candidato": row["Candidato"], 
                "votos": int(row["Votos"])
            })
    if payload:
        try:
            supabase.table("resultados_votos").insert(payload).execute()
            st.cache_data.clear() # Limpa o cache após postar
            return True
        except: return False
    return False

@st.cache_data(ttl=0) # TTL 0 força a atualização constante
def listar_cidades(refresh_key):
    try:
        res = supabase.table("resultados_votos").select("cidade").execute()
        return sorted(list(set([item['cidade'] for item in res.data])))
    except: return []

# --- MENU LATERAL ---
with st.sidebar:
    st.title("🏆 Painel")
    modo = st.radio("Navegação:", ["🔍 Ver Resultados", "⚙️ Administrador"])
    if modo == "⚙️ Administrador":
        senha = st.text_input("Senha de Acesso", type="password")
        if senha != "suasenha123": st.stop()

# --- MODO ADMINISTRADOR (UPLOAD) ---
if modo == "⚙️ Administrador":
    st.header("⚙️ Publicar Novo Arquivo")
    cidade_in = st.text_input("Nome da Cidade")
    uploaded_zip = st.file_uploader("Selecione o ZIP com os CSVs", type=["zip"])

    if uploaded_zip and cidade_in and st.button("🚀 ENVIAR E PUBLICAR"):
        resultados = {}
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "process.zip")
            with open(zip_path, "wb") as f: f.write(uploaded_zip.read())
            with zipfile.ZipFile(zip_path, "r") as z: z.extractall(tmpdir)
            
            for arq in [f for f in os.listdir(tmpdir) if f.endswith((".csv", ".xlsx"))]:
                cat = os.path.splitext(arq)[0]
                try:
                    df = pd.read_csv(os.path.join(tmpdir, arq)) if arq.endswith(".csv") else pd.read_excel(os.path.join(tmpdir, arq))
                    col_txt = "commentText" if "commentText" in df.columns else df.columns[3]
                    col_usr = "userName" if "userName" in df.columns else df.columns[1]

                    v_validos, users = [], set()
                    for _, row in df.iterrows():
                        votos = extrair_votos(row[col_txt])
                        u = normalizar(row[col_usr])
                        if u not in users and votos:
                            v_validos.append(votos[0])
                            users.add(u)
                    
                    if v_validos:
                        contagem = Counter(v_validos)
                        resultados[cat] = pd.DataFrame(contagem.items(), columns=["Candidato", "Votos"]).sort_values(by="Votos", ascending=False)
                except: continue

        if resultados and salvar_no_banco(cidade_in, resultados):
            st.success(f"✅ Dados de {cidade_in} publicados!"); st.balloons()
            st.rerun()

# --- MODO PÚBLICO (VISUALIZAÇÃO) ---
else:
    st.title("🔍 Resultados em Tempo Real")
    # O random.random força o Streamlit a ignorar o cache da lista de cidades
    cidades = listar_cidades(random.random()) 
    
    if not cidades:
        st.info("Nenhum dado encontrado. Acesse o modo Administrador para subir arquivos.")
    else:
        cidade_sel = st.selectbox("Escolha a Cidade:", cidades)
        
        # Busca votos da cidade selecionada
        res = supabase.table("resultados_votos").select("*").eq("cidade", cidade_sel).execute()
        df_votos = pd.DataFrame(res.data)

        if not df_votos.empty:
            for cat in df_votos['categoria'].unique():
                with st.expander(f"📊 CATEGORIA: {cat.upper()}", expanded=True):
                    # Processamento da categoria
                    dados_cat = df_votos[df_votos['categoria'] == cat]
                    total_votos_categoria = dados_cat['votos'].sum()
                    dados = dados_cat.sort_values(by="votos", ascending=False).head(3).reset_index(drop=True)
                    
                    # Gráfico
                    plt.close('all')
                    fig, ax = plt.subplots(figsize=(10, 7))
                    fig.patch.set_facecolor('#000000')
                    ax.set_facecolor('#000000')
                    
                    ordem, cores = [1, 0, 2], ["#FFD700", "#C0C0C0", "#CD7F32"]
                    
                    for i, row in dados.iterrows():
                        if i >= len(ordem): break
                        x, h = ordem[i], [0.9, 0.7, 0.5][i]
                        
                        # Cálculo da porcentagem apenas para exibição
                        p_val = round((row['votos'] / total_votos_categoria * 100), 1) if total_votos_categoria > 0 else 0

                        ax.bar(x, h, color=cores[i], width=0.8, edgecolor='white', linewidth=0.5)
                        ax.text(x, h + 0.05, f"@{row['candidato']}", color=cores[i], ha='center', weight='bold', fontsize=12)
                        
                        # EXIBE APENAS A PORCENTAGEM (conforme solicitado)
                        ax.text(x, h/2, f"{p_val}%", color='black', ha='center', weight='bold', fontsize=16)

                    ax.axis('off')
                    
                    # Gerar imagem em memória (Base64)
                    buf = io.BytesIO()
                    fig.savefig(buf, format="png", bbox_inches='tight', facecolor='#000000', dpi=150)
                    img_bytes = buf.getvalue()
                    
                    # Mostrar imagem
                    st.markdown(f'<img src="data:image/png;base64,{base64.b64encode(img_bytes).decode()}" style="width:100%; border: 1px solid #333; border-radius: 10px;">', unsafe_allow_html=True)
                    
                    # Botão de Download
                    st.download_button(
                        label=f"📥 Baixar Imagem ({cat})",
                        data=img_bytes,
                        file_name=f"{cidade_sel}_{cat}.png",
                        mime="image/png",
                        key=f"dl_{cat}_{random.randint(0,9999)}"
                    )
                    plt.close(fig)
