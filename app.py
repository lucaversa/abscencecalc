# app.py
from flask import Flask, render_template, request, flash, redirect, url_for, session, jsonify
import json
from statistics import mode, multimode
from collections import defaultdict, Counter
import math
import datetime
import logging
from flask_session import Session
import tempfile
import time

from scraper import scrape_portal

app = Flask(__name__)

# Configurar logging
logging.basicConfig(level=logging.DEBUG)

app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = tempfile.gettempdir()
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SECRET_KEY'] = '1234567890'  

Session(app)

# Função para mapear a porcentagem de faltas para uma cor
def get_color(porcentagem_faltas):
    try:
        porcentagem_faltas = float(porcentagem_faltas)
    except (ValueError, TypeError):
        porcentagem_faltas = 0.0

    if porcentagem_faltas >= 25:
        # Gradiente completo para vermelho
        gradient = 'linear-gradient(to right, rgb(220, 53, 0), rgb(220, 53, 0))'
    else:
        # Calcula a cor intermediária baseada na porcentagem
        ratio = porcentagem_faltas / 25.0
        r = int(32 + (220 - 32) * ratio)      # De 32 a 220
        g = int(178 + (53 - 178) * ratio)     # De 178 a 53
        b = int(170 + (0 - 170) * ratio)      # De 170 a 0
        # Cria um gradiente que começa com azul-turquesa e vai até a cor calculada
        gradient = f'linear-gradient(to right, rgb(32, 178, 170), rgb({r}, {g}, {b}))'
    return gradient

# Registrar a função como um filtro
app.jinja_env.filters['get_color'] = get_color

@app.route('/')
def login():
    return render_template('login.html')

