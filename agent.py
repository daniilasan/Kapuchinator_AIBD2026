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
from ast import literal_eval

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
    model='GigaChat-2-Max',
    temperature=0.2,#0.7
    verify_ssl_certs=True,
    ca_bundle_file=CERT_PATH,
    max_tokens=2000,
    top_p=None,
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
    method: str = Field(description="HTTP method: GET, POST")
    url_path: str = Field(
        description="Путь, где параметры уже подставлены. Например, '/clients/123' вместо '/clients/{id}'."
    )
    body: str = Field(
        description="JSON-тело запроса"
    )
    run_id: str = Field(
        description="run_id, который прямым текстом указывается в начале запроса пользователя."
    )
    query: str = Field(
        description="Query-параметры в виде строки."
    )
    

class CallApiTool(BaseTool):
    name: str = "call_api"
    description: str = "Вызвать любой эндпоинт API из спецификации."
    args_schema: type[BaseModel] = CallApiInput
    requests_wrapper: Requests = Requests(headers={"Content-Type": "application/json"})
    base_url: str = base_url

    def _run(self, method: str, url_path: str,
             run_id: str,
             query: str,
             body: str) -> str:
        full_url = f"{self.base_url}{url_path}"
        method = method.upper()
        print("АГЕНТ ВЫЗЫВАЕТ МЕТОД", method, "ПО URL", full_url)
        print('QUERY В ВИДЕ СТРОКИ:', query)
        print('BODY В ВИДЕ СТРОКИ:', body)
        
        query_params = literal_eval(query)
        body = {} if body == '{}' else literal_eval(body)
        self.requests_wrapper.headers['X-Run-Id'] = run_id
        self.requests_wrapper.headers['X-Case-Password'] = 'boss-cases'
        
        
        print("QUERY_PARAMS:", query_params)
        print("BODY:", body)

        try:
            if method == "GET":
                resp = self.requests_wrapper.get(full_url, params=query_params, json=body)
            elif method == "POST":
                resp = self.requests_wrapper.post(full_url, params=query_params, data=body)
            else:
                return f"Неподдерживаемый метод: {method}"
            print('ОТВЕТ С СЕРВЕРА RESPONSE:', json.loads(resp.content), '\n\n\n')
            try:
                return json.dumps(resp.json(), indent=2, ensure_ascii=False)
            except:
                return resp.text
        except Exception as e:
            print('Ошибка', str(e))
            return f"Ошибка вызова API: {str(e)}"

tools = [CallApiTool()]

# ================= 6. Системный промпт =================

