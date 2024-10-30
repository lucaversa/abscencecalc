# request_ia.py

import logging
import os
import re
import google.generativeai as genai
import json
import markdown  # Importar a biblioteca markdown

# Configurar a API Key de forma segura
# GENAI_API_KEY = os.environ.get("GENAI_API_KEY")
GENAI_API_KEY = "AIzaSyDngoemSHtclSXsoVlZe1Vnz50a8o7AcEg"  # Defina essa variável no seu ambiente

if not GENAI_API_KEY:
    raise ValueError("A variável de ambiente 'GENAI_API_KEY' não está definida.")

genai.configure(api_key=GENAI_API_KEY)

# Configuração do modelo
generation_config = {
    "temperature": 0.7,  # Ajuste conforme necessário
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 5500,  # Ajuste conforme a necessidade
    "response_mime_type": "text/plain",
}

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config=generation_config,
)

def analyze_performance(metrica, info_aluno):
    """
    Envia os dados de métricas e informações do aluno para a IA e retorna a análise em HTML.

    :param metrica: Dicionário contendo as métricas de desempenho.
    :param info_aluno: Dicionário contendo as informações do aluno.
    :return: String com a análise gerada pela IA em HTML.
    """
    try:
        # Construir o prompt conforme especificações
        prompt_instructions = (
            "Por favor, faça uma análise abrangente e detalhada do desempenho acadêmico fornecido com base nas informações seguintes. "
            "A análise deve ser adequada para uma interface de aplicativo e incluir os seguintes elementos, cada um começando com um título de seção em negrito e acompanhado de um emoji relevante dentro de um parágrafo HTML (<p><strong>📊 Título da Seção</strong></p>):\n\n"
            "1. Visão geral do desempenho, incluindo a média global. \n"
            "   - **Nota:** Ao calcular a média global, considere todas as disciplinas, inclusive aquelas com período maior que 12.\n"
            "2. Evolução do desempenho entre os períodos, considerando métricas relevantes.\n"
            "   - **Nota:** Para esta e todas as demais análises, desconsidere quaisquer disciplinas com período maior que 12.\n"
            "3. Análise dos pontos e áreas fortes com emojis (sempre enviar as notas e lembre-se que as notas são números inteiros e não porcentagem).\n"
            "4. Áreas para melhoria com recomendações práticas e emojis (sempre enviar as notas e lembre-se que as notas são números inteiros e não porcentagem). Considere uma área para melhoria apenas aquelas disciplinas em que a nota for menor que 65.\n"
            "5. Avaliação da consistência das notas.\n"
            "6. Diferenciação entre habilidades práticas e teóricas.\n"
            "7. Sugestões práticas para melhorias e uso de emojis para manter o texto leve.\n"
            "8. Destacar os pontos fortes e positivos a serem mantidos.\n\n"
            "O texto deve ser envolvente, conciso e utilizar uma linguagem que motive o usuário, incluindo o uso de emojis e frases curtas.\n\n"
            "- Utilize como referência: o ideal é a média do período ou global ser acima de 75 (não cite essa frase diretamente).\n\n"
            "- Utilize tópicos, mas não exagere para não poluir a visualização.\n\n"
            "- NÃO UTILIZE asteriscos em nenhuma parte do texto.\n\n"
            "**Formatação HTML:**\n"
            "- Cada seção deve começar com um parágrafo contendo o título da seção em negrito e acompanhado de um emoji relevante. Exemplo:\n"
            "  `<p><strong>📊 Visão Geral do Desempenho</strong></p>`\n"
            "- O conteúdo de cada seção deve estar imediatamente abaixo do título correspondente, utilizando tags HTML apropriadas, como `<p>`, `<ul>`, `<li>`, etc.\n\n"
            "- **NÃO UTILIZE SOB NENHUMA HIPÓTESE** delimitadores de blocos de código como ```html no início e ``` no final da saída.\n\n"
            "A saída deve ser apenas o HTML necessário para renderizar as seções corretamente no seu aplicativo.\n\n"
            "Aqui estão os dados para análise:\n"
        )

        # Serializar os dados para inclusão no prompt
        dados_json = json.dumps({
            'metrica': metrica,
            'info_aluno': info_aluno
        }, ensure_ascii=False, indent=4)

        prompt = f"{prompt_instructions}{dados_json}"

        # Iniciar a sessão de chat
        chat_session = model.start_chat(
            history=[]
        )

        # Enviar a mensagem para a IA
        response = chat_session.send_message(prompt)

        # Obter o texto da resposta
        resposta_texto = response.text

        # Converter Markdown para HTML
        resposta_html = markdown.markdown(resposta_texto)

        return resposta_html

    except Exception as e:
        logging.error(f"Erro na análise da performance: {str(e)}")
        return {
            "error": True,
            "message": f"Ocorreu um erro ao analisar a performance: {str(e)}"
        }

