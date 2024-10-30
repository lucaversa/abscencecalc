# app.py

import datetime
import json
import logging
import math
import tempfile
import threading
import time
import uuid
from collections import Counter, defaultdict
from statistics import mode, multimode
from request_ia import analyze_curriculo, analyze_performance, gerar_feedback, processar_analisar_curriculo_feluma

from flask import (
    Flask, jsonify, redirect, render_template,
    request, session, flash, url_for
)
from flask_session import Session
from threading import Lock

from scraper import scrape_portal

# Inicialização de Locks
progress_lock = Lock()
results_lock = Lock()

# Dicionários globais
RESULTS = {}
PROGRESS = {}

# Fases do processamento
PHASE_SCRAPING = "SCRAPING"
PHASE_PROCESSING = "PROCESSING"

# Inicialização da aplicação Flask
app = Flask(__name__)

# Configurações de sessão
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = tempfile.gettempdir()
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SECRET_KEY'] = '1234567890'
app.config['JSON_AS_ASCII'] = False

Session(app)

# Configuração de logging
logging.basicConfig(level=logging.DEBUG)

# Função para mapear a porcentagem de faltas para uma cor
def get_color(porcentagem_faltas):
    try:
        porcentagem_faltas = float(porcentagem_faltas)
    except (ValueError, TypeError):
        porcentagem_faltas = 0.0

    if porcentagem_faltas >= 25:
        # Gradiente completo para vermelho
        gradient = 'linear-gradient(to right, rgb(220, 53, 0), rgb(255, 0, 0))'
    else:
        # Calcula a cor intermediária baseada na porcentagem
        ratio = porcentagem_faltas / 25.0
        r = int(32 + (255 - 32) * ratio)  # De 32 a 255 (mais vermelho)
        g = int(178 + (0 - 178) * ratio)  # De 178 a 0
        b = int(170 + (0 - 170) * ratio)  # De 170 a 0
        # Cria um gradiente que começa com azul-turquesa e vai até a cor calculada
        gradient = f'linear-gradient(to right, rgb(32, 178, 170), rgb({r}, {g}, {b}))'
    return gradient

# Registrar a função como um filtro Jinja
app.jinja_env.filters['get_color'] = get_color

# Função para mapear o desempenho para uma cor (usado no controle_notas.html)
def get_color_from_performance(performance):
    """
    Retorna uma cor baseada no desempenho (0 a 100).
    Cores variam de vermelho (baixo desempenho) a verde (alto desempenho).
    """
    if performance >= 85:
        return '#20B2AA'  # Turquesa (bom desempenho)
    elif performance >= 70:
        return '#66CDAA'  # Aquamarine
    elif performance >= 60:
        return '#F4A460'  # Sanja
    elif performance >= 40:
        return '#FFD700'  # Dourado
    elif performance >= 20:
        return '#FF8C00'  # Laranja escuro
    else:
        return '#FF0000'  # Vermelho (baixo desempenho)

# Registrar a função como um filtro Jinja
app.jinja_env.filters['get_color_from_performance'] = get_color_from_performance

# Função para atribuir um ID de sessão único
def assign_session_id():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())

# Registrar funções antes de cada requisição
@app.before_request
def before_request():
    log_request_info()
    assign_session_id()

def log_request_info():
    logging.debug(f"Nova requisição: {request.path}, Método: {request.method}, Session ID: {session.get('session_id')}")

# Rota de login
@app.route('/')
def login():
    return render_template('login.html')

# Funções auxiliares

def filtrar_disciplinas(faltas_ch_data):
    """
    Filtra as disciplinas que estão aprovadas, não possuem IMG igual a 'equivalente.gif',
    e que possuem 'NOTA' diferente de 0.
    
    :param faltas_ch_data: Lista de dicionários contendo os dados de APRESENTACAOHISTORICO.
    :return: Lista filtrada de disciplinas.
    """
    disciplinas_filtradas = []
    for entry in faltas_ch_data:
        status = entry.get("STATUS", "").strip().upper()
        img = entry.get("IMG", "").strip().lower()
        periodo = entry.get("CODPERIODO", 0)
        nota = entry.get("NOTA", 0)  # Obtém a nota, default para 0 se não existir
        
        # Tenta converter o período para inteiro, se possível
        try:
            periodo = int(periodo)
        except (ValueError, TypeError):
            # Se não for possível converter, assume que o período é inválido e desconsidera a entrada
            continue
        
        # Tenta converter a nota para float, se possível
        try:
            nota_float = float(str(nota).replace(',', '.'))
        except (ValueError, TypeError):
            # Se não for possível converter, assume que a nota é inválida e desconsidera a entrada
            continue
        
        # Aplica as condições de filtro:
        # 1. Status deve ser "APROVADO"
        # 2. IMG não deve ser "equivalente.gif"
        # 3. NOTA deve ser diferente de 0
        if status == "APROVADO" and img != "equivalente.gif" and nota_float != 0:
            disciplinas_filtradas.append(entry)
    
    return disciplinas_filtradas

def extrair_informacoes_aluno(shabilitacao_aluno):
    """
    Extrai o nome do aluno, RA e nome do curso a partir de SHabilitacaoAluno.

    :param shabilitacao_aluno: Lista de dicionários contendo os dados de SHabilitacaoAluno.
    :return: Dicionário com 'nome_aluno', 'ra' e 'nome_curso'.
    """
    if not shabilitacao_aluno:
        return {
            'nome_aluno': 'N/A',
            'ra': 'N/A',
            'nome_curso': 'N/A'
        }

    # Considerando que há pelo menos uma entrada
    aluno_info = shabilitacao_aluno[0]  # Pega a primeira entrada
    nome_aluno = aluno_info.get('NOMEALUNO', 'N/A')
    ra = aluno_info.get('RA', 'N/A')
    nome_curso = aluno_info.get('NOMECURSO', 'N/A')

    return {
        'nome_aluno': nome_aluno,
        'ra': ra,
        'nome_curso': nome_curso
    }

def ordenar_disciplinas_por_periodo_e_nota(disciplinas):
    """
    Ordena as disciplinas por período (ascendente) e por nota (descendente),
    retornando apenas período, nome da matéria e nota.

    :param disciplinas: Lista de disciplinas filtradas.
    :return: Lista de disciplinas ordenadas com apenas os campos desejados.
    """
    def sort_key(disciplina):
        # Obtém o período, padrão 0 se ausente ou inválido
        try:
            periodo = int(disciplina.get('CODPERIODO', 0))
        except ValueError:
            periodo = 0

        # Obtém a nota, padrão 0.0 se ausente ou inválida
        nota_str = disciplina.get('NOTA', '0').replace(',', '.')
        try:
            nota = float(nota_str)
        except ValueError:
            nota = 0.0
        return (periodo, -nota)  # Ordena por período ascendente e nota descendente

    # Ordena as disciplinas
    disciplinas_ordenadas = sorted(disciplinas, key=sort_key)

    # Extrai apenas os campos desejados
    disciplinas_simplificadas = []
    for disciplina in disciplinas_ordenadas:
        try:
            periodo = int(disciplina.get('CODPERIODO', 0))
        except ValueError:
            periodo = 0
        nome_materia = disciplina.get('DISCIPLINA', 'N/A')
        nota_str = disciplina.get('NOTA', '0').replace(',', '.')
        try:
            nota = float(nota_str)
        except ValueError:
            nota = 0.0
        disciplinas_simplificadas.append({
            'período': periodo,
            'nome_da_materia': nome_materia,
            'nota': nota
        })

    return disciplinas_simplificadas

def calcular_media_global(disciplinas):
    """
    Calcula a média das notas de todas as disciplinas aprovadas.

    :param disciplinas: Lista de disciplinas filtradas.
    :return: Média global das notas.
    """
    notas = []
    for disciplina in disciplinas:
        nota = disciplina.get('NOTA')
        if nota is not None and nota != '':
            try:
                nota_float = float(nota.replace(',', '.'))
                notas.append(nota_float)
            except ValueError:
                continue  # Ignora notas inválidas
    if not notas:
        return 0.0
    media = sum(notas) / len(notas)
    return round(media, 2)

