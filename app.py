import streamlit as st
import pandas as pd
import zipfile, os, tempfile, re, io
from supabase import create_client, Client

# --- CONFIGURAÇÃO ---
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

def listar_cidades_fixo():
    try:
        # Busca direta na tabela sem depender de função RPC
        res = supabase.table("resultados_votos").select("cidade").execute()
        return sorted(list(set([item['cidade'] for item in res.data if item.get('cidade')])))
    except: return []

# --- PAINEL ADM ---
# (Assumindo que você já tem o código do modo ADM montado, substitua as abas t2 e t4 por estas abaixo)

with t2: # PREVIEW
    st.write("### Teste de Processamento")
    arq_p = st.file_uploader("Suba um CSV/XLSX para visualizar o resultado", type=["csv", "xlsx"])
    if arq_p:
        df = pd.read_csv(arq_p) if arq_p.name.endswith(".csv") else pd.read_excel(arq_p)
        c_t = next((c for c in df.columns if 'comment' in c.lower() or 'text' in c.lower()), df.columns[-1])
        c_u = next((c for c in df.columns if 'user' in c.lower() or 'name' in c.lower()), df.columns[1])
        
        st.write(f"Colunas detectadas: Comentário: '{c_t}', Usuário: '{c_u}'")
        if st.button("Processar Preview"):
            ct = Counter()
            for _, r in df.iterrows():
                v = extrair_votos(r[c_t], autor=str(r[c_u]))
                if v: ct[v[0]] += 1
            df_preview = pd.DataFrame([{"Candidato": k, "Votos": v} for k, v in ct.items()])
            st.table(df_preview.sort_values("Votos", ascending=False))

with t4: # CIDADES (Lista Robusta)
    st.write("### Cidades no Banco")
    lista = listar_cidades_fixo()
    if lista:
        st.write(lista)
    else:
        st.warning("Nenhuma cidade encontrada ou erro de conexão.")