def analyze_curriculo(metrica, info_aluno, extensao, eventos_sus, cursos_aperfeicoamento, 
                     monitoria, pesquisa_ic, eventos_regionais, eventos_nacionais, 
                     artigos_nao_indexados, artigos_doi, congressos, representacao_estudantil,
                     ligas_academicas, lingua_estrangeira, pet_saude, estagio_nao_obrigatorio):
    try:
        # Construir o prompt base com formato JSON explícito
        prompt_instructions = (
            "Analise os dados abaixo e calcule a pontuação total do usuário (máximo 100 pontos)."
            "\n\n"
            "IMPORTANTE: NÃO utilize asteriscos em sua resposta."
            "\n"
            "Nota: não é necessário citar diretamente o nome do usuário."
            "\n"
            "IMPORTANTE: Retorne APENAS o JSON puro, sem usar marcadores de código como ```json ou ```."
            "\n"
            "Use APENAS aspas duplas (\") para strings no JSON, nunca aspas simples (')."
            "\n\n"
            "FORNEÇA AS STRINGS DO JSON ESCAPANDO TODAS AS ASPAS INTERNAS COM \\\"."
            "\n\n"
            "A resposta deve seguir exatamente o seguinte formato JSON:"
            "\n"
            "{"
            "\n  \"valor_curriculo\": <número>,"
            "\n  \"feedback_geral\": \"<Análise geral do currículo com: Avaliação geral e principais áreas para foco. Use emojis adequados 📚✨>\","
            "\n  \"componentes\": ["
            "\n    {"
            "\n      \"nome\": \"<nome>\","
            "\n      \"pontuacao_obtida\": <número>,"
            "\n      \"pontuacao_maxima\": <número>,"
            "\n      \"feedback\": \"<Análise detalhada individual do componente de acordo com a pontuação.>\""
            "\n    }"
            "\n  ]"
            "\n}"
            "\n\n"
            "Cada componente deve seguir as regras abaixo e não pode exceder a pontuação máxima definida."
            "\n\n"
            "Componentes e Regras de Pontuação:"
        )

        # Adicionar cada componente com suas regras
        componentes = [
            {
                "nome": "HISTÓRICO ESCOLAR",
                "valor": f"{metrica}, {info_aluno}",
                "pontuacao_maxima": 50,
                "regra": (
                    "50 pontos: 50% ou mais de menções A/SS ou notas 9-10;"
                    "40 pontos: 50% ou mais de menções A-B/SS-MS ou notas 7-10;"
                    "30 pontos: 50% ou mais de menções A,B,C/SS,MS,MM ou notas 5-10."
                    "Na análise individual deste componente, cite a frequência de notas do candidato."
                )
            },
            {
                "nome": "PROGRAMA DE EXTENSÃO",
                "valor": extensao,
                "pontuacao_maxima": 8,
                "regra": "4 pontos por programa/projeto (mínimo 30h cada). Exceto ligas acadêmicas e cursos de extensão."
            },
            {
                "nome": "EVENTOS SUS",
                "valor": eventos_sus,
                "pontuacao_maxima": 1,
                "regra": "0,25 pontos por evento (mínimo 20h)."
            },
            {
                "nome": "CURSOS DE APERFEIÇOAMENTO",
                "valor": cursos_aperfeicoamento,
                "pontuacao_maxima": 2,
                "regra": "0,5 pontos por curso (mínimo 180h)."
            },
            {
                "nome": "MONITORIA",
                "valor": str(monitoria) + " semestres",
                "pontuacao_maxima": 9,
                "regra": "3 pontos por semestre."
            },
            {
                "nome": "PESQUISA/INICIAÇÃO CIENTÍFICA",
                "valor": pesquisa_ic,
                "pontuacao_maxima": 12,
                "regra": "6 pontos por atividade."
            },
            {
                "nome": "APRESENTAÇÃO EM EVENTOS CIENTÍFICOS REGIONAIS",
                "valor": eventos_regionais,
                "pontuacao_maxima": 1.5,
                "regra": "0,3 pontos por trabalho."
            },
            {
                "nome": "APRESENTAÇÃO EM EVENTOS CIENTÍFICOS NACIONAIS",
                "valor": eventos_nacionais,
                "pontuacao_maxima": 1.5,
                "regra": "0,5 pontos por trabalho."
            },
            {
                "nome": "ARTIGOS EM PERIÓDICOS NÃO INDEXADOS",
                "valor": artigos_nao_indexados,
                "pontuacao_maxima": 3,
                "regra": "1 ponto por trabalho."
            },
            {
                "nome": "ARTIGOS COM DOI",
                "valor": artigos_doi,
                "pontuacao_maxima": 4.5,
                "regra": "1,5 pontos por trabalho."
            },
            {
                "nome": "PARTICIPAÇÃO EM CONGRESSOS",
                "valor": congressos,
                "pontuacao_maxima": 0.5,
                "regra": "0,1 ponto por evento."
            },
            {
                "nome": "REPRESENTAÇÃO ESTUDANTIL",
                "valor": representacao_estudantil,
                "pontuacao_maxima": 2,
                "regra": "1 ponto por atividade."
            },
            {
                "nome": "LIGAS ACADÊMICAS",
                "valor": ligas_academicas,
                "pontuacao_maxima": 1,
                "regra": "0,5 pontos por liga."
            },
            {
                "nome": "LÍNGUA ESTRANGEIRA",
                "valor": lingua_estrangeira,
                "pontuacao_maxima": 1,
                "regra": "1 ponto por língua."
            },
            {
                "nome": "PET SAÚDE/PET MEC",
                "valor": pet_saude,
                "pontuacao_maxima": 2,
                "regra": "1 ponto por ano."
            },
            {
                "nome": "ESTÁGIO NÃO OBRIGATÓRIO",
                "valor": str(estagio_nao_obrigatorio) + " horas",
                "pontuacao_maxima": 1,
                "regra": "1 ponto a cada 180 HORAS REALIZADAS. ATENÇÃO: se o usuário informar MENOS que 180 horas a pontuação é ZERO."
            }
        ]

        for componente in componentes:
            prompt_instructions += (
                f"\n- **{componente['nome']}** (máximo {componente['pontuacao_maxima']} pontos)"
                f"\n  Regras: {componente['regra']}"
                f"\n  Valor: {componente['valor']}"
            )

        prompt_instructions += (
            "\n\n**Regras Adicionais:**"
            "\n- A pontuação obtida para cada componente não pode exceder a pontuação máxima definida."
            "\n- A pontuação total do currículo não pode exceder 100 pontos."
            "\n\nForneça a resposta em formato JSON válido conforme especificado acima."
        )

        # Iniciar a sessão de chat
        chat_session = model.start_chat(history=[])

        # Enviar a mensagem para a IA
        response = chat_session.send_message(prompt_instructions)

        # Função para limpar a resposta JSON
        def clean_json_response(response_text):
            # Remover marcadores de código se presentes
            text = response_text.strip()
            if text.startswith('```'):
                # Remove qualquer variação de ``` no início (```json, ```JSON, etc)
                text = re.sub(r'^```(?:json)?\s*', '', text)
            if text.endswith('```'):
                text = re.sub(r'```$', '', text)
            
            # Substituir aspas simples por aspas duplas, mas apenas quando forem delimitadores de strings
            text = re.sub(r"(?<!\\)'([^']*(?:\\.[^']*)*)'", r'"\1"', text)
            
            return text

        # Limpar e processar a resposta
        cleaned_response = clean_json_response(response.text)
        
        try:
            resultado = json.loads(cleaned_response)
            # Validar se o JSON está no formato esperado
            required_keys = {'valor_curriculo', 'feedback_geral', 'componentes'}
            if not all(key in resultado for key in required_keys):
                raise ValueError("JSON não contém todas as chaves requeridas")
            
            # Validar e ajustar pontuações
            total_pontuacao = 0
            for componente in resultado['componentes']:
                if componente['pontuacao_obtida'] > componente['pontuacao_maxima']:
                    logging.warning(
                        f"Pontuação do componente {componente['nome']} excede o máximo. Ajustando de {componente['pontuacao_obtida']} para {componente['pontuacao_maxima']}."
                    )
                    componente['pontuacao_obtida'] = componente['pontuacao_maxima']
                total_pontuacao += componente['pontuacao_obtida']
            
            if total_pontuacao > 100:
                logging.warning(
                    f"Pontuação total excede 100. Ajustando de {total_pontuacao} para 100."
                )
                resultado['valor_curriculo'] = 100
            else:
                resultado['valor_curriculo'] = total_pontuacao
            
            return resultado
                
        except json.JSONDecodeError as e:
            logging.error(f"Erro ao decodificar JSON: {str(e)}\nResposta recebida: {cleaned_response}")
            raise ValueError(f"A resposta da IA não está no formato JSON esperado: {str(e)}")
    
    except Exception as e:
        logging.error(f"Erro na análise do currículo: {str(e)}")
        return {
            "error": True,
            "message": f"Ocorreu um erro ao analisar o currículo: {str(e)}"
        }