@app.route('/process-login', methods=['POST'])
def process_login():

    logging.debug("Iniciando process_login")
    start_time = time.time()

    username = request.form.get('username')
    password = request.form.get('password')

    logging.debug(f"Tempo decorrido: {time.time() - start_time:.2f}s - Verificando credenciais")
    
    # Verificar se os campos de usuário e senha foram preenchidos
    if not username or not password:
        flash("Erro: Por favor, forneça um nome de usuário e senha.", "error")
        return redirect(url_for('login'))
    
    # Chamar a função de scraping
    try:
        logging.debug(f"Tempo decorrido: {time.time() - start_time:.2f}s - Iniciando scraping")
        data1, data2 = scrape_portal(username, password)
        logging.debug(f"Tempo decorrido: {time.time() - start_time:.2f}s - Scraping concluído")
        logging.debug(f"Scrape Portal retornou data1: {data1}, data2: {data2}")
        
        # Armazene data2 na sessão
        session['horario_data'] = data2

        logging.debug(f"Tempo decorrido: {time.time() - start_time:.2f}s - Processando dados")
        
    except Exception as e:
        logging.error(f"Exceção durante o scraping: {e}")
        flash("Erro: Ocorreu um problema ao realizar o login. Por favor, tente novamente mais tarde.", "error")
        return redirect(url_for('login'))
    
    # Verificar se os dados foram obtidos corretamente
    if data1 is None or data2 is None:
        flash("Erro: Falha ao obter os dados do portal. Verifique suas credenciais.", "error")
        return redirect(url_for('login'))
    
    # Verificar se 'data1' e 'data2' são JSON-serializáveis
    try:
        json.dumps(data1)
        json.dumps(data2)
    except TypeError as e:
        logging.error(f"Erro de serialização de dados: {e}")
        flash("Erro: Dados obtidos não são válidos.", "error")
        return redirect(url_for('login'))
    
    # Processar os dados para obter 'resultados'
    try:
        logging.debug("Iniciando processamento de dados")
        faltas_ch_data = data1
        horario_data = data2

        # Verifique se 'horario_data' é um dicionário
        if not isinstance(horario_data, dict):
            logging.error("horario_data não é um dicionário.")
            flash("Erro: Dados de horário inválidos.", "error")
            return redirect(url_for('login'))

        # Dados de horário
        try:
            schedule_data = horario_data["data"]["SHorarioAluno"]
            logging.debug("schedule_data extraído com sucesso.")
        except KeyError as e:
            logging.error(f"Chave ausente em horario_data: {e}")
            flash(f"Erro: Chave ausente no JSON de horário: {e}", "error")
            return redirect(url_for('login'))
        try:
            faltas_ch_data = faltas_ch_data["data"]["APRESENTACAOHISTORICO"]
            logging.debug("faltas_ch_data extraído com sucesso.")
        except KeyError as e:
            logging.error(f"Chave ausente em faltas_ch_data: {e}")
            flash(f"Erro: Chave ausente no JSON de faltas: {e}", "error")
            return redirect(url_for('login'))

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

            # Verifica se DIASEMANA está entre 1 e 6 (exclui Sábado - 7)
            if dia_semana < 1 or dia_semana > 6:
                continue  # Ignora dias inválidos e Sábado

            # Extrai a data (parte antes do 'T')
            data = data_inicial.split("T")[0]

            # Incrementa a contagem para a matéria, dia da semana e data
            subjects_days_dates[cod_disc][dia_semana][data] += 1

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
                    return {"regular": min(first_frequent, second_frequent), 
                            "practical": max(first_frequent, second_frequent)}
            
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

        # Função para mapear números para nomes dos dias da semana (exclui Sábado)
        def get_day_name(day_number, is_practical=False):
            days = {
                1: "Domingo",
                2: "Segunda-feira",
                3: "Terça-feira",
                4: "Quarta-feira",
                5: "Quinta-feira",
                6: "Sexta-feira"
            }
            base_name = days.get(day_number, "Dia inválido")
            return f"{base_name} (com prática)" if is_practical else base_name

        # Criação do dicionário de aulas por matéria e dia da semana
        subjects_aulas_por_dia = defaultdict(list)

        for cod_disc, dias in subjects_mode_per_day.items():
            nome_materia = faltas_ch_info.get(cod_disc, {}).get("nome_materia", "Nome desconhecido")
            for dia in range(1, 7):  # De Domingo (1) a Sexta-feira (6)
                aulas_info = dias.get(dia, {"regular": 0, "practical": 0})
                if aulas_info["regular"] > 0:
                    subjects_aulas_por_dia[cod_disc].append({"Dia": get_day_name(dia), "Aulas": aulas_info["regular"]})
                if aulas_info["practical"] > 0:
                    # Adiciona aulas práticas apenas se forem diferentes das regulares ou se não houver aulas regulares
                    if aulas_info["practical"] != aulas_info["regular"] or aulas_info["regular"] == 0:
                        subjects_aulas_por_dia[cod_disc].append({"Dia": get_day_name(dia, True), "Aulas": aulas_info["practical"]})

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
            total_aulas_restantes = calcular_aulas_restantes(subjects_days_dates, cod_disc)

            dias_restantes = calcular_dias_restantes(subjects_days_dates, cod_disc)

            dias_info = []
            for aula in aulas_list:
                dia = aula['Dia']
                num_aulas = aula['Aulas']
                # Mapeia o nome do dia para o número
                dia_num = None
                for num, nome in {
                    1: "Domingo",
                    2: "Segunda-feira",
                    3: "Terça-feira",
                    4: "Quarta-feira",
                    5: "Quinta-feira",
                    6: "Sexta-feira"
                }.items():
                    if nome in dia:  # Usamos 'in' para pegar tanto dias normais quanto com prática
                        dia_num = num
                        break
                dias_restantes_na_semana = dias_restantes.get(dia_num, 0)
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

            resultados.append({
                'nome_materia': nome_materia,
                'ch': ch,
                'faltas': faltas,
                'porcentagem_faltas': porcentagem_faltas,
                'porcentagem_restante': porcentagem_restante,
                'faltas_permitidas_restantes': faltas_permitidas_restantes,
                'total_aulas_restantes': total_aulas_restantes,
                                'total_aulas_restantes': total_aulas_restantes,
                'dias_info': dias_info
            })

        # Ordenar os resultados em ordem decrescente de porcentagem de faltas
        resultados.sort(key=lambda x: x['porcentagem_faltas'], reverse=True)

        logging.debug("Processamento de dados concluído")
        logging.debug(f"Resultados: {resultados}")

        # Armazenar resultados na sessão
        session['resultados'] = resultados

        # Redirecionar para a página de resultados
        return redirect(url_for('resultado'))

    except Exception as e:
        logging.error(f"Erro durante o processamento dos dados: {e}")
        flash("Erro: Ocorreu um problema ao processar os dados. Por favor, tente novamente mais tarde.", "error")
        return redirect(url_for('login'))

    # Este return nunca deve ser alcançado, mas é uma boa prática incluí-lo
    return redirect(url_for('login'))

@app.route('/resultado')
def resultado():
    resultados = session.get('resultados', None)
    if resultados is None:
        flash("Erro: Nenhum dado de faltas encontrado. Por favor, faça login novamente.", "error")
        return redirect(url_for('login'))
    return render_template('resultado.html', resultados=resultados)

@app.route('/simulador')
def simulador():
    resultados = session.get('resultados', None)
    if resultados is None:
        flash("Erro: Nenhum dado de faltas encontrado. Por favor, faça login novamente.", "error")
        return redirect(url_for('login'))
    return render_template('simulador.html', resultados=resultados)

