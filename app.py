import streamlit as st
import pandas as pd
import zipfile, os, tempfile, re, io, random, textwrap
import matplotlib.pyplot as plt
from collections import Counter
from supabase import create_client, Client

# --- IMPORTS PARA PDF (REPORTLAB) ---
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Portal de Apuração", layout="wide", page_icon="🏆")
SUPABASE_URL = "https://nualgtyikfijnjzmybsg.supabase.co"
SUPABASE_KEY = "sb_publishable_e9RRmaN-2XIryrki_lpWhA_uC5sHZ1K"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ESTILO ---
st.markdown("<style>.main {background-color: #000; color: #fff;}</style>", unsafe_allow_html=True)

# --- FUNÇÕES DE APURAÇÃO ---
def extrair_votos(texto, autor=None):
    if pd.isna(texto): return []
    texto_str = str(texto).strip()
    mencoes_brutas = [m.group(0) for m in re.finditer(r'@[A-Za-z0-9_.-]+', texto_str)]
    if not mencoes_brutas:
        return []
    
    mencoes_limpas = [m.lower().strip().replace(" ", "") for m in mencoes_brutas]
    if autor:
        autor_limpo = f"@{str(autor).lower().strip()}"
        # Remove o voto em si mesmo se houver
        mencoes_limpas = [m for m in mencoes_limpas if m != autor_limpo]
    return mencoes_limpas

def listar_cidades():
    try:
        res = supabase.table("cidades_unicas").select("cidade").execute()
        if res.data:
            return sorted(list(set([item['cidade'].strip() for item in res.data if item.get('cidade')])))
        return []
    except Exception as e:
        st.error(f"Erro técnico ao listar cidades: {e}")
        return []

def buscar_todos_dados_cidade(cidade):
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
        v_val = row.get('votos', 0)
        pct = round((v_val/total*100), 1) if total > 0 else 0
        
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