def processar_analisar_curriculo_feluma(
    media_curricular,
    
    projeto_pesquisa,
    projeto_extensao,
    estagio_nao_obrigatorio,
    monitoria_pid,
    diretoria_liga,
    membro_liga,
    projeto_comunidade,
    
    doutorado_mestrado,
    residencia_pos_hospitalar,
    primeira_especializacao,
    segunda_especializacao,
    
    curso_acls,
    curso_pals,
    curso_atls,
    curso_also,
    curso_phtls,
    curso_bls,
    
    primeira_publicacao_artigo,
    segunda_publicacao_artigo,
    primeiro_capitulo_livro,
    segundo_capitulo_livro,
    primeira_organizacao_livro,
    segunda_organizacao_livro,
    
    primeira_comissao_organizadora,
    segunda_comissao_organizadora,
    primeira_premiacao,
    segunda_premiacao,
    primeira_palestra,
    segunda_palestra,
    apresentacao_trabalho,
    
    proficiencia_ingles,
    proficiencia_outra_lingua,
    proficiencia_portugues
):
    try:
        resultado = {
            "valor_curriculo": 0,
            "feedback_geral": "",
            "grupos": []
        }
        
        total_pontuacao = 0
        
        # Grupo 1 - Aproveitamento Curricular
        grupo1_max = 2.0
        if media_curricular >= 90.00:
            pontuacao_grupo1 = 2.0
        elif media_curricular >= 80.00:
            pontuacao_grupo1 = 1.0
        else:
            pontuacao_grupo1 = 0.0
        
        componentes_grupo1 = [
            {
                "nome": "Média Curricular",
                "valor": media_curricular,
                "pontuacao": pontuacao_grupo1
            }
        ]
        
        resultado['grupos'].append({
            "nome": "APROVEITAMENTO CURRICULAR NO CURSO DE GRADUAÇÃO EM MEDICINA",
            "pontuacao_obtida": pontuacao_grupo1,
            "pontuacao_maxima": grupo1_max,
            "componentes": componentes_grupo1,
            "feedback": ""  # Será preenchido pela IA
        })
        total_pontuacao += pontuacao_grupo1
        
        # Grupo 2 - Aproveitamento Extracurricular
        grupo2_max = 2.0
        pontuacao_grupo2 = 0.0
        componentes_grupo2 = [
            {
                "nome": "Participação em projeto de pesquisa com duração mínima de 06 meses",
                "valor": projeto_pesquisa,
                "pontuacao": 1.0 if projeto_pesquisa else 0.0
            },
            {
                "nome": "Participação em projeto de extensão com carga horária mínima de 80 horas",
                "valor": projeto_extensao,
                "pontuacao": 1.0 if projeto_extensao else 0.0
            },
            {
                "nome": "Estágio não obrigatório com duração mínima de 04 meses",
                "valor": estagio_nao_obrigatorio,
                "pontuacao": 0.6 if estagio_nao_obrigatorio else 0.0
            },
            {
                "nome": "Monitoria ou PID com duração mínima de 03 meses",
                "valor": monitoria_pid,
                "pontuacao": 0.6 if monitoria_pid else 0.0
            },
            {
                "nome": "Participação em diretorias de ligas acadêmicas com duração mínima de 12 meses",
                "valor": diretoria_liga,
                "pontuacao": 0.3 if diretoria_liga else 0.0
            },
            {
                "nome": "Participação como membro/ligante em ligas acadêmicas com duração mínima de 12 meses",
                "valor": membro_liga,
                "pontuacao": 0.1 if membro_liga else 0.0
            },
            {
                "nome": "Participação voluntária em projeto junto à comunidade com duração mínima de 08 horas",
                "valor": projeto_comunidade,
                "pontuacao": 0.1 if projeto_comunidade else 0.0
            }
        ]
        
        # Calcular a pontuação do grupo 2
        for componente in componentes_grupo2:
            pontuacao_grupo2 += componente['pontuacao']
        
        pontuacao_grupo2 = min(pontuacao_grupo2, grupo2_max)
        
        # Atualizar os componentes para refletir a pontuação limitada
        if pontuacao_grupo2 < sum(c['pontuacao'] for c in componentes_grupo2):
            fator = pontuacao_grupo2 / sum(c['pontuacao'] for c in componentes_grupo2) if sum(c['pontuacao'] for c in componentes_grupo2) > 0 else 1
            for componente in componentes_grupo2:
                componente['pontuacao'] = round(componente['pontuacao'] * fator, 2)
        
        resultado['grupos'].append({
            "nome": "APROVEITAMENTO EXTRACURRICULAR NO CURSO DE GRADUAÇÃO EM MEDICINA",
            "pontuacao_obtida": pontuacao_grupo2,
            "pontuacao_maxima": grupo2_max,
            "componentes": componentes_grupo2,
            "feedback": ""  # Será preenchido pela IA
        })
        total_pontuacao += pontuacao_grupo2
        
        # Grupo 3 - Stricto Sensu, Residência, Pós-graduação
        grupo3_max = 1.0
        pontuacao_grupo3 = 0.0
        componentes_grupo3 = [
            {
                "nome": "Doutorado / Mestrado",
                "valor": doutorado_mestrado,
                "pontuacao": 1.0 if doutorado_mestrado else 0.0
            },
            {
                "nome": "Residência Médica ou Pós-Graduação Lato Sensu Hospitalar",
                "valor": residencia_pos_hospitalar,
                "pontuacao": 1.0 if residencia_pos_hospitalar else 0.0
            },
            {
                "nome": "Primeiro Curso de Especialização Lato Sensu na área da saúde",
                "valor": primeira_especializacao,
                "pontuacao": 0.5 if primeira_especializacao else 0.0
            },
            {
                "nome": "Segundo Curso de Especialização Lato Sensu na área da saúde",
                "valor": segunda_especializacao,
                "pontuacao": 0.5 if segunda_especializacao else 0.0
            }
        ]
        
        for componente in componentes_grupo3:
            pontuacao_grupo3 += componente['pontuacao']
        
        pontuacao_grupo3 = min(pontuacao_grupo3, grupo3_max)
        
        # Proporcionalmente reduzir as pontuações dos componentes se necessário
        if pontuacao_grupo3 < sum(c['pontuacao'] for c in componentes_grupo3):
            fator = pontuacao_grupo3 / sum(c['pontuacao'] for c in componentes_grupo3) if sum(c['pontuacao'] for c in componentes_grupo3) > 0 else 1
            for componente in componentes_grupo3:
                componente['pontuacao'] = round(componente['pontuacao'] * fator, 2)
        
        resultado['grupos'].append({
            "nome": "CURSOS DE STRICTO SENSU, RESIDÊNCIA MÉDICA E PÓS-GRADUAÇÃO LATO SENSU CONCLUÍDOS",
            "pontuacao_obtida": pontuacao_grupo3,
            "pontuacao_maxima": grupo3_max,
            "componentes": componentes_grupo3,
            "feedback": ""  # Será preenchido pela IA
        })
        total_pontuacao += pontuacao_grupo3
        
        # Grupo 4 - Cursos de Suporte à Vida
        grupo4_max = 1.0
        pontuacao_grupo4 = 0.0
        componentes_grupo4 = [
            {
                "nome": "Advanced Cardiac Life Support - ACLS",
                "valor": curso_acls,
                "pontuacao": 0.8 if curso_acls else 0.0
            },
            {
                "nome": "Pediatric Advanced Life Support - PALS",
                "valor": curso_pals,
                "pontuacao": 0.8 if curso_pals else 0.0
            },
            {
                "nome": "Advanced Trauma Life Support - ATLS",
                "valor": curso_atls,
                "pontuacao": 0.8 if curso_atls else 0.0
            },
            {
                "nome": "Advanced Life Support in Obstetrics - ALSO",
                "valor": curso_also,
                "pontuacao": 0.8 if curso_also else 0.0
            },
            {
                "nome": "Pre Hospital Trauma Life Support - PHTLS",
                "valor": curso_phtls,
                "pontuacao": 0.8 if curso_phtls else 0.0
            },
            {
                "nome": "Basic Life Support - BLS",
                "valor": curso_bls,
                "pontuacao": 0.5 if curso_bls else 0.0
            }
        ]
        
        for componente in componentes_grupo4:
            pontuacao_grupo4 += componente['pontuacao']
        
        pontuacao_grupo4 = min(pontuacao_grupo4, grupo4_max)
        
        # Proporcionalmente reduzir as pontuações dos componentes se necessário
        if pontuacao_grupo4 < sum(c['pontuacao'] for c in componentes_grupo4):
            fator = pontuacao_grupo4 / sum(c['pontuacao'] for c in componentes_grupo4) if sum(c['pontuacao'] for c in componentes_grupo4) > 0 else 1
            for componente in componentes_grupo4:
                componente['pontuacao'] = round(componente['pontuacao'] * fator, 2)
        
        resultado['grupos'].append({
            "nome": "CURSOS DE SUPORTE À VIDA",
            "pontuacao_obtida": pontuacao_grupo4,
            "pontuacao_maxima": grupo4_max,
            "componentes": componentes_grupo4,
            "feedback": ""  # Será preenchido pela IA
        })
        total_pontuacao += pontuacao_grupo4
        
        # Grupo 5 - Publicação Científica
        grupo5_max = 2.0
        pontuacao_grupo5 = 0.0
        componentes_grupo5 = [
            {
                "nome": "Primeira publicação como autor/coautor de artigos científicos em revistas indexadas",
                "valor": primeira_publicacao_artigo,
                "pontuacao": 1.0 if primeira_publicacao_artigo else 0.0
            },
            {
                "nome": "Segunda publicação como autor/coautor de artigos científicos em revistas indexadas",
                "valor": segunda_publicacao_artigo,
                "pontuacao": 1.0 if segunda_publicacao_artigo else 0.0
            },
            {
                "nome": "Primeira publicação como autor/coautor de capítulos de livros",
                "valor": primeiro_capitulo_livro,
                "pontuacao": 1.0 if primeiro_capitulo_livro else 0.0
            },
            {
                "nome": "Segunda publicação como autor/coautor de capítulos de livros",
                "valor": segundo_capitulo_livro,
                "pontuacao": 1.0 if segundo_capitulo_livro else 0.0
            },
            {
                "nome": "Primeira Organização de livros",
                "valor": primeira_organizacao_livro,
                "pontuacao": 1.0 if primeira_organizacao_livro else 0.0
            },
            {
                "nome": "Segunda Organização de livros",
                "valor": segunda_organizacao_livro,
                "pontuacao": 1.0 if segunda_organizacao_livro else 0.0
            }
        ]
        
        for componente in componentes_grupo5:
            pontuacao_grupo5 += componente['pontuacao']
        
        pontuacao_grupo5 = min(pontuacao_grupo5, grupo5_max)
        
        # Proporcionalmente reduzir as pontuações dos componentes se necessário
        if pontuacao_grupo5 < sum(c['pontuacao'] for c in componentes_grupo5):
            fator = pontuacao_grupo5 / sum(c['pontuacao'] for c in componentes_grupo5) if sum(c['pontuacao'] for c in componentes_grupo5) > 0 else 1
            for componente in componentes_grupo5:
                componente['pontuacao'] = round(componente['pontuacao'] * fator, 2)
        
        resultado['grupos'].append({
            "nome": "PUBLICAÇÃO DE TRABALHOS CIENTÍFICOS",
            "pontuacao_obtida": pontuacao_grupo5,
            "pontuacao_maxima": grupo5_max,
            "componentes": componentes_grupo5,
            "feedback": ""  # Será preenchido pela IA
        })
        total_pontuacao += pontuacao_grupo5
        
        # Grupo 6 - Eventos e Premiações
        grupo6_max = 1.0
        pontuacao_grupo6 = 0.0
        componentes_grupo6 = [
            {
                "nome": "Primeira Participação em evento científico na Comissão Organizadora",
                "valor": primeira_comissao_organizadora,
                "pontuacao": 0.7 if primeira_comissao_organizadora else 0.0
            },
            {
                "nome": "Segunda Participação em evento científico na Comissão Organizadora",
                "valor": segunda_comissao_organizadora,
                "pontuacao": 0.7 if segunda_comissao_organizadora else 0.0
            },
            {
                "nome": "Primeira Premiação de trabalhos, TCC, dissertação ou tese",
                "valor": primeira_premiacao,
                "pontuacao": 0.7 if primeira_premiacao else 0.0
            },
            {
                "nome": "Segunda Premiação de trabalhos, TCC, dissertação ou tese",
                "valor": segunda_premiacao,
                "pontuacao": 0.7 if segunda_premiacao else 0.0
            },
            {
                "nome": "Primeira Participação em evento científico como palestrante",
                "valor": primeira_palestra,
                "pontuacao": 0.5 if primeira_palestra else 0.0
            },
            {
                "nome": "Segunda Participação em evento científico como palestrante",
                "valor": segunda_palestra,
                "pontuacao": 0.5 if segunda_palestra else 0.0
            },
            {
                "nome": "Apresentação de trabalho em evento científico",
                "valor": apresentacao_trabalho,
                "pontuacao": 0.5 if apresentacao_trabalho else 0.0
            }
        ]
        
        for componente in componentes_grupo6:
            pontuacao_grupo6 += componente['pontuacao']
        
        pontuacao_grupo6 = min(pontuacao_grupo6, grupo6_max)
        
        # Proporcionalmente reduzir as pontuações dos componentes se necessário
        if pontuacao_grupo6 < sum(c['pontuacao'] for c in componentes_grupo6):
            fator = pontuacao_grupo6 / sum(c['pontuacao'] for c in componentes_grupo6) if sum(c['pontuacao'] for c in componentes_grupo6) > 0 else 1
            for componente in componentes_grupo6:
                componente['pontuacao'] = round(componente['pontuacao'] * fator, 2)
        
        resultado['grupos'].append({
            "nome": "EVENTOS CIENTÍFICOS E PREMIAÇÕES",
            "pontuacao_obtida": pontuacao_grupo6,
            "pontuacao_maxima": grupo6_max,
            "componentes": componentes_grupo6,
            "feedback": ""  # Será preenchido pela IA
        })
        total_pontuacao += pontuacao_grupo6
        
        # Grupo 7 - Proficiência em Línguas
        grupo7_max = 1.0
        pontuacao_grupo7 = 0.0
        componentes_grupo7 = [
            {
                "nome": "Proficiência em língua inglesa",
                "valor": proficiencia_ingles,
                "pontuacao": 1.0 if proficiencia_ingles else 0.0
            },
            {
                "nome": "Proficiência em outra língua estrangeira",
                "valor": proficiencia_outra_lingua,
                "pontuacao": 1.0 if proficiencia_outra_lingua else 0.0
            },
            {
                "nome": "Proficiência em língua portuguesa",
                "valor": proficiencia_portugues,
                "pontuacao": 1.0 if proficiencia_portugues else 0.0
            }
        ]
        
        for componente in componentes_grupo7:
            pontuacao_grupo7 += componente['pontuacao']
        
        pontuacao_grupo7 = min(pontuacao_grupo7, grupo7_max)
        
        # Proporcionalmente reduzir as pontuações dos componentes se necessário
        if pontuacao_grupo7 < sum(c['pontuacao'] for c in componentes_grupo7):
            fator = pontuacao_grupo7 / sum(c['pontuacao'] for c in componentes_grupo7) if sum(c['pontuacao'] for c in componentes_grupo7) > 0 else 1
            for componente in componentes_grupo7:
                componente['pontuacao'] = round(componente['pontuacao'] * fator, 2)
        
        resultado['grupos'].append({
            "nome": "PROFICIÊNCIA EM LÍNGUA ESTRANGEIRA",
            "pontuacao_obtida": pontuacao_grupo7,
            "pontuacao_maxima": grupo7_max,
            "componentes": componentes_grupo7,
            "feedback": ""  # Será preenchido pela IA
        })
        total_pontuacao += pontuacao_grupo7
        
        # Limitar a pontuação total a 10
        pontuacao_total_final = min(total_pontuacao, 10.0)
        resultado['valor_curriculo'] = pontuacao_total_final
        
        return resultado
    
    except Exception as e:
        logging.error(f"Erro na análise do currículo: {str(e)}")
        return {
            "error": True,
            "message": f"Ocorreu um erro ao analisar o currículo: {str(e)}"
        }
    
