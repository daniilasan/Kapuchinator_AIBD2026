import os
from dotenv import load_dotenv
from gigachat import GigaChat

_ = load_dotenv()

GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS")
if not GIGACHAT_CREDENTIALS:
    raise ValueError("Переменная окружения GIGACHAT_CREDENTIALS не установлена")

CERT_PATH = os.getenv("SERTIFICATE_PATH")
if not CERT_PATH:
    raise ValueError("Переменная окружения CERT_PATH не установлена")

model = GigaChat(
    credentials=GIGACHAT_CREDENTIALS,
    model="GigaChat-2-Max",
    temperature=0.7,
    verify_ssl_certs=True,
    ca_bundle_file=CERT_PATH,
    max_tokens=2000,
    top_p=0.9,
    profanity_check=True,
    timeout=30)

# для теста
prompt = """
   Оформи ответ, используя Markdown:
   - Заголовки (###)
   - Маркированные списки
   - Жирный текст для названий
   """

response = model.chat(prompt)
content = response.choices[0].message.content
print(content)
