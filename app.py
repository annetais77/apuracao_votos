import streamlit as st
import pandas as pd
import zipfile, os, tempfile, re, io, random, textwrap
import matplotlib.pyplot as plt
from collections import Counter
from supabase import create_client, Client

# Imports para geração de PDF com ReportLab
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

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
    mencoes_brutas = [m.group(0) for m in re.finditer(r'@[A-Za-z0-9_.-]+', texto_str)]
    
    if not mencoes_brutas:
        return []

    if len(mencoes_brutas) > 1 and texto_str.startswith(mencoes_brutas[0]):
        mencoes_brutas = mencoes_brutas[1:]

    mencoes_limpas = [m.lower().strip().replace(" ", "") for m in mencoes_brutas]

    if autor:
        autor_limpo = f"@{str(autor).lower().strip()}"
        mencoes_limpas = [m for m in mencoes_limpas if m != autor_limpo]

    return mencoes_limpas

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

def buscar_todos_dados_cidade(cidade):
    """Busca todos os registros de uma cidade paginando para evitar o limite de 1000 linhas do Supabase"""
    todos_dados = []
    chunk = 1000
    inicio = 0
    while True:
        res = supabase.table("resultados_votos").select("*").eq("cidade", cidade).range(inicio, inicio + chunk - 1).execute()
        if not res.data:
            break
        todos_dados.extend(res.data)
        if len(res.data) < chunk:
            break
        inicio += chunk
    return todos_dados

def criar_grafico_instagram(categoria, df_cat):
    df_sorted = df_cat.sort_values("votos", ascending=False).reset_index(drop=True)
    df_sorted['rank'] = df_sorted['votos'].rank(method='min', ascending=False).astype(int)
    total = df_sorted['votos'].sum()
    top3_df = df_sorted.head(3)
    n_candidatos = len(top3_df)
    
    plt.close('all')
    fig, ax = plt.subplots(figsize=(10.8, 13.5))
    fig.patch.set_facecolor('#000000'); ax.set_facecolor('#000000')
    
    for _ in range(150): 
        ax.scatter(random.uniform(-0.6, 2.6), random.uniform(0, 1.2), alpha=0.3, s=15, color="white")
    
    ax.text(1, 1.18, str(categoria).upper(), color='white', fontsize=32, ha='center', weight='bold')
    
    mapa_cores = {1: "#FFD700", 2: "#C0C0C0", 3: "#CD7F32"}
    mapa_alturas = {1: 0.85, 2: 0.65, 3: 0.45}
    
    if n_candidatos == 1:
        pos_x = [1]
    elif n_candidatos == 2:
        pos_x = [0.5, 1.5]
    else:
        pos_x = [1, 0, 2]
    
    for i, (_, row) in enumerate(top3_df.iterrows()):
        rank = row['rank']
        cor, altura = mapa_cores.get(rank, "#CD7F32"), mapa_alturas.get(rank, 0.45)
        pct = round((row['votos']/total*100), 1) if total > 0 else 0
        
        ax.bar(pos_x[i], altura, color=cor, width=0.75, edgecolor='white', linewidth=2, zorder=3)
        
        nome_ajustado = "\n".join(textwrap.wrap(str(row['candidato']), width=12))
        ax.text(pos_x[i], altura + 0.035, nome_ajustado, color='white', ha='center', weight='black', fontsize=20, va='bottom')
        
        ax.text(pos_x[i], altura/2, f"{pct}%", color='black', ha='center', weight='black', fontsize=24, zorder=4)
        
    ax.set_xlim(-0.8, 2.8)
    ax.set_ylim(0, 1.3)
    ax.axis('off')
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.5, facecolor='#000000', dpi=100)
    return buf.getvalue()

