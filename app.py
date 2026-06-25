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
        res = supabase.table("resultados_votos").select("cidade").execute()
        return sorted(list(set([item['cidade'] for item in res.data if item.get('cidade')])))
    except Exception as e:
        st.error(f"Erro no banco: {e}")
        return []

# --- MODO ADM ---
if st.sidebar.radio("Navegação:", ["Público", "ADM"]) == "ADM":
    if st.text_input("Senha", type="password") == "123":
        cid_in = st.text_input("Nome da Cidade")
        arq = st.file_uploader("Upload ZIP", type="zip")
        
        if arq and cid_in and st.button("PUBLICAR NO BANCO"):
            with st.spinner("Processando arquivos..."):
                with tempfile.TemporaryDirectory() as tmp:
                    with zipfile.ZipFile(arq, "r") as z: z.extractall(tmp)
                    pay = []
                    total_arquivos = 0
                    
                    for f in [x for x in os.listdir(tmp) if x.endswith((".csv", ".xlsx"))]:
                        df = pd.read_csv(os.path.join(tmp, f)) if f.endswith(".csv") else pd.read_excel(os.path.join(tmp, f))
                        
                        # VALIDADOR: Verifica se colunas básicas existem
                        if len(df.columns) < 2:
                            st.warning(f"⚠️ Arquivo {f} ignorado: formato de colunas inválido.")
                            continue
                            
                        total_arquivos += 1
                        # Lógica de extração
                        c_t = df.columns[3] if len(df.columns) > 3 else df.columns[-1]
                        c_u = df.columns[1] if len(df.columns) > 1 else df.columns[0]
                        
                        ct = Counter()
                        for _, r in df.iterrows():
                            u = str(r[c_u]).lower().strip()
                            v = extrair_votos(r[c_t], autor=u)
                            if v: ct[v[0]] += 1
                        
                        pay.extend([{"cidade": cid_in, "categoria": os.path.splitext(f)[0], "candidato": c, "votos": v} for c, v in ct.items()])
                    
                    if pay:
                        try:
                            supabase.table("resultados_votos").delete().eq("cidade", cid_in).execute()
                            supabase.table("resultados_votos").insert(pay).execute()
                            st.success(f"✅ Sucesso! Cidade '{cid_in}' processada com {len(pay)} elementos distribuídos em {total_arquivos} categorias.")
                        except Exception as e:
                            st.error(f"❌ Erro ao salvar no banco: {e}")
                    else:
                        st.error("❌ Nenhum dado válido foi encontrado. Verifique se os arquivos possuem colunas de texto.")

# --- MODO PÚBLICO ---
else:
    st.title("🏆 Resultados")
    cidades = listar_cidades()
    escolha = st.selectbox("Selecione a cidade:", ["-- Escolha --"] + cidades)
    
    if escolha != "-- Escolha --":
        res = supabase.table("resultados_votos").select("*").eq("cidade", escolha).execute()
        df = pd.DataFrame(res.data)
        
        if df.empty:
            st.warning("Nenhum dado encontrado para esta cidade.")
        else:
            categorias = df['categoria'].unique()
            st.write(f"📂 Encontradas {len(categorias)} categorias para {escolha}.")
            for cat in categorias:
                with st.expander(f"Categoria: {cat.upper()}"):
                    cat_data = df[df['categoria'] == cat]
                    st.table(cat_data[['candidato', 'votos']].sort_values('votos', ascending=False))
