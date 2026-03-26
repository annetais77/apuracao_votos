import streamlit as st
import pandas as pd
import zipfile
import os
import tempfile
import re
import io
import random
from collections import Counter
import matplotlib.pyplot as plt
from supabase import create_client, Client
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Portal de Apuração Oficial", layout="wide", page_icon="🏆")

# --- CONEXÃO SUPABASE ---
SUPABASE_URL = "https://nualgtyikfijnjzmybsg.supabase.co"
SUPABASE_KEY = "sb_publishable_e9RRmaN-2XIryrki_lpWhA_uC5sHZ1K"

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"Erro ao conectar ao banco de dados: {e}")

# --- ESTILIZAÇÃO CSS (Tema Escuro/Dourado) ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: white; }
    .stExpander { border: 1px solid #DAA520; border-radius: 10px; background-color: #1a1c23; margin-bottom: 20px; }
    .votos-destaque { color: #FFD700; font-weight: bold; font-size: 22px; }
    h1, h2, h3, p { color: white !important; }
    div[data-testid="stMetricValue"] { color: #FFD700 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE PROCESSAMENTO ---
def detectar_coluna_comentario(df):
    for col in ["commentText", "CommentText", "comment", "Comment", "text"]:
        if col in df.columns: return col
    return df.columns[0]

def detectar_coluna_usuario(df):
    for col in ["userName", "username", "UserName"]:
        if col in df.columns: return col
    return None

def normalizar(texto):
    texto = str(texto).lower().replace(" ", "")
    for char in [("ã","a"), ("á","a"), ("é","e"), ("í","i"), ("ó","o"), ("ú","u")]:
        texto = texto.replace(char[0], char[1])
    return texto

def extrair_votos(texto):
    encontrados = re.findall(r'@[A-Za-z0-9_.-]+', texto)
    return [normalizar(v) for v in encontrados]

# --- FUNÇÕES DE BANCO DE DADOS ---
def salvar_resultados_no_banco(cidade, resultados_dict):
    payload = []
    for categoria, top3 in resultados_dict.items():
        for _, row in top3.iterrows():
            payload.append({
                "cidade": cidade,
                "categoria": categoria,
                "candidato": row["Candidato"],
                "votos": int(row["Votos"])
            })
    if payload:
        supabase.table("resultados_votos").insert(payload).execute()

def listar_cidades_disponiveis():
    try:
        res = supabase.table("resultados_votos").select("cidade").execute()
        return sorted(list(set([item['cidade'] for item in res.data])))
    except:
        return []

def buscar_dados_cidade(cidade_nome):
    res = supabase.table("resultados_votos").select("*").eq("cidade", cidade_nome).execute()
    return pd.DataFrame(res.data)

def gerar_pdf_resultados(cat, df, cidade):
    output = io.BytesIO()
    c = canvas.Canvas(output, pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(100, 750, f"RESULTADO OFICIAL: {cat.upper()}")
    c.setFont("Helvetica", 12)
    c.drawString(100, 730, f"Cidade: {cidade}")
    c.line(100, 720, 500, 720)
    
    y = 690
    for i, (_, row) in enumerate(df.iterrows()):
        c.drawString(100, y, f"{i+1}º LUGAR: {row['candidato']} - {row['votos']} votos")
        y -= 25
    
    c.showPage()
    c.save()
    output.seek(0)
    return output

# --- BARRA LATERAL ---
with st.sidebar:
    st.title("🏆 Navegação")
    modo = st.radio("Escolha o acesso:", ["🔍 Ver Resultados", "⚙️ Administrador (Upload)"])
    st.divider()
    if modo == "⚙️ Administrador (Upload)":
        senha = st.text_input("Senha de acesso", type="password")
        if senha != "suasenha123":
            st.warning("Aguardando senha correta...")
            st.stop()

# --- MODO ADMINISTRADOR ---
if modo == "⚙️ Administrador (Upload)":
    st.header("⚙️ Painel de Upload")
    cidade_input = st.text_input("Nome da Cidade")
    uploaded_zip = st.file_uploader("ZIP com CSVs/Excels", type=["zip"])

    if uploaded_zip and cidade_input:
        if st.button("🚀 Processar e Publicar"):
            resultados = {}
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = os.path.join(tmpdir, "arquivos.zip")
                with open(zip_path, "wb") as f: f.write(uploaded_zip.read())
                with zipfile.ZipFile(zip_path, "r") as zip_ref: zip_ref.extractall(tmpdir)
                
                arquivos = [f for f in os.listdir(tmpdir) if f.endswith((".csv", ".xlsx"))]
                for arquivo in arquivos:
                    categoria = os.path.splitext(arquivo)[0]
                    caminho = os.path.join(tmpdir, arquivo)
                    try:
                        df = pd.read_csv(caminho) if arquivo.endswith(".csv") else pd.read_excel(caminho)
                        col_coment = detectar_coluna_comentario(df)
                        col_user = detectar_coluna_usuario(df)
                        votos_validos, users_voted = [], set()

                        for _, row in df.iterrows():
                            u = normalizar(row[col_user]) if col_user else None
                            votos_ext = extrair_votos(str(row[col_coment]))
                            if u and u not in users_voted and votos_ext:
                                votos_validos.append(votos_ext[0])
                                users_voted.add(u)
                        
                        if votos_validos:
                            contagem = Counter(votos_validos)
                            resultados[categoria] = pd.DataFrame(contagem.items(), columns=["Candidato", "Votos"]).sort_values(by="Votos", ascending=False).head(3)
                    except: continue

            if resultados:
                salvar_resultados_no_banco(cidade_input, resultados)
                st.success(f"✅ Resultados de {cidade_input} publicados!")
            else:
                st.error("Nenhum dado processado.")

# --- MODO PÚBLICO ---
else:
    st.title("🔍 Resultados Oficiais")
    cidades = listar_cidades_disponiveis()
    
    if not cidades:
        st.info("Nenhum resultado disponível.")
    else:
        cidade_sel = st.selectbox("Selecione a cidade:", cidades)
        if cidade_sel:
            df_votos = buscar_dados_cidade(cidade_sel)
            st.subheader(f"📍 Exibindo: {cidade_sel}")

            for cat in df_votos['categoria'].unique():
                with st.expander(f"📊 CATEGORIA: {cat.upper()}", expanded=True):
                    dados_cat = df_votos[df_votos['categoria'] == cat].sort_values(by="votos", ascending=False).head(3)
                    
                    # Gráfico de Pódio Estilizado
                    fig, ax = plt.subplots(figsize=(10, 5))
                    fig.patch.set_facecolor('#0e1117')
                    ax.set_facecolor('#0e1117')
                    
                    # Simulação de Estrelas
                    for _ in range(150):
                        ax.plot(random.uniform(-0.5, 2.5), random.uniform(0, 1.2), 'w*', 
                                markersize=random.uniform(0.1, 1.5), alpha=0.3)

                    # Dados do Pódio (Ordem visual: 2º, 1º, 3º)
                    # Para facilitar o código, vamos manter a ordem 1, 2, 3 no pódio linear
                    pos = [0, 1, 2]
                    alturas = [1.0, 0.8, 0.6] # 1º lugar é o mais alto
                    labels_lugar = ["1º Lugar", "2º Lugar", "3º Lugar"]
                    
                    total_v_cat = dados_cat['votos'].sum()
                    
                    for i, (idx, row) in enumerate(dados_cat.iterrows()):
                        # Desenha Barra Dourada
                        ax.bar(pos[i], alturas[i], color='#FFD700', edgecolor='#DAA520', linewidth=3, zorder=3)
                        # Brilho Central
                        ax.bar(pos[i], alturas[i], color='white', alpha=0.15, width=0.4, zorder=4)
                        
                        # Textos dentro da barra
                        perc = (row['votos']/total_v_cat*100) if total_v_cat > 0 else 0
                        ax.text(pos[i], alturas[i]/2, labels_lugar[i], color='black', fontsize=14, ha='center', weight='bold', zorder=5)
                        ax.text(pos[i], alturas[i]/2 - 0.1, f"{perc:.1f}%", color='black', fontsize=12, ha='center', zorder=5)
                        
                        # Nome do Candidato abaixo
                        ax.text(pos[i], -0.1, row['candidato'].upper(), color='#FFD700', fontsize=12, ha='center', weight='bold', zorder=5)

                    ax.set_xlim(-0.8, 2.8)
                    ax.set_ylim(-0.2, 1.3)
                    ax.axis('off')
                    
                    st.pyplot(fig)

                    # Botões
                    c1, c2 = st.columns(2)
                    with c1:
                        st.button(f"📄 VER LISTA COMPLETA", key=f"btn_{cat}")
                    with c2:
                        pdf = gerar_pdf_resultados(cat, dados_cat, cidade_sel)
                        st.download_button("📥 DOWNLOAD RESULTADO", data=pdf, file_name=f"{cat}.pdf", key=f"dl_{cat}")

            # Top 3 Geral
            st.divider()
            st.header(f"👑 TOP 3 GERAL DA CIDADE")
            top3_geral = df_votos.groupby("candidato")["votos"].sum().reset_index().sort_values(by="votos", ascending=False).head(3)
            
            cols = st.columns(3)
            for i, (_, row) in enumerate(top3_geral.iterrows()):
                with cols[i]:
                    st.markdown(f"""
                        <div style="text-align: center; border: 2px solid #FFD700; padding: 15px; border-radius: 10px; background-color: #1a1c23;">
                            <h2 style="margin:0;">{["🥇","🥈","🥉"][i]}</h2>
                            <p style="font-size: 18px; font-weight: bold; margin:0;">{row['candidato']}</p>
                            <p style="font-size: 22px; color: #FFD700;">{row['votos']} Votos</p>
                        </div>
                    """, unsafe_allow_html=True)