def gerar_pdf_relatorio(cidade, escopo, categoria_nome, dados_brutos_processamento):
    """Gera um PDF formatado profissionalmente com o ReportLab"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#1f2937'), spaceAfter=6, alignment=1)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#4b5563'), spaceAfter=15, alignment=1)
    h2_style = ParagraphStyle('H2Style', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor('#111827'), spaceBefore=10, spaceAfter=6)
    body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#374151'), spaceAfter=4)
    
    # Cabeçalho
    story.append(Paragraph(f"<b>RELATÓRIO DE APURAÇÃO DE VOTOS</b>", title_style))
    story.append(Paragraph(f"<b>Cidade:</b> {cidade.upper()} | <b>Escopo:</b> {escopo.upper()}", subtitle_style))
    story.append(Spacer(1, 10))
    
    # Se os dados brutos de processamento estiverem disponíveis
    if dados_brutos_processamento:
        totais = dados_brutos_processamento.get("totais", {})
        story.append(Paragraph("<b>Métricas Gerais do Processamento:</b>", h2_style))
        
        metricas_data = [
            ["Métrica / Categoria", "Quantidade"],
            ["Total Geral de Votos Encontrados", str(totais.get("total_bruto", 0))],
            ["Total de Votos Válidos Computados", str(totais.get("validos", 0))],
            ["Votos Repetidos / Múltiplos Anulados", str(totais.get("repetidos", 0))],
            ["Votos Indecisos / Conflitantes Anulados", str(totais.get("indecisos", 0))],
            ["Votos com @ Inválidos / Errados", str(totais.get("errados", 0))]
        ]
        
        t_metricas = Table(metricas_data, colWidths=[300, 200])
        t_metricas.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e5e7eb')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#111827')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ]))
        story.append(t_metricas)
        story.append(Spacer(1, 15))
        
        story.append(Paragraph("<b>Detalhamento de Eleitores e Decisões de Voto:</b>", h2_style))
        detalhes = dados_brutos_processamento.get("detalhes_eleitores", [])
        if detalhes:
            det_data = [["Eleitor (@)", "Status do Voto", "Candidato / Motivo"]]
            for d in detalhes[:100]: # Limita para caber bem no PDF se houver muitos registros
                det_data.append([Paragraph(str(d.get("eleitor","")), body_style), 
                                 Paragraph(str(d.get("status","")), body_style), 
                                 Paragraph(str(d.get("info","")), body_style)])
            
            t_det = Table(det_data, colWidths=[120, 110, 270])
            t_det.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(t_det)
    else:
        story.append(Paragraph("Nenhum dado analítico detalhado carregado nesta sessão para montar o relatório por arquivo ZIP. Utilize o Painel de Upload para registrar as métricas.", body_style))
        
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

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
        t1, t2, t3, t4, t5, t6 = st.tabs(["🚀 Upload ZIP", "👁️ Preview", "✏️ Limpar Cidade", "📊 Cidades Ativas", "🔧 Central de Correção", "📄 Relatórios PDF"])
        
        with t1:
            cid_in = st.text_input("Nome da Cidade para Inserção/Atualização")
            arq = st.file_uploader("Subir arquivo compactado ZIP", type="zip")
            
            if arq and cid_in and st.button("PUBLICAR NO BANCO"):
                with tempfile.TemporaryDirectory() as tmp:
                    zipfile.ZipFile(arq, "r").extractall(tmp)
                    pay = []
                    
                    relatorio_aceitas = []
                    relatorio_rejeitadas = []
                    total_arquivos_encontrados = 0
                    
                    st.write("### 📝 Relatório Detalhado de Processamento do ZIP:")
                    
                    for root, dirs, files in os.walk(tmp):
                        for f in files:
                            if f.lower().endswith((".csv", ".xlsx")) and not f.startswith('.'):
                                total_arquivos_encontrados += 1
                                caminho_completo = os.path.join(root, f)
                                rel_path = os.path.relpath(caminho_completo, tmp)
                                nome_categoria = os.path.splitext(os.path.basename(f))[0].strip()
                                
                                try:
                                    df = pd.read_csv(caminho_completo) if f.lower().endswith(".csv") else pd.read_excel(caminho_completo)
                                    
                                    c_t = next((c for c in df.columns if any(k in c.lower() for k in ['text', 'coment', 'message', 'comment', 'texto']) and 'id' not in c.lower()), None)
                                    if not c_t and len(df.columns) > 0:
                                        c_t = df.columns[-1]
                                        
                                    c_u = next((c for c in df.columns if any(k in c.lower() for k in ['user', 'name', 'author', 'owner', 'usuari', 'perfil']) and 'id' not in c.lower()), None)
                                    if not c_u and len(df.columns) > 1:
                                        c_u = df.columns[1]
                                        
                                    if not c_t or not c_u or df.empty:
                                        motivo = f"Planilha vazia ou colunas de texto/usuário não identificadas no arquivo."
                                        relatorio_rejeitadas.append({"arquivo": rel_path, "categoria": nome_categoria, "motivo": motivo})
                                        continue

                                    votos_por_eleitor = {}
                                    votos_errados_count = 0
                                    
                                    for _, r in df.iterrows():
                                        u = str(r[c_u]).lower().strip() if pd.notna(r[c_u]) else "desconhecido"
                                        votos_comentario = extrair_votos(r[c_t], autor=u)
                                        
                                        if not votos_comentario:
                                            votos_errados_count += 1
                                        
                                        if u and votos_comentario:
                                            if u not in votos_por_eleitor:
                                                votos_por_eleitor[u] = []
                                            votos_por_eleitor[u].append({
                                                "voto": votos_comentario[0],
                                                "texto": str(r[c_t])[:60]
                                            })

                                    ct = Counter()
                                    detalhes_votos_arquivo = []
                                    eleitores_anulados_detalhes = []
                                    
                                    votos_validos_total = 0
                                    votos_repetidos_count = 0
                                    votos_indecisos_count = 0
                                    
                                    lista_auditoria_detalhada = []

                                    for eleitor, registros in votos_por_eleitor.items():
                                        candidatos_distintos = set(reg["voto"] for reg in registros)
                                        
                                        if len(candidatos_distintos) > 1:
                                            votos_indecisos_count += 1
                                            eleitores_anulados_detalhes.append(
                                                f"O eleitor @{eleitor} tentou votar em múltiplos candidatos distintos ({', '.join(candidatos_distintos)}) e teve seus votos anulados."
                                            )
                                            lista_auditoria_detalhada.append({
                                                "eleitor": f"@{eleitor}",
                                                "status": "Anulado (Indeciso)",
                                                "info": f"Múltiplos candidatos: {', '.join(candidatos_distintos)}"
                                            })
                                        elif len(registros) > 1:
                                            votos_repetidos_count += 1
                                            voto_final = registros[0]["voto"]
                                            ct[voto_final] += 1
                                            votos_validos_total += 1
                                            lista_auditoria_detalhada.append({
                                                "eleitor": f"@{eleitor}",
                                                "status": "Válido (Repetido computado 1x)",
                                                "info": f"Votou em {voto_final} várias vezes"
                                            })
                                        else:
                                            voto_final = registros[0]["voto"]
                                            ct[voto_final] += 1
                                            votos_validos_total += 1
                                            lista_auditoria_detalhada.append({
                                                "eleitor": f"@{eleitor}",
                                                "status": "Válido",
                                                "info": f"Votou em {voto_final}"
                                            })
                                    
                                    total_bruto_arq = len(df)
                                    
                                    # Armazenar estado global na sessão para o relatório PDF
                                    if "relatorios_cache_pdf" not in st.session_state:
                                        st.session_state["relatorios_cache_pdf"] = {}
                                        
                                    st.session_state["relatorios_cache_pdf"][f"{cid_in.strip()}_{nome_categoria}"] = {
                                        "totais": {
                                            "total_bruto": total_bruto_arq,
                                            "validos": votos_validos_total,
                                            "repetidos": votos_repetidos_count,
                                            "indecisos": votos_indecisos_count,
                                            "errados": votos_errados_count
                                        },
                                        "detalhes_eleitores": lista_auditoria_detalhada
                                    }

                                    votos_deste_arquivo = [{"cidade": cid_in.strip(), "categoria": nome_categoria, "candidato": cand, "votos": qtd} for cand, qtd in ct.items()]
                                    
                                    if votos_deste_arquivo:
                                        pay.extend(votos_deste_arquivo)
                                        relatorio_aceitas.append({
                                            "categoria": nome_categoria,
                                            "arquivo": rel_path,
                                            "candidatos": len(votos_deste_arquivo),
                                            "total_votos": sum(ct.values()),
                                            "alertas_anulacao": eleitores_anulados_detalhes,
                                            "detalhes": detalhes_votos_arquivo
                                        })
                                    else:
                                        motivo = "A planilha foi lida, mas nenhum @ válido de voto foi encontrado."
                                        relatorio_rejeitadas.append({"arquivo": rel_path, "categoria": nome_categoria, "motivo": motivo})
                                        
                                except Exception as err_arq:
                                    relatorio_rejeitadas.append({"arquivo": rel_path, "categoria": nome_categoria, "motivo": f"Erro técnico na leitura: {err_arq}"})
                    
                    if pay:
                        try:
                            df_pay_temp = pd.DataFrame(pay)
                            df_pay_agrupado = df_pay_temp.groupby(['cidade', 'categoria', 'candidato'], as_index=False)['votos'].sum()
                            pay_final = df_pay_agrupado.to_dict(orient='records')

                            cats_no_zip = list(set([item['categoria'] for item in pay_final]))
                            
                            for categoria_deletar in cats_no_zip:
                                supabase.table("resultados_votos").delete().eq("cidade", cid_in.strip()).eq("categoria", categoria_deletar).execute()
                            
                            chunk_size = 100
                            for chunk_id in range(0, len(pay_final), chunk_size):
                                supabase.table("resultados_votos").insert(pay_final[chunk_id:chunk_id + chunk_size]).execute()
                            
                            st.success(f"🏆 Publicação concluída com sucesso no banco para '{cid_in.strip()}'! Total de categorias salvas: {len(cats_no_zip)}")
                        except Exception as database_error:
                            st.error(f"🚨 O Supabase recusou os dados! Motivo técnico: {database_error}")
                    else:
                        st.error("❌ O ZIP continha planilhas, mas nenhuma delas possuía dados válidos computáveis para salvar.")

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
                res_cats = buscar_todos_dados_cidade(cid)
                cats = sorted(list(set([i['categoria'] for i in res_cats]))) if res_cats else []
                
                if not cats:
                    st.info("Nenhuma categoria encontrada para esta cidade.")
                else:
                    cat = st.selectbox("2. Escolha a Categoria para editar/visualizar:", cats, key="m_cat")
                    if cat:
                        df_c = pd.DataFrame([i for i in res_cats if i['categoria'] == cat])
                        if not df_c.empty:
                            df_c = df_c.sort_values("votos", ascending=False).reset_index(drop=True)
                            df_editado = st.data_editor(df_c[['candidato', 'votos']], key="editor_grade")
                            
                            if st.button("💾 SALVAR EDIÇÕES DA TABELA"):
                                for idx, row in df_editado.iterrows():
                                    linha_orig = df_c.iloc[idx]
                                    if row['votos'] != linha_orig['votos'] or row['candidato'] != linha_orig['candidato']:
                                        supabase.table("resultados_votos").update({"candidato": row['candidato'], "votos": int(row['votos'])}).eq("cidade", cid).eq("categoria", cat).eq("candidato", linha_orig['candidato']).execute()
                                st.success("Tabela atualizada!")
                                st.rerun()
            else:
                st.info("Nenhuma cidade cadastrada no banco.")

        with t6:
            st.write("### 📄 Central de Relatórios Profissionais (PDF)")
            cidades_pdf = listar_cidades()
            if cidades_pdf:
                cidade_esc = st.selectbox("Selecione a Cidade:", cidades_pdf, key="pdf_cidade")
                
                res_pdf = buscar_todos_dados_cidade(cidade_esc)
                cats_pdf = sorted(list(set([i['categoria'] for i in res_pdf]))) if res_pdf else []
                
                tipo_relatorio = st.radio("Escolha o Escopo do Relatório:", ["Relatório por Categoria Específica", "Relatório Consolidado de Todas as Categorias"])
                
                cat_selecionada = None
                if tipo_relatorio == "Relatório por Categoria Específica" and cats_pdf:
                    cat_selecionada = st.selectbox("Escolha a Categoria:", cats_pdf, key="pdf_cat_esp")
                
                cache_key = f"{cidade_esc}_{cat_selecionada}" if cat_selecionada else f"{cidade_esc}_geral"
                dados_amostra = st.session_state.get("relatorios_cache_pdf", {}).get(cache_key, None)
                
                if st.button("📥 GERAR RELATÓRIO PDF PROFISSIONAL"):
                    with st.spinner("Compilando PDF..."):
                        pdf_bytes = gerar_pdf_relatorio(
                            cidade=cidade_esc,
                            escopo=tipo_relatorio,
                            categoria_nome=cat_selecionada or "Todas as Categorias",
                            dados_brutos_processamento=dados_amostra
                        )
                        st.download_button(
                            label="⬇️ Clique aqui para baixar o PDF gerado",
                            data=pdf_bytes,
                            file_name=f"Relatorio_Apuracao_{cidade_esc}.pdf",
                            mime="application/pdf"
                        )
            else:
                st.info("Nenhuma cidade disponível para gerar relatórios.")

# --- MODO PÚBLICO ---
else:
    st.title("🔍 Painel de Resultados Disponíveis")
    cidades = listar_cidades()
    escolha = st.selectbox("Selecione a cidade desejada:", ["-- Escolha --"] + cidades)
    if escolha != "-- Escolha --":
        dados_completos = buscar_todos_dados_cidade(escolha)
        df = pd.DataFrame(dados_completos)
        
        if not df.empty:
            if st.button("📦 GERAR E BAIXAR TODOS OS GRÁFICOS (ZIP)"):
                with st.spinner("Compilando todos os gráficos de todas as categorias..."):
                    z_buf = io.BytesIO()
                    with zipfile.ZipFile(z_buf, "w") as zf:
                        for cat in df['categoria'].unique():
                            img_bytes = criar_grafico_instagram(cat, df[df['categoria'] == cat])
                            zf.writestr(f"{cat}.png", img_bytes)
                    st.download_button("📥 BAIXAR ENVELOPE ZIP COMPLETO", z_buf.getvalue(), f"{escolha}_graficos.zip", "application/zip")
            
            st.success(f"📂 Total de categorias carregadas: **{len(df['categoria'].unique())}**")
            
            for cat in df['categoria'].unique():
                with st.expander(f"Ver Classificação: {cat.upper()} (Total de Votos: {df[df['categoria'] == cat]['votos'].sum()})"):
                    st.table(df[df['categoria'] == cat][['candidato', 'votos']].sort_values("votos", ascending=False).reset_index(drop=True))
        else:
            st.info("Nenhum dado encontrado para esta cidade.")
