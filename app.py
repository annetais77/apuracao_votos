import streamlit as st
import pandas as pd
import zipfile, os, tempfile, re, io, random, textwrap
import matplotlib.pyplot as plt
from collections import Counter
from supabase import create_client, Client

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Portal de Apuração", layout="wide", page_icon="🏆")
SUPABASE_URL = "https://nualgtyikfijnjzmybsg.supabase.co"
SUPABASE_KEY = "sb_publishable_e9RRmaN-2XIryrki_lpWhA_uC5sHZ1K"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ESTILO ---
st.markdown("<style>.main {background-color: #000; color: #fff;}</style>", unsafe_allow_html=True)

# --- FUNÇÕES ---
def extrair_votos(texto, autor=None):
    if pd.isna(texto): return []
    
    texto_str = str(texto).strip()
    
    # Encontra todas as menções e suas posições no texto original
    mencoes_brutas = [m.group(0) for m in re.finditer(r'@[A-Za-z0-9_.-]+', texto_str)]
    
    if not mencoes_brutas:
        return []

    # REGRA 1: Ignorar o @ de quem está respondendo a outro comentário
    # No Instagram/TikTok, respostas começam obrigatoriamente com a tag no índice 0
    if texto_str.startswith(mencoes_brutas[0]):
        mencoes_brutas = mencoes_brutas[1:]

    # Padronização (minúsculo, sem espaços)
    mencoes_limpas = [m.lower().strip().replace(" ", "") for m in mencoes_brutas]

    # REGRA 2: O autor não pode votar em si mesmo
    if autor:
        autor_limpo = f"@{str(autor).lower().strip()}"
        mencoes_limpas = [m for m in mencoes_limpas if m != autor_limpo]

    return mencoes_limpas

def identificar_eleitores_anulados(df, c_u, c_t):
    """Mapeia eleitores que votaram em mais de um candidato diferente na mesma categoria"""
    votos_por_eleitor = {}
    
    for _, r in df.iterrows():
        u = str(r[c_u]).lower().strip()
        votos = extrair_votos(r[c_t], autor=u)
        
        if u and votos:
            if u not in votos_por_eleitor:
                votos_por_eleitor[u] = set()
            votos_por_eleitor[u].add(votos[0])
            
    # Retorna conjunto de usuários que tentaram votar em 2 ou mais candidatos distintos
    return {u for u, candidatos in votos_por_eleitor.items() if len(candidatos) > 1}

def listar_cidades():
    """Busca a lista de cidades diretamente da View otimizada do Supabase"""
    try:
        res = supabase.table("cidades_unicas").select("cidade").execute()
        if res.data:
            return sorted(list(set([item['cidade'].strip() for item in res.data if item.get('cidade')])))
        return []
    except Exception as e:
        st.error(f"Erro técnico ao listar cidades: {e}")
        return []

def criar_grafico_instagram(categoria, df_cat):
    df_sorted = df_cat.sort_values("votos", ascending=False).reset_index(drop=True)
    df_sorted['rank'] = df_sorted['votos'].rank(method='min', ascending=False).astype(int)
    total = df_sorted['votos'].sum()
    top3_df = df_sorted.head(3)
    
    plt.close('all')
    fig, ax = plt.subplots(figsize=(10.8, 13.5))
    fig.patch.set_facecolor('#000000'); ax.set_facecolor('#000000')
    
    for _ in range(150): 
        ax.scatter(random.uniform(-0.6, 2.6), random.uniform(0, 1.2), alpha=0.3, s=15, color="white")
    
    ax.text(1, 1.18, str(categoria).upper(), color='white', fontsize=32, ha='center', weight='bold')
    
    mapa_cores = {1: "#FFD700", 2: "#C0C0C0", 3: "#CD7F32"}
    mapa_alturas = {1: 0.85, 2: 0.65, 3: 0.45}
    pos_x = [1, 0, 2]
    
    for i, (_, row) in enumerate(top3_df.iterrows()):
        rank = row['rank']
        cor, altura = mapa_cores.get(rank, "#CD7F32"), mapa_alturas.get(rank, 0.45)
        pct = round((row['votos']/total*100), 1) if total > 0 else 0
        
        ax.bar(pos_x[i], altura, color=cor, width=0.75, edgecolor='white', linewidth=2, zorder=3)
        
        # FONTE DO ARROBA ALTERADA AQUI: Aumentado para 19 e peso 'black'
        nome_ajustado = "\n".join(textwrap.wrap(str(row['candidato']), width=12))
        ax.text(pos_x[i], altura + 0.035, nome_ajustado, color='white', ha='center', weight='black', fontsize=23, va='bottom')
        
        ax.text(pos_x[i], altura/2, f"{pct}%", color='black', ha='center', weight='black', fontsize=24, zorder=4)
        
    ax.set_xlim(-0.8, 2.8)
    ax.set_ylim(0, 1.3)
    ax.axis('off')
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.5, facecolor='#000000', dpi=100)
    return buf.getvalue()

