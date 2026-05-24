import requests
import json
from agent import *

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


def get_user_question(case_id):
    url = 'http://127.0.0.1:8000/cases/' + case_id
    user_question = json.loads(requests.get(url).content)['customer_message']
    return user_question


def evaluate_run(run_id, case_id, answer : str, evidence: list, actions : list):
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

    case_number = 0
    while case_number < 2:
        run_id = create_run()
        print('Run_id:', run_id)

        case_id = get_case_id(case_number)
        print('Case_id:', case_id)

        user_id = get_user_id(case_id)
        print('User_id:', user_id)

        user_question = get_user_question(case_id)

        answer, evidence, actions = exec_agent(run_id, user_question, user_id)
        

        evaluate_run(run_id, case_id, answer, evidence, actions)
        case_number += 1

        print('\n=== ОТВЕТ ПОЛЬЗОВАТЕЛЮ ===\n')
        print(answer)

        metrics = get_metrics(run_id)
        export = get_export(run_id)
        print('\n=== МЕТРИКИ ===\n')
        print(metrics)
        print(export)
    