def gerar_feedback(resultado_calculado):
    try:
        # Construir o prompt base com formato JSON explícito
        prompt_instrucoes = (
            "Analise os dados de pontuação abaixo e gere um feedback detalhado para cada grupo e um feedback geral sobre o currículo do usuário. Utilize emojis apropriados e mantenha o formato JSON conforme especificado.\n\n"
            "### Dados de Pontuação:\n"
            f"{json.dumps(resultado_calculado, ensure_ascii=False, indent=2)}\n\n"
            "### Instruções:"
            "\n- Preencha os campos 'feedback' de cada grupo com uma análise detalhada da pontuação obtida, pesquisando na internet opções para o candidato otimizar o currículo de acordo com os componentes do grupo. Utilize emojis se necessário."
            "\n- Preencha o campo 'feedback_geral' com uma análise geral do currículo do usuário, destacando pontos fortes e áreas para melhoria. Utilize emojis se necessário."
            "\n- RETORNE APENAS o JSON completo, sem qualquer explicação adicional."
            "\n- Utilize apenas aspas duplas (\") no JSON."
        )
        
        # Iniciar a sessão de chat com o modelo IA existente
        chat_session = model.start_chat(history=[])
        
        # Enviar a mensagem para a IA
        response = chat_session.send_message(prompt_instrucoes)
        
        # Função para limpar a resposta JSON
        def limpar_json_response(response_text):
            # Remover marcadores de código se presentes
            texto = response_text.strip()
            if texto.startswith('```'):
                texto = re.sub(r'^```(?:json)?\s*', '', texto)
            if texto.endswith('```'):
                texto = re.sub(r'```$', '', texto)
            
            # Substituir aspas simples por aspas duplas apenas quando delimitadores de strings
            texto = re.sub(r"(?<!\\)'([^']*(?:\\.[^']*)*)'", r'"\1"', texto)
            
            return texto
        
        # Limpar e processar a resposta
        resposta_limpa = limpar_json_response(response.text)
        print(resposta_limpa)
        
        try:
            resultado_com_feedback = json.loads(resposta_limpa)
            
            # Validar se o JSON está no formato esperado
            chaves_requeridas = {'valor_curriculo', 'feedback_geral', 'grupos'}
            if not all(chave in resultado_com_feedback for chave in chaves_requeridas):
                raise ValueError("JSON não contém todas as chaves requeridas")
            
            # Garantir que a pontuação total não exceda 10
            resultado_com_feedback['valor_curriculo'] = min(resultado_com_feedback['valor_curriculo'], 10.0)
            
            return resultado_com_feedback
        
        except json.JSONDecodeError as e:
            logging.error(f"Erro ao decodificar JSON: {str(e)}\nResposta recebida: {resposta_limpa}")
            raise ValueError(f"A resposta da IA não está no formato JSON esperado: {str(e)}")
    
    except Exception as e:
        logging.error(f"Erro ao gerar feedback com a IA: {str(e)}")
        raise e