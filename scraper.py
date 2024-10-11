# scraper.py
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def scrape_portal(username, password):
    logger.info(f"Current PATH: {os.environ['PATH']}")
    
    chrome_path = "/opt/render/project/.render/chrome/opt/google/chrome/chrome"
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.binary_location = chrome_path

    logger.info(f"Chrome binary location: {chrome_options.binary_location}")
    
    service = Service(chrome_path)
    
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        # Passo 1: Acessar o portal do aluno
        driver.get("https://fundacaoeducacional132827.rm.cloudtotvs.com.br/FrameHTML/web/app/edu/PortalEducacional/login/")
        
        # Passo 2: Fazer login no portal
        try:
            # Esperar até que os campos de usuário e senha estejam presentes
            username_field = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "User"))
            )
            password_field = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "Pass"))
            )
            
            # Preencher os campos de usuário e senha
            username_field.send_keys(username)
            password_field.send_keys(password)
            
            # Submeter o formulário de login
            password_field.send_keys(Keys.RETURN)
        
            # Esperar alguns segundos para garantir que o login seja concluído
            time.sleep(5)
        except Exception as e:
            print("Erro durante o login:", e)
            return None, None
        
        # Passo 3: Acessar as URLs que contêm os dados JSON
        # URL das faltas e cargas horárias
        driver.get("https://fundacaoeducacional132827.rm.cloudtotvs.com.br/FrameHTML/RM/API/TOTVSEducacional/GradeCurricular/EnsinoSuperior")
        time.sleep(5)
        data1_json = driver.find_element(By.TAG_NAME, "body").text
        data1 = json.loads(data1_json)
        
        # URL do horário do aluno
        driver.get("https://fundacaoeducacional132827.rm.cloudtotvs.com.br/FrameHTML/RM/API/TOTVSEducacional/QuadroHorarioAluno")
        time.sleep(5)
        data2_json = driver.find_element(By.TAG_NAME, "body").text
        data2 = json.loads(data2_json)
        
        return data1, data2
    finally:
        # Fechar o navegador
        driver.quit()
