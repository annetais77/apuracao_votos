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

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Portal de Apuração", layout="wide", page_icon="🏆")

# --- CONEXÃO ---
SUPABASE_URL = "https://nualgtyikfijnjzmybsg.supabase.co"
SUPABASE_KEY = "sb_publishable_e9RRmaN-2XIryrki_lpWhA_uC5sHZ1K"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ESTILO ---
st.markdown("<style>.main {background-color: #000; color: #fff;}</style>", unsafe_allow_html=True)

# --- FUNÇÕES ---
def extrair_votos(texto):
    return [str(v).lower().strip().replace(" ", "") for v in re.findall(r'@[A-Za-z0-9_.-]+', str(texto))]

def listar_cidades():
    """Busca cidades ignorando qualquer tipo de cache ou limite padrão"""
    try:
        # Forçamos uma consulta limpa e ampla
        res = supabase.table("resultados_votos").select("cidade").limit(10000).execute()
        if res.data:
            # Filtramos nomes vazios e removemos espaços extras
            nomes = [str(item['cidade']).strip() for item in res.data if item.get('cidade')]
            # Set remove duplicatas, sorted organiza de A-Z
            return sorted(list(set(nomes)))
        return []
    except Exception as e:
        st.error(f"Erro de Conexão: {e}")
        return []

def criar_grafico_instagram(categoria, df_cat):
    total = df_cat['votos'].sum()
    top3 = df_cat.sort_values("votos", ascending=False).head(3).reset_index(drop=True)
    plt.close('all')
    fig, ax = plt.subplots(figsize=(10.8, 13.5))
    fig.patch.set_facecolor('#000000')
    ax.set_facecolor('#000000')
    for _ in range(150):
        ax.scatter(random.uniform(-0.6, 2.6), random.uniform(0, 1.2), 
                   alpha=random.uniform(0.1, 0.5), s=random.randint(5, 25), color="white")
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
    st.title("🏆 Painel Anne")
    modo = st.radio("Ir para:", ["🔍 Resultados Públicos", "⚙️ Painel ADM"])
    st.divider()
    if st.button("🔄 LIMPAR CACHE E ATUALIZAR"):
        st.cache_data.clear()
        st.rerun()

# --- MODO ADM ---
if modo == "⚙️ Painel ADM":
    senha = st.text_input("Senha", type="password")
    if senha == "suasenha123":
        t1, t2, t3 = st.tabs(["🚀 Upload", "✏️ Gerenciar", "📊 Ver Banco"])
        
        with t1:
            cid_in = st.text_input("Nome da Cidade")
            arq = st.file_uploader("Arquivo ZIP", type="zip")
            if arq and cid_in and st.button("🚀 PUBLICAR"):
                with tempfile.TemporaryDirectory() as tmp:
                    z_path = os.path.join(tmp, "u.zip")
                    with open(z_path, "wb") as f: f.write(arq.read())
                    with zipfile.ZipFile(z_path, "r") as z: z.extractall(tmp)
                    pay = []
                    for f in [x for x in os.listdir(tmp) if x.endswith((".csv", ".xlsx"))]:
                        cat = os.path.splitext(f)[0]
                        df = pd.read_csv(os.path.join(tmp, f)) if f.endswith(".csv") else pd.read_excel(os.path.join(tmp, f))
                        c_t = "commentText" if "commentText" in df.columns else df.columns[3]
                        c_u = "userName" if "userName" in df.columns else df.columns[1]
                        ct, vs = Counter(), set()
                        for _, r in df.iterrows():
                            v = extrair_votos(r[c_t]); u = str(r[c_u]).lower().strip()
                            if u not in vs and v: ct[v[0]] += 1; vs.add(u)
                        for cand, qtd in ct.items():
                            pay.append({"cidade": cid_in.strip(), "categoria": cat, "candidato": cand, "votos": qtd})
                    if pay:
                        supabase.table("resultados_votos").delete().eq("cidade", cid_in.strip()).execute()
                        supabase.table("resultados_votos").insert(pay).execute()
                        st.cache_data.clear()
                        st.success("Publicado!"); st.rerun()

        with t2:
            lista = listar_cidades()
            if lista:
                sel = st.selectbox("Selecione para excluir:", lista)
                if st.button("🗑️ DELETAR"):
                    supabase.table("resultados_votos").delete().eq("cidade", sel).execute()
                    st.cache_data.clear(); st.rerun()

        with t3:
            st.write("Cidades no Banco de Dados (Tempo Real):")
            cidades_reais = listar_cidades()
            for c in cidades_reais:
                st.write(f"📍 {c}")
    else:
        st.warning("Insira a senha.")

# --- MODO PÚBLICO ---
else:
    st.title("🔍 Resultados")
    cidades_disponiveis = listar_cidades()
    if not cidades_disponiveis:
        st.info("Nenhuma cidade encontrada.")
    else:
        escolha = st.selectbox("Escolha a Cidade:", ["-- Selecione --"] + cidades_disponiveis)
        if escolha != "-- Selecione --":
            res = supabase.table("resultados_votos").select("*").eq("cidade", escolha).execute()
            df = pd.DataFrame(res.data)
            if not df.empty:
                if st.button(f"📦 GERAR ZIP ({escolha})"):
                    z_buf = io.BytesIO()
                    with zipfile.ZipFile(z_buf, "w") as zf:
                        for c in df['categoria'].unique():
                            img = criar_grafico_instagram(c, df[df['categoria'] == c])
                            zf.writestr(f"{c}.png", img)
                    st.download_button("📥 BAIXAR ZIP", z_buf.getvalue(), f"{escolha}.zip", "application/zip")
                st.divider()
                for cat in df['categoria'].unique()[:3]:
                    with st.expander(f"Ver: {cat.upper()}"):
                        img = criar_grafico_instagram(cat, df[df['categoria'] == cat])
                        st.write(f'<img src="data:image/png;base64,{base64.b64encode(img).decode()}" style="width:100%;">', unsafe_allow_html=True)
