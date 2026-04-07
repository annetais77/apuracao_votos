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
def extrair_votos(texto, autor=None):
    """Extrai @menções e remove o autor se ele se auto-mencionar"""
    mencoes = [str(v).lower().strip().replace(" ", "") for v in re.findall(r'@[A-Za-z0-9_.-]+', str(texto))]
    if autor:
        autor_limpo = f"@{str(autor).lower().strip()}"
        # Filtra para não contar quando o autor marca a si mesmo
        mencoes = [m for m in mencoes if m != autor_limpo]
    return mencoes

def listar_cidades():
    try:
        res = supabase.rpc("obter_cidades_unicas").execute()
        if res.data:
            return [item['nome_cidade'] for item in res.data if item.get('nome_cidade')]
        return []
    except Exception as e:
        st.error(f"Erro ao listar cidades: {e}")
        return []

def criar_grafico_instagram(categoria, df_cat):
    """Gera arte 1080x1350 para Instagram"""
    total = df_cat['votos'].sum()
    top3 = df_cat.sort_values("votos", ascending=False).head(3).reset_index(drop=True)
    
    plt.close('all')
    fig, ax = plt.subplots(figsize=(10.8, 13.5))
    fig.patch.set_facecolor('#000000')
    ax.set_facecolor('#000000')
    
    for _ in range(150):
        ax.scatter(random.uniform(-0.6, 2.6), random.uniform(0, 1.2), 
                   alpha=random.uniform(0.1, 0.5), s=random.randint(5, 25), color="white")

    ax.text(1, 1.18, str(categoria).upper(), color='white', fontsize=32, ha='center', weight='bold')
    ax.text(1, 1.12, "MELHORES DO ANO", color='#FFD700', fontsize=16, ha='center', alpha=0.8)

    pos, cores = [1, 0, 2], ["#FFD700", "#C0C0C0", "#CD7F32"]
    alturas = [0.85, 0.65, 0.45] 
    
    for i, row in top3.iterrows():
        if i >= len(pos): break
        x, h = pos[i], alturas[i]
        pct = round((row['votos']/total*100), 1) if total > 0 else 0
        ax.bar(x, h, color=cores[i], width=0.75, edgecolor='white', linewidth=1.5, zorder=3)
        ax.text(x, h + 0.03, f"{row['candidato']}", color='white', ha='center', weight='bold', fontsize=20)
        ax.text(x, h/2, f"{pct}%", color='black', ha='center', weight='black', fontsize=28, zorder=4)

    ax.set_xlim(-0.8, 2.8); ax.set_ylim(0, 1.3); ax.axis('off')
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.5, facecolor='#000000', dpi=100)
    plt.close(fig)
    return buf.getvalue()

# --- SIDEBAR ---
with st.sidebar:
    st.title("🏆 Painel Anne")
    modo = st.radio("Navegação:", ["🔍 Resultados Públicos", "⚙️ Painel ADM"])
    st.divider()
    if st.button("🔄 Sincronizar Banco"):
        st.cache_data.clear()
        st.rerun()

# --- MODO ADMINISTRADOR ---
if modo == "⚙️ Painel ADM":
    senha = st.text_input("Senha", type="password")
    if senha == "123":
        t1, t2, t3, t4 = st.tabs(["🚀 Novo Upload", "👁️ Preview Rápido", "✏️ Gerenciar", "📊 Cidades"])
        
        with t1:
            cid_in = st.text_input("Nome da Cidade")
            arq = st.file_uploader("Subir ZIP com CSVs", type="zip")
            if arq and cid_in and st.button("🚀 PUBLICAR NO BANCO"):
                with tempfile.TemporaryDirectory() as tmp:
                    z_path = os.path.join(tmp, "u.zip")
                    with open(z_path, "wb") as f: f.write(arq.read())
                    with zipfile.ZipFile(z_path, "r") as z: z.extractall(tmp)
                    pay = []
                    for f in [x for x in os.listdir(tmp) if x.endswith((".csv", ".xlsx"))]:
                        cat = os.path.splitext(f)[0]
                        df_temp = pd.read_csv(os.path.join(tmp, f)) if f.endswith(".csv") else pd.read_excel(os.path.join(tmp, f))
                        
                        c_t = "commentText" if "commentText" in df_temp.columns else df_temp.columns[3]
                        c_u = "userName" if "userName" in df_temp.columns else df_temp.columns[1]
                        
                        ct, vs = Counter(), set()
                        for _, r in df_temp.iterrows():
                            u = str(r[c_u]).lower().strip()
                            v = extrair_votos(r[c_t], autor=u) # Passando autor para filtrar auto-menção
                            if u not in vs and v: 
                                ct[v[0]] += 1; vs.add(u)
                        
                        for cand, qtd in ct.items():
                            pay.append({"cidade": cid_in.strip(), "categoria": cat, "candidato": cand, "votos": qtd})
                    
                    if pay:
                        supabase.table("resultados_votos").delete().eq("cidade", cid_in.strip()).execute()
                        supabase.table("resultados_votos").insert(pay).execute()
                        st.cache_data.clear()
                        st.success(f"✅ {cid_in} Publicado!"); st.rerun()

        with t2:
            st.subheader("👁️ Gerar Gráfico sem Salvar")
            arq_unitario = st.file_uploader("Subir CSV ou Excel da Categoria", type=["csv", "xlsx"], key="unit")
            nome_cat = st.text_input("Nome da Categoria (Ex: Melhor Restaurante)")
            
            if arq_unitario and nome_cat:
                df_u = pd.read_csv(arq_unitario) if arq_unitario.name.endswith(".csv") else pd.read_excel(arq_unitario)
                
                c_t = "commentText" if "commentText" in df_u.columns else df_u.columns[3]
                c_u = "userName" if "userName" in df_u.columns else df_u.columns[1]
                
                ct_u, vs_u = Counter(), set()
                for _, r in df_u.iterrows():
                    u = str(r[c_u]).lower().strip()
                    v = extrair_votos(r[c_t], autor=u)
                    if u not in vs_u and v: 
                        ct_u[v[0]] += 1; vs_u.add(u)
                
                if ct_u:
                    df_preview = pd.DataFrame([{"candidato": k, "votos": v} for k, v in ct_u.items()])
                    img_preview = criar_grafico_instagram(nome_cat, df_preview)
                    
                    st.image(img_preview, caption="Preview do Gráfico", use_container_width=True)
                    st.download_button("📥 BAIXAR ESTE GRÁFICO", img_preview, f"{nome_cat}.png", "image/png")
                else:
                    st.warning("Nenhum voto válido encontrado neste arquivo.")

        with t3:
            c_lista = listar_cidades()
            if c_lista:
                sel = st.selectbox("Selecione para excluir:", c_lista)
                if st.button("🗑️ DELETAR TUDO"):
                    supabase.table("resultados_votos").delete().eq("cidade", sel).execute()
                    st.cache_data.clear(); st.rerun()

        with t4:
            st.subheader("Cidades no Banco:")
            cidades_reais = listar_cidades()
            for c in cidades_reais: st.write(f"📍 {c}")
    else:
        st.warning("Insira a senha para acessar.")

# --- MODO PÚBLICO ---
else:
    st.title("🔍 Resultados")
    cidades_finais = listar_cidades()
    if not cidades_finais:
        st.info("Aguardando publicações...")
    else:
        escolha = st.selectbox("Escolha a Cidade:", ["-- Selecione --"] + cidades_finais)
        if escolha != "-- Selecione --":
            res = supabase.table("resultados_votos").select("*").eq("cidade", escolha).limit(5000).execute()
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