# --- SIDEBAR ---
with st.sidebar:
    st.title("🏆 Painel Anne")
    modo = st.radio("Navegação:", ["🔍 Resultados Públicos", "⚙️ Painel ADM"])
    if st.button("🔄 Atualizar Dados"): 
        st.cache_data.clear()
        st.rerun()

# --- MODO ADM ---
if modo == "⚙️ Painel ADM":
    if st.text_input("Senha de Acesso", type="password") == "123":
        t1, t2, t3, t4, t5 = st.tabs(["🚀 Upload ZIP", "👁️ Preview", "✏️ Limpar Cidade", "📊 Cidades Ativas", "🔧 Central de Correção"])
        
        with t1:
            cid_in = st.text_input("Nome da Cidade para Inserção/Atualização")
            arq = st.file_uploader("Subir arquivo compactado ZIP", type="zip")
            if arq and cid_in and st.button("PUBLICAR NO BANCO"):
                with tempfile.TemporaryDirectory() as tmp:
                    zipfile.ZipFile(arq, "r").extractall(tmp)
                    pay = []
                    arquivos_processados = 0
                    arquivos_ignorados_ou_vazios = 0
                    total_anulados_geral = 0
                    
                    st.write("### 📝 Relatório de Processamento do ZIP:")
                    
                    for root, dirs, files in os.walk(tmp):
                        for f in files:
                            if f.lower().endswith((".csv", ".xlsx")):
                                caminho_completo = os.path.join(root, f)
                                try:
                                    df = pd.read_csv(caminho_completo) if f.lower().endswith(".csv") else pd.read_excel(caminho_completo)
                                    
                                    c_t = next((c for c in df.columns if ('text' in c.lower() or 'coment' in c.lower()) and 'id' not in c.lower()), None)
                                    if not c_t:
                                        c_t = next((c for c in df.columns if 'comment' in c.lower() or 'text' in c.lower()), df.columns[-1])
                                        
                                    c_u = next((c for c in df.columns if ('user' in c.lower() or 'name' in c.lower()) and 'id' not in c.lower()), None)
                                    if not c_u:
                                        c_u = next((c for c in df.columns if 'user' in c.lower() or 'name' in c.lower()), df.columns[1])
                                    
                                    # Passo 1: Descobre quem tentou votar em 2+ candidatos na mesma categoria
                                    eleitores_fraudadores = identificar_eleitores_anulados(df, c_u, c_t)
                                    total_anulados_geral += len(eleitores_fraudadores)
                                    
                                    ct, vs = Counter(), set()
                                    
                                    # Passo 2: Computação justa
                                    for _, r in df.iterrows():
                                        u = str(r[c_u]).lower().strip()
                                        
                                        # Se o usuário está na lista negra de multivoto, pula o registro inteiro
                                        if u in eleitores_fraudadores:
                                            continue
                                            
                                        v = extrair_votos(r[c_t], autor=u)
                                        if u not in vs and v: 
                                            ct[v[0]] += 1
                                            vs.add(u)
                                    
                                    votos_deste_arquivo = [{"cidade": cid_in.strip(), "categoria": os.path.splitext(f)[0], "candidato": cand, "votos": qtd} for cand, qtd in ct.items()]
                                    
                                    if votos_deste_arquivo:
                                        pay.extend(votos_deste_arquivo)
                                        arquivos_processados += 1
                                        aviso_anulados = f" | 🚫 {len(eleitores_fraudadores)} eleitores anulados por multivoto." if eleitores_fraudadores else ""
                                        st.info(f"✔️ **{f}**: Lido! Encontrados {len(votos_deste_arquivo)} candidatos{aviso_anulados}")
                                    else:
                                        arquivos_ignorados_ou_vazios += 1
                                        st.warning(f"⚠️ **{f}**: Planilha lida, mas nenhum voto válido restou após as filtragens.")
                                
                                except Exception as err_arq:
                                    st.error(f"❌ Erro ao ler o arquivo {f}: {err_arq}")
                    
                    if pay:
                        try:
                            cats_no_zip = list(set([item['categoria'] for item in pay]))
                            for categoria_deletar in cats_no_zip:
                                supabase.table("resultados_votos").delete().eq("cidade", cid_in.strip()).eq("categoria", categoria_deletar).execute()
                            
                            chunk_size = 200
                            for chunk_id in range(0, len(pay), chunk_size):
                                supabase.table("resultados_votos").insert(pay[chunk_id:chunk_id + chunk_size]).execute()
                            
                            st.success(f"🏆 Concluído! {arquivos_processados} arquivo(s) salvos no banco para '{cid_in.strip()}'! (Total de malandrinhos bloqueados no ZIP: {total_anulados_geral})")
                            st.rerun()
                        except Exception as database_error:
                            st.error(f"🚨 O Supabase recusou os dados! Motivo técnico: {database_error}")
                    else:
                        st.error("❌ O ZIP continha planilhas, mas nenhuma delas possuía dados válidos computáveis.")

        with t2:
            st.write("### Preview de Arquivos")
            arq_p = st.file_uploader("Suba um arquivo individual para checagem rápida", type=["csv", "xlsx"])
            if arq_p:
                df_p = pd.read_csv(arq_p) if arq_p.name.endswith(".csv") else pd.read_excel(arq_p)
                st.dataframe(df_p.head())
        
        with t3:
            st.write("### 🚨 Zona de Perigo")
            sel = st.selectbox("Selecione a cidade para apagar COMPLETAMENTE:", listar_cidades(), key="del_completo")
            if st.button("⚠️ DELETAR TODOS OS REGISTROS DESTA CIDADE"):
                supabase.table("resultados_votos").delete().eq("cidade", sel).execute()
                st.warning(f"Cidade {sel} removida completamente.")
                st.rerun()
        
        with t4:
            st.write("### Cidades Ativas no Banco de Dados")
            st.write(listar_cidades())
            
        with t5:
            st.write("### 🔧 Central de Modificação Manual e Unificação")
            cidades_corr = listar_cidades()
            if cidades_corr:
                cid = st.selectbox("1. Escolha a Cidade:", cidades_corr, key="m_cid")
                res = supabase.table("resultados_votos").select("categoria").eq("cidade", cid).execute()
                cats = sorted(list(set([i['categoria'] for i in res.data])))
                cat = st.selectbox("2. Escolha a Categoria:", cats, key="m_cat")
                
                if cat:
                    res_c = supabase.table("resultados_votos").select("candidato", "votos").eq("cidade", cid).eq("categoria", cat).execute()
                    df_c = pd.DataFrame(res_c.data)
                    
                    if not df_c.empty:
                        df_c = df_c.sort_values("votos", ascending=False).reset_index(drop=True)
                        
                        st.write("#### 📊 Visualização do Gráfico em Tempo Real")
                        img_bytes = criar_grafico_instagram(cat, df_c)
                        st.image(img_bytes, caption=f"Visualização de {cat.upper()}", use_container_width=True)
                        
                        st.markdown("---")
                        st.write("#### 🔗 Unificar / Mesclar Candidatos Duplicados")
                        
                        lista_cand = df_c['candidato'].tolist()
                        if len(lista_cand) >= 2:
                            col_m1, col_m2 = st.columns(2)
                            with col_m1:
                                cand_origem = st.selectbox("Candidato que digitou ERRADO (vai SUMIR):", lista_cand, key="m_origem")
                            with col_m2:
                                lista_destino = [c for c in lista_cand if c != cand_origem]
                                cand_destino = st.selectbox("Candidato CORRETO (vai RECEBER os votos):", lista_destino, key="m_destino")
                            
                            if st.button("🤝 CONFIRMAR UNIÃO E SOMAR VOTOS"):
                                votos_origem = int(df_c[df_c['candidato'] == cand_origem]['votos'].values[0])
                                votos_destino = int(df_c[df_c['candidato'] == cand_destino]['votos'].values[0])
                                soma_votos = votos_destino + votos_origem
                                
                                with st.spinner("Somando votos no banco..."):
                                    supabase.table("resultados_votos").update({"votos": soma_votos}).eq("cidade", cid).eq("categoria", cat).eq("candidato", cand_destino).execute()
                                    supabase.table("resultados_votos").delete().eq("cidade", cid).eq("categoria", cat).eq("candidato", cand_origem).execute()
                                
                                st.success(f"Sucesso! Votos consolidados.")
                                st.rerun()
                        
                        st.markdown("---")
                        st.write("#### ✏️ Alterar Valores ou Nomes Diretamente")
                        
                        df_editado = st.data_editor(
                            df_c,
                            column_config={
                                "candidato": st.column_config.TextColumn("Nome do Candidato", required=True),
                                "votos": st.column_config.NumberColumn("Contagem de Votos", min_value=0, step=1)
                            },
                            key="editor_grade"
                        )
                        
                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            if st.button("💾 SALVAR EDIÇÕES DA TABELA"):
                                with st.spinner("Atualizando registros..."):
                                    for idx, row in df_editado.iterrows():
                                        linha_original = df_c.iloc[idx]
                                        if row['votos'] != linha_original['votos'] or row['candidato'] != linha_original['candidato']:
                                            supabase.table("resultados_votos").update({
                                                "candidato": row['candidato'],
                                                "votos": int(row['votos'])
                                            }).eq("cidade", cid).eq("categoria", cat).eq("candidato", linha_original['candidato']).execute()
                                    st.success("Tabela updated!")
                                    st.rerun()
                                    
                        with col_btn2:
                            cand_remover = st.selectbox("Excluir definitivamente um candidato:", df_c['candidato'].tolist(), key="del_individual")
                            if st.button("🗑️ REMOVER CANDIDATO"):
                                supabase.table("resultados_votos").delete().eq("cidade", cid).eq("categoria", cat).eq("candidato", cand_remover).execute()
                                st.error(f"{cand_remover} removido.")
                                st.rerun()

# --- MODO PÚBLICO ---
else:
    st.title("🔍 Painel de Resultados Disponíveis")
    cidades = listar_cidades()
    escolha = st.selectbox("Selecione a cidade desejada:", ["-- Escolha --"] + cidades)
    if escolha != "-- Escolha --":
        res = supabase.table("resultados_votos").select("*").eq("cidade", escolha).execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            if st.button("📦 GERAR E BAIXAR TODOS OS GRÁFICOS (ZIP)"):
                with st.spinner("Compilando relatórios visuais..."):
                    z_buf = io.BytesIO()
                    with zipfile.ZipFile(z_buf, "w") as zf:
                        for cat in df['categoria'].unique():
                            img_bytes = criar_grafico_instagram(cat, df[df['categoria'] == cat])
                            zf.writestr(f"{cat}.png", img_bytes)
                    st.download_button("📥 BAIXAR ENVELOPE ZIP", z_buf.getvalue(), f"{escolha}_graficos.zip", "application/zip")
            
            for cat in df['categoria'].unique():
                with st.expander(f"Ver Classificação: {cat.upper()}"):
                    st.table(df[df['categoria'] == cat][['candidato', 'votos']].sort_values("votos", ascending=False).reset_index(drop=True))
