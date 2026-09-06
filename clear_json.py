#!/usr/bin/env python3
import json
import re


# Check whether a string is a 32-character hash (e.g. MD5)
def is_hash_id(task_id: str) -> bool:
    return re.fullmatch(r'[a-f0-9]{32}', task_id) is not None


def clean_all_tasks(tasks):
    unique_tasks = {}
    for task in tasks:
        task_id = task.get("id", "")
        if task_id not in unique_tasks:
            unique_tasks[task_id] = task
    # Drop entries whose id is a hash
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

    # Load the current state
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Get the initial sizes
    all_tasks_initial = data.get("all_tasks", [])
    sent_tasks_initial = data.get("sent_tasks", [])

    print("Initial task count (all_tasks):", len(all_tasks_initial))
    print("Initial sent id count (sent_tasks):", len(sent_tasks_initial))

    # Clean up the task list and the sent id list
    cleaned_all_tasks = clean_all_tasks(all_tasks_initial)
    cleaned_sent_tasks = clean_sent_tasks(sent_tasks_initial)

    data["all_tasks"] = cleaned_all_tasks
    data["sent_tasks"] = cleaned_sent_tasks

    print("Task count after cleanup (all_tasks):", len(cleaned_all_tasks))
    print("Sent id count after cleanup (sent_tasks):", len(cleaned_sent_tasks))

    # Write the result back out
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Cleaned state written to {output_file}")


if __name__ == '__main__':
    main()
