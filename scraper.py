import json
import logging
from collections import defaultdict

import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Configurações de logging
logging.basicConfig(level=logging.DEBUG)

# Constantes
LOGIN_URL = "https://fundacaoeducacional132827.rm.cloudtotvs.com.br/FrameHTML/web/app/edu/PortalEducacional/login/"
FALTAS_URL = "https://fundacaoeducacional132827.rm.cloudtotvs.com.br/FrameHTML/RM/API/TOTVSEducacional/GradeCurricular/EnsinoSuperior"
HORARIO_URL = "https://fundacaoeducacional132827.rm.cloudtotvs.com.br/FrameHTML/RM/API/TOTVSEducacional/QuadroHorarioAluno"
AVALIACAO_ALUNO_PERIODO_LETIVO_URL = "https://fundacaoeducacional132827.rm.cloudtotvs.com.br/FrameHTML/RM/API/TOTVSEducacional/AvaliacaoAlunoPeriodoLetivo"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/112.0.0.0 Safari/537.36"
)

def scrape_portal(username, password, session_id, update_progress_callback):
    """
    Realiza o scraping do portal educacional utilizando Selenium e Requests.

    Args:
        username (str): Nome de usuário para login.
        password (str): Senha para login.
        session_id (str): ID da sessão para rastrear o progresso.
        update_progress_callback (function): Função de callback para atualizar o progresso.

    Returns:
        tuple: Dados de faltas, horários e avaliações ou (None, ...) em caso de erro.
    """

    def scraper_progress(description, percentage):
        """Atualiza o progresso do scraping."""
        update_progress_callback(session_id, "SCRAPING", description, percentage)

    # Configurações do Chrome para o Selenium
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Executa sem abrir o navegador (modo invisível)
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"user-agent={USER_AGENT}")

    # Inicializar o driver do Chrome
    service = ChromeService()  # Pode especificar o caminho do chromedriver se necessário
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        # Passo 1: Acessar o portal do aluno
        scraper_progress("Acessando o EduConnect", 5)
        driver.get(LOGIN_URL)

        # Passo 2: Fazer login no portal
        try:
            scraper_progress("Localizando campos de login", 10)
            wait = WebDriverWait(driver, 20)

            # Esperar até que os campos de usuário e senha estejam clicáveis
            username_field = wait.until(EC.element_to_be_clickable((By.ID, "User")))
            password_field = wait.until(EC.element_to_be_clickable((By.ID, "Pass")))

            # Preencher os campos de usuário e senha
            scraper_progress("Preenchendo campos de login", 20)
            username_field.send_keys(username)
            password_field.send_keys(password)

            # Submeter o formulário de login
            scraper_progress("Submetendo o formulário de login", 30)
            password_field.send_keys(Keys.RETURN)

            # Esperar até que o elemento pós-login apareça
            scraper_progress("Aguardando confirmação de login", 40)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "span.ico-mural")))
            scraper_progress("Login realizado com sucesso", 50)
        except Exception as e:
            logging.exception("Erro durante o login:")
            scraper_progress(f"Erro durante o login: {e}", 100)
            return None, None, None

        # Passo 3: Capturar os cookies após o login
        scraper_progress("Capturando cookies após o login", 55)
        selenium_cookies = driver.get_cookies()
        logging.debug(f"Cookies capturados pelo Selenium: {selenium_cookies}")

        # Converter os cookies para o formato de dicionário do requests
        session_requests = requests.Session()
        for cookie in selenium_cookies:
            session_requests.cookies.set(
                name=cookie['name'],
                value=cookie['value'],
                domain=cookie.get('domain'),
                path=cookie.get('path')
            )

        # Definir headers padrão, como o User-Agent
        session_requests.headers.update({'User-Agent': USER_AGENT})

        # Verificar se os cookies foram corretamente transferidos
        logging.debug(f"Cookies na sessão do requests: {session_requests.cookies.get_dict()}")

        # Passo 4: Fazer requisições com requests usando os cookies capturados
        scraper_progress("Fazendo requisições para obter dados", 60)

        # Requisição para dados de faltas
        logging.debug(f"Fazendo requisição para: {FALTAS_URL}")
        response_faltas = session_requests.get(FALTAS_URL)
        if response_faltas.status_code == 200:
            try:
                data_faltas = response_faltas.json()
                logging.debug("Dados de faltas obtidos com sucesso.")
                scraper_progress("Dados de faltas obtidos", 65)
            except json.JSONDecodeError:
                logging.error("Erro ao decodificar JSON dos dados de faltas.")
                data_faltas = None
                scraper_progress("Erro ao decodificar dados de faltas", 100)
        else:
            logging.error(f"Erro na requisição para {FALTAS_URL}: Status {response_faltas.status_code}")
            data_faltas = None
            scraper_progress(f"Erro na requisição de faltas: Status {response_faltas.status_code}", 100)

        # Requisição para dados de horários
        logging.debug(f"Fazendo requisição para: {HORARIO_URL}")
        response_horario = session_requests.get(HORARIO_URL)
        if response_horario.status_code == 200:
            try:
                data_horario = response_horario.json()
                logging.debug("Dados de horário obtidos com sucesso.")
                scraper_progress("Dados de horário obtidos", 70)
            except json.JSONDecodeError:
                logging.error("Erro ao decodificar JSON dos dados de horário.")
                data_horario = None
                scraper_progress("Erro ao decodificar dados de horário", 100)
        else:
            logging.error(f"Erro na requisição para {HORARIO_URL}: Status {response_horario.status_code}")
            data_horario = None
            scraper_progress(f"Erro na requisição de horário: Status {response_horario.status_code}", 100)

        # Requisição para dados de avaliações (AvaliacaoAlunoPeriodoLetivo)
        logging.debug(f"Fazendo requisição para: {AVALIACAO_ALUNO_PERIODO_LETIVO_URL}")
        response_avaliacao = session_requests.get(AVALIACAO_ALUNO_PERIODO_LETIVO_URL)
        if response_avaliacao.status_code == 200:
            try:
                data_avaliacao = response_avaliacao.json()
                logging.debug("Dados de avaliações obtidos com sucesso.")
                scraper_progress("Dados de avaliações obtidos", 80)
            except json.JSONDecodeError:
                logging.error("Erro ao decodificar JSON dos dados de avaliações.")
                data_avaliacao = None
                scraper_progress("Erro ao decodificar dados de avaliações", 100)
        else:
            logging.error(f"Erro na requisição para {AVALIACAO_ALUNO_PERIODO_LETIVO_URL}: Status {response_avaliacao.status_code}")
            data_avaliacao = None
            scraper_progress(f"Erro na requisição de avaliações: Status {response_avaliacao.status_code}", 100)

        scraper_progress("Dados obtidos com sucesso", 100)
        return data_faltas, data_horario, data_avaliacao

    finally:
        # Fechar o navegador
        driver.quit()
        logging.debug("Navegador fechado.")
