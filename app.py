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
# Use as suas credenciais reais aqui
SUPABASE_URL = "https://nualgtyikfijnjzmybsg.supabase.co"
SUPABASE_KEY = "sb_publishable_e9RRmaN-2XIryrki_lpWhA_uC5sHZ1K"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ESTILO GLOBAL ---
st.markdown("""
    <style>
    .main {background-color: #000000; color: #ffffff;}
    .stSelectbox label, .stTextInput label {color: #ffffff !important;}
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE PROCESSAMENTO ---
def extrair_votos(texto):
    """Extrai menções com @ e normaliza"""
    return [str(v).lower().strip().replace(" ", "") for v in re.findall(r'@[A-Za-z0-9_.-]+', str(texto))]

@st.cache_data(ttl=1)
def listar_cidades(refresh_key):
    """Lista as cidades cadastradas no banco sem duplicatas"""
    try:
        res = supabase.table("resultados_votos").select("cidade").execute()
        return sorted(list(set([item['cidade'] for item in res.data])))
    except:
        return []

def criar_grafico_instagram(categoria, df_cat):
    """Gera a arte no formato 1080x1350 para Instagram"""
    total = df_cat['votos'].sum()
    top3 = df_cat.sort_values("votos", ascending=False).head(3).reset_index(drop=True)
    
    plt.close('all')
    # Proporção 4:5 ideal para Instagram
    fig, ax = plt.subplots(figsize=(10.8, 13.5))
    fig.patch.set_facecolor('#000000')
    ax.set_facecolor('#000000')
    
    # Pontos luminosos de fundo (Efeito Estelar)
    for _ in range(150):
        ax.scatter(random.uniform(-0.6, 2.6), random.uniform(0, 1.2), 
                   alpha=random.uniform(0.1, 0.5), s=random.randint(5, 25), color="white")

    # TEXTOS NO TOPO (Corrigido sem o erro de 'ls')
    ax.text(1, 1.18, categoria.upper(), color='white', fontsize=32, ha='center', weight='bold')
    ax.text(1, 1.12, "MELHORES DO ANO", color='#FFD700', fontsize=16, ha='center', alpha=0.8)

    pos, cores = [1, 0, 2], ["#FFD700", "#C0C0C0", "#CD7F32"]
    alturas_podio = [0.85, 0.65, 0.45] 
    
    for i, row in top3.iterrows():
        if i >= len(pos): break
        x, h = pos[i], alturas_podio[i]
        pct = round((row['votos']/total*100), 1) if total > 0 else 0
        
        # Barra do Candidato
        ax.bar(x, h, color=cores[i], width=0.75, edgecolor='white', linewidth=1.5, zorder=3)
        
        # Nome do Candidato
        ax.text(x, h + 0.03, f"@{row['candidato']}", color='white', ha='center', weight='bold', fontsize=20)
        
        # Porcentagem Centralizada
        ax.text(x, h/2, f"{pct}%", color='black', ha='center', weight='black', fontsize=28, zorder=4)

    ax.set_xlim(-0.8, 2.8)
    ax.set_ylim(0, 1.3)
    ax.axis('off')
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.5, facecolor='#000000', dpi=100)
    plt.close(fig)
    return buf.getvalue()

# --- NAVEGAÇÃO LATERAL ---
with st.sidebar:
    st.title("🏆 Apuração Digital")
    modo = st.radio("Selecione o modo:", ["🔍 Ver Resultados", "⚙️ Administrador"])
    if modo == "⚙️ Administrador":
        senha = st.text_input("Senha de Acesso", type="password")
        if senha != "suasenha123": # Mude sua senha aqui
            st.warning("Aguardando senha...")
            st.stop()

# --- MODO ADMINISTRADOR ---
if modo == "⚙️ Administrador":
    st.header("⚙️ Painel de Controle")
    tab1, tab2 = st.tabs(["🚀 Publicar Novo", "✏️ Gerenciar Cidades"])
    
    with tab1:
        st.subheader("Subir Novo Arquivo")
        cidade_nome = st.text_input("Nome da Cidade (Ex: Afogados)")
        arquivo_zip = st.file_uploader("ZIP com arquivos CSV/Excel", type="zip")
        
        if arquivo_zip and cidade_nome and st.button("🚀 ENVIAR E PUBLICAR"):
            with tempfile.TemporaryDirectory() as tmpdir:
                z_path = os.path.join(tmpdir, "upload.zip")
                with open(z_path, "wb") as f: f.write(arquivo_zip.read())
                with zipfile.ZipFile(z_path, "r") as z: z.extractall(tmpdir)
                
                payload = []
                for f in [x for x in os.listdir(tmpdir) if x.endswith((".csv", ".xlsx"))]:
                    categoria = os.path.splitext(f)[0]
                    df = pd.read_csv(os.path.join(tmpdir, f)) if f.endswith(".csv") else pd.read_excel(os.path.join(tmpdir, f))
                    
                    # Identifica colunas automaticamente
                    col_txt = "commentText" if "commentText" in df.columns else df.columns[3]
                    col_usr = "userName" if "userName" in df.columns else df.columns[1]
                    
                    contagem = Counter()
                    vistos = set()
                    for _, row in df.iterrows():
                        votos = extrair_votos(row[col_txt])
                        user = str(row[col_usr]).lower().strip()
                        if user not in vistos and votos:
                            contagem[votos[0]] += 1
                            vistos.add(user)
                    
                    for cand, qtd in contagem.items():
                        payload.append({"cidade": cidade_nome.strip(), "categoria": categoria, "candidato": cand, "votos": qtd})
                
                if payload:
                    supabase.table("resultados_votos").insert(payload).execute()
                    st.success(f"✅ {cidade_nome} publicado com sucesso!"); st.rerun()

    with tab2:
        st.subheader("Editar Cidades Existentes")
        cidades_bd = listar_cidades(random.random())
        if cidades_bd:
            cid_alvo = st.selectbox("Selecione a cidade:", cidades_bd)
            
            # Renomear
            novo_nome = st.text_input("Novo nome para esta cidade:")
            if st.button("💾 Salvar Novo Nome"):
                supabase.table("resultados_votos").update({"cidade": novo_nome}).eq("cidade", cid_alvo).execute()
                st.success("Cidade renomeada!"); st.rerun()
            
            st.divider()
            # Excluir
            st.error("Zona Crítica")
            if st.button("🗑️ EXCLUIR TODOS OS DADOS DESTA CIDADE"):
                supabase.table("resultados_votos").delete().eq("cidade", cid_alvo).execute()
                st.warning("Cidade removida do sistema!"); st.rerun()

# --- MODO PÚBLICO ---
else:
    st.title("🔍 Resultados Oficiais")
    lista_cidades = listar_cidades(random.random())
    
    if not lista_cidades:
        st.info("Nenhum resultado disponível no momento.")
    else:
        escolha = st.selectbox("Selecione a Cidade:", lista_cidades)
        res_bd = supabase.table("resultados_votos").select("*").eq("cidade", escolha).execute()
        df_final = pd.DataFrame(res_bd.data)
        
        if not df_final.empty:
            # BOTÃO DE DOWNLOAD DO ZIP
            st.subheader(f"📍 {escolha.upper()}")
            
            if st.button(f"📦 GERAR ZIP COM TODOS OS CARDS ({escolha})"):
                with st.spinner("Preparando artes para o Instagram..."):
                    zip_mem = io.BytesIO()
                    with zipfile.ZipFile(zip_mem, "w") as zf:
                        for cat in df_final['categoria'].unique():
                            img = criar_grafico_instagram(cat, df_final[df_final['categoria'] == cat])
                            zf.writestr(f"{cat}.png", img)
                    
                    st.download_button(
                        label="🔥 BAIXAR PACOTE DE IMAGENS (.ZIP)",
                        data=zip_mem.getvalue(),
                        file_name=f"INSTAGRAM_{escolha}.zip",
                        mime="application/zip"
                    )
            
            st.divider()
            
            # PRÉVIA DOS CARDS
            st.write("### Prévia dos Resultados")
            categorias_unicas = df_final['categoria'].unique()
            # Mostra apenas os 3 primeiros para não pesar o carregamento
            for cat in categorias_unicas[:3]:
                with st.expander(f"Ver card: {cat.upper()}"):
                    img_bytes = criar_grafico_instagram(cat, df_final[df_final['categoria'] == cat])
                    b64_img = base64.b64encode(img_bytes).decode()
                    st.write(f'<img src="data:image/png;base64,{b64_img}" style="width:100%; max-width:400px; border-radius:10px;">', unsafe_allow_html=True)
            
            if len(categorias_unicas) > 3:
                st.info(f"Existem mais {len(categorias_unicas)-3} categorias. Use o botão de ZIP acima para baixar todas as artes!")