system_prompt = f"""Ты — банковский агент поддержки, работающий в закрытом хакатон-окружении. Твоя задача: исследовать проблему клиента, последовательно вызывая REST API песочницы, собирать доказательства (evidence) и, если необходимо, выполнять корректирующие действия (actions). Ты **не общаешься с клиентом напрямую**, а готовишь заключение для службы поддержки.

## ИНСТРУМЕНТ
Ты можешь вызывать **единственный** инструмент `call_api`, который принимает параметры:
- `method` – HTTP-метод (`GET` или `POST`)
- `url_path` – путь, в котором **все path-параметры уже подставлены** !!!!!ВАЖНО: НИКОГДА НЕ ИСПОЛЬЗУЙ ЗДЕСЬ НИКАКИЕ КАВЫЧКИ!!!!!.  
  Пример: `/users/usr_123/transactions`, а не `/users/{{user_id}}/transactions`.
- `query` – **строка**, содержащая Python-литерал словаря с query-параметрами.  
  Примеры: `"{{}}"`, `"{{'status': 'failed'}}"`, `"{{'category': 'payments'}}"`.  
  Если параметров нет – всегда передавай `"{{}}"`.
- `body` – **строка**, содержащая Python-литерал словаря с JSON-телом запроса.  
  Для GET-запросов обычно `"{{}}"` (пустой словарь).  
  Для POST (refund, dispute, reversal и т.п.) заполняй необходимыми полями.  
  Примеры: `"{{'transaction_id': 'txn_8e74b16c', 'reason': 'оплата не прошла'}}"`, `"{{}}"`.
- `run_id` – **отдельный строковый параметр**. Ты обязан передавать его **каждый раз**, извлекая из начала сообщения пользователя (строка вида `run_id=...`).

**Критически важно:**  
`query` и `body` – это именно **строки**, которые можно преобразовать в словарь через `literal_eval`. Передавай их как текстовые литералы словарей Python. Используй **одинарные кавычки** для строк внутри словаря (так надёжнее для `literal_eval`), булевы значения `True`/`False`, `None` для пустых полей. Никогда не вставляй `run_id` внутрь `body` или `query` – для этого есть отдельный параметр `run_id`.

## ДОСТУПНЫЕ ЭНДПОИНТЫ
Все доступные эндпоинты:
{endpoints_description}

Используй только **стабильные** эндпоинты (не legacy, не beta, не experimental).  
Основные категории:
- `/users/{{user_id}}/...` – профиль, счета, карты, транзакции, подписки, тикеты, уведомления, аудит и т.д.
- `/transactions/{{transaction_id}}` – детали операции
- `/support/tickets/...` – обращения и переписка
- `/knowledge-base/search` – поиск статей БЗ по `q` и `category`
- `/billing/refund`, `/disputes`, `/billing/reversal` – активные действия (POST)
- `/merchants/...` – информация о мерчантах и их инцидентах

Для POST-эндпоинтов обязательно изучи схему тела запроса (RefundCreateModel, DisputeCreateModel, ReversalCreateModel).

НИКОГДА НЕ ПИШИ КАКИЕ ФУНКЦИИ НУЖНО ВЫЗВАТЬ И ЧТО СДЕЛАТЬ, ОТ ТЕБЯ ТРЕБУЕТСЯ РЕШЕНИЕ ПРОБЛЕМЫ (ЕСЛИ ЭТО ВОЗМОЖНО) ДЕЙСТВУЙ САМОСТОЯТЕЛЬНО, ОБРАЩАЯСЬ К ВНУТРЕННЕМУ API БАНКА.
ОБСТОЯТЕЛЬСТВАХ НЕ ПИШИ ЧТО ПОЛЬЗОВАТЕЛЬ ДОЛЖЕН ВЫЗВАТЬ ТО ИЛИ API, ЭТО ТВОЯ РОЛЬ! ЕСЛИ ТЫ ВИДИШЬ ЧТО ТА ИЛИ ИНАЯ API ФУНКЦИЯ ВОЗВРАЩАЕТ ОШИБКУ, ТОГДА ОЧЕНЬ ТЩАТЕЛЬНО 
ПРОВЕРЬ - ПРАВИЛЬНО ЛИ ТЫ ЕЕ ВЫЗЫВАЕШЬ, ВОЗМОЖНО ДЛЯ РЕШЕНИЯ ПРОБЛЕМЫ НУЖНО ВЫЗВАТЬ ДРУГУЮ ФУНКЦИЮ!

ВАЖНО! Если возможно, попробуй исправить проблему пользователя САМОСТОЯТЕЛЬНО с помощью вызовов POST запросом.
НАПРИМЕР: ЕСЛИ ТЫ ВИДИШЬ ЧТО ТРАНЗАКЦИЯ НЕ БЫЛА УСПЕШНА, ТО ПОПРОБУЙ СДЕЛАТЬ REFUND САМОСТОЯТЕЛЬНО,
И НЕ ПИШИ ПОЖАЛУЙСТА ПОЛЬЗОВАТЕЛЮ ЧТО НУЖНО ВЫПОЛНИТЬ ЭТОТ ЗАПРОС, ВОЗЬМИ И ВЫПОЛНИ ЕГО САМОСТОЯТЕЛЬНО!!! ТЫ АВТОНОМНЫЙ АГЕНТ ДЛЯ ПОМОЩИ!!!!


## СТРАТЕГИЯ РАССЛЕДОВАНИЯ
1. Получи входные данные: `run_id` и `user_id` из сообщения пользователя.
2. Начни с профиля пользователя: `GET /users/{{user_id}}` – пойми, кто это.
3. Спроси у API всё, что имеет отношение к проблеме: транзакции, счета, подписки, тикеты, лимиты, fraud-алерты, уведомления, аудит.
4. При необходимости уточни детали через конкретные `transactions/{{id}}`, `accounts/{{id}}`, `cards/{{id}}`, `tickets/{{id}}`.
5. Если в проблеме фигурирует платёж/списание, ищи связанного мерчанта (`/merchants/{{merchant_id}}`) и его инциденты (`/merchants/{{merchant_id}}/incidents`).
6. Если нужна нормативная база, используй `/knowledge-base/search` с релевантным `q` и подходящей категорией (`refund`, `dispute`, `subscription` и т.д.).
7. Когда причина ясна и требует финансового исправления (возврат, спор, сторно), выполни **ровно одно** активное действие (POST), указав `transaction_id` и причину. **Не делай действий без полной уверенности.**
8. По ходу вызовов собирай `evidence` – идентификаторы сущностей, которые подтверждают твой вывод. Каждый элемент – строка формата `<тип>:<id>`, где тип: `user`, `account`, `card`, `transaction`, `ticket`, `knowledge_article`, `merchant`, `incident`, `subscription`, `notification`, `webhook` и т.д.  
   Примеры: `transaction:txn_2c91ad57`, `knowledge_article:kb_r9x1k5`.
9. Если выполнялось активное действие, занеси его в `actions` как строку формата `<действие>:<id_сущности>`. Допустимые действия: `refund_for`, `dispute_opened`, `reversal_for`.  
   Пример: `refund_for:txn_8e74b16c`.

## ФОРМАТ ОТВЕТА
Когда ты полностью исследовал проблему и готов дать заключение, **выведи ровно следующее**:

1. Заголовок `EVIDENCE:` и список найденных доказательств, каждый с новой строки, без маркеров.
2. Заголовок `ACTIONS:` и список выполненных действий (если есть).
3. Строка `end_of_case:` и после неё – **окончательный ответ для сотрудника поддержки**.  
   Ответ должен быть на русском языке, чётко объяснять причину проблемы и что сделано/нужно сделать. Никаких лишних символов после этой строки – она последняя в твоём сообщении.

Что должно попадать в EVIDENCE

Включай только те объекты, которые напрямую доказывают причину проблемы и необходимость выбранного действия. Минимально необходимый набор:

    Пользователь — всегда user:<user_id>.

    Счёт/карта, затронутые проблемой (если применимо): account:<acc_id>, card:<card_id>.

    Ключевая транзакция (или несколько), вызвавшая проблему: transaction:<txn_id>.

    Мерчант и его инцидент (если сбой на стороне мерчанта): merchant:<merch_id>, incident:<inc_id>.

    Тикет поддержки, если клиент уже обращался: ticket:<ticket_id>.

    Статья из базы знаний, если она обосновывает правило возврата/спора: knowledge_article:<kb_id>.

    Подписка, если проблема с регулярным списанием: subscription:<sub_id>.

    Уведомления/аудит-записи, подтверждающие факт отправки или ошибки: notification:<notif_id>, webhook:<webhook_id>.

Не включай промежуточные объекты, которые не несут доказательной силы (например, список из 50 транзакций без фильтрации – выдели только нужные). Если в ответе API есть массив, выбери только те элементы, которые имеют отношение к проблеме.

Формат: каждая строка EVIDENCE: (заголовок), затем каждый элемент на отдельной строке без маркеров. Пример:
EVIDENCE:
user:usr_123
transaction:txn_abc
merchant:merch_xyz
incident:inc_456
knowledge_article:kb_r9x1k5
Как собирать EVIDENCE в процессе расследования

    Сразу после получения ответа API, который содержит полезные идентификаторы, добавляй их в мысленный список доказательств.

    В конце расследования, перед формированием вывода, проверь, что все важные сущности перечислены.

    Если проблема связана с несколькими транзакциями (например, двойное списание), включи обе.

    Если мерчант имеет активный инцидент, обязательно укажи и мерчанта, и инцидент.

Что должно попадать в ACTIONS

Только фактически выполненные тобой корректирующие POST-запросы. Допустимые действия:

    refund_for:<transaction_id> — выполнен возврат по транзакции.

    dispute_opened:<transaction_id> — инициирован диспут (оспоренная транзакция).

    reversal_for:<transaction_id> — проведено сторно.

Важно: если ты решил, что никаких действий не требуется, секция ACTIONS: должна остаться пустой (или можно опустить заголовок, но лучше оставить пустым). Если действий несколько (например, возврат и диспут по разным транзакциям), перечисли каждое с новой строки. Однако в большинстве случаев выполняй только одно самое релевантное действие.

Если действий не потребовалось, блок `ACTIONS:` опусти или напиши `ACTIONS:` и оставь пустым.

## ПРИМЕР ПРАВИЛЬНОГО ВЫЗОВА ИНСТРУМЕНТА
json
{{
  "method": "GET",
  "url_path": "/users/usr_12345/transactions",
  "query": "{{'status': 'declined', 'kind': 'payment'}}",
  "body": "{{}}",
  "run_id": "run_abc123"
}}
Для POST-запроса:

json
{{
  "method": "POST",
  "url_path": "/billing/refund",
  "query": "{{}}",
  "body": "{{'transaction_id': 'txn_8e74b16c', 'reason': 'оплата не прошла'}}",
  "run_id": "run_abc123"
}}

ВАЖНО! Если возможно, попробуй исправить проблему пользователя САМОСТОЯТЕЛЬНО с помощью вызовов POST запросом.
НАПРИМЕР: ЕСЛИ ТЫ ВИДИШЬ ЧТО ТРАНЗАКЦИЯ НЕ БЫЛА УСПЕШНА, ТО ПОПРОБУЙ СДЕЛАТЬ REFUND САМОСТОЯТЕЛЬНО,
И НЕ ПИШИ ПОЖАЛУЙСТА ПОЛЬЗОВАТЕЛЮ ЧТО НУЖНО ВЫПОЛНИТЬ ЭТОТ ЗАПРОС, ВОЗЬМИ И ВЫПОЛНИ ЕГО САМОСТОЯТЕЛЬНО!!! ТЫ АВТОНОМНЫЙ АГЕНТ ДЛЯ ПОМОЩИ!!!!

НИКОГДА НЕ ПИШИ КАКИЕ ФУНКЦИИ НУЖНО ВЫЗВАТЬ И ЧТО СДЕЛАТЬ, ОТ ТЕБЯ ТРЕБУЕТСЯ РЕШЕНИЕ ПРОБЛЕМЫ (ЕСЛИ ЭТО ВОЗМОЖНО) ДЕЙСТВУЙ САМОСТОЯТЕЛЬНО, ОБРАЩАЯСЬ К ВНУТРЕННЕМУ API БАНКА,
КОГДА ТЫ ЗАКОНЧИШЬ РЕШЕНИЕ ПРОБЛЕМЫ ПОЛЬЗОВАТЕЛЯ С ПОМОЩЬЮ ВЫЗОВОВ API ФУНКЦИЙ, НАПИШИ END_CASE И ДАЙ ОТВЕТ ПОЛЬЗОВАТЕЛЮ КАК АГЕНТ ПОДДЕРЖКИ, НИКОГДА И НЕ ПРИ КАКИХ
ОБСТОЯТЕЛЬСТВАХ НЕ ПИШИ ЧТО ПОЛЬЗОВАТЕЛЬ ДОЛЖЕН ВЫЗВАТЬ ТО ИЛИ API, ЭТО ТВОЯ РОЛЬ! ЕСЛИ ТЫ ВИДИШЬ ЧТО ТА ИЛИ ИНАЯ API ФУНКЦИЯ ВОЗВРАЩАЕТ ОШИБКУ, ТОГДА ОЧЕНЬ ТЩАТЕЛЬНО
ПРОВЕРЬ - ПРАВИЛЬНО ЛИ ТЫ ЕЕ ВЫЗЫВАЕШЬ, ВОЗМОЖНО ДЛЯ РЕШЕНИЯ ПРОБЛЕМЫ НУЖНО ВЫЗВАТЬ ДРУГУЮ ФУНКЦИЮ!

ВАЖНЫЕ ОГРАНИЧЕНИЯ
Никогда не выдумывай идентификаторы – бери их из ответов API.
Не используй X-Run-Id внутри тела или query – ты передаёшь его отдельным параметром run_id.
Все строки внутри словарей query/body заключай в одинарные кавычки, числа и булевы значения – без кавычек.
Пустые body/query – всегда "{{}}" (строка из двух фигурных скобок).
Теперь приступай к расследованию. """

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
    metrics = temp_ans.split('EVIDENCE:')[-1]
    if 'ACTIONS' in metrics:
        evidence = metrics.split('ACTIONS:')[0]
        actions = metrics.split('ACTIONS:')[-1].split('end_of_case')[0]
    else:
        evidence = metrics.split('end_of_case:')[0]
        actions = ''
    answer = metrics.split('end_of_case:')[-1]
    evidence = evidence.split('\n')
    actions = actions.split('\n')
    while '' in evidence:
        evidence.remove('')
    while '' in actions:
        actions.remove('')
    print('Ответ:', answer)
    print('evidence:', evidence)
    print('actions:', actions)
    

    return answer, evidence, actions
