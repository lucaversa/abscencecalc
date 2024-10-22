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

def calcular_data_pode_faltar(aulas_restantes, faltas_permitidas, schedule_data, cod_disc, dias_info):
    hoje = datetime.date.today()
    
    # Filtra e ordena as aulas válidas futuras
    aulas_validas = [
        aula for aula in schedule_data 
        if aula.get('CODDISC') == cod_disc and aula.get('DATAINICIAL')
    ]
    aulas_futuras = [
        aula for aula in aulas_validas
        if datetime.datetime.strptime(aula['DATAINICIAL'].split('T')[0], "%Y-%m-%d").date() >= hoje
    ]
    aulas_ordenadas = sorted(aulas_futuras, key=lambda x: x['DATAINICIAL'])
    
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

def calcular_dias_restantes(subjects_days_dates, cod_disc):
    hoje = datetime.date.today()
    dias_restantes = defaultdict(int)  # chave: "dia_semana" ou "dia_semana_pratica"
    dias_datas = subjects_days_dates.get(cod_disc, {})
    
    for dia_semana, datas in dias_datas.items():
        aulas_por_data = defaultdict(int)
        for data_str, num_aulas in datas.items():
            try:
                data_aula = datetime.datetime.strptime(data_str, "%Y-%m-%d").date()
                if data_aula >= hoje:
                    aulas_por_data[data_str] = num_aulas
            except ValueError:
                continue

        if not aulas_por_data:
            continue

        # Analisa o padrão de aulas para este dia da semana
        contagens = list(aulas_por_data.values())
        if not contagens:
            continue

        counter = Counter(contagens)
        sorted_counts = sorted(counter.items(), key=lambda x: (x[1], -x[0]), reverse=True)
        
        # Se só tem um tipo de aula neste dia
        if len(sorted_counts) == 1:
            dias_restantes[f"{dia_semana}"] = len(aulas_por_data)
            continue

        # Se tem dois padrões diferentes (regular e prática)
        aula_regular = min(sorted_counts[0][0], sorted_counts[1][0])
        aula_pratica = max(sorted_counts[0][0], sorted_counts[1][0])

        # Conta dias restantes para cada tipo
        dias_regulares = sum(1 for num_aulas in aulas_por_data.values() if num_aulas == aula_regular)
        dias_pratica = sum(1 for num_aulas in aulas_por_data.values() if num_aulas == aula_pratica)

        # Armazena separadamente dias regulares e com prática
        if dias_regulares > 0:
            dias_restantes[f"{dia_semana}"] = dias_regulares
        if dias_pratica > 0:
            dias_restantes[f"{dia_semana}_pratica"] = dias_pratica

    return dias_restantes

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
            data1, data2 = scrape_portal(username, password, session_id, update_progress)
            logging.debug("Scraping concluído com sucesso")
        except Exception as e:
            logging.error(f"Erro durante o scraping: {e}", exc_info=True)
            update_progress(session_id, PHASE_SCRAPING, f"Erro durante o scraping: {e}", 100)
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
                contagens = list(aulas_por_data.values())
                if len(contagens) < 4:  # Precisamos de pelo menos 4 semanas de dados para determinar
                    return {"regular": max(set(contagens), key=contagens.count), "practical": 0}

                counter = Counter(contagens)
                sorted_counts = sorted(counter.items(), key=lambda x: (x[1], -x[0]), reverse=True)

                if len(sorted_counts) == 1:
                    return {"regular": sorted_counts[0][0], "practical": 0}

                # Identificar os dois padrões mais frequentes
                first_frequent = sorted_counts[0][0]
                second_frequent = sorted_counts[1][0] if len(sorted_counts) > 1 else 0

                # Calcular as frequências relativas
                freq_first = counter[first_frequent] / len(contagens)
                freq_second = counter[second_frequent] / len(contagens)

                # Caso especial: aulas práticas quinzenais ou mensais
                if freq_first <= 0.6 and counter[0] / len(contagens) > 0.3:
                    return {"regular": 0, "practical": max(contagens)}

                # Caso com aulas regulares e práticas
                if first_frequent != second_frequent and freq_first + freq_second > 0.8:
                    # Verifica se o segundo padrão é frequente o suficiente para ser considerado prática
                    if freq_second > 0.2:
                        return {
                            "regular": min(first_frequent, second_frequent),
                            "practical": max(first_frequent, second_frequent)
                        }

                # Caso padrão: apenas aulas regulares
                return {"regular": first_frequent, "practical": 0}

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

            # Armazenar resultados no dicionário RESULTS
            logging.debug(f"Armazenando resultados no RESULTS para session_id: {session_id}")
            with results_lock:
                RESULTS[session_id] = {
                    'resultados': resultados,
                    'horario_data': horario_data
                }
            logging.debug(f"Dados armazenados em RESULTS[{session_id}]: chaves: {list(RESULTS[session_id].keys())}")

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

        disciplina_simulada['faltas_permitidas_info'] = f"{disciplina_simulada['faltas_permitidas_restantes']} ({porcentagem_faltas_permitidas:.2f}%)"

        simulacao_resultados.append(disciplina_simulada)

    return jsonify(simulacao_resultados)

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
