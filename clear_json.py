#!/usr/bin/env python3
import json
import re


# Функция для проверки, является ли строка 32-символьным хешем (например, MD5)
def is_hash_id(task_id: str) -> bool:
    return re.fullmatch(r'[a-f0-9]{32}', task_id) is not None


def clean_all_tasks(tasks):
    unique_tasks = {}
    for task in tasks:
        task_id = task.get("id", "")
        if task_id not in unique_tasks:
            unique_tasks[task_id] = task
    # Фильтруем записи, исключая те, у которых id является хешем
    filtered = [task for task in unique_tasks.values() if not is_hash_id(task.get("id", ""))]
    return filtered


def clean_sent_tasks(sent_tasks):
    cleaned = []
    seen = set()
    for task_id in sent_tasks:
        if task_id not in seen:
            seen.add(task_id)
            if not is_hash_id(task_id):
                cleaned.append(task_id)
    return cleaned


def main():
    input_file = 'state.json'
    output_file = 'state.json'

    # Загрузка исходного состояния
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Получаем начальные размеры компонентов
    all_tasks_initial = data.get("all_tasks", [])
    sent_tasks_initial = data.get("sent_tasks", [])

    print("Начальное количество задач (all_tasks):", len(all_tasks_initial))
    print("Начальное количество отправленных id (sent_tasks):", len(sent_tasks_initial))

    # Очищаем список задач и отправленных id
    cleaned_all_tasks = clean_all_tasks(all_tasks_initial)
    cleaned_sent_tasks = clean_sent_tasks(sent_tasks_initial)

    data["all_tasks"] = cleaned_all_tasks
    data["sent_tasks"] = cleaned_sent_tasks

    print("Количество задач после очистки (all_tasks):", len(cleaned_all_tasks))
    print("Количество отправленных id после очистки (sent_tasks):", len(cleaned_sent_tasks))

    # Записываем результат в новый файл
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Очищенное состояние записано в файл {output_file}")


if __name__ == '__main__':
    main()
