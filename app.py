import streamlit as st
import pandas as pd
import zipfile, os, tempfile, re, io, random
import matplotlib.pyplot as plt
from collections import Counter
from supabase import create_client, Client

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Portal de Apuração", layout="wide", page_icon="🏆")
SUPABASE_URL = "https://nualgtyikfijnjzmybsg.supabase.co"
SUPABASE_KEY = "sb_publishable_e9RRmaN-2XIryrki_lpWhA_uC5sHZ1K"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- FUNÇÕES ---
def extrair_votos(texto, autor=None):
    if pd.isna(texto): return []
    mencoes = [str(v).lower().strip().replace(" ", "") for v in re.findall(r'@[A-Za-z0-9_.-]+', str(texto))]
    if autor:
        autor_limpo = f"@{str(autor).lower().strip()}"
        mencoes = [m for m in mencoes if m != autor_limpo]
    return mencoes

def listar_cidades():
    try:
        res = supabase.table("resultados_votos").select("cidade").execute()
        return sorted(list(set([item['cidade'] for item in res.data if item.get('cidade')])))
    except: return []

# Gráfico usado APENAS no ZIP
def criar_grafico_instagram(categoria, df_cat):
    df_sorted = df_cat.sort_values("votos", ascending=False).reset_index(drop=True)
    df_sorted['rank'] = df_sorted['votos'].rank(method='min', ascending=False).astype(int)
    total = df_sorted['votos'].sum()
    top3_df = df_sorted.head(3)
    
    plt.close('all')
    fig, ax = plt.subplots(figsize=(10.8, 13.5))
    fig.patch.set_facecolor('#000000'); ax.set_facecolor('#000000')
    for _ in range(150): ax.scatter(random.uniform(-0.6, 2.6), random.uniform(0, 1.2), alpha=0.3, s=15, color="white")
    ax.text(1, 1.18, str(categoria).upper(), color='white', fontsize=32, ha='center', weight='bold')
    
    mapa_cores = {1: "#FFD700", 2: "#C0C0C0", 3: "#CD7F32"}
    mapa_alturas = {1: 0.85, 2: 0.65, 3: 0.45}
    pos_x = [1, 0, 2]
    
    for i, (_, row) in enumerate(top3_df.iterrows()):
        rank = row['rank']
        cor, altura = mapa_cores.get(rank, "#CD7F32"), mapa_alturas.get(rank, 0.45)
        pct = round((row['votos']/total*100), 1) if total > 0 else 0
        ax.bar(pos_x[i], altura, color=cor, width=0.75, edgecolor='white', linewidth=2, zorder=3)
        ax.text(pos_x[i], altura + 0.03, str(row['candidato']), color='white', ha='center', weight='bold', fontsize=18)
        ax.text(pos_x[i], altura/2, f"{pct}%", color='black', ha='center', weight='black', fontsize=24, zorder=4)
    ax.set_xlim(-0.8, 2.8); ax.set_ylim(0, 1.3); ax.axis('off')
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.5, facecolor='#000000', dpi=100)
    return buf.getvalue()

# --- INTERFACE ---
modo = st.sidebar.radio("Navegação:", ["🔍 Resultados Públicos", "⚙️ Painel ADM"])

if modo == "⚙️ Painel ADM":
    if st.text_input("Senha", type="password") == "123":
        t1, t2, t3 = st.tabs(["🚀 Upload", "✏️ Gerenciar Cidades", "🔧 Corrigir Votos"])
        
        with t1: # UPLOAD
            cid_in = st.text_input("Nome da Cidade")
            arq = st.file_uploader("ZIP", type="zip")
            if arq and cid_in and st.button("PUBLICAR"):
                with tempfile.TemporaryDirectory() as tmp:
                    zipfile.ZipFile(arq, "r").extractall(tmp)
                    pay = []
                    for f in [x for x in os.listdir(tmp) if x.endswith((".csv", ".xlsx"))]:
                        df = pd.read_csv(os.path.join(tmp, f)) if f.endswith(".csv") else pd.read_excel(os.path.join(tmp, f))
                        c_t, c_u = df.columns[-1], df.columns[1]
                        ct = Counter()
                        for _, r in df.iterrows():
                            v = extrair_votos(r[c_t], autor=str(r[c_u]))
                            if v: ct[v[0]] += 1
                        pay.extend([{"cidade": cid_in, "categoria": os.path.splitext(f)[0], "candidato": c, "votos": v} for c, v in ct.items()])
                    supabase.table("resultados_votos").delete().eq("cidade", cid_in).execute()
                    supabase.table("resultados_votos").insert(pay).execute()
                    st.success("✅ Cidade publicada com sucesso!"); st.rerun()

        with t2: # GERENCIAR
            sel = st.selectbox("Selecione para Deletar:", listar_cidades())
            if st.button("DELETAR CIDADE"):
                supabase.table("resultados_votos").delete().eq("cidade", sel).execute(); st.rerun()

        with t3: # CORRIGIR
            c_sel = st.selectbox("Cidade para corrigir:", listar_cidades())
            res = supabase.table("resultados_votos").select("*").eq("cidade", c_sel).execute()
            df = pd.DataFrame(res.data)
            st.table(df[['categoria', 'candidato', 'votos']].sort_values(['categoria', 'votos'], ascending=[True, False]))

else: # PÚBLICO - OTIMIZADO (SEM CARREGAR GRÁFICOS)
    st.title("🔍 Resultados")
    cidades = listar_cidades()
    escolha = st.selectbox("Selecione a cidade:", ["-- Escolha --"] + cidades)
    
    if escolha != "-- Escolha --":
        res = supabase.table("resultados_votos").select("*").eq("cidade", escolha).execute()
        df = pd.DataFrame(res.data)
        
        # AQUI É A MÁGICA DA PERFORMANCE:
        # Mostramos apenas os dados em tabela ou texto, sem Matplotlib (que pesa)
        # O gráfico só é gerado no botão de ZIP abaixo
        
        if st.button("📦 GERAR E BAIXAR ZIP COM GRÁFICOS"):
            with st.spinner("Gerando imagens, aguarde..."):
                z_buf = io.BytesIO()
                with zipfile.ZipFile(z_buf, "w") as zf:
                    for cat in df['categoria'].unique():
                        img_bytes = criar_grafico_instagram(cat, df[df['categoria'] == cat])
                        zf.writestr(f"{cat}.png", img_bytes)
                st.download_button("📥 CLIQUE PARA BAIXAR O ZIP", z_buf.getvalue(), f"{escolha}_graficos.zip", "application/zip")
        
        st.divider()
        for cat in df['categoria'].unique():
            st.write(f"### Categoria: {cat.upper()}")
            st.table(df[df['categoria'] == cat][['candidato', 'votos']].sort_values('votos', ascending=False))
