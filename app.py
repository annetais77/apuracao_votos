import streamlit as st
import pandas as pd
import zipfile
import os
import tempfile
import re
from collections import Counter
import matplotlib.pyplot as plt
from io import BytesIO
from supabase import create_client, Client

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Portal de Apuração Oficial", layout="wide", page_icon="🏆")

# --- CONEXÃO SUPABASE ---
# Substitua pelos seus dados reais do painel do Supabase
SUPABASE_URL = "https://nualgtyikfijnjzmybsg.supabase.co"
SUPABASE_KEY = "sb_publishable_e9RRmaN-2XIryrki_lpWhA_uC5sHZ1K"

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except:
    st.error("Erro ao conectar ao banco de dados. Verifique as credenciais.")

# --- ESTILIZAÇÃO CSS ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .card {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    .votos-destaque { color: #1E3A8A; font-weight: bold; font-size: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE FILTRAGEM (ORIGINAIS MANTIDAS) ---
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
    res = supabase.table("resultados_votos").select("cidade").execute()
    return sorted(list(set([item['cidade'] for item in res.data])))

def buscar_dados_cidade(cidade_nome):
    res = supabase.table("resultados_votos").select("*").eq("cidade", cidade_nome).execute()
    return pd.DataFrame(res.data)

# --- BARRA LATERAL (NAVEGAÇÃO) ---
with st.sidebar:
    st.title("🏆 Navegação")
    modo = st.radio("Escolha o acesso:", ["🔍 Ver Resultados", "⚙️ Administrador (Upload)"])
    st.divider()
    if modo == "⚙️ Administrador (Upload)":
        senha = st.text_input("Senha de acesso", type="password")
        if senha != "suasenha123": # Altere sua senha aqui
            st.warning("Senha incorreta.")
            st.stop()

# --- MODO ADMINISTRADOR (UPLOAD E PROCESSAMENTO) ---
if modo == "⚙️ Administrador (Upload)":
    st.header("⚙️ Painel de Upload de Dados")
    cidade_input = st.text_input("Nome da Cidade (Ex: Bezerros)")
    uploaded_zip = st.file_uploader("Envie o arquivo ZIP com CSVs/Excels", type=["zip"])

    if uploaded_zip and cidade_input:
        if st.button("🚀 Processar e Publicar Resultados"):
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
                    except: continue

                    col_coment = detectar_coluna_comentario(df)
                    col_user = detectar_coluna_usuario(df)
                    
                    votos_validos = []
                    users_voted = set()

                    for _, row in df.iterrows():
                        u = normalizar(row[col_user]) if col_user else None
                        votos_ext = extrair_votos(str(row[col_coment]))
                        
                        if u and u not in users_voted and votos_ext:
                            votos_validos.append(votos_ext[0])
                            users_voted.add(u)
                    
                    if votos_validos:
                        contagem = Counter(votos_validos)
                        resultados[categoria] = pd.DataFrame(contagem.items(), columns=["Candidato", "Votos"]).sort_values(by="Votos", ascending=False).head(3)

            if resultados:
                salvar_resultados_no_banco(cidade_input, resultados)
                st.success(f"✅ Resultados de {cidade_input} publicados com sucesso!")
            else:
                st.error("Nenhum voto válido processado.")

# --- MODO PÚBLICO (CONSULTA) ---
else:
    st.title("🔍 Consulta de Resultados Oficiais")
    cidades = listar_cidades_disponiveis()
    
    if not cidades:
        st.info("Nenhum resultado publicado ainda.")
    else:
        cidade_selecionada = st.selectbox("Selecione a cidade:", cidades)
        
        if cidade_selecionada:
            df_votos = buscar_dados_cidade(cidade_selecionada)
            st.divider()
            st.subheader(f"📍 Resultados em: {cidade_selecionada}")

            # 1. EXIBIÇÃO POR CATEGORIAS
            categorias = df_votos['categoria'].unique()
            for cat in categorias:
                with st.expander(f"📊 Categoria: {cat}", expanded=True): # Deixei expanded=True para facilitar a leitura
                    dados_cat = df_votos[df_votos['categoria'] == cat].sort_values(by="votos", ascending=False)
                    
                    # Cartões de Medalhas
                    cols = st.columns(len(dados_cat))
                    for i, (idx, row) in enumerate(dados_cat.iterrows()):
                        with cols[i]:
                            medalha = ["🥇", "🥈", "🥉"][i]
                            st.metric(label=f"{medalha} {i+1}º Lugar", value=row['candidato'], delta=f"{row['votos']} votos")
                    
                    # --- NOVIDADE: GRÁFICO POR CATEGORIA ---
                    st.write("---") # Linha divisória sutil dentro do expander
                    
                    # Criando um gráfico de barras horizontais (fica mais elegante para nomes)
                    fig, ax = plt.subplots(figsize=(10, 3))
                    cores = ['#FFD700', '#C0C0C0', '#CD7F32'] # Ouro, Prata, Bronze
                    
                    # Se houver menos de 3 candidatos, ajustamos as cores
                    barras = ax.barh(dados_cat['candidato'][::-1], dados_cat['votos'][::-1], color=cores[:len(dados_cat)][::-1])
                    
                    # Estilização do Gráfico
                    ax.set_title(f"Distribuição de Votos: {cat}", fontsize=12, pad=15)
                    ax.set_xlabel("Número de Votos")
                    ax.spines['top'].set_visible(False)
                    ax.spines['right'].set_visible(False)
                    
                    # Adiciona o número de votos ao lado da barra
                    for bar in barras:
                        width = bar.get_width()
                        ax.text(width + 0.3, bar.get_y() + bar.get_height()/2, f'{int(width)}', va='center')

                    st.pyplot(fig)
            
            # --- TOP 3 GERAL DA CIDADE ---
            st.divider()
            st.header(f"👑 Top 3 Geral: {cidade_selecionada}")
            # ... (o restante do seu código do Top 3 Geral pode continuar igual)            
            # --- NOVIDADE: TOP 3 GERAL DA CIDADE ---
            st.divider()
            st.header(f"👑 Top 3 Geral: {cidade_selecionada}")
            st.write("Estes são os candidatos mais votados somando todas as categorias da cidade.")

            # Agrupa por candidato e soma os votos (caso ele concorra em mais de uma categoria)
            top3_geral = df_votos.groupby("candidato")["votos"].sum().reset_index()
            top3_geral = top3_geral.sort_values(by="votos", ascending=False).head(3)

            col1, col2, col3 = st.columns(3)
            medalhas_geral = ["🥇", "🥈", "🥉"]
            
            for i, (idx, row) in enumerate(top3_geral.iterrows()):
                with [col1, col2, col3][i]:
                    st.markdown(f"""
                    <div style="text-align: center; border: 2px solid #FFD700; padding: 20px; border-radius: 15px; background-color: #FFF9E6;">
                        <h2 style="margin: 0;">{medalhas_geral[i]}</h2>
                        <p style="font-size: 18px; font-weight: bold; color: #333;">{row['candidato']}</p>
                        <p style="font-size: 24px; color: #1E3A8A; margin: 0;">{row['votos']} Votos</p>
                        <small>Votos Totais na Cidade</small>
                    </div>
                    """, unsafe_allow_html=True)
            
            # Gráfico de barras do Top Geral
            fig_geral, ax_geral = plt.subplots(figsize=(10, 4))
            ax_geral.bar(top3_geral['candidato'], top3_geral['votos'], color='#FFD700')
            ax_geral.set_title(f"Candidatos Mais Populares - {cidade_selecionada}")
            st.pyplot(fig_geral)