@app.route('/get_disciplinas_por_data', methods=['POST'])
def get_disciplinas_por_data():
    data = request.json['data']
    horario_data = session.get('horario_data')
    
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
    datas_faltas = data['datas_faltas']
    
    resultados = session.get('resultados', None)
    if resultados is None:
        return jsonify({'error': 'Dados não encontrados. Faça login novamente.'}), 400

    horario_data = session.get('horario_data')
    if horario_data is None:
        return jsonify({'error': 'Dados de horário não encontrados'}), 400

    # Contar o número de aulas para cada disciplina nas datas selecionadas
    aulas_por_disciplina = defaultdict(int)
    for data_falta in datas_faltas:
        for aula in horario_data['data']['SHorarioAluno']:
            aula_data = aula.get('DATAINICIAL', '')
            if aula_data:
                if aula_data.split('T')[0] == data_falta['data']:
                    nome = aula.get('NOME')
                    if nome in data_falta['disciplinas']:
                        aulas_por_disciplina[nome] += 1

    simulacao_resultados = []
    for disciplina in resultados:
        disciplina_simulada = disciplina.copy()
        disciplina_simulada['faltas_atuais'] = disciplina['faltas']
        disciplina_simulada['porcentagem_faltas_atual'] = calcular_porcentagem_faltas(disciplina['faltas'], disciplina['ch'])
        
        if disciplina['nome_materia'] in aulas_por_disciplina:
            faltas_adicionais = aulas_por_disciplina[disciplina['nome_materia']]
            disciplina_simulada['faltas'] += faltas_adicionais
            disciplina_simulada['porcentagem_faltas'] = calcular_porcentagem_faltas(disciplina_simulada['faltas'], disciplina_simulada['ch'])
            disciplina_simulada['porcentagem_restante'] = max(25.0 - disciplina_simulada['porcentagem_faltas'], 0.0)
            disciplina_simulada['faltas_permitidas_restantes'] = max(math.floor((disciplina_simulada['porcentagem_restante'] * disciplina_simulada['ch']) / 100), 0)
        else:
            disciplina_simulada['faltas'] = disciplina['faltas']
            disciplina_simulada['porcentagem_faltas'] = disciplina_simulada['porcentagem_faltas_atual']
            disciplina_simulada['porcentagem_restante'] = max(25.0 - disciplina_simulada['porcentagem_faltas'], 0.0)
            disciplina_simulada['faltas_permitidas_restantes'] = max(math.floor((disciplina_simulada['porcentagem_restante'] * disciplina_simulada['ch']) / 100), 0)
        
        disciplina_simulada['total_aulas_restantes'] = calcular_aulas_restantes(horario_data, disciplina['nome_materia'])
        
        # Calcular a porcentagem de faltas permitidas restantes
        if disciplina_simulada['total_aulas_restantes'] > 0:
            porcentagem_faltas_permitidas = (disciplina_simulada['faltas_permitidas_restantes'] / disciplina_simulada['total_aulas_restantes']) * 100
        else:
            porcentagem_faltas_permitidas = 0

        disciplina_simulada['faltas_permitidas_info'] = f"{disciplina_simulada['faltas_permitidas_restantes']} ({porcentagem_faltas_permitidas:.2f}%)"
        
        simulacao_resultados.append(disciplina_simulada)

    return jsonify(simulacao_resultados)

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

def calcular_aulas_restantes(horario_data, nome_materia):
    hoje = datetime.date.today()
    total_restante = 0
    for aula in horario_data['data']['SHorarioAluno']:
        if aula.get('NOME') == nome_materia:
            aula_data = aula.get('DATAINICIAL', '')
            if aula_data:
                data_aula = datetime.datetime.strptime(aula_data.split('T')[0], "%Y-%m-%d").date()
                if data_aula >= hoje:
                    total_restante += 1
    return total_restante

def calcular_dias_restantes(subjects_days_dates, cod_disc):
    hoje = datetime.date.today()
    dias_restantes = defaultdict(int)  # dia_da_semana: quantidade
    dias_datas = subjects_days_dates.get(cod_disc, {})
    for dia_semana, datas in dias_datas.items():
        for data_str in datas.keys():
            try:
                data_aula = datetime.datetime.strptime(data_str, "%Y-%m-%d").date()
            except ValueError:
                continue  # Ignora datas inválidas
            if data_aula >= hoje:
                dias_restantes[dia_semana] += 1
    return dias_restantes  # Retorna um dict com dia_semana: quantidade

@app.route('/logout')
def logout():
    session.clear()
    flash("Você foi deslogado com sucesso.", "info")
    return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(debug=True)

                
