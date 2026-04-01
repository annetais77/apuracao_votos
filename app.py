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

# --- FUNÇÕES ---
def normalizar(texto):
    return str(texto).lower().strip().replace(" ", "")

def extrair_votos(texto):
    return [normalizar(v) for v in re.findall(r'@[A-Za-z0-9_.-]+', str(texto))]

def salvar_no_banco(cidade, resultados_dict):
    payload = []
    for cat, df_cat in resultados_dict.items():
        total_votos_cat = df_cat["Votos"].sum()
        for _, row in df_cat.iterrows():
            # Calcula porcentagem para salvar (backup)
            porcentagem = (row["Votos"] / total_votos_cat * 100) if total_votos_cat > 0 else 0
            payload.append({
                "cidade": cidade.strip(), 
                "categoria": cat,
                "candidato": row["Candidato"], 
                "votos": int(row["Votos"]),
                "porcentagem": float(round(porcentagem, 1))
            })
    if payload:
        try:
            supabase.table("resultados_votos").insert(payload).execute()
            st.cache_data.clear()
            return True
        except: return False
    return False

@st.cache_data(ttl=10)
def listar_cidades():
    try:
        res = supabase.table("resultados_votos").select("cidade").execute()
        return sorted(list(set([item['cidade'] for item in res.data])))
    except: return []

# --- MENU ---
with st.sidebar:
    modo = st.radio("Acesso:", ["🔍 Ver Resultados", "⚙️ Administrador"])
    if modo == "⚙️ Administrador":
        if st.text_input("Senha", type="password") != "suasenha123": st.stop()

# --- MODO ADMIN ---
if modo == "⚙️ Administrador":
    st.header("⚙️ Upload de Dados")
    cidade_in = st.text_input("Cidade")
    uploaded_zip = st.file_uploader("Arquivo ZIP", type=["zip"])

    if uploaded_zip and cidade_in and st.button("🚀 PUBLICAR"):
        resultados = {}
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "arq.zip")
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
            st.success("✅ Publicado!"); st.balloons(); st.rerun()

# --- MODO PÚBLICO ---
else:
    st.title("🔍 Resultados")
    cidades = listar_cidades()
    if cidades:
        cidade_sel = st.selectbox("Cidade:", cidades)
        res = supabase.table("resultados_votos").select("*").eq("cidade", cidade_sel).execute()
        df_votos = pd.DataFrame(res.data)

        if not df_votos.empty:
            for cat in df_votos['categoria'].unique():
                with st.expander(f"📊 {cat.upper()}", expanded=True):
                    # Filtra e ordena
                    dados_cat = df_votos[df_votos['categoria'] == cat]
                    total_cat = dados_cat['votos'].sum()
                    dados = dados_cat.sort_values(by="votos", ascending=False).head(3).reset_index(drop=True)
                    
                    plt.close('all')
                    fig, ax = plt.subplots(figsize=(10, 8))
                    fig.patch.set_facecolor('#000000')
                    ax.set_facecolor('#000000')
                    
                    ordem, cores = [1, 0, 2], ["#FFD700", "#C0C0C0", "#CD7F32"]
                    
                    for i, row in dados.iterrows():
                        if i >= len(ordem): break
                        x, h = ordem[i], [0.9, 0.7, 0.5][i]
                        
                        # --- CÁLCULO SEGURO DA PORCENTAGEM ---
                        # Se a coluna existir no banco usa ela, senão calcula na hora
                        if 'porcentagem' in row and row['porcentagem'] > 0:
                            p_val = row['porcentagem']
                        else:
                            p_val = round((row['votos'] / total_cat * 100), 1) if total_cat > 0 else 0

                        ax.bar(x, h, color=cores[i], width=0.8)
                        ax.text(x, h + 0.05, f"@{row['candidato']}", color=cores[i], ha='center', weight='bold', fontsize=12)
                        
                        txt_votos = f"{int(row['votos'])} votos\n({p_val}%)"
                        ax.text(x, h/2, txt_votos, color='black', ha='center', weight='bold', fontsize=11)

                    ax.axis('off')
                    
                    # Buffer para imagem
                    buf = io.BytesIO()
                    fig.savefig(buf, format="png", bbox_inches='tight', facecolor='#000000', dpi=150)
                    img_data = buf.getvalue()
                    
                    # Exibição Base64
                    st.markdown(f'<img src="data:image/png;base64,{base64.b64encode(img_data).decode()}" width="100%">', unsafe_allow_html=True)
                    
                    # Download
                    st.download_button(
                        label=f"📥 Baixar Card: {cat}",
                        data=img_data,
                        file_name=f"resultado_{cidade_sel}_{cat}.png",
                        mime="image/png",
                        key=f"btn_{cat}_{random.randint(0,999)}"
                    )
                    plt.close(fig)
