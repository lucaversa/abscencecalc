# request_ia.py

import os
import google.generativeai as genai
import json
import markdown  # Importar a biblioteca markdown

# Configurar a API Key de forma segura
GENAI_API_KEY = os.environ.get("GENAI_API_KEY")  # Defina essa variável no seu ambiente

if not GENAI_API_KEY:
    raise ValueError("A variável de ambiente 'GENAI_API_KEY' não está definida.")

genai.configure(api_key=GENAI_API_KEY)

# Configuração do modelo
generation_config = {
    "temperature": 0.7,  # Ajuste conforme necessário
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 1500,  # Ajuste conforme a necessidade
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
            "A análise deve ser adequada para uma interface de aplicativo, e incluir os seguintes elementos:\n\n"
            "1. Visão geral do desempenho, incluindo a média global.\n"
            "2. Evolução do desempenho entre os períodos, considerando métricas relevantes.\n"
            "3. Análise dos pontos fortes com emojis (sempre enviar as notas e lembre-se que as notas são números inteiros e não porcentagem).\n"
            "4. Áreas para melhoria com recomendações práticas e emojis (sempre enviar as notas e lembre-se que as notas são números inteiros e não porcentagem).\n"
            "5. Avaliação da consistência das notas.\n"
            "6. Diferenciação entre habilidades práticas e teóricas.\n"
            "7. Sugestões práticas para melhorias e uso de emojis para manter o texto leve.\n"
            "8. Destacar os pontos fortes e positivos a serem mantidos.\n\n"
            "O texto deve ser envolvente, conciso, e utilizar uma linguagem que motive o usuário, incluindo o uso de emojis e frases curtas.\n\n"
            "Utilize a referência: Média do Período ou Global abaixo de 75% não é bom (não cite essa frase diretamente).\n\n"
            "Utilize tópicos mas não exagere para não poluir a visualização.\n\n"
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
        # Tratar possíveis erros
        return f"<p>Ocorreu um erro ao processar a análise: {str(e)}</p>"