import streamlit as st
import pandas as pd
import zipfile, os, tempfile, re, io, random, textwrap
import matplotlib.pyplot as plt
from collections import Counter
from supabase import create_client, Client

# --- IMPORTS PARA PDF (REPORTLAB) ---
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
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

def gerar_pdf_relatorio(cidade, dados_relatorio, tipo_relatorio="categoria"):
    buffer = io.BytesIO()
    # Usando orientação paisagem (landscape) para dar espaço confortável para todas as colunas
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, textColor=colors.HexColor("#111111"), spaceAfter=4, alignment=1)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, textColor=colors.HexColor("#555555"), spaceAfter=12, alignment=1)
    section_style = ParagraphStyle('SectionStyle', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12, textColor=colors.HexColor("#2C3E50"), spaceBefore=10, spaceAfter=6)
    normal_style = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor("#333333"))
    bold_style = ParagraphStyle('BoldStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor("#111111"))

    elements.append(Paragraph("🏆 RELATÓRIO ANALÍTICO DE APURAÇÃO POR ELEITOR", title_style))
    elements.append(Paragraph(f"<b>Cidade:</b> {cidade.upper()} | <b>Tipo:</b> {tipo_relatorio.capitalize()}", subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2C3E50"), spaceAfter=12))

    for cat_nome, cat_info in dados_relatorio.items():
        elements.append(Paragraph(f"📁 Categoria: {cat_nome.upper()}", section_style))
        
        elements.append(Paragraph("<b>Classificação Geral de Candidatos:</b>", bold_style))
        elements.append(Spacer(1, 3))
        
        cand_data = [["Candidato / @", "Total de Votos Válidos"]]
        for cand, qtd in sorted(cat_info['resumo_candidatos'].items(), key=lambda x: x[1], reverse=True):
            cand_data.append([Paragraph(str(cand), normal_style), Paragraph(str(qtd), bold_style)])
        
        t_cand = Table(cand_data, colWidths=[350, 150])
        t_cand.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2C3E50")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('BOTTOMPADDING', (0,0), (-1,0), 5),
            ('TOPPADDING', (0,0), (-1,0), 5),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8F9F9")]),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#BDC3C7")),
        ]))
        elements.append(t_cand)
        elements.append(Spacer(1, 10))

        elements.append(Paragraph("<b>Extrato Detalhado por Eleitor (@):</b>", bold_style))
        elements.append(Spacer(1, 3))

        # Adicionada a coluna "Arrobas Marcados" antes do Motivo
        eleitores_data = [["Eleitor (@)", "Apurados", "Descartados", "Resultado Final", "Arrobas Marcados", "Motivo / Observação do Descarte"]]
        
        for item_eleitor in cat_info['extrato_eleitores']:
            motivo_txt = item_eleitor['motivo'] if item_eleitor['motivo'] else "Voto computado com sucesso."
            mot_cor = colors.HexColor("#C0392B") if item_eleitor['descartados'] > 0 else colors.HexColor("#27AE60")
            
            eleitores_data.append([
                Paragraph(str(item_eleitor['eleitor']), normal_style),
                Paragraph(str(item_eleitor['apurados']), normal_style),
                Paragraph(str(item_eleitor['descartados']), normal_style),
                Paragraph(str(item_eleitor['validos']), bold_style),
                Paragraph(str(item_eleitor['arrobas_marcados']), normal_style),
                Paragraph(f"<font color='{mot_cor.hexval()}'>{motivo_txt}</font>", normal_style)
            ])

        if len(eleitores_data) > 1:
            # Larguras ajustadas para o formato paisagem (Total útil: ~742 pt)
            t_eleitores = Table(eleitores_data, colWidths=[120, 55, 65, 80, 160, 262])
            t_eleitores.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#34495E")),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,0), 8),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('TOPPADDING', (0,0), (-1,-1), 4),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#BDC3C7")),
            ]))
            elements.append(t_eleitores)
        else:
            elements.append(Paragraph("Nenhum registro de eleitor encontrado.", normal_style))

        elements.append(Spacer(1, 15))

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

                                    votos_por_eleitor = {}
                                    for _, r in df.iterrows():
                                        u = str(r[c_u]).lower().strip() if pd.notna(r[c_u]) else "desconhecido"
                                        votos_comentario = extrair_votos(r[c_t], autor=u)
                                        
                                        if u and votos_comentario:
                                            if u not in votos_por_eleitor:
                                                votos_por_eleitor[u] = []
                                            for v_encontrado in votos_comentario:
                                                votos_por_eleitor[u].append(v_encontrado)

                                    ct = Counter()
                                    for eleitor, lista_votos in votos_por_eleitor.items():
                                        candidatos_distintos = set(lista_votos)
                                        if len(candidatos_distintos) == 1:
                                            ct[list(candidatos_distintos)[0]] += 1
                                    
                                    votos_deste_arquivo = [{"cidade": cid_in.strip(), "categoria": nome_categoria, "candidato": cand, "votos": qtd} for cand, qtd in ct.items()]
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
            st.markdown("Gera um relatório profissional completo contendo o extrato por eleitor (`@`), exibindo a quantidade apurada, descartados, resultado final, arrobas marcados e o motivo.")
            
            cidades_pdf = listar_cidades()
            if cidades_pdf:
                cid_pdf = st.selectbox("Selecione a Cidade:", cidades_pdf, key="pdf_cidade")
                
                st.markdown("#### 📂 Envie a planilha ou ZIP original correspondente para gerar o relatório analítico por eleitor:")
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

                                votos_por_eleitor_detalhes = {}
                                resumo_cand = Counter()
                                extrato_eleitores = []

                                for _, r in df_lido.iterrows():
                                    u = str(r[c_u]).lower().strip() if pd.notna(r[c_u]) else "desconhecido"
                                    votos_com = extrair_votos(r[c_t], autor=u)
                                    if u:
                                        if u not in votos_por_eleitor_detalhes:
                                            votos_por_eleitor_detalhes[u] = []
                                        for v in votos_com:
                                            votos_por_eleitor_detalhes[u].append(v)

                                for eleitor, lista_votos in votos_por_eleitor_detalhes.items():
                                    apurados = len(lista_votos)
                                    if apurados == 0:
                                        continue
                                    
                                    candidatos_distintos = set(lista_votos)
                                    arrobas_marcados_str = ", ".join(sorted(list(candidatos_distintos)))
                                    
                                    if len(candidatos_distintos) > 1:
                                        # Caso 1: Votou em candidatos diferentes -> Anula tudo
                                        descartados = apurados
                                        validos = 0
                                        motivo = f"Descartado: Tentativa de voto em múltiplos candidatos distintos ({arrobas_marcados_str})."
                                    elif len(candidatos_distintos) == 1:
                                        # Caso 2: Votou no mesmo candidato várias vezes -> Conta 1 válido e descarta as repetições
                                        voto_final = list(candidatos_distintos)[0]
                                        validos = 1
                                        descartados = apurados - 1
                                        resumo_cand[voto_final] += validos
                                        if descartados > 0:
                                            motivo = f"Descartado: Excesso de repetição ({apurados} votos apurados para o mesmo candidato, computado apenas 1)."
                                        else:
                                            motivo = ""

                                    extrato_eleitores.append({
                                        "eleitor": f"@{eleitor}",
                                        "apurados": apurados,
                                        "descartados": descartados,
                                        "validos": validos,
                                        "arrobas_marcados": arrobas_marcados_str,
                                        "motivo": motivo
                                    })

                                dados_para_pdf[nome_cat] = {
                                    "resumo_candidatos": dict(resumo_cand),
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
