import streamlit as st
import pandas as pd
import zipfile
import os
import tempfile
import re
import io
import random
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
def extrair_votos(texto, autor=None):
    if pd.isna(texto): return []
    mencoes = [str(v).lower().strip().replace(" ", "") for v in re.findall(r'@[A-Za-z0-9_.-]+', str(texto))]
    if autor:
        autor_limpo = f"@{str(autor).lower().strip()}"
        mencoes = [m for m in mencoes if m != autor_limpo]
    return mencoes

def listar_cidades():
    try:
        res = supabase.rpc("obter_cidades_unicas").execute()
        return [item['nome_cidade'] for item in res.data if item.get('nome_cidade')] if res.data else []
    except Exception as e:
        return []

def criar_grafico_instagram(categoria, df_cat):
    # Ranking com tratamento de empate (method='min')
    df_sorted = df_cat.sort_values("votos", ascending=False).reset_index(drop=True)
    df_sorted['rank'] = df_sorted['votos'].rank(method='min', ascending=False).astype(int)
    
    total = df_sorted['votos'].sum()
    top3_df = df_sorted.head(3)
    
    plt.close('all')
    fig, ax = plt.subplots(figsize=(10.8, 13.5))
    fig.patch.set_facecolor('#000000')
    ax.set_facecolor('#000000')
    
    for _ in range(150):
        ax.scatter(random.uniform(-0.6, 2.6), random.uniform(0, 1.2), alpha=0.3, s=15, color="white")

    ax.text(1, 1.18, str(categoria).upper(), color='white', fontsize=32, ha='center', weight='bold')
    
    # Mapeamento para empates (Rank 1 = Ouro, Rank 2 = Prata, etc)
    mapa_cores = {1: "#FFD700", 2: "#C0C0C0", 3: "#CD7F32"}
    mapa_alturas = {1: 0.85, 2: 0.65, 3: 0.45}
    pos_x = [1, 0, 2]
    
    for i, (_, row) in enumerate(top3_df.iterrows()):
        rank = row['rank']
        cor = mapa_cores.get(rank, "#CD7F32")
        altura = mapa_alturas.get(rank, 0.45)
        
        x = pos_x[i]
        pct = round((row['votos']/total*100), 1) if total > 0 else 0
        
        ax.bar(x, altura, color=cor, width=0.75, edgecolor='white', linewidth=2, zorder=3)
        ax.text(x, altura + 0.03, str(row['candidato']), color='white', ha='center', weight='bold', fontsize=18)
        ax.text(x, altura/2, f"{pct}%", color='black', ha='center', weight='black', fontsize=24, zorder=4)

    ax.set_xlim(-0.8, 2.8); ax.set_ylim(0, 1.3); ax.axis('off')
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.5, facecolor='#000000', dpi=100)
    plt.close(fig)
    return buf.getvalue()

# --- SIDEBAR ---
with st.sidebar:
    st.title("🏆 Painel Anne")
    modo = st.radio("Navegação:", ["🔍 Resultados Públicos", "⚙️ Painel ADM"])
    if st.button("🔄 Sincronizar Banco"):
        st.cache_data.clear()
        st.rerun()

