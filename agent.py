import os
import json
import requests
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from langchain.agents import create_agent
from langchain.tools import BaseTool
from langchain_community.utilities.requests import Requests
from langchain_gigachat.chat_models.gigachat import GigaChat
from dotenv import load_dotenv

load_dotenv()

# ================= 1. Конфигурация =================
CERT_PATH = os.getenv('CERT_PATH')
if not CERT_PATH:
    raise ValueError('Переменная окружения CERT_PATH не установлена')


GIGACHAT_CREDENTIALS = os.getenv('GIGACHAT_CREDENTIALS')
if not GIGACHAT_CREDENTIALS:
    raise ValueError('GIGACHAT_CREDENTIALS not set')

# ================= 2. Модель =================
model = GigaChat(
    credentials=GIGACHAT_CREDENTIALS,
    model='GigaChat-2-Pro',
    temperature=0.7,
    verify_ssl_certs=True,
    ca_bundle_file=CERT_PATH,
    max_tokens=2000,
    top_p=0.9,
    profanity_check=True,
    timeout=30)

# ================= 3. Загрузка OpenAPI спецификации =================
spec_response = requests.get("http://127.0.0.1:8000/openapi.json")
spec_response.raise_for_status()
spec = spec_response.json()

# Берём базовый URL (первый сервер из спецификации)
base_url = spec.get('servers', [{'url': 'http://127.0.0.1:8000'}])[0]['url']

# ================= 4. Формируем текстовое описание эндпоинтов =================
with open('openapi_gigachat', 'r', encoding='utf-8') as f:
    endpoints_description = f.read()

# ================= 5. Единый инструмент call_api =================
class CallApiInput(BaseModel):
    method: str = Field(description="HTTP method: GET, POST, PUT, DELETE, PATCH")
    url_path: str = Field(
        description="Путь, где параметры уже подставлены. Например, '/clients/123' вместо '/clients/{id}'."
    )
    body: Dict[str, Any] = Field(
        description="JSON-тело запроса"
    )
    run_id: str = Field(
        description="run_id, который прямым текстом указывается в начале запроса пользователя."
    )
    query_params: Dict[str, Any] = Field(
        description="Query-параметры в виде словаря. Например: {'q': 'подписка', 'limit': 10}"
    )
    

class CallApiTool(BaseTool):
    name: str = "call_api"
    description: str = "Вызвать любой эндпоинт API из спецификации."
    args_schema: type[BaseModel] = CallApiInput
    requests_wrapper: Requests = Requests(headers={"Content-Type": "application/json"})
    base_url: str = base_url

    def _run(self, method: str, url_path: str,
             run_id: str,
             body: Optional[Dict] = None,
             query_params: Optional[Dict] = None) -> str:
        full_url = f"{self.base_url}{url_path}"
        method = method.upper()
        body['X-Run-Id'] = run_id
        
        print("АГЕНТ ВЫЗЫВАЕТ МЕТОД", method, "ПО URL", full_url)
        print("QUERY_PARAMS:", query_params)
        print("BODY:", body)

        try:
            if method == "GET":
                resp = self.requests_wrapper.get(full_url, params=query_params, json=body)
            elif method == "POST":
                resp = self.requests_wrapper.post(full_url, params=query_params, json=body)
            else:
                return f"Неподдерживаемый метод: {method}"
            try:
                return json.dumps(resp.json(), indent=2, ensure_ascii=False)
            except:
                return resp.text
        except Exception as e:
            return f"Ошибка вызова API: {str(e)}"

tools = [CallApiTool()]

# ================= 6. Системный промпт =================
system_prompt = f"""
Ты — ассистент, который умеет вызывать API. Доступны следующие эндпоинты:

{endpoints_description}

Для вызова API используй инструмент `call_api`. ВАЖНО:
- Параметр `url_path` должен содержать уже подставленные значения. Например, вместо `/clients/{{id}}` передавай `/clients/123`.
- Если пользователь спрашивает, какие API есть, перечисли их, используя описание выше.
- Старайся не пользоваться Legacy и Beta эндпоинтами, если этого можно избежать

Никогда не выдумывай эндпоинты, которых нет в списке.

Анализируй вызываемые функции API, чтобы понять, решена ли проблема пользователя.
ТОЛЬКО если проблема решена, то отправь сообщение следующего вида:
end_of_case: Ответ
Ответ должен представлять из себя описание проделанных действий и отчёт о том, что проблема выполнена (Пример: Здравствуйте, проблема с подпиской возникла на нашей стороне, был оформлен возврат средств на ваш счёт)


"""

# ================= 7. Агент =================
agent = create_agent(
    model=model,
    tools=tools,
    system_prompt=system_prompt
)

# ================= 8. Запуск (пример) =================
def exec_agent(run_id, user_question, user_id):
    # user_question = "Почему не прошла оплата 18500 в магазине?"
    question = 'run_id=' + run_id
    question += '\nПользователь с user_id=' + user_id + ' обратился в поддержку со следующим вопросом: \n' + user_question + '\n Предположи, какую функцию из API нужно вызвать, чтобы найти причину ошибки сервиса'
    result = agent.invoke({
        "messages": [{"role": "user", "content": question}]
    })
    temp_ans = result["messages"][-1].content
    print("\n=== ОТВЕТ АГЕНТА ===\n")
    print(temp_ans)

    return temp_ans.split('end_of_case: ')[-1], ['Неопровержимые доказательства'], ['Запрещённые политикой действия']