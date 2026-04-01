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

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Portal de Apuração", layout="wide")

# --- CONEXÃO ---
SUPABASE_URL = "https://nualgtyikfijnjzmybsg.supabase.co"
SUPABASE_KEY = "sb_publishable_e9RRmaN-2XIryrki_lpWhA_uC5sHZ1K"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- FUNÇÕES ---
def extrair_votos(texto):
    return [str(v).lower().strip().replace(" ", "") for v in re.findall(r'@[A-Za-z0-9_.-]+', str(texto))]

@st.cache_data(ttl=2) # Cache curtíssimo para atualizar rápido
def listar_cidades(check):
    try:
        res = supabase.table("resultados_votos").select("cidade").execute()
        return sorted(list(set([item['cidade'] for item in res.data])))
    except: return []

# --- MENU ---
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
        if arquivo and cid_nome and st.button("PUBLICAR AGORA"):
            with tempfile.TemporaryDirectory() as tmp:
                z_path = os.path.join(tmp, "data.zip")
                with open(z_path, "wb") as f: f.write(arquivo.read())
                with zipfile.ZipFile(z_path, "r") as z: z.extractall(tmp)
                
                votos_batch = []
                for f in [x for x in os.listdir(tmp) if x.endswith((".csv", ".xlsx"))]:
                    cat_nome = os.path.splitext(f)[0]
                    df = pd.read_csv(os.path.join(tmp, f)) if f.endswith(".csv") else pd.read_excel(os.path.join(tmp, f))
                    
                    col_txt = "commentText" if "commentText" in df.columns else df.columns[3]
                    col_usr = "userName" if "userName" in df.columns else df.columns[1]
                    
                    contagem = Counter()
                    u_vistos = set()
                    for _, r in df.iterrows():
                        v = extrair_votos(r[col_txt])
                        u = str(r[col_usr]).lower().strip()
                        if u not in u_vistos and v:
                            contagem[v[0]] += 1
                            u_vistos.add(u)
                    
                    for cand, qtd in contagem.items():
                        votos_batch.append({"cidade": cid_nome.strip(), "categoria": cat_nome, "candidato": cand, "votos": qtd})
                
                if votos_batch:
                    supabase.table("resultados_votos").insert(votos_batch).execute()
                    st.success("✅ Publicado com sucesso!"); st.rerun()

    with t2:
        st.subheader("Renomear ou Excluir")
        todas = listar_cidades(random.random())
        if todas:
            cid_sel = st.selectbox("Escolha a cidade:", todas)
            novo_n = st.text_input("Novo nome para esta cidade:")
            
            c1, c2 = st.columns(2)
            if c1.button("Salvar Novo Nome"):
                supabase.table("resultados_votos").update({"cidade": novo_n}).eq("cidade", cid_sel).execute()
                st.success("Nome atualizado!"); st.rerun()
            
            if c2.button("⚠️ EXCLUIR TUDO DESTA CIDADE"):
                supabase.table("resultados_votos").delete().eq("cidade", cid_sel).execute()
                st.error("Cidade removida!"); st.rerun()

# --- MODO PÚBLICO ---
else:
    st.title("🔍 Resultados")
    cidades = listar_cidades(random.random())
    if cidades:
        escolha = st.selectbox("Selecione a Cidade:", cidades)
        dados_raw = supabase.table("resultados_votos").select("*").eq("cidade", escolha).execute()
        df = pd.DataFrame(dados_raw.data)

        for categoria in df['categoria'].unique():
            with st.container():
                st.markdown(f"### 📊 {categoria.upper()}")
                df_c = df[df['categoria'] == categoria]
                total = df_c['votos'].sum()
                top3 = df_c.sort_values("votos", ascending=False).head(3).reset_index(drop=True)
                
                plt.close('all')
                fig, ax = plt.subplots(figsize=(10, 6))
                fig.patch.set_facecolor('#000000'); ax.set_facecolor('#000000')
                
                # --- PONTOS LUMINOSOS (O que você gosta) ---
                for _ in range(120):
                    ax.scatter(random.uniform(-0.5, 2.5), random.uniform(0, 1.1), 
                               alpha=random.uniform(0.1, 0.4), s=random.randint(3, 12), color="white")

                pos, cores = [1, 0, 2], ["#FFD700", "#C0C0C0", "#CD7F32"]
                for i, row in top3.iterrows():
                    if i >= len(pos): break
                    x, h = pos[i], [0.9, 0.7, 0.5][i]
                    pct = round((row['votos']/total*100), 1) if total > 0 else 0
                    
                    ax.bar(x, h, color=cores[i], width=0.8, edgecolor='white', zorder=3)
                    ax.text(x, h + 0.05, f"@{row['candidato']}", color=cores[i], ha='center', weight='bold', fontsize=12)
                    
                    # APENAS PORCENTAGEM (Como você pediu)
                    ax.text(x, h/2, f"{pct}%", color='black', ha='center', weight='bold', fontsize=18, zorder=4)

                ax.axis('off')
                
                # Renderização Segura
                buf = io.BytesIO()
                fig.savefig(buf, format="png", bbox_inches='tight', facecolor='#000000')
                b64 = base64.b64encode(buf.getvalue()).decode()
                st.write(f'<img src="data:image/png;base64,{b64}" style="width:100%;">', unsafe_allow_html=True)
                
                st.download_button("📥 Baixar Card", buf.getvalue(), f"{categoria}.png", "image/png", key=f"d_{categoria}_{random.randint(0,999)}")
                st.markdown("---")
