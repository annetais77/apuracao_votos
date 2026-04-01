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

# --- FUNÇÕES ---
def extrair_votos(texto):
    """Extrai @menções e limpa espaços"""
    return [str(v).lower().strip().replace(" ", "") for v in re.findall(r'@[A-Za-z0-9_.-]+', str(texto))]

def listar_cidades():
    """Busca cidades no banco em tempo real"""
    try:
        res = supabase.table("resultados_votos").select("cidade").execute()
        return sorted(list(set([item['cidade'] for item in res.data])))
    except:
        return []

def criar_grafico_instagram(categoria, df_cat):
    """Gera arte 1080x1350 para Instagram"""
    total = df_cat['votos'].sum()
    top3 = df_cat.sort_values("votos", ascending=False).head(3).reset_index(drop=True)
    
    plt.close('all')
    fig, ax = plt.subplots(figsize=(10.8, 13.5))
    fig.patch.set_facecolor('#000000')
    ax.set_facecolor('#000000')
    
    # Pontos luminosos (Estrelas)
    for _ in range(150):
        ax.scatter(random.uniform(-0.6, 2.6), random.uniform(0, 1.2), 
                   alpha=random.uniform(0.1, 0.5), s=random.randint(5, 25), color="white")

    # Títulos (SEM o erro de 'ls')
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

# --- SIDEBAR ---
with st.sidebar:
    st.title(f"🏆 Menu de {escolha if 'escolha' in locals() else 'Apuração'}")
    modo = st.radio("Navegação:", ["🔍 Resultados Públicos", "⚙️ Painel ADM"])
    
    st.divider()
    if st.button("🔄 Sincronizar Banco"):
        st.cache_data.clear()
        st.rerun()

    if modo == "⚙️ Painel ADM":
        senha = st.text_input("Senha", type="password")
        if senha != "suasenha123":
            st.stop()

# --- MODO ADMINISTRADOR ---
if modo == "⚙️ Painel ADM":
    st.header("⚙️ Gerenciamento")
    t1, t2 = st.tabs(["🚀 Publicar Cidade", "✏️ Editar/Excluir"])
    
    with t1:
        cidade_in = st.text_input("Nome da Cidade")
        arquivo = st.file_uploader("Subir ZIP com CSVs", type="zip")
        
        if arquivo and cidade_in and st.button("🚀 PUBLICAR AGORA"):
            with tempfile.TemporaryDirectory() as tmp:
                z_path = os.path.join(tmp, "up.zip")
                with open(z_path, "wb") as f: f.write(arquivo.read())
                with zipfile.ZipFile(z_path, "r") as z: z.extractall(tmp)
                
                payload = []
                for f in [x for x in os.listdir(tmp) if x.endswith((".csv", ".xlsx"))]:
                    cat = os.path.splitext(f)[0]
                    df = pd.read_csv(os.path.join(tmp, f)) if f.endswith(".csv") else pd.read_excel(os.path.join(tmp, f))
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
                    # Limpa apenas esta cidade antes de inserir
                    supabase.table("resultados_votos").delete().eq("cidade", cidade_in.strip()).execute()
                    supabase.table("resultados_votos").insert(payload).execute()
                    st.cache_data.clear()
                    st.success(f"✅ {cidade_in} publicado!")
                    st.balloons()

    with t2:
        cidades_list = listar_cidades()
        if cidades_list:
            sel = st.selectbox("Escolha uma cidade:", cidades_list)
            novo_n = st.text_input("Novo nome para renomear:")
            c1, c2 = st.columns(2)
            
            if c1.button("💾 Salvar Nome"):
                if novo_n:
                    supabase.table("resultados_votos").update({"cidade": novo_n.strip()}).eq("cidade", sel).execute()
                    st.cache_data.clear(); st.rerun()
            
            if c2.button("🗑️ DELETAR CIDADE"):
                supabase.table("resultados_votos").delete().eq("cidade", sel).execute()
                st.cache_data.clear(); st.rerun()

# --- MODO PÚBLICO ---
else:
    st.title("🔍 Resultados")
    cidades_pub = listar_cidades()
    
    if not cidades_pub:
        st.info("Nenhum dado disponível.")
    else:
        escolha = st.selectbox("Selecione:", ["-- Escolha --"] + cidades_pub)
        if escolha != "-- Escolha --":
            res = supabase.table("resultados_votos").select("*").eq("cidade", escolha).execute()
            df_res = pd.DataFrame(res.data)
            
            if not df_res.empty:
                st.subheader(f"📍 {escolha}")
                
                if st.button(f"📦 BAIXAR TODOS OS CARROSÉIS ({escolha})"):
                    with st.spinner("Gerando imagens..."):
                        z_mem = io.BytesIO()
                        with zipfile.ZipFile(z_mem, "w") as zf:
                            for c in df_res['categoria'].unique():
                                img = criar_grafico_instagram(c, df_res[df_res['categoria'] == c])
                                zf.writestr(f"{c}.png", img)
                        st.download_button("🔥 DOWNLOAD ZIP", z_mem.getvalue(), f"{escolha}.zip", "application/zip")
                
                st.divider()
                # Mostra prévia das 3 primeiras
                for cat in df_res['categoria'].unique()[:3]:
                    with st.expander(f"Ver prévia: {cat.upper()}"):
                        img_p = criar_grafico_instagram(cat, df_res[df_res['categoria'] == cat])
                        st.write(f'<img src="data:image/png;base64,{base64.b64encode(img_p).decode()}" style="width:100%; max-width:400px;">', unsafe_allow_html=True)