def calcular_melhor_pior_periodo(disciplinas):
    """
    Calcula o melhor e o pior período com base nas médias das notas,
    considerando apenas disciplinas com CODPERIODO <= 12 e NOTA != 0.

    :param disciplinas: Lista de disciplinas filtradas.
    :return: Tupla contendo o melhor período e o pior período.
    """
    periodo_notas = defaultdict(list)
    
    for disciplina in disciplinas:
        periodo = disciplina.get('CODPERIODO')
        nota = disciplina.get('NOTA')
        
        # Verificar se CODPERIODO e NOTA são válidos
        if periodo is None or nota in [None, '']:
            continue  # Ignorar entradas inválidas
        
        try:
            periodo_int = int(periodo)
        except ValueError:
            continue  # Ignorar CODPERIODO inválidos
        
        if periodo_int > 12:
            continue  # Ignorar disciplinas com CODPERIODO > 12
        
        try:
            nota_float = float(str(nota).replace(',', '.'))
        except ValueError:
            continue  # Ignorar NOTA inválidas
        
        if nota_float == 0:
            continue  # Ignorar NOTA igual a 0
        
        periodo_notas[periodo_int].append(nota_float)
    
    medias_periodo = {}
    for periodo, notas in periodo_notas.items():
        if notas:
            medias_periodo[periodo] = round(sum(notas) / len(notas), 2)
    
    if not medias_periodo:
        return None, None
    
    melhor_periodo = max(medias_periodo, key=medias_periodo.get)
    pior_periodo = min(medias_periodo, key=medias_periodo.get)
    
    return melhor_periodo, pior_periodo

def calcular_melhores_areas(disciplinas, top_n=5):
    """
    Calcula as disciplinas com as melhores médias de notas,
    considerando apenas disciplinas com CODPERIODO <= 12 e NOTA != 0.

    :param disciplinas: Lista de disciplinas filtradas.
    :param top_n: Número máximo de disciplinas a retornar.
    :return: Lista de tuplas (disciplina, média).
    """
    disciplina_notas = defaultdict(list)
    
    for disciplina in disciplinas:
        nome = disciplina.get('DISCIPLINA')
        nota = disciplina.get('NOTA')
        periodo = disciplina.get('CODPERIODO')
        
        # Verificar se DISCIPLINA, CODPERIODO e NOTA são válidos
        if not nome or nota in [None, ''] or periodo is None:
            continue  # Ignorar entradas inválidas
        
        try:
            periodo_int = int(periodo)
        except ValueError:
            continue  # Ignorar CODPERIODO inválidos
        
        if periodo_int > 12:
            continue  # Ignorar disciplinas com CODPERIODO > 12
        
        try:
            nota_float = float(str(nota).replace(',', '.'))
        except ValueError:
            continue  # Ignorar NOTA inválidas
        
        if nota_float == 0:
            continue  # Ignorar NOTA igual a 0
        
        disciplina_notas[nome].append(nota_float)
    
    medias_disciplina = {}
    for disciplina, notas in disciplina_notas.items():
        if notas:
            medias_disciplina[disciplina] = round(sum(notas) / len(notas), 2)
    
    # Ordena as disciplinas pela média descendente
    melhores_areas = sorted(medias_disciplina.items(), key=lambda x: x[1], reverse=True)[:top_n]
    
    return melhores_areas

def calcular_piores_areas(disciplinas, top_n=5):
    """
    Calcula as disciplinas com as piores médias de notas,
    considerando apenas disciplinas com CODPERIODO <= 12 e NOTA != 0.

    :param disciplinas: Lista de disciplinas filtradas.
    :param top_n: Número máximo de disciplinas a retornar.
    :return: Lista de tuplas (disciplina, média).
    """
    disciplina_notas = defaultdict(list)
    
    for disciplina in disciplinas:
        nome = disciplina.get('DISCIPLINA')
        nota = disciplina.get('NOTA')
        periodo = disciplina.get('CODPERIODO')
        
        # Verificar se DISCIPLINA, CODPERIODO e NOTA são válidos
        if not nome or nota in [None, ''] or periodo is None:
            continue  # Ignorar entradas inválidas
        
        try:
            periodo_int = int(periodo)
        except ValueError:
            continue  # Ignorar CODPERIODO inválidos
        
        if periodo_int > 12:
            continue  # Ignorar disciplinas com CODPERIODO > 12
        
        try:
            nota_float = float(str(nota).replace(',', '.'))
        except ValueError:
            continue  # Ignorar NOTA inválidas
        
        if nota_float == 0:
            continue  # Ignorar NOTA igual a 0
        
        disciplina_notas[nome].append(nota_float)
    
    medias_disciplina = {}
    for disciplina, notas in disciplina_notas.items():
        if notas:
            medias_disciplina[disciplina] = round(sum(notas) / len(notas), 2)
    
    # Ordena as disciplinas pela média ascendente (piores notas primeiro)
    piores_areas = sorted(medias_disciplina.items(), key=lambda x: x[1])[:top_n]
    
    return piores_areas

def calcular_metricas_por_periodo(disciplinas):
    """
    Calcula, para cada período (CODPERIODO <= 12), a média das notas, a melhor e a pior nota,
    além das top 10 melhores e top 3 piores disciplinas com suas respectivas notas.

    :param disciplinas: Lista de disciplinas filtradas.
    :return: Dicionário com as métricas por período.
    """
    periodo_notas = defaultdict(list)
    disciplina_por_periodo = defaultdict(list)

    # Agrupar notas por período e armazenar disciplinas por período
    for disciplina in disciplinas:
        periodo = disciplina.get('CODPERIODO')
        nota = disciplina.get('NOTA')
        nome_disciplina = disciplina.get('DISCIPLINA')

        # Filtrar disciplinas com CODPERIODO <= 12
        if periodo is None or nota in [None, '']:
            continue  # Ignorar disciplinas sem período ou sem nota

        try:
            periodo_int = int(periodo)
        except ValueError:
            continue  # Ignorar CODPERIODO inválidos

        if periodo_int > 12:
            continue  # Ignorar disciplinas com CODPERIODO > 12

        try:
            nota_float = float(str(nota).replace(',', '.'))
        except ValueError:
            continue  # Ignora notas inválidas

        periodo_notas[periodo_int].append(nota_float)
        disciplina_por_periodo[periodo_int].append({'DISCIPLINA': nome_disciplina, 'NOTA': nota_float})

    metricas_por_periodo = {}
    for periodo, notas in periodo_notas.items():
        if notas:
            media = round(sum(notas) / len(notas), 2)
            melhor_nota = max(notas)
            pior_nota = min(notas)

            # Obter as top 10 melhores disciplinas
            disciplinas_periodo = disciplina_por_periodo[periodo]
            top_melhores = sorted(disciplinas_periodo, key=lambda x: x['NOTA'], reverse=True)[:10]
            top_piores = sorted(disciplinas_periodo, key=lambda x: x['NOTA'])[:3]

            # Formatar as disciplinas para exibição
            top_melhores_formatado = [
                {'DISCIPLINA': d['DISCIPLINA'], 'NOTA': d['NOTA']} for d in top_melhores
            ]
            top_piores_formatado = [
                {'DISCIPLINA': d['DISCIPLINA'], 'NOTA': d['NOTA']} for d in top_piores
            ]

            metricas_por_periodo[periodo] = {
                'media': media,
                'melhor_nota': melhor_nota,
                'pior_nota': pior_nota,
                'top_melhores_disciplinas': top_melhores_formatado,
                'top_piores_disciplinas': top_piores_formatado
            }
    return metricas_por_periodo

