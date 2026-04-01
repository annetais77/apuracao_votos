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
from supabase import create_client, Client

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Portal de Apuração", layout="wide")

# --- CONEXÃO ---
SUPABASE_URL = "https://nualgtyikfijnjzmybsg.supabase.co"
SUPABASE_KEY = "sb_publishable_e9RRmaN-2XIryrki_lpWhA_uC5sHZ1K"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ESTILO ---
st.markdown("<style>.main {background-color: #000; color: #fff;}</style>", unsafe_allow_html=True)

# --- FUNÇÕES ---
def extrair_votos(texto):
    return [str(v).lower().strip().replace(" ", "") for v in re.findall(r'@[A-Za-z0-9_.-]+', str(texto))]

@st.cache_data(ttl=2)
def listar_cidades(check):
    try:
        res = supabase.table("resultados_votos").select("cidade").execute()
        return sorted(list(set([item['cidade'] for item in res.data])))
    except: return []

def criar_grafico_instagram(categoria, df_cat):
    """Gera o gráfico no formato 1080x1350 (Instagram Vertical)"""
    total = df_cat['votos'].sum()
    top3 = df_cat.sort_values("votos", ascending=False).head(3).reset_index(drop=True)
    
    plt.close('all')
    # Proporção 4:5 (10.8 x 13.5 polegadas a 100 DPI = 1080x1350px)
    fig, ax = plt.subplots(figsize=(10.8, 13.5))
    fig.patch.set_facecolor('#000000')
    ax.set_facecolor('#000000')
    
    # Pontos luminosos de fundo (Estrelas)
    for _ in range(150):
        ax.scatter(random.uniform(-0.6, 2.6), random.uniform(0, 1.2), 
                   alpha=random.uniform(0.1, 0.5), s=random.randint(5, 20), color="white")

    # TÍTULO DA CATEGORIA DENTRO DA IMAGEM
    ax.text(1, 1.1, categoria.upper(), color='white', fontsize=28, ha='center', weight='bold', alpha=0.9)
    ax.text(1, 1.05, "MELHORES DO ANO", color='#FFD700', fontsize=14, ha='center', ls='--', alpha=0.7)

    pos, cores = [1, 0, 2], ["#FFD700", "#C0C0C0", "#CD7F32"]
    alturas_podio = [0.85, 0.65, 0.45] # Alturas ajustadas para o formato vertical
    
    for i, row in top3.iterrows():
        if i >= len(pos): break
        x, h = pos[i], alturas_podio[i]
        pct = round((row['votos']/total*100), 1) if total > 0 else 0
        
        # Barra do Candidato
        ax.bar(x, h, color=cores[i], width=0.75, edgecolor='white', linewidth=1, zorder=3)
        
        # Nome do Candidato (Em cima da barra)
        ax.text(x, h + 0.03, f"@{row['candidato']}", color='white', ha='center', weight='bold', fontsize=18)
        
        # PORCENTAGEM (No meio da barra)
        ax.text(x, h/2, f"{pct}%", color='black', ha='center', weight='bold', fontsize=26, zorder=4)

    ax.set_xlim(-0.7, 2.7)
    ax.set_ylim(0, 1.25)
    ax.axis('off')
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.5, facecolor='#000000', dpi=100)
    plt.close(fig)
    return buf.getvalue()

# --- MENU LATERAL ---
with st.sidebar:
    st.title("🏆 Menu")
    modo = st.radio("Ir para:", ["🔍 Resultados", "⚙️ Painel ADM"])
    if modo == "⚙️ Painel ADM":
        if st.text_input("Senha", type="password") != "suasenha123": st.stop()

# --- MODO ADM ---
if modo == "⚙️ Painel ADM":
    t1, t2 = st.tabs(["🚀 Novo Upload", "✏️ Gerenciar Cidades"])
    with t1:
        st.subheader("Subir Dados")
        cid_nome = st.text_input("Nome da Cidade")
        arquivo = st.file_uploader("ZIP com CSVs", type="zip")
        if arquivo and cid_nome and st.button("PUBLICAR"):
            with tempfile.TemporaryDirectory() as tmp:
                z_path = os.path.join(tmp, "data.zip")
                with open(z_path, "wb") as f: f.write(arquivo.read())
                with zipfile.ZipFile(z_path, "r") as z: z.extractall(tmp)
                v_batch = []
                for f in [x for x in os.listdir(tmp) if x.endswith((".csv", ".xlsx"))]:
                    cat_n = os.path.splitext(f)[0]
                    df = pd.read_csv(os.path.join(tmp, f)) if f.endswith(".csv") else pd.read_excel(os.path.join(tmp, f))
                    col_txt = "commentText" if "commentText" in df.columns else df.columns[3]
                    col_usr = "userName" if "userName" in df.columns else df.columns[1]
                    cont = Counter(); u_v = set()
                    for _, r in df.iterrows():
                        v = extrair_votos(r[col_txt]); u = str(r[col_usr]).lower().strip()
                        if u not in u_v and v: cont[v[0]] += 1; u_v.add(u)
                    for cand, qtd in cont.items():
                        v_batch.append({"cidade": cid_nome.strip(), "categoria": cat_n, "candidato": cand, "votos": qtd})
                if v_batch:
                    supabase.table("resultados_votos").insert(v_batch).execute()
                    st.success("✅ Publicado!"); st.rerun()

    with t2:
        todas = listar_cidades(random.random())
        if todas:
            cid_sel = st.selectbox("Cidade:", todas)
            n_nome = st.text_input("Renomear para:")
            c1, c2 = st.columns(2)
            if c1.button("Salvar"):
                supabase.table("resultados_votos").update({"cidade": n_nome}).eq("cidade", cid_sel).execute()
                st.rerun()
            if c2.button("EXCLUIR"):
                supabase.table("resultados_votos").delete().eq("cidade", cid_sel).execute()
                st.rerun()

# --- MODO PÚBLICO ---
else:
    st.title("🔍 Resultados Oficiais")
    cidades = listar_cidades(random.random())
    if cidades:
        escolha = st.selectbox("Selecione a Cidade:", cidades)
        dados_raw = supabase.table("resultados_votos").select("*").eq("cidade", escolha).execute()
        df = pd.DataFrame(dados_raw.data)

        if not df.empty:
            st.success(f"Dados carregados para {escolha}!")
            
            # --- GERAR ZIP DE TODOS OS CARDS ---
            if st.button(f"📦 GERAR ZIP COM TODOS OS CARROSÉIS ({escolha})"):
                with st.spinner("Criando artes para o Instagram..."):
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w") as zf:
                        for cat in df['categoria'].unique():
                            img = criar_grafico_instagram(cat, df[df['categoria'] == cat])
                            zf.writestr(f"{cat}.png", img)
                    
                    st.download_button(
                        label="🔥 BAIXAR PACOTE DE IMAGENS (.ZIP)",
                        data=zip_buffer.getvalue(),
                        file_name=f"INSTAGRAM_{escolha}.zip",
                        mime="application/zip"
                    )
            
            st.divider()

            # --- PRÉVIA NA TELA (Só os 3 primeiros para carregar rápido) ---
            cats = df['categoria'].unique()
            for cat in cats[:3]:
                with st.expander(f"Ver prévia: {cat.upper()}"):
                    img = criar_grafico_instagram(cat, df[df['categoria'] == cat])
                    b64 = base64.b64encode(img).decode()
                    st.write(f'<img src="data:image/png;base64,{b64}" style="width:100%; max-width:400px; border:1px solid #333;">', unsafe_allow_html=True)
