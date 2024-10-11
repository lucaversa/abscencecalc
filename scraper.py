# scraper.py
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import requests

def scrape_portal(username, password):
    # Configurações do Chrome para o Selenium
    options = Options()
    options.add_argument("--headless")  # Executa sem abrir o navegador (modo invisível)
    options.add_argument('--no-sandbox')   
    options.add_argument('--disable-dev-shm-usage')  
    
    # Inicializar o driver do Chrome
    driver = webdriver.Chrome(service=ChromeService(), options=options)
    
    try:
        # Passo 1: Acessar o portal do aluno
        login_url = "https://fundacaoeducacional132827.rm.cloudtotvs.com.br/FrameHTML/web/app/edu/PortalEducacional/login/"
        print(f"Acessando o portal: {login_url}")
        driver.get(login_url)
        
        # Passo 2: Fazer login no portal
        try:
            # Esperar até que os campos de usuário e senha estejam presentes
            username_field = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.ID, "User"))
            )
            password_field = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.ID, "Pass"))
            )
            
            # Preencher os campos de usuário e senha
            print("Preenchendo campos de login.")
            username_field.send_keys(username)
            password_field.send_keys(password)
            
            # Submeter o formulário de login
            print("Submetendo o formulário de login.")
            password_field.send_keys(Keys.RETURN)
        
            # Esperar até que o elemento pós-login apareça
            # Usaremos o seletor CSS para <span class="ico-mural"></span>
            print("Aguardando confirmação de login.")
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "span.ico-mural"))
            )
            print("Login realizado com sucesso.")
        except Exception as e:
            print("Erro durante o login:", e)
            return None, None
        
        # Passo 3: Capturar os cookies após o login
        selenium_cookies = driver.get_cookies()
        print(f"Cookies capturados pelo Selenium: {selenium_cookies}")
        
        # Converter os cookies para o formato de dicionário do requests
        session = requests.Session()
        for cookie in selenium_cookies:
            session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'), path=cookie.get('path'))
        
        # Opcional: Definir headers padrão, como o User-Agent, se necessário
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ' \
                          'AppleWebKit/537.36 (KHTML, like Gecko) ' \
                          'Chrome/112.0.0.0 Safari/537.36'
        })
        
        # Verificar se os cookies foram corretamente transferidos
        print(f"Cookies na sessão do requests: {session.cookies.get_dict()}")
        
        # Passo 4: Fazer requisições com requests usando os cookies capturados
        
        # URL das faltas e cargas horárias
        url1 = "https://fundacaoeducacional132827.rm.cloudtotvs.com.br/FrameHTML/RM/API/TOTVSEducacional/GradeCurricular/EnsinoSuperior"
        print(f"Fazendo requisição para: {url1}")
        response1 = session.get(url1)
        if response1.status_code == 200:
            try:
                data1 = response1.json()
                print("Dados da primeira requisição obtidos com sucesso.")
            except json.JSONDecodeError:
                print("Erro ao decodificar JSON da primeira requisição.")
                data1 = None
        else:
            print(f"Erro na requisição para {url1}: Status {response1.status_code}")
            data1 = None
        
        # URL do horário do aluno
        url2 = "https://fundacaoeducacional132827.rm.cloudtotvs.com.br/FrameHTML/RM/API/TOTVSEducacional/QuadroHorarioAluno"
        print(f"Fazendo requisição para: {url2}")
        response2 = session.get(url2)
        if response2.status_code == 200:
            try:
                data2 = response2.json()
                print("Dados da segunda requisição obtidos com sucesso.")
            except json.JSONDecodeError:
                print("Erro ao decodificar JSON da segunda requisição.")
                data2 = None
        else:
            print(f"Erro na requisição para {url2}: Status {response2.status_code}")
            data2 = None
        
        return data1, data2
    finally:
        # Fechar o navegador
        driver.quit()
        print("Navegador fechado.")