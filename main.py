import os
from dotenv import load_dotenv
from gigachat import GigaChat
import requests
import json


_ = load_dotenv()

GIGACHAT_CREDENTIALS = os.getenv('GIGACHAT_CREDENTIALS')
if not GIGACHAT_CREDENTIALS:
    raise ValueError('Переменная окружения GIGACHAT_CREDENTIALS не установлена')

CERT_PATH = os.getenv('CERT_PATH')
if not CERT_PATH:
    raise ValueError('Переменная окружения CERT_PATH не установлена')

model = GigaChat(
    credentials=GIGACHAT_CREDENTIALS,
    model='GigaChat-2-Max',
    temperature=0.7,
    verify_ssl_certs=True,
    ca_bundle_file=CERT_PATH,
    max_tokens=2000,
    top_p=0.9,
    profanity_check=True,
    timeout=30)


def is_service_avaliable():
    health_url = 'http://127.0.0.1:8000/health'
    try:
        avaliability = json.loads(requests.get(health_url).content)['status']
    except requests.exceptions.ConnectionError:
        return False
    return True if avaliability == 'ok' else False


def create_run():
    url = 'http://127.0.0.1:8000/runs'
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json'
    }
    payload = {
        'team_name': 'Kapuchinator'
    }
    response = requests.post(url, headers=headers, json=payload)
    data = json.loads(response.content)
    return data['id']


def get_case_id(case_number):
    url = 'http://127.0.0.1:8000/cases/'
    cases = json.loads(requests.get(url).content)
    return cases[case_number]['id']


def get_user_id(case_id):
    url = 'http://127.0.0.1:8000/cases/' + case_id
    ticket_id = json.loads(requests.get(url).content)['intake']['ticket_id']
    ticket_url = 'http://127.0.0.1:8000/support/tickets/' + ticket_id
    user_id = json.loads(requests.get(ticket_url).content)['user_id']
    return user_id


def evaluate_run(run_id, case_id, answer : str, evidence: list, actions : list): # 'evidence': [ 'string' ]    я хз это что, наверное список строк
    url = 'http://127.0.0.1:8000/cases/case_01_subscription_activation/evaluate'
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json'
    }
    payload = {
        'run_id': run_id,
        'case_id': case_id,
        'answer': answer,
        'evidence': evidence,
        'actions': actions
    }

    requests.post(url, headers=headers, json=payload)


def get_metrics(run_id):
    url = 'http://127.0.0.1:8000/runs/' + run_id + '/metrics'
    metrics = json.loads(requests.get(url).content)
    return metrics


def get_export(run_id):
    url = 'http://127.0.0.1:8000/runs/' + run_id + '/export'
    export = json.loads(requests.get(url).content)
    return export


if __name__ == '__main__':
    if not is_service_avaliable():
        print('Сервис в данный момент недоступен')
        exit()
    
    run_id = create_run()
    print(run_id)

    case_number = 0
    while case_number < 6:
        case_id = get_case_id(case_number)
        print(case_id)

        user_id = get_user_id(case_id)
        print(user_id)

        answer = 'Зачем ты пишешь в поддержку'
        evidence = 'Неопровержимые доказательства'
        actions = 'Запрещённые политикой действия'


        '''  Часть с ИИ агентом  '''
        

        evaluate_run(run_id, case_id, answer, evidence, actions)
        case_number += 1

    metrics = get_metrics(run_id)
    export = get_export(run_id)
    print(metrics)
    print(export)