def gerar_pdf_relatorio(cidade, dados_relatorio, tipo_relatorio="categoria"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=14, textColor=colors.HexColor("#111111"), spaceAfter=3, alignment=1)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, textColor=colors.HexColor("#555555"), spaceAfter=8, alignment=1)
    section_style = ParagraphStyle('SectionStyle', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor("#2C3E50"), spaceBefore=6, spaceAfter=3)
    normal_style = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=7, textColor=colors.HexColor("#333333"))
    center_style = ParagraphStyle('CenterStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=7, textColor=colors.HexColor("#333333"), alignment=1)
    bold_style = ParagraphStyle('BoldStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, textColor=colors.HexColor("#111111"))

    elements.append(Paragraph("🏆 RELATÓRIO ANALÍTICO DE APURAÇÃO", title_style))
    elements.append(Paragraph(f"<b>Cidade:</b> {cidade.upper()} | <b>Tipo:</b> {tipo_relatorio.capitalize()}", subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2C3E50"), spaceAfter=8))

    primeira_categoria = True
    for cat_nome, cat_info in dados_relatorio.items():
        if not primeira_categoria:
            elements.append(PageBreak())
        primeira_categoria = False

        elements.append(Paragraph(f"📁 Categoria: {cat_nome.upper()}", section_style))
        elements.append(Paragraph("<b>Classificação Geral de Candidatos por @:</b>", bold_style))
        elements.append(Spacer(1, 2))
        
        cand_data = [["Candidato / @", "Total Votos", "Válidos", "Repetidos", "Indecisos", "@ Errados"]]
        for cand, info in sorted(cat_info['resumo_candidatos'].items(), key=lambda x: x[1]['validos'], reverse=True):
            cand_data.append([
                Paragraph(str(cand), normal_style),
                Paragraph(str(info['total']), center_style),
                Paragraph(str(info['validos']), center_style),
                Paragraph(str(info['repetidos']), center_style),
                Paragraph(str(info['indecisos']), center_style),
                Paragraph(str(info['errados']), center_style)
            ])
        
        t_cand = Table(cand_data, colWidths=[351.89, 90, 90, 90, 90, 90], repeatRows=1)
        t_cand.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2C3E50")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8F9F9")]),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#BDC3C7")),
        ]))
        elements.append(t_cand)
        elements.append(Spacer(1, 6))

        elements.append(Paragraph("<b>Extrato Detalhado por Eleitor (@):</b>", bold_style))
        elements.append(Spacer(1, 2))

        eleitores_data = [["Eleitor (@)", "@ Mencionado", "Status / Descarte", "Motivo da Observação"]]
        for item_eleitor in cat_info['extrato_eleitores']:
            eleitores_data.append([
                Paragraph(str(item_eleitor['eleitor']), normal_style),
                Paragraph(str(item_eleitor['mencionado']), normal_style),
                Paragraph(str(item_eleitor['status']), bold_style),
                Paragraph(str(item_eleitor['motivo']), normal_style)
            ])

        if len(eleitores_data) > 1:
            t_eleitores = Table(eleitores_data, colWidths=[150, 150, 120, 381.89], repeatRows=1)
            t_eleitores.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#34495E")),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 3),
                ('TOPPADDING', (0,0), (-1,-1), 3),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#BDC3C7")),
            ]))
            elements.append(t_eleitores)
        else:
            elements.append(Paragraph("Nenhum registro de eleitor encontrado.", normal_style))

        elements.append(Spacer(1, 8))

    doc.build(elements)
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
        t1, t2, t3, t4, t5, t6 = st.tabs([
            "🚀 Upload ZIP", 
            "👁️ Preview", 
            "✏️ Limpar Cidade", 
            "📊 Cidades Ativas", 
            "🔧 Central de Correção", 
            "📄 Relatório PDF"
        ])
        
        with t1:
            cid_in = st.text_input("Nome da Cidade para Inserção/Atualização")
            arq = st.file_uploader("Subir arquivo compactado ZIP", type="zip")
            
            if arq and cid_in and st.button("PUBLICAR NO BANCO"):
                with tempfile.TemporaryDirectory() as tmp:
                    zipfile.ZipFile(arq, "r").extractall(tmp)
                    pay = []
                    
                    for root, dirs, files in os.walk(tmp):
                        for f in files:
                            if f.lower().endswith((".csv", ".xlsx")) and not f.startswith('.'):
                                caminho_completo = os.path.join(root, f)
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
                                        continue

                                    resumo_cand_temp = {}
                                    for _, r in df.iterrows():
                                        u = str(r[c_u]).lower().strip() if pd.notna(r[c_u]) else "desconhecido"
                                        votos_com = extrair_votos(r[c_t], autor=u)
                                        if votos_com:
                                            cand_votado = votos_com[0]
                                            # Considera válido se houver menção limpa unificada
                                            if len(set(votos_com)) == 1:
                                                if cand_votado not in resumo_cand_temp:
                                                    resumo_cand_temp[cand_votado] = 0
                                                resumo_cand_temp[cand_votado] += 1
                                    
                                    votos_deste_arquivo = [{"cidade": cid_in.strip(), "categoria": nome_categoria, "candidato": cand, "votos": qtd} for cand, qtd in resumo_cand_temp.items()]
                                    if votos_deste_arquivo:
                                        pay.extend(votos_deste_arquivo)
                                except Exception:
                                    pass
                    
                    if pay:
                        try:
                            df_pay_temp = pd.DataFrame(pay)
                            df_pay_agrupado = df_pay_temp.groupby(['cidade', 'categoria', 'candidato'], as_index=False)['votos'].sum()
                            pay_final = df_pay_agrupado.to_dict(orient='records')
                            cats_no_zip = list(set([item['categoria'] for item in pay_final]))
                            
                            for categoria_deletar in cats_no_zip:
                                supabase.table("resultados_votos").delete().eq("cidade", cid_in.strip()).eq("categoria", categoria_deletar).execute()
                            
                            for chunk_id in range(0, len(pay_final), 100):
                                supabase.table("resultados_votos").insert(pay_final[chunk_id:chunk_id + 100]).execute()
                            
                            st.success(f"🏆 Publicação concluída com sucesso no banco para '{cid_in.strip()}'!")
                        except Exception as database_error:
                            st.error(f"🚨 Erro no Supabase: {database_error}")

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
                
                if cats:
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

        with t6:
            st.write("### 📄 Central de Geração de Relatórios em PDF")
            st.markdown("Gera um relatório profissional completo contendo as tabelas consolidadas por candidato e o extrato detalhado por eleitor (`@`).")
            
            cidades_pdf = listar_cidades()
            if cidades_pdf:
                cid_pdf = st.selectbox("Selecione a Cidade:", cidades_pdf, key="pdf_cidade")
                
                st.markdown("#### 📂 Envie a planilha ou ZIP original correspondente para gerar o relatório analítico:")
                arq_pdf_origem = st.file_uploader("Arquivo da Categoria (CSV, XLSX ou ZIP)", type=["csv", "xlsx", "zip"], key="pdf_arq_origem")
                
                modo_pdf = st.radio("Escopo do Relatório:", ["Relatório por Categoria Específica", "Relatório Consolidado (Todas as Categorias do Arquivo)"])
                
                if arq_pdf_origem:
                    dados_para_pdf = {}
                    
                    with tempfile.TemporaryDirectory() as tmp_pdf:
                        if arq_pdf_origem.name.endswith(".zip"):
                            zipfile.ZipFile(arq_pdf_origem, "r").extractall(tmp_pdf)
                            arquivos_para_ler = []
                            for r, ds, fs in os.walk(tmp_pdf):
                                for f in fs:
                                    if f.lower().endswith((".csv", ".xlsx")) and not f.startswith('.'):
                                        arquivos_para_ler.append((os.path.join(r, f), os.path.splitext(f)[0].strip()))
                        else:
                            caminho_unico = os.path.join(tmp_pdf, arq_pdf_origem.name)
                            with open(caminho_unico, "wb") as f_out:
                                f_out.write(arq_pdf_origem.getbuffer())
                            arquivos_para_ler = [(caminho_unico, os.path.splitext(arq_pdf_origem.name)[0].strip())]

                        for caminho_arq, nome_cat in arquivos_para_ler:
                            try:
                                df_lido = pd.read_csv(caminho_arq) if caminho_arq.endswith(".csv") else pd.read_excel(caminho_arq)
                                c_t = next((c for c in df_lido.columns if any(k in c.lower() for k in ['text', 'coment', 'message', 'comment', 'texto']) and 'id' not in c.lower()), df_lido.columns[-1])
                                c_u = next((c for c in df_lido.columns if any(k in c.lower() for k in ['user', 'name', 'author', 'owner', 'usuari', 'perfil']) and 'id' not in c.lower()), df_lido.columns[1])

                                resumo_cand_estruturado = {}
                                extrato_eleitores = []

                                for _, r in df_lido.iterrows():
                                    u = str(r[c_u]).lower().strip() if pd.notna(r[c_u]) else "desconhecido"
                                    texto_str = str(r[c_t]).strip() if pd.notna(r[c_t]) else ""
                                    
                                    mencoes_brutas = [m.group(0) for m in re.finditer(r'@[A-Za-z0-9_.-]+', texto_str)]
                                    votos_com = extrair_votos(texto_str, autor=u)
                                    candidatos_distintos = set(votos_com)
                                    
                                    mencao_str = ", ".join(mencoes_brutas) if mencoes_brutas else "Nenhuma menção"
                                    
                                    # Lógica robusta de status e contadores atualizada
                                    if len(mencoes_brutas) == 0:
                                        status = "Descartado"
                                        motivo = "Comentário sem menção de @."
                                    elif len(candidatos_distintos) > 1:
                                        status = "Descartado"
                                        motivo = "Tentativa de voto em múltiplos candidatos distintos (Indeciso)."
                                        for cand_err in candidatos_distintos:
                                            if cand_err not in resumo_cand_estruturado:
                                                resumo_cand_estruturado[cand_err] = {"total": 0, "validos": 0, "repetidos": 0, "indecisos": 0, "errados": 0}
                                            resumo_cand_estruturado[cand_err]["total"] += 1
                                            resumo_cand_estruturado[cand_err]["indecisos"] += 1
                                    elif len(votos_com) == 0:
                                        status = "Descartado"
                                        motivo = "Menção de @ incorreta ou voto em si mesmo."
                                    else:
                                        cand_alvo = list(candidatos_distintos)[0]
                                        if cand_alvo not in resumo_cand_estruturado:
                                            resumo_cand_estruturado[cand_alvo] = {"total": 0, "validos": 0, "repetidos": 0, "indecisos": 0, "errados": 0}
                                        
                                        # Verifica se houve repetição de menção ao mesmo candidato no mesmo comentário
                                        if len(votos_com) > 1:
                                            status = "Computado (Com Repetições)"
                                            motivo = "Voto válido, mas com menções repetidas ao mesmo candidato."
                                            resumo_cand_estruturado[cand_alvo]["validos"] += 1
                                            resumo_cand_estruturado[cand_alvo]["repetidos"] += 1
                                            resumo_cand_estruturado[cand_alvo]["total"] += 1
                                        else:
                                            status = "Computado"
                                            motivo = "Voto computado com sucesso."
                                            resumo_cand_estruturado[cand_alvo]["validos"] += 1
                                            resumo_cand_estruturado[cand_alvo]["total"] += 1

                                    extrato_eleitores.append({
                                        "eleitor": f"@{u}",
                                        "mencionado": mencao_str,
                                        "status": status,
                                        "motivo": motivo
                                    })

                                dados_para_pdf[nome_cat] = {
                                    "resumo_candidatos": resumo_cand_estruturado,
                                    "extrato_eleitores": extrato_eleitores
                                }
                            except Exception as e:
                                st.warning(f"Erro ao processar arquivo {nome_cat}: {e}")

                    if modo_pdf == "Relatório por Categoria Específica" and dados_para_pdf:
                        cat_escolhida_pdf = st.selectbox("Escolha a Categoria:", list(dados_para_pdf.keys()))
                        dados_filtrados = {cat_escolhida_pdf: dados_para_pdf[cat_escolhida_pdf]}
                    else:
                        dados_filtrados = dados_para_pdf

                    if dados_filtrados and st.button("📥 GERAR E BAIXAR RELATÓRIO PDF ANALÍTICO"):
                        pdf_bytes = gerar_pdf_relatorio(cid_pdf, dados_filtrados, tipo_relatorio="Consolidado" if len(dados_filtrados) > 1 else "Categoria")
                        st.download_button(
                            label="📄 Baixar PDF Analítico por Eleitor",
                            data=pdf_bytes,
                            file_name=f"Relatorio_Analitico_{cid_pdf}.pdf",
                            mime="application/pdf"
                        )
                else:
                    st.info("Envie o arquivo original da categoria ou ZIP para calcular os totais por eleitor no relatório PDF.")
            else:
                st.info("Nenhuma cidade cadastrada.")

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
                with st.spinner("Compilando todos os gráficos..."):
                    z_buf = io.BytesIO()
                    with zipfile.ZipFile(z_buf, "w") as zf:
                        for cat in df['categoria'].unique():
                            img_bytes = criar_grafico_instagram(cat, df[df['categoria'] == cat])
                            zf.writestr(f"{cat}.png", img_bytes)
                    st.download_button("📥 BAIXAR ENVELOPE ZIP COMPLETO", z_buf.getvalue(), f"{escolha}_graficos.zip", "application/zip")
            
            for cat in df['categoria'].unique():
                with st.expander(f"Ver Classificação: {cat.upper()} (Total de Votos: {df[df['categoria'] == cat]['votos'].sum()})"):
                    st.table(df[df['categoria'] == cat][['candidato', 'votos']].sort_values("votos", ascending=False).reset_index(drop=True))
        else:
            st.info("Nenhum dado encontrado para esta cidade.")