def calcular_data_pode_faltar(aulas_restantes, faltas_permitidas, schedule_data, cod_disc, dias_info):
    hoje = datetime.date.today()
    
    logging.debug(f"\n=== INÍCIO DEBUG DATA PODE FALTAR ===")
    logging.debug(f"Aulas restantes: {aulas_restantes}")
    logging.debug(f"Faltas permitidas: {faltas_permitidas}")
    logging.debug(f"Código disciplina: {cod_disc}")
    logging.debug(f"Dias info: {dias_info}")
    
    # Filtra e ordena as aulas válidas futuras
    aulas_validas = [
        aula for aula in schedule_data 
        if aula.get('CODDISC') == cod_disc and aula.get('DATAINICIAL')
    ]
    
    logging.debug(f"Total de aulas válidas encontradas: {len(aulas_validas)}")
    
    aulas_futuras = [
        aula for aula in aulas_validas
        if datetime.datetime.strptime(aula['DATAINICIAL'].split('T')[0], "%Y-%m-%d").date() >= hoje
    ]
    
    logging.debug(f"Total de aulas futuras: {len(aulas_futuras)}")
    
    aulas_ordenadas = sorted(aulas_futuras, key=lambda x: x['DATAINICIAL'])
    
    for aula in aulas_ordenadas[:5]:  # Mostra as primeiras 5 aulas para debug
        logging.debug(f"Aula futura: {aula['DATAINICIAL']}")
    
    logging.debug("=== FIM DEBUG DATA PODE FALTAR ===\n")
    
    if not aulas_ordenadas:
        return "Não há aulas futuras programadas"
    
    # Verifica se todas as porcentagens são iguais
    porcentagens = [dia['porcentagem_perda'] for dia in dias_info]
    todas_iguais = len(set(porcentagens)) == 1
    
    aulas_obrigatorias = aulas_restantes - faltas_permitidas
    if aulas_obrigatorias <= 0:
        return "Você pode faltar o restante das aulas"
    
    if todas_iguais:
        # Caso 1: Todas as porcentagens são iguais
        if len(aulas_ordenadas) <= aulas_obrigatorias:
            return "Você não pode faltar mais nenhuma aula"
        
        data_corte = datetime.datetime.strptime(aulas_ordenadas[aulas_obrigatorias - 1]['DATAINICIAL'].split('T')[0], "%Y-%m-%d").date()
    else:
        # Caso 2: Porcentagens diferentes por dia da semana
        aulas_contadas = 0
        for aula in aulas_ordenadas:
            data_aula = datetime.datetime.strptime(aula['DATAINICIAL'].split('T')[0], "%Y-%m-%d").date()
            dia_semana = data_aula.weekday()
            dia_info = next((d for d in dias_info if d['dia'] == ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo'][dia_semana]), None)
            
            if dia_info:
                aulas_contadas += 1
                if aulas_contadas == aulas_obrigatorias:
                    data_corte = data_aula
                    break
        else:
            return "Você não pode faltar mais nenhuma aula"
    
    data_pode_faltar = data_corte + datetime.timedelta(days=1)
    return f"Você pode faltar o restante das aulas a partir de {data_pode_faltar.strftime('%d/%m/%Y')}"

def calcular_porcentagem_faltas(faltas, ch):
    if ch == 0:
        return 0.0
    return (faltas / ch) * 100

def calcular_perda_por_dia(aulas_no_dia, ch):
    if ch == 0:
        return 0.0
    return (aulas_no_dia / ch) * 100

def calcular_faltas_permitidas(faltas, ch, aulas_no_dia):
    porcentagem_atual_faltas = calcular_porcentagem_faltas(faltas, ch)
    porcentagem_permitida = 25.0
    if porcentagem_atual_faltas >= porcentagem_permitida:
        return 0
    porcentagem_restante = porcentagem_permitida - porcentagem_atual_faltas
    porcentagem_por_dia = calcular_perda_por_dia(aulas_no_dia, ch)
    if porcentagem_por_dia == 0:
        return 0
    faltas_permitidas_dia = math.floor(porcentagem_restante / porcentagem_por_dia)
    faltas_permitidas_dia = max(faltas_permitidas_dia, 0)
    return faltas_permitidas_dia

def calcular_aulas_restantes(schedule_data, cod_disc):
    hoje = datetime.date.today()
    total_restante = 0
    for aula in schedule_data:
        if aula.get('CODDISC') == cod_disc:
            aula_data = aula.get('DATAINICIAL', '')
            if aula_data:
                try:
                    data_aula = datetime.datetime.strptime(aula_data.split('T')[0], "%Y-%m-%d").date()
                    if data_aula >= hoje:
                        total_restante += 1
                except ValueError:
                    continue  # Ignora datas inválidas
    return total_restante

# Função para atualizar o progresso
def update_progress(session_id, phase, description, percentage):
    with progress_lock:
        logging.debug(f"Atualizando progresso para session_id {session_id}: Fase {phase} - {percentage}% - {description}")
        PROGRESS[session_id] = {
            'phase': phase,
            'description': description,
            'percentage': percentage
        }

# Função para limpar o progresso (mantém o último estado como COMPLETED)
def clear_progress(session_id):
    with progress_lock:
        if session_id in PROGRESS:
            PROGRESS[session_id] = {'phase': 'COMPLETED', 'description': 'Processamento concluído', 'percentage': 100}

# Função principal de processamento em thread
def process_login_thread(username, password, session_id):
    logging.debug(f"Iniciando process_login_thread com session_id: {session_id}")
    try:
        update_progress(session_id, PHASE_SCRAPING, "Iniciando o processo de login", 0)

        # Passo 1: Acessar o portal e fazer login
        try:
            data1, data2, data_avaliacao = scrape_portal(username, password, session_id, update_progress)
            logging.debug("Scraping concluído com sucesso")
        except Exception as e:
            logging.error(f"Erro durante o scraping: {e}", exc_info=True)
            update_progress(session_id, PHASE_SCRAPING, f"Erro: {e}", 100)
            return

        if data1 is None or data2 is None:
            logging.error("Dados não obtidos corretamente do portal")
            update_progress(session_id, PHASE_SCRAPING, "Falha ao obter os dados do portal. Verifique suas credenciais.", 100)
            return

        logging.debug("Iniciando fase de processamento")
        update_progress(session_id, PHASE_PROCESSING, "Iniciando processamento dos dados", 0)

        # Processar os dados para obter 'resultados'
        try:
            logging.debug("Processando dados obtidos")
            faltas_ch_data = data1
            informacoes_aluno = data1
            horario_data = data2
            
            # Verifique se 'horario_data' é um dicionário
            if not isinstance(horario_data, dict):
                logging.error("horario_data não é um dicionário.")
                update_progress(session_id, PHASE_PROCESSING, "Erro: Dados de horário inválidos.", 100)
                return

            # Dados de horário
            try:
                schedule_data = horario_data["data"]["SHorarioAluno"]
                logging.debug("schedule_data extraído com sucesso.")
                update_progress(session_id, PHASE_PROCESSING, "Extraindo dados de horário", 20)
            except KeyError as e:
                logging.error(f"Chave ausente em horario_data: {e}")
                update_progress(session_id, PHASE_PROCESSING, f"Erro: Chave ausente no JSON de horário: {e}", 100)
                return

            try:
                faltas_ch_data = faltas_ch_data["data"]["APRESENTACAOHISTORICO"]
                logging.debug("faltas_ch_data extraído com sucesso.")
                update_progress(session_id, PHASE_PROCESSING, "Extraindo dados de faltas", 40)
            except KeyError as e:
                logging.error(f"Chave ausente em faltas_ch_data: {e}")
                update_progress(session_id, PHASE_PROCESSING, f"Erro: Chave ausente no JSON de faltas: {e}", 100)
                return
            
            try:
                informacoes_aluno = informacoes_aluno["data"]["SHabilitacaoAluno"]
                logging.debug("informacoes_aluno extraído com sucesso.")
                update_progress(session_id, PHASE_PROCESSING, "Extraindo dados do aluno", 40)
            except KeyError as e:
                logging.error(f"Chave ausente em informacoes_aluno: {e}")
                update_progress(session_id, PHASE_PROCESSING, f"Erro: Chave ausente no JSON de alunos: {e}", 100)
                return

            # Dicionário para mapear CODDISC para informações de faltas e CH (apenas CURSANDO)
            faltas_ch_info = {}
            for entry in faltas_ch_data:
                status = entry.get("STATUS", "").strip().upper()
                if status != "CURSANDO":
                    continue  # Considera apenas disciplinas com STATUS "CURSANDO"

                cod_disc = entry.get("CODDISC")
                nome_materia = entry.get("DISCIPLINA")
                faltas_str = entry.get("FALTAS", "0")
                ch_str = entry.get("CH", "0")

                # Converte faltas e CH para números
                try:
                    faltas = int(faltas_str) if faltas_str else 0
                except ValueError:
                    faltas = 0
                try:
                    ch = float(ch_str.replace(",", ".")) if ch_str else 0.0
                except ValueError:
                    ch = 0.0

                if cod_disc and nome_materia:
                    faltas_ch_info[cod_disc] = {
                        "nome_materia": nome_materia,
                        "faltas": faltas,
                        "ch": ch
                    }

            update_progress(session_id, PHASE_PROCESSING, "Mapeando informações de faltas e créditos", 60)

            # Dicionário para armazenar a contagem de aulas por matéria, dia da semana e data
            subjects_days_dates = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

            for entry in schedule_data:
                dia_semana_str = entry.get("DIASEMANA")
                cod_disc = entry.get("CODDISC")
                data_inicial = entry.get("DATAINICIAL")

                # Considera apenas disciplinas que estão "CURSANDO"
                if cod_disc not in faltas_ch_info:
                    continue  # Ignora disciplinas que não estão "CURSANDO"

                # Verifica se DIASEMANA e DATAINICIAL estão presentes
                if dia_semana_str is None or data_inicial is None:
                    continue  # Ignora esta entrada se faltar informação

                try:
                    dia_semana = int(dia_semana_str)
                except ValueError:
                    continue  # Ignora se DIASEMANA não for um número válido

                # Permitir dias entre 1 e 7 (inclui Sábado)
                if dia_semana < 1 or dia_semana > 7:
                    continue  # Ignora dias inválidos

                # Extrai a data (parte antes do 'T')
                data = data_inicial.split("T")[0]

                # Incrementa a contagem para a matéria, dia da semana e data
                subjects_days_dates[cod_disc][dia_semana][data] += 1

            # Tratamento especial para Sábados
            # Apenas considera aulas de sábado para matérias que têm mais de 1 aula nesse dia
            for cod_disc in list(subjects_days_dates.keys()):
                if 7 in subjects_days_dates[cod_disc]:
                    # Iterar sobre cada data no sábado
                    for data in list(subjects_days_dates[cod_disc][7].keys()):
                        num_aulas = subjects_days_dates[cod_disc][7][data]
                        if num_aulas <= 1:
                            del subjects_days_dates[cod_disc][7][data]  # Remove a data se tiver 1 ou nenhuma aula
                    # Se, após a remoção, não houver mais datas no sábado para a disciplina, remove o dia 7
                    if not subjects_days_dates[cod_disc][7]:
                        del subjects_days_dates[cod_disc][7]

            update_progress(session_id, PHASE_PROCESSING, "Contando aulas por matéria e dia", 70)

            # Função para analisar o padrão de aulas
            def analyze_class_pattern(aulas_por_data):
                """
                Analisa o padrão de aulas para determinar quais são regulares e práticas.
                """
                contagens = list(aulas_por_data.values())
                if not contagens:
                    return {"regular": 0, "practical": 0}

                counter = Counter(contagens)
                sorted_counts = sorted(counter.items(), key=lambda x: (x[1], x[0]), reverse=True)
                
                logging.debug(f"Contagens encontradas: {sorted_counts}")

                # Se temos mais de um padrão
                if len(sorted_counts) > 1:
                    # Ordenar por número de aulas para comparar
                    patterns_by_hours = sorted(counter.items(), key=lambda x: x[0])
                    menor_padrao = patterns_by_hours[0][0]
                    maior_padrao = patterns_by_hours[-1][0]
                    
                    # Se a diferença entre o maior e menor é significativa
                    if maior_padrao - menor_padrao >= 2:
                        # Verificar se o padrão maior é frequente o suficiente
                        freq_maior = counter[maior_padrao] / len(contagens)
                        if freq_maior >= 0.2:  # Pelo menos 20% das aulas
                            # Encontrar o padrão regular (o menor com frequência significativa)
                            for padrao, contagem in patterns_by_hours:
                                if contagem/len(contagens) >= 0.2:
                                    menor_significativo = padrao
                                    break
                            else:
                                menor_significativo = menor_padrao

                            return {"regular": menor_significativo, "practical": maior_padrao}

                # Caso padrão: usar o mais frequente como regular
                return {"regular": sorted_counts[0][0], "practical": 0}
            
            def calcular_dias_restantes(subjects_days_dates, cod_disc):
                """
                Calcula os dias restantes de aula para uma disciplina.
                """
                hoje = datetime.date.today()
                dias_restantes = defaultdict(int)
                dias_datas = subjects_days_dates.get(cod_disc, {})
                
                logging.debug(f"\n=== INÍCIO DEBUG DIAS RESTANTES ===")
                logging.debug(f"Código da disciplina: {cod_disc}")
                
                for dia_semana, datas in dias_datas.items():
                    aulas_por_data = defaultdict(int)
                    for data_str, num_aulas in datas.items():
                        try:
                            data_aula = datetime.datetime.strptime(data_str, "%Y-%m-%d").date()
                            if data_aula >= hoje:
                                aulas_por_data[data_str] = num_aulas
                                logging.debug(f"Data futura encontrada: {data_str} com {num_aulas} aulas")
                        except ValueError:
                            continue

                    if not aulas_por_data:
                        logging.debug(f"Nenhuma aula futura para o dia {dia_semana}")
                        continue

                    # Analisa o padrão de aulas
                    padrao = analyze_class_pattern(aulas_por_data)
                    logging.debug(f"Dia {dia_semana}: Padrão analisado = {padrao}")

                    # Se existe padrão prático
                    if padrao["practical"] > 0:
                        padrao_pratico = padrao["practical"]
                        padrao_regular = padrao["regular"]

                        # Se não há padrão regular definido, todas são práticas
                        if padrao_regular == 0:
                            dias_pratica = len(aulas_por_data)
                            dias_restantes[f"{dia_semana}_pratica"] = dias_pratica
                            logging.debug(f"Dia {dia_semana}: {dias_pratica} dias práticos (todas práticas)")
                        else:
                            # Classificar aulas como regulares ou práticas
                            meio_termo = (padrao_regular + padrao_pratico) / 2
                            dias_regulares = sum(1 for num_aulas in aulas_por_data.values() 
                                            if num_aulas < meio_termo)
                            dias_pratica = sum(1 for num_aulas in aulas_por_data.values() 
                                            if num_aulas >= meio_termo)

                            if dias_regulares > 0:
                                dias_restantes[f"{dia_semana}"] = dias_regulares
                                logging.debug(f"Dia {dia_semana}: {dias_regulares} dias regulares")
                            if dias_pratica > 0:
                                dias_restantes[f"{dia_semana}_pratica"] = dias_pratica
                                logging.debug(f"Dia {dia_semana}: {dias_pratica} dias práticos")
                    else:
                        # Se não tem prática, todas são regulares
                        dias_restantes[f"{dia_semana}"] = len(aulas_por_data)
                        logging.debug(f"Dia {dia_semana}: {len(aulas_por_data)} dias regulares")

                logging.debug(f"Resultado final dias_restantes: {dict(dias_restantes)}")
                logging.debug("=== FIM DEBUG DIAS RESTANTES ===\n")
                
                return dias_restantes

            # Dicionário para armazenar o valor de moda de aulas por matéria e dia da semana
            subjects_mode_per_day = defaultdict(lambda: defaultdict(dict))

            for cod_disc, dias in subjects_days_dates.items():
                for dia, datas in dias.items():
                    if not datas:
                        subjects_mode_per_day[cod_disc][dia] = {"regular": 0, "practical": 0}
                        continue

                    aulas_info = analyze_class_pattern(datas)
                    subjects_mode_per_day[cod_disc][dia] = aulas_info

            update_progress(session_id, PHASE_PROCESSING, "Analisando padrões de aulas", 80)

            def get_day_name(day_number, is_practical=False):
                days = {
                    1: "Domingo",
                    2: "Segunda-feira",
                    3: "Terça-feira",
                    4: "Quarta-feira",
                    5: "Quinta-feira",
                    6: "Sexta-feira",
                    7: "Sábado"
                }
                base_name = days.get(day_number, "Dia inválido")
                return f"{base_name} (com prática)" if is_practical else base_name
            
            def get_day_key(day_number, is_practical=False):
                """Converte número do dia para chave do dicionário de dias restantes"""
                if not isinstance(day_number, int) or day_number < 1 or day_number > 7:
                    return None
                
                return f"{day_number}_pratica" if is_practical else str(day_number)


            # Criação do dicionário de aulas por matéria e dia da semana
            subjects_aulas_por_dia = defaultdict(list)

            for cod_disc, dias in subjects_mode_per_day.items():
                nome_materia = faltas_ch_info.get(cod_disc, {}).get("nome_materia", "Nome desconhecido")
                for dia in range(1, 8):  # De Domingo (1) a Sábado (7)
                    aulas_info = dias.get(dia, {"regular": 0, "practical": 0})
                    if aulas_info["regular"] > 0:
                        subjects_aulas_por_dia[cod_disc].append({
                            "Dia": get_day_name(dia),
                            "Aulas": aulas_info["regular"]
                        })
                    if aulas_info["practical"] > 0:
                        # Adiciona aulas práticas apenas se forem diferentes das regulares ou se não houver aulas regulares
                        if aulas_info["practical"] != aulas_info["regular"] or aulas_info["regular"] == 0:
                            subjects_aulas_por_dia[cod_disc].append({
                                "Dia": get_day_name(dia, True),
                                "Aulas": aulas_info["practical"]
                            })

            update_progress(session_id, PHASE_PROCESSING, "Organizando informações de aulas por dia", 90)

            # Preparar dados para exibição
            resultados = []
            for cod_disc, aulas_list in subjects_aulas_por_dia.items():
                info = faltas_ch_info.get(cod_disc, {})
                nome_materia = info.get("nome_materia", "Nome desconhecido")
                faltas = info.get("faltas", 0)
                ch = info.get("ch", 0.0)
                porcentagem_faltas = calcular_porcentagem_faltas(faltas, ch)
                porcentagem_restante = 25.0 - porcentagem_faltas
                if porcentagem_restante < 0:
                    porcentagem_restante = 0.0

                # Calcular o número de faltas que o aluno ainda pode ter
                faltas_permitidas_restantes = math.floor((porcentagem_restante * ch) / 100)
                faltas_permitidas_restantes = max(faltas_permitidas_restantes, 0)

                # Calcular o número de aulas restantes
                total_aulas_restantes = calcular_aulas_restantes(schedule_data, cod_disc)

                # Calcular dias restantes
                dias_restantes = calcular_dias_restantes(subjects_days_dates, cod_disc)
                logging.debug(dias_restantes)

                dias_info = []
                for aula in aulas_list:
                    dia = aula['Dia']
                    num_aulas = aula['Aulas']
                    # Mapeia o nome do dia para o número
                    dia_num = None
                    is_practical = False
                    for num, nome in {
                        1: "Domingo",
                        2: "Segunda-feira",
                        3: "Terça-feira",
                        4: "Quarta-feira",
                        5: "Quinta-feira",
                        6: "Sexta-feira",
                        7: "Sábado"
                    }.items():
                        if nome in dia:  # Usamos 'in' para pegar tanto dias normais quanto com prática
                            dia_num = num
                            is_practical = "(com prática)" in dia
                            break

                    if dia_num is None:
                        continue  # Pula este dia se não for reconhecido

                    day_key = get_day_key(dia_num, is_practical)
                    dias_restantes_na_semana = dias_restantes.get(day_key, 0)
                    
                    # **Nova Condição: Apenas incluir o dia se houver aulas restantes**
                    if dias_restantes_na_semana <= 0:
                        continue  # Pula este dia, não inclui nos resultados

                    porcentagem_perda = calcular_perda_por_dia(num_aulas, ch)
                    # Calcula quantas vezes você pode faltar nesse dia sem exceder 25%
                    faltas_permitidas_dia = calcular_faltas_permitidas(faltas, ch, num_aulas)
                    # Calcula a porcentagem (faltas_permitidas_dia / dias_restantes_na_semana) * 100
                    if dias_restantes_na_semana > 0:
                        percentage_can_miss = round((faltas_permitidas_dia / dias_restantes_na_semana) * 100, 2)
                        percentage_can_miss = min(percentage_can_miss, 100.0)
                    else:
                        percentage_can_miss = 0.0
                    dias_info.append({
                        'dia': dia,
                        'num_aulas': num_aulas,
                        'porcentagem_perda': porcentagem_perda,
                        'faltas_permitidas_dia': faltas_permitidas_dia,
                        'dias_restantes': dias_restantes_na_semana,
                        'percentage_can_miss': percentage_can_miss
                    })


                # Calcular a data a partir da qual o aluno pode faltar
                data_pode_faltar = calcular_data_pode_faltar(
                    total_aulas_restantes,
                    faltas_permitidas_restantes,
                    schedule_data,
                    cod_disc,
                    dias_info
                )

                # **Nova Condição: Apenas incluir a disciplina se houver dias com aulas restantes**
                if not dias_info:
                    continue  # Pula esta disciplina, não inclui nos resultados

                resultados.append({
                    'nome_materia': nome_materia,
                    'ch': ch,
                    'faltas': faltas,
                    'porcentagem_faltas': porcentagem_faltas,
                    'porcentagem_restante': porcentagem_restante,
                    'faltas_permitidas_restantes': faltas_permitidas_restantes,
                    'total_aulas_restantes': total_aulas_restantes,
                    'dias_info': dias_info, 
                    'data_pode_faltar': data_pode_faltar
                })

            # Ordenar os resultados em ordem decrescente de porcentagem de faltas
            resultados.sort(key=lambda x: x['porcentagem_faltas'], reverse=True)

            logging.debug("Processamento de dados concluído")
            logging.debug(f"Resultados preparados: {len(resultados)} disciplinas processadas.")

            informacoes_aluno_filtradas = extrair_informacoes_aluno(informacoes_aluno)
            logging.debug(f"Info Aluno: {informacoes_aluno_filtradas}")

            # Filtrar disciplinas conforme os critérios
            disciplinas_filtradas = filtrar_disciplinas(faltas_ch_data)
            logging.debug(f"Disciplinas filtradas: {len(disciplinas_filtradas)}")
            update_progress(session_id, PHASE_PROCESSING, "Filtrando disciplinas aprovadas", 45)

            # Ordenar disciplinas por período e nota
            disciplinas_ordenadas = ordenar_disciplinas_por_periodo_e_nota(disciplinas_filtradas)
            logging.debug(f"Disciplinas ordenadas: {disciplinas_ordenadas}")
            
            # Calcula as métricas desejadas
            media_global = calcular_media_global(disciplinas_filtradas)
            melhor_periodo, pior_periodo = calcular_melhor_pior_periodo(disciplinas_filtradas)
            melhores_areas = calcular_melhores_areas(disciplinas_filtradas)
            piores_areas = calcular_piores_areas(disciplinas_filtradas)
            metricas_por_periodo = calcular_metricas_por_periodo(disciplinas_filtradas)

            # Imprimir os resultados das métricas no console e logs
            logging.debug(f"Média Global: {media_global}")
            logging.debug(f"Melhor Período: {melhor_periodo}")
            logging.debug(f"Pior Período: {pior_periodo}")
            logging.debug(f"Melhores Áreas: {melhores_areas}")
            logging.debug(f"Piores Áreas: {piores_areas}")
            logging.debug(f"Métricas por Período: {metricas_por_periodo}")

            # Adicionar as métricas ao dicionário de resultados
            resultados_metrica = {
                'media_global': media_global,
                'melhor_periodo': melhor_periodo,
                'pior_periodo': pior_periodo,
                'melhores_areas': melhores_areas,
                'piore_areas': piores_areas,
                'metricas_por_periodo': metricas_por_periodo,
                'disciplinas_ordenadas': disciplinas_ordenadas
            }

            logging.debug(resultados_metrica)

            # Processar data_avaliacao
            try:
                avaliacao_data = data_avaliacao.get('data', [])
                logging.debug("Dados de avaliação extraídos com sucesso.")
                update_progress(session_id, PHASE_PROCESSING, "Processando dados de avaliação", 85)
            except KeyError as e:
                logging.error(f"Chave ausente em data_avaliacao: {e}")
                update_progress(session_id, PHASE_PROCESSING, f"Erro: Chave ausente no JSON de avaliação: {e}", 100)
                return

            # Filtrar os campos ETAPA, DISCIPLINA, MEDIA, VALOR, NOTA
            notas = []
            for item in avaliacao_data:
                nota_info = {
                    'ETAPA': item.get('ETAPA'),
                    'DISCIPLINA': item.get('DISCIPLINA'),
                    'MEDIA': item.get('MEDIA'),
                    'VALOR': item.get('VALOR'),
                    'NOTA': item.get('NOTA')
                }
                notas.append(nota_info)

            # Armazenar resultados no dicionário RESULTS
            logging.debug(f"Armazenando resultados no RESULTS para session_id: {session_id}")
            with results_lock:
                RESULTS[session_id] = {
                    'resultados': resultados,
                    'horario_data': horario_data, 
                    'metrica': resultados_metrica,
                    'info_aluno': informacoes_aluno_filtradas,
                    'notas': notas
                }
            logging.debug(f"Dados armazenados em RESULTS[{session_id}]: chaves: {list(RESULTS[session_id].keys())}")

             # Chamar a função de análise da IA
            logging.debug("Chamando a função de análise de desempenho da IA")
            update_progress(session_id, PHASE_PROCESSING, "Analisando seu progresso no curso...", 80)
            analise_ia = analyze_performance(resultados_metrica, informacoes_aluno_filtradas)
            
            # Armazenar a análise da IA no RESULTS
            with results_lock:
                RESULTS[session_id]['analise_ia'] = analise_ia

            logging.debug("Análise da IA armazenada com sucesso")
            logging.debug(f"IA: {analise_ia}")

            # Atualizar progresso para 100% após armazenar os dados
            update_progress(session_id, PHASE_PROCESSING, "Processamento concluído", 100)
            logging.debug("Processo de login e processamento concluído com sucesso")
        except Exception as e:
            logging.error(f"Erro durante o processamento dos dados: {e}", exc_info=True)
            update_progress(session_id, PHASE_PROCESSING, "Ocorreu um problema ao processar os dados. Por favor, tente novamente mais tarde.", 100)
    except Exception as e:
        logging.error(f"Erro inesperado no process_login_thread: {e}", exc_info=True)
        update_progress(session_id, PHASE_PROCESSING, "Ocorreu um problema inesperado. Por favor, tente novamente mais tarde.", 100)
    finally:
        logging.debug(f"Finalizando process_login_thread para session_id: {session_id}")

# Rotas da aplicação

@app.route('/process-login', methods=['POST'])
def process_login():
    username = request.form.get('username')
    password = request.form.get('password')

    # Verificar se os campos de usuário e senha foram preenchidos
    if not username or not password:
        flash("Erro: Por favor, forneça um nome de usuário e senha.", "error")
        return jsonify({'status': 'error'}), 400

    session_id = session['session_id']

    # Iniciar o processo de login em uma nova thread
    thread = threading.Thread(target=process_login_thread, args=(username, password, session_id))
    thread.start()

    return jsonify({'status': 'processing'}), 202

@app.route('/get_progress')
def get_progress():
    session_id = session.get('session_id')
    logging.debug(f"Solicitação de progresso para session_id: {session_id}")
    if not session_id:
        logging.error("Sessão inválida na solicitação de progresso")
        return jsonify({'phase': '', 'description': 'Sessão inválida.', 'percentage': 0}), 400

    with progress_lock:
        progress = PROGRESS.get(session_id, {'phase': '', 'description': 'Aguardando início...', 'percentage': 0})
    logging.debug(f"Progresso retornado: {progress}")
    return jsonify(progress)

@app.route('/resultado')
def resultado():
    session_id = session.get('session_id')
    logging.debug(f"/resultado: session_id = {session_id}")

    # Espera até que os dados estejam disponíveis (com timeout)
    timeout = 30  # 30 segundos de timeout
    start_time = time.time()
    while True:
        with results_lock:
            data = RESULTS.get(session_id)
        if data is not None:
            break
        if time.time() - start_time > timeout:
            flash("Erro: Tempo limite excedido ao aguardar os dados. Por favor, tente novamente.", "error")
            return redirect(url_for('login'))
        time.sleep(0.5)  # Espera 0.5 segundos antes de verificar novamente

    resultados = data['resultados']
    return render_template('resultado.html', resultados=resultados)

@app.route('/check_data_ready')
def check_data_ready():
    session_id = session.get('session_id')
    with results_lock:
        data_ready = session_id in RESULTS
    return jsonify({'ready': data_ready})

@app.route('/check_processing_state')
def check_processing_state():
    session_id = session.get('session_id')
    if not session_id:
        return jsonify({'error': 'Sessão inválida'}), 400

    with results_lock:
        results = RESULTS.get(session_id)

    with progress_lock:
        progress = PROGRESS.get(session_id)

    state = {
        'results_available': results is not None,
        'current_progress': progress
    }
    logging.debug(f"Estado atual do processamento: {state}")
    return jsonify(state)

@app.route('/check_processing_complete')
def check_processing_complete():
    session_id = session.get('session_id')
    if not session_id:
        return jsonify({'error': 'Sessão inválida'}), 400

    with results_lock:
        results = RESULTS.get(session_id)

    is_complete = results is not None
    return jsonify({'is_complete': is_complete})

@app.route('/simulador')
def simulador():
    session_id = session.get('session_id')
    logging.debug(f"/simulador: session_id = {session_id}")
    with results_lock:
        data = RESULTS.get(session_id)
    if data is None:
        flash("Erro: Nenhum dado de faltas encontrado. Por favor, faça login novamente.", "error")
        return redirect(url_for('login'))
    resultados = data['resultados']
    return render_template('simulador.html', resultados=resultados)

@app.route('/meu_progresso')
def analise_ia():
    session_id = session.get('session_id')
    logging.debug(f"/analise_ia: session_id = {session_id}")

    if not session_id:
        flash("Erro: Sessão inválida. Por favor, faça login novamente.", "error")
        return redirect(url_for('login'))

    with results_lock:
        data = RESULTS.get(session_id)

    if not data:
        flash("Erro: Dados não encontrados. Por favor, faça login novamente.", "error")
        return redirect(url_for('login'))

    analise_ia = data.get('analise_ia')
    metricas_por_periodo = data.get('metrica', {}).get('metricas_por_periodo', {})

    # Passar 'metricas_por_periodo' como JSON para o template
    return render_template('analise_ia.html', analise_ia=analise_ia, metricas_por_periodo=metricas_por_periodo)

@app.route('/get_disciplinas_por_data', methods=['POST'])
def get_disciplinas_por_data():
    data = request.json.get('data')
    session_id = session.get('session_id')
    results_data = RESULTS.get(session_id)
    if results_data is None:
        return jsonify({'error': 'Dados não encontrados. Faça login novamente.'}), 400
    horario_data = results_data.get('horario_data')

    if horario_data is None:
        return jsonify({'error': 'Dados de horário não encontrados'}), 400

    disciplinas_do_dia = {}
    try:
        for aula in horario_data['data']['SHorarioAluno']:
            aula_data = aula.get('DATAINICIAL', '')
            if aula_data:
                aula_data = aula_data.split('T')[0]
                if aula_data == data:
                    nome = aula.get('NOME', 'Nome não disponível')
                    if nome in disciplinas_do_dia:
                        disciplinas_do_dia[nome]['quantidade'] += 1
                    else:
                        disciplinas_do_dia[nome] = {
                            'nome': nome,
                            'quantidade': 1
                        }
    except Exception as e:
        logging.error(f"Erro ao processar dados de horário: {e}")
        return jsonify({'error': 'Erro ao processar dados de horário'}), 500

    return jsonify(list(disciplinas_do_dia.values()))

@app.route('/simular_falta', methods=['POST'])
def simular_falta():
    data = request.json
    datas_faltas = data.get('datas_faltas', [])

    session_id = session.get('session_id')
    with results_lock:
        results_data = RESULTS.get(session_id)
    if results_data is None:
        return jsonify({'error': 'Dados não encontrados. Faça login novamente.'}), 400

    resultados = results_data.get('resultados')
    horario_data = results_data.get('horario_data')

    if resultados is None or horario_data is None:
        return jsonify({'error': 'Dados incompletos. Faça login novamente.'}), 400

    # Contar o número de aulas para cada disciplina nas datas selecionadas
    aulas_por_disciplina = defaultdict(int)
    for data_falta in datas_faltas:
        for aula in horario_data.get('data', {}).get('SHorarioAluno', []):
            aula_data = aula.get('DATAINICIAL', '')
            if aula_data:
                if aula_data.split('T')[0] == data_falta.get('data'):
                    nome = aula.get('NOME')
                    if nome in data_falta.get('disciplinas', []):
                        aulas_por_disciplina[nome] += 1

    simulacao_resultados = []
    for disciplina in resultados:
        disciplina_simulada = disciplina.copy()
        disciplina_simulada['faltas_atuais'] = disciplina['faltas']
        disciplina_simulada['porcentagem_faltas_atual'] = calcular_porcentagem_faltas(disciplina['faltas'], disciplina['ch'])

        if disciplina['nome_materia'] in aulas_por_disciplina:
            faltas_adicionais = aulas_por_disciplina[disciplina['nome_materia']]
            disciplina_simulada['faltas'] += faltas_adicionais
            disciplina_simulada['porcentagem_faltas'] = calcular_porcentagem_faltas(disciplina_simulada['faltas'], disciplina['ch'])
            disciplina_simulada['porcentagem_restante'] = max(25.0 - disciplina_simulada['porcentagem_faltas'], 0.0)
            disciplina_simulada['faltas_permitidas_restantes'] = max(math.floor((disciplina_simulada['porcentagem_restante'] * disciplina_simulada['ch']) / 100), 0)
        else:
            disciplina_simulada['faltas'] = disciplina['faltas']
            disciplina_simulada['porcentagem_faltas'] = disciplina_simulada['porcentagem_faltas_atual']
            disciplina_simulada['porcentagem_restante'] = max(25.0 - disciplina_simulada['porcentagem_faltas'], 0.0)
            disciplina_simulada['faltas_permitidas_restantes'] = max(math.floor((disciplina_simulada['porcentagem_restante'] * disciplina_simulada['ch']) / 100), 0)

        disciplina_simulada['total_aulas_restantes'] = calcular_aulas_restantes(
            horario_data.get('data', {}).get('SHorarioAluno', []),
            disciplina['nome_materia']
        )

        # Calcular a porcentagem de faltas permitidas restantes
        if disciplina_simulada['total_aulas_restantes'] > 0:
            porcentagem_faltas_permitidas = (disciplina_simulada['faltas_permitidas_restantes'] / disciplina_simulada['total_aulas_restantes']) * 100
        else:
            porcentagem_faltas_permitidas = 0

        disciplina_simulada['faltas_permitidas_info'] = f"{disciplina_simulada['faltas_permitidas_restantes']} restantes"

        simulacao_resultados.append(disciplina_simulada)

    return jsonify(simulacao_resultados)

@app.route('/controle_notas')
def controle_notas():
    session_id = session.get('session_id')
    logging.debug(f"/controle_notas: session_id = {session_id}")

    if not session_id:
        flash("Erro: Sessão inválida. Por favor, faça login novamente.", "error")
        return redirect(url_for('login'))

    with results_lock:
        data = RESULTS.get(session_id)

    if not data or 'notas' not in data:
        flash("Erro: Dados de notas não encontrados. Por favor, faça login novamente.", "error")
        return redirect(url_for('login'))

    notas = data['notas']

    # Processar as notas para agrupar por disciplina e ETAPA
    disciplinas_notas = {}
    for nota in notas:
        disciplina = nota.get('DISCIPLINA')
        etapa = nota.get('ETAPA')
        if not disciplina or not etapa:
            continue  # Ignora se disciplina ou etapa estiverem ausentes
        if etapa == 'Exame Especial':
            continue  # Ignora etapas de Exame Especial

        nota_valor = nota.get('NOTA')
        valor = nota.get('VALOR')
        media = nota.get('MEDIA')

        # Verificar se NOTA e VALOR estão presentes e não são None ou vazios
        if nota_valor in (None, '') or valor in (None, ''):
            continue  # Ignora etapas com NOTA ou VALOR inválidos

        # Tentar converter NOTA e VALOR para float
        try:
            nota_num = float(str(nota_valor).replace(',', '.').strip())
            valor_num = float(str(valor).replace(',', '.').strip())
        except (ValueError, TypeError):
            continue  # Ignora se NOTA ou VALOR não são válidos

        # Se MEDIA é None ou '', considerar como 60% de VALOR
        if media in (None, ''):
            media_num = valor_num * 0.6
        else:
            try:
                media_num = float(str(media).replace(',', '.').strip())
            except (ValueError, TypeError):
                media_num = valor_num * 0.6  # Se MEDIA não for válida, usar 60% de VALOR

        # Prosseguir com o processamento
        if disciplina not in disciplinas_notas:
            disciplinas_notas[disciplina] = {
                'ETAPAs': {},
                'total_nota': 0.0,
                'total_valor': 0.0,
                'sum_media': 0.0,
            }

        if etapa not in disciplinas_notas[disciplina]['ETAPAs']:
            disciplinas_notas[disciplina]['ETAPAs'][etapa] = {
                'nota_nominal': 0.0,
                'VALOR': 0.0,
                'MEDIA': 0.0,
                'performance': 0.0,
                'width': 0.0,
            }

        disciplinas_notas[disciplina]['ETAPAs'][etapa]['nota_nominal'] += nota_num
        disciplinas_notas[disciplina]['ETAPAs'][etapa]['VALOR'] += valor_num
        disciplinas_notas[disciplina]['ETAPAs'][etapa]['MEDIA'] += media_num

        disciplinas_notas[disciplina]['total_nota'] += nota_num
        disciplinas_notas[disciplina]['total_valor'] += valor_num
        disciplinas_notas[disciplina]['sum_media'] += media_num

    # Calcular o desempenho para cada ETAPA e a largura da barra
    for disciplina, data_disciplinas in disciplinas_notas.items():
        total_nota = data_disciplinas['total_nota']
        total_valor = data_disciplinas['total_valor']
        sum_media = data_disciplinas['sum_media']

        # Desempenho total
        if total_valor > 0:
            total_performance = (total_nota / total_valor) * 100
        else:
            total_performance = 0.0
        data_disciplinas['total_performance'] = round(total_performance, 2)

        # Definir a média como a soma das médias das etapas
        average = sum_media
        data_disciplinas['average'] = round(average, 2)

        # Diferença da média (total_nota - average)
        data_disciplinas['difference_from_average'] = round(total_nota - average, 2)

        for etapa, data_etapa in data_disciplinas['ETAPAs'].items():
            valor = data_etapa['VALOR']
            nota = data_etapa['nota_nominal']
            media = data_etapa['MEDIA']
            if valor > 0:
                performance = (nota / valor) * 100
            else:
                performance = 0.0
            data_etapa['performance'] = round(performance, 2)

            # A largura da seção da barra é proporcional à NOTA obtida na etapa
            data_etapa['width'] = (nota / 100) * 100  # Calcula a porcentagem baseada em 100 pontos

    # Ordenar as disciplinas por nome
    disciplinas_ordenadas = dict(sorted(disciplinas_notas.items()))

    # Novo código para calcular o aproveitamento necessário
    notas_completas = data['notas']

    # Dicionário para armazenar os novos cálculos
    disciplinas_calculos = {}

    for nota in notas_completas:
        disciplina = nota.get('DISCIPLINA')
        etapa = nota.get('ETAPA')
        if not disciplina or not etapa:
            continue  # Ignora se disciplina ou etapa estiverem ausentes
        if etapa == 'Exame Especial':
            continue  # Ignora etapas de Exame Especial

        valor = nota.get('VALOR')
        media = nota.get('MEDIA')
        nota_valor = nota.get('NOTA')

        # Verificar se VALOR está presente e não é None ou vazio
        if valor in (None, ''):
            continue  # Ignora etapas com VALOR inválido

        # Tentar converter VALOR para float
        try:
            valor_num = float(str(valor).replace(',', '.').strip())
        except (ValueError, TypeError):
            continue  # Ignora se VALOR não é válido

        # Se MEDIA é None ou '', considerar como 60% de VALOR
        if media in (None, ''):
            media_num = valor_num * 0.6
        else:
            try:
                media_num = float(str(media).replace(',', '.').strip())
            except (ValueError, TypeError):
                media_num = valor_num * 0.6  # Se MEDIA não for válida, usar 60% de VALOR

        # Inicializar o dicionário da disciplina se ainda não existe
        if disciplina not in disciplinas_calculos:
            disciplinas_calculos[disciplina] = {
                'sum_media': 0.0,                # Soma de todas as médias
                'sum_notas': 0.0,                # Soma de todas as notas
                'sum_valor_distribuido': 0.0,    # Soma de VALOR onde NOTA está presente
            }

        # Atualizar a soma de todas as médias
        disciplinas_calculos[disciplina]['sum_media'] += media_num

        # Se NOTA está presente, adicionar ao sum_notas e sum_valor_distribuido
        if nota_valor not in (None, ''):
            try:
                nota_num = float(str(nota_valor).replace(',', '.').strip())
                disciplinas_calculos[disciplina]['sum_notas'] += nota_num
                disciplinas_calculos[disciplina]['sum_valor_distribuido'] += valor_num
            except (ValueError, TypeError):
                pass  # Ignora se a conversão falhar

    # Agora, para cada disciplina, calcular o aproveitamento necessário
    for disciplina, calculos in disciplinas_calculos.items():
        sum_media = calculos['sum_media']
        sum_notas = calculos['sum_notas']
        sum_valor_distribuido = calculos['sum_valor_distribuido']

        # Pontos faltantes para atingir a média fixa de 60
        required_points = max(0, 60 - sum_notas)

        # Pontos ainda a serem distribuídos
        remaining_valor = max(0, 100 - sum_valor_distribuido)

        # Porcentagem necessária de aproveitamento
        if remaining_valor > 0 and required_points > 0:
            required_performance = (required_points / remaining_valor) * 100
            calculos['required_performance'] = round(required_performance, 2)
        elif required_points <= 0:
            # Já atingiu ou ultrapassou a média
            calculos['required_performance'] = 0.0
        else:
            # Não há mais pontos a serem distribuídos e ainda não atingiu a média
            calculos['required_performance'] = None

        # Armazenar os valores adicionais para o template
        calculos['required_points'] = round(required_points, 2)
        calculos['remaining_valor'] = round(remaining_valor, 2)

        # Adicionar logs para depuração
        logging.debug(f"Disciplina: {disciplina}")
        logging.debug(f"Sum Media: {sum_media}, Sum Notas: {sum_notas}")
        logging.debug(f"Required Points: {required_points}, Remaining Valor: {remaining_valor}")
        logging.debug(f"Required Performance: {calculos.get('required_performance')}%")

    # Passar disciplinas_calculos para o template
    return render_template('controle_notas.html', disciplinas_notas=disciplinas_ordenadas, disciplinas_calculos=disciplinas_calculos)

# Nova rota para a página de simulação de currículo
@app.route('/simulador_residencia')
def simulador_residencia():
    session_id = session.get('session_id')
    logging.debug(f"/simulador_residencia: session_id = {session_id}")
    
    if not session_id:
        flash("Erro: Sessão inválida. Por favor, faça login novamente.", "error")
        return redirect(url_for('login'))
        
    with results_lock:
        data = RESULTS.get(session_id)
        
    if not data:
        flash("Erro: Dados não encontrados. Por favor, faça login novamente.", "error")
        return redirect(url_for('login'))
    
    return render_template('simulador_residencia.html')

# Nova rota para processar a análise do currículo
@app.route('/analisar_curriculo', methods=['POST'])
def analisar_curriculo():
    session_id = session.get('session_id')
    logging.debug(f"/analisar_curriculo: Iniciando análise para session_id = {session_id}")
    
    if not session_id:
        return jsonify({'error': 'Sessão inválida'}), 400

    try:
        # Obter dados da sessão (histórico e info do aluno)
        with results_lock:
            session_data = RESULTS.get(session_id)
            if not session_data:
                return jsonify({'error': 'Dados da sessão não encontrados'}), 400
            
            metrica = session_data.get('metrica', {}).get('disciplinas_ordenadas', 0)
            info_aluno = session_data.get('info_aluno')

        # Obter dados do formulário
        form_data = request.json
        logging.debug(f"Dados do formulário recebidos: {form_data}")

        # Chamar a função de análise com todos os parâmetros
        resultado = analyze_curriculo(
            metrica=metrica,
            info_aluno=info_aluno,
            extensao=int(form_data.get('extensao', 0)),
            eventos_sus=int(form_data.get('eventos_sus', 0)),
            cursos_aperfeicoamento=int(form_data.get('cursos_aperfeicoamento', 0)),
            monitoria=int(form_data.get('monitoria', 0)),
            pesquisa_ic=int(form_data.get('pesquisa_ic', 0)),
            eventos_regionais=int(form_data.get('eventos_regionais', 0)),
            eventos_nacionais=int(form_data.get('eventos_nacionais', 0)),
            artigos_nao_indexados=int(form_data.get('artigos_nao_indexados', 0)),
            artigos_doi=int(form_data.get('artigos_doi', 0)),
            congressos=int(form_data.get('congressos', 0)),
            representacao_estudantil=int(form_data.get('representacao_estudantil', 0)),
            ligas_academicas=int(form_data.get('ligas_academicas', 0)),
            lingua_estrangeira=int(form_data.get('lingua_estrangeira', 0)),
            pet_saude=int(form_data.get('pet_saude', 0)),
            estagio_nao_obrigatorio=int(form_data.get('estagio_nao_obrigatorio', 0))
        )

        # Limpar e sanitizar as strings no resultado
        if isinstance(resultado, dict):
            # Limpar feedback geral
            if 'feedback_geral' in resultado:
                resultado['feedback_geral'] = resultado['feedback_geral'].replace('\n', ' ').strip()
            
            # Limpar componentes
            if 'componentes' in resultado and isinstance(resultado['componentes'], list):
                for componente in resultado['componentes']:
                    if 'feedback' in componente:
                        componente['feedback'] = componente['feedback'].replace('\n', ' ').strip()
                    if 'nome' in componente:
                        componente['nome'] = componente['nome'].replace('\n', ' ').strip()

        logging.debug(f"Análise concluída com sucesso: {resultado}")
        return jsonify(resultado)

    except ValueError as ve:
        # Erros relacionados à validação do JSON
        logging.error(f"Erro na validação do JSON: {str(ve)}", exc_info=True)
        return jsonify({
            'error': True,
            'message': f'Ocorreu um erro ao analisar o currículo: {str(ve)}'
        }), 400

    except Exception as e:
        logging.error(f"Erro ao analisar currículo: {str(e)}", exc_info=True)
        return jsonify({
            'error': True,
            'message': f'Ocorreu um erro ao processar a análise do currículo: {str(e)}'
        }), 500

@app.route('/simulador_feluma')
def simulador_feluma():
    session_id = session.get('session_id')
    logging.debug(f"/simulador_feluma: session_id = {session_id}")
    
    if not session_id:
        flash("Erro: Sessão inválida. Por favor, faça login novamente.", "error")
        return redirect(url_for('login'))
        
    with results_lock:
        data = RESULTS.get(session_id)
        
    if not data:
        flash("Erro: Dados não encontrados. Por favor, faça login novamente.", "error")
        return redirect(url_for('login'))
    
    return render_template('simulador_feluma.html')

@app.route('/analisar_curriculo_feluma', methods=['POST'])
def analisar_curriculo_feluma_route():
    session_id = session.get('session_id')
    logging.debug(f"/analisar_curriculo_feluma: Iniciando análise para session_id = {session_id}")
    
    if not session_id:
        return jsonify({'error': 'Sessão inválida'}), 400

    try:
        # Obter dados da sessão (histórico e info do aluno)
        with results_lock:
            session_data = RESULTS.get(session_id)
            if not session_data:
                return jsonify({'error': 'Dados da sessão não encontrados'}), 400
            
            # Obter a média do aluno das métricas
            media_curricular = session_data.get('metrica', {}).get('media_global', 0)
            info_aluno = session_data.get('info_aluno')

        # Obter dados do formulário
        form_data = request.json
        logging.debug(f"Dados do formulário recebidos: {form_data}")

        # Extrair todos os parâmetros necessários com valores padrão
        parametros = {
            'media_curricular': media_curricular,
            'projeto_pesquisa': form_data.get('projeto_pesquisa', False),
            'projeto_extensao': form_data.get('projeto_extensao', False),
            'estagio_nao_obrigatorio': form_data.get('estagio_nao_obrigatorio', False),
            'monitoria_pid': form_data.get('monitoria_pid', False),
            'diretoria_liga': form_data.get('diretoria_liga', False),
            'membro_liga': form_data.get('membro_liga', False),
            'projeto_comunidade': form_data.get('projeto_comunidade', False),
            'doutorado_mestrado': form_data.get('doutorado_mestrado', False),
            'residencia_pos_hospitalar': form_data.get('residencia_pos_hospitalar', False),
            'primeira_especializacao': form_data.get('primeira_especializacao', False),
            'segunda_especializacao': form_data.get('segunda_especializacao', False),
            'curso_acls': form_data.get('curso_acls', False),
            'curso_pals': form_data.get('curso_pals', False),
            'curso_atls': form_data.get('curso_atls', False),
            'curso_also': form_data.get('curso_also', False),
            'curso_phtls': form_data.get('curso_phtls', False),
            'curso_bls': form_data.get('curso_bls', False),
            'primeira_publicacao_artigo': form_data.get('primeira_publicacao_artigo', False),
            'segunda_publicacao_artigo': form_data.get('segunda_publicacao_artigo', False),
            'primeiro_capitulo_livro': form_data.get('primeiro_capitulo_livro', False),
            'segundo_capitulo_livro': form_data.get('segundo_capitulo_livro', False),
            'primeira_organizacao_livro': form_data.get('primeira_organizacao_livro', False),
            'segunda_organizacao_livro': form_data.get('segunda_organizacao_livro', False),
            'primeira_comissao_organizadora': form_data.get('primeira_comissao_organizadora', False),
            'segunda_comissao_organizadora': form_data.get('segunda_comissao_organizadora', False),
            'primeira_premiacao': form_data.get('primeira_premiacao', False),
            'segunda_premiacao': form_data.get('segunda_premiacao', False),
            'primeira_palestra': form_data.get('primeira_palestra', False),
            'segunda_palestra': form_data.get('segunda_palestra', False),
            'apresentacao_trabalho': form_data.get('apresentacao_trabalho', False),
            'proficiencia_ingles': form_data.get('proficiencia_ingles', False),
            'proficiencia_outra_lingua': form_data.get('proficiencia_outra_lingua', False),
            'proficiencia_portugues': form_data.get('proficiencia_portugues', False)
        }

        # Calcular as pontuações
        resultado_calculado = processar_analisar_curriculo_feluma(**parametros)
        
        # Gerar feedbacks utilizando a IA existente
        resultado_com_feedback = gerar_feedback(resultado_calculado)

        # Garantir que a pontuação total não exceda 10
        resultado_com_feedback['valor_curriculo'] = min(resultado_com_feedback['valor_curriculo'], 10.0)

        # Limpar e sanitizar as strings no resultado
        if isinstance(resultado_com_feedback, dict):
            if 'feedback_geral' in resultado_com_feedback:
                resultado_com_feedback['feedback_geral'] = resultado_com_feedback['feedback_geral'].replace('\n', ' ').strip()
            
            if 'grupos' in resultado_com_feedback and isinstance(resultado_com_feedback['grupos'], list):
                for grupo in resultado_com_feedback['grupos']:
                    if 'feedback' in grupo:
                        grupo['feedback'] = grupo['feedback'].replace('\n', ' ').strip()
                    if 'nome' in grupo:
                        grupo['nome'] = grupo['nome'].replace('\n', ' ').strip()

        logging.debug(f"Análise concluída com sucesso: {resultado_com_feedback}")
        return jsonify(resultado_com_feedback)

    except ValueError as ve:
        logging.error(f"Erro na validação dos dados: {str(ve)}", exc_info=True)
        return jsonify({
            'error': True,
            'message': f'Ocorreu um erro ao analisar o currículo: {str(ve)}'
        }), 400

    except Exception as e:
        logging.error(f"Erro ao analisar currículo: {str(e)}", exc_info=True)
        return jsonify({
            'error': True,
            'message': f'Ocorreu um erro ao processar a análise do currículo: {str(e)}'
        }), 500    

@app.route('/logout')
def logout():
    session_id = session.get('session_id')
    if session_id in RESULTS:
        del RESULTS[session_id]
    session.clear()
    flash("Você foi deslogado com sucesso.", "info")
    return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(debug=True)