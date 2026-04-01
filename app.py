import streamlit as st
import pandas as pd
import zipfile
import os
import tempfile
import re
import io
import random
import base64
import matplotlib.pyplot as plt
from collections import Counter
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
def extrair_votos(texto):
    return [str(v).lower().strip().replace(" ", "") for v in re.findall(r'@[A-Za-z0-9_.-]+', str(texto))]

def listar_cidades():
    """Busca cidades no banco sem cache e com limite aumentado"""
    try:
        # Aumentamos o limite para 5000 para garantir que pegue tudo
        res = supabase.table("resultados_votos").select("cidade").limit(5000).execute()
        if res.data:
            # Extrai os nomes, remove nulos/vazios e limpa duplicatas
            nomes = [item['cidade'] for item in res.data if item['cidade']]
            return sorted(list(set(nomes)))
        return []
    except Exception as e:
        st.error(f"Erro ao carregar cidades: {e}")
        return []

def criar_grafico_instagram(categoria, df_cat):
    """Gera a arte no formato 1080x1350 para Instagram"""
    total = df_cat['votos'].sum()
    top3 = df_cat.sort_values("votos", ascending=False).head(3).reset_index(drop=True)
    
    plt.close('all')
    fig, ax = plt.subplots(figsize=(10.8, 13.5))
    fig.patch.set_facecolor('#000000')
    ax.set_facecolor('#000000')
    
    # Efeito estelar de fundo
    for _ in range(150):
        ax.scatter(random.uniform(-0.6, 2.6), random.uniform(0, 1.2), 
                   alpha=random.uniform(0.1, 0.5), s=random.randint(5, 25), color="white")

    # Títulos
    ax.text(1, 1.18, categoria.upper(), color='white', fontsize=32, ha='center', weight='bold')
    ax.text(1, 1.12, "MELHORES DO ANO", color='#FFD700', fontsize=16, ha='center', alpha=0.8)

    pos, cores = [1, 0, 2], ["#FFD700", "#C0C0C0", "#CD7F32"]
    alturas = [0.85, 0.65, 0.45] 
    
    for i, row in top3.iterrows():
        if i >= len(pos): break
        x, h = pos[i], alturas[i]
        pct = round((row['votos']/total*100), 1) if total > 0 else 0
        
        ax.bar(x, h, color=cores[i], width=0.75, edgecolor='white', linewidth=1.5, zorder=3)
        ax.text(x, h + 0.03, f"@{row['candidato']}", color='white', ha='center', weight='bold', fontsize=20)
        ax.text(x, h/2, f"{pct}%", color='black', ha='center', weight='black', fontsize=28, zorder=4)

    ax.set_xlim(-0.8, 2.8); ax.set_ylim(0, 1.3); ax.axis('off')
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.5, facecolor='#000000', dpi=100)
    plt.close(fig)
    return buf.getvalue()

# --- MENU LATERAL ---
with st.sidebar:
    st.title("🏆 Painel Anne")
    modo = st.radio("Navegação:", ["🔍 Resultados Públicos", "⚙️ Painel ADM"])
    
    st.divider()
    if st.button("🔄 Sincronizar Banco"):
        st.cache_data.clear()
        st.rerun()

    if modo == "⚙️ Painel ADM":
        senha = st.text_input("Senha", type="password")
        if senha != "suasenha123": # Mude sua senha aqui
            st.stop()

# --- MODO ADMINISTRADOR ---
if modo == "⚙️ Painel ADM":
    st.header("⚙️ Área do Administrador")
    t1, t2, t3 = st.tabs(["🚀 Novo Upload", "✏️ Gerenciar", "📊 Cidades no Banco"])
    
    with t1:
        cidade_in = st.text_input("Nome da Cidade")
        arquivo = st.file_uploader("Subir ZIP com CSVs", type="zip")
        
        if arquivo and cidade_in and st.button("🚀 PUBLICAR"):
            with tempfile.TemporaryDirectory() as tmp:
                z_path = os.path.join(tmp, "up.zip")
                with open(z_path, "wb") as f: f.write(arquivo.read())
                with zipfile.ZipFile(z_path, "r") as z: z.extractall(tmp)
                
                payload = []
                for f in [x for x in os.listdir(tmp) if x.endswith((".csv", ".xlsx"))]:
                    cat = os.path.splitext(f)[0]
                    df = pd.read_csv(os.path.join(tmp, f)) if f.endswith(".csv") else pd.read_excel(os.path.join(tmp, f))
                    
                    # Identificação de colunas
                    col_txt = "commentText" if "commentText" in df.columns else df.columns[3]
                    col_usr = "userName" if "userName" in df.columns else df.columns[1]
                    
                    cont, vistos = Counter(), set()
                    for _, r in df.iterrows():
                        v = extrair_votos(r[col_txt]); u = str(r[col_usr]).lower().strip()
                        if u not in vistos and v:
                            cont[v[0]] += 1; vistos.add(u)
                    
                    for cand, qtd in cont.items():
                        payload.append({"cidade": cidade_in.strip(), "categoria": cat, "candidato": cand, "votos": qtd})
                
                if payload:
                    # Deleta a cidade antiga e insere a nova
                    supabase.table("resultados_votos").delete().eq("cidade", cidade_in.strip()).execute()
                    supabase.table("resultados_votos").insert(payload).execute()
                    st.cache_data.clear()
                    st.success(f"✅ {cidade_in} publicado com sucesso!"); st.balloons()

    with t2:
        cidades_list = listar_cidades()
        if cidades_list:
            sel = st.selectbox("Escolha uma cidade para excluir:", cidades_list)
            if st.button("🗑️ DELETAR TUDO DESTA CIDADE"):
                supabase.table("resultados_votos").delete().eq("cidade", sel).execute()
                st.cache_data.clear(); st.rerun()

    with t3:
        st.subheader("Cidades encontradas no Banco:")
        cidades_bd = listar_cidades()
        if cidades_bd:
            for c in cidades_bd:
                st.write(f"📍 {c}")
        else:
            st.info("Nenhuma cidade no banco.")

# --- MODO PÚBLICO ---
else:
    st.title("🔍 Resultados Oficiais")
    cidades_pub = listar_cidades()
    
    if not cidades_pub:
        st.info("Aguardando novas publicações...")
    else:
        escolha = st.selectbox("Selecione a Cidade:", ["-- Selecione --"] + cidades_pub)
        
        if escolha != "-- Selecione --":
            res = supabase.table("resultados_votos").select("*").eq("cidade", escolha).execute()
            df_res = pd.DataFrame(res.data)
            
            if not df_res.empty:
                if st.button(f"📦 BAIXAR ZIP ({escolha})"):
                    z_mem = io.BytesIO()
                    with zipfile.ZipFile(z_mem, "w") as zf:
                        for c in df_res['categoria'].unique():
                            img = criar_grafico_instagram(c, df_res[df_res['categoria'] == c])
                            zf.writestr(f"{c}.png", img)
                    st.download_button("🔥 DOWNLOAD ZIP", z_mem.getvalue(), f"{escolha}.zip", "application/zip")
                
                st.divider()
                for cat in df_res['categoria'].unique()[:3]:
                    with st.expander(f"Ver prévia: {cat.upper()}"):
                        img_p = criar_grafico_instagram(cat, df_res[df_res['categoria'] == cat])
                        st.write(f'<img src="data:image/png;base64,{base64.b64encode(img_p).decode()}" style="width:100%; max-width:400px;">', unsafe_allow_html=True)