# --- MODO ADMINISTRADOR ---
if modo == "⚙️ Painel ADM":
    if st.text_input("Senha", type="password") == "123":
        t1, t2, t3, t5 = st.tabs(["🚀 Upload", "👁️ Preview", "✏️ Gerenciar", "🔧 Corrigir"])
        with t1:
            cid_in = st.text_input("Nome da Cidade")
            arq = st.file_uploader("Subir ZIP", type="zip")
            if arq and cid_in and st.button("PUBLICAR"):
                with tempfile.TemporaryDirectory() as tmp:
                    z_path = os.path.join(tmp, "u.zip")
                    with open(z_path, "wb") as f: f.write(arq.read())
                    with zipfile.ZipFile(z_path, "r") as z: z.extractall(tmp)
                    arquivos = [x for x in os.listdir(tmp) if x.endswith((".csv", ".xlsx"))]
                    pay = []
                    for f in arquivos:
                        df = pd.read_csv(os.path.join(tmp, f)) if f.endswith(".csv") else pd.read_excel(os.path.join(tmp, f))
                        c_t = next((c for c in df.columns if 'comment' in c.lower() or 'text' in c.lower()), df.columns[3])
                        c_u = next((c for c in df.columns if 'user' in c.lower() or 'name' in c.lower()), df.columns[1])
                        ct, vs = Counter(), set()
                        for _, r in df.iterrows():
                            u = str(r[c_u]).lower().strip()
                            v = extrair_votos(r[c_t], autor=u)
                            if u not in vs and v: ct[v[0]] += 1; vs.add(u)
                        pay.extend([{"cidade": cid_in.strip(), "categoria": os.path.splitext(f)[0], "candidato": cand, "votos": qtd} for cand, qtd in ct.items()])
                    
                    if pay:
                        supabase.table("resultados_votos").delete().eq("cidade", cid_in.strip()).execute()
                        supabase.table("resultados_votos").insert(pay).execute()
                        st.success(f"✅ {len(pay)} registros salvos em {cid_in}!"); st.cache_data.clear()
        with t2:
            arq_u = st.file_uploader("Arquivo da Categoria", type=["csv", "xlsx"])
            nome_cat = st.text_input("Nome da Categoria")
            if arq_u and nome_cat:
                df_u = pd.read_csv(arq_u) if arq_u.name.endswith(".csv") else pd.read_excel(arq_u)
                c_t = next((c for c in df_u.columns if 'comment' in c.lower() or 'text' in c.lower()), df_u.columns[3])
                c_u = next((c for c in df_u.columns if 'user' in c.lower() or 'name' in c.lower()), df_u.columns[1])
                ct_u, vs_u = Counter(), set()
                for _, r in df_u.iterrows():
                    u = str(r[c_u]).lower().strip(); v = extrair_votos(r[c_t], autor=u)
                    if u not in vs_u and v: ct_u[v[0]] += 1; vs_u.add(u)
                if ct_u:
                    df_p = pd.DataFrame([{"candidato": k, "votos": v} for k, v in ct_u.items()]).sort_values("votos", ascending=False)
                    st.table(df_p)
                    img = criar_grafico_instagram(nome_cat, df_p)
                    st.image(img); st.download_button("BAIXAR GRÁFICO", img, f"{nome_cat}.png")
        with t3:
            c_lista = listar_cidades()
            if c_lista:
                sel = st.selectbox("Selecione:", c_lista)
                if st.button("DELETAR TUDO"): supabase.table("resultados_votos").delete().eq("cidade", sel).execute(); st.rerun()

# --- MODO PÚBLICO ---
else:
    st.title("🔍 Resultados")
    cidades = listar_cidades()
    if cidades:
        escolha = st.selectbox("Escolha a Cidade:", ["-- Selecione --"] + cidades)
        if escolha != "-- Selecione --":
            res = supabase.table("resultados_votos").select("*").eq("cidade", escolha).execute()
            df = pd.DataFrame(res.data)
            if not df.empty:
                if st.button("📦 PREPARAR DOWNLOAD (ZIP)"):
                    with st.spinner("Gerando gráficos..."):
                        z_buf = io.BytesIO()
                        with zipfile.ZipFile(z_buf, "w") as zf:
                            for cat in df['categoria'].unique():
                                img_bytes = criar_grafico_instagram(cat, df[df['categoria'] == cat])
                                zf.writestr(f"{cat}.png", img_bytes)
                        st.download_button("📥 BAIXAR ZIP AGORA", z_buf.getvalue(), f"{escolha}_graficos.zip", "application/zip")
            for cat in df['categoria'].unique():
                with st.expander(f"Ver categoria: {cat.upper()}"):
                    img = criar_grafico_instagram(cat, df[df['categoria'] == cat])
                    st.image(img, use_container_width=True)
