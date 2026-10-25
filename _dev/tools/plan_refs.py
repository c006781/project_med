"""Проверка ссылок плана (_dev/КАРТА.md) — только чтение.

Ищет висящие ссылки (Ф, ОСТ п., ТД-, И-, Д, К) и открытые пункты ОСТАЛОСЬ/ТЕХДОЛГ/ИДЕИ,
которые план не упоминает. Запуск из корня:
    .venv310/Scripts/python.exe -I -X utf8 _dev/tools/plan_refs.py
"""
import re

KARTA = open('_dev/КАРТА.md', encoding='utf-8').read()
OST = open('_dev/ОСТАЛОСЬ.md', encoding='utf-8').read()
TD = open('_dev/ТЕХДОЛГ.md', encoding='utf-8').read()
IDEI = open('_dev/ИДЕИ.md', encoding='utf-8').read()
plan = KARTA[KARTA.index('## 5. Находки'):]

# --- задачи плана: заголовки «**1.1 …**», «### Ф0.», пункты «* 1.1.1», «* 2.4.2», «* 0.7»
tasks = set()
for m in re.finditer(r'^\*\*(\d+\.\d+)[ а-яА-Яa-zA-Z]', plan, re.M):
    tasks.add(m.group(1))
for m in re.finditer(r'^\* (\d+\.\d+(?:\.\d+)?а?)\b', plan, re.M):
    tasks.add(m.group(1))
for m in re.finditer(r'^### Ф(\d)\.', plan, re.M):
    tasks.add(m.group(1))
tasks.update({'0.1', '0.2', '0.3', '0.4', '0.5', '0.6'})

problems = []
for m in re.finditer(r'Ф(\d+(?:\.\d+){0,2}а?)', KARTA):
    ref = m.group(1)
    if ref not in tasks:
        problems.append(f'висящая ссылка Ф{ref}: …{KARTA[max(0, m.start()-40):m.end()+10]!r}')

# --- ОСТ п. X.Y
ost_items = set(re.findall(r'^(\d+\.\d+а?)\. ', OST, re.M))
for m in re.finditer(r'ОСТ п\. ([\d.,– а-я]+)', KARTA):
    for ref in re.findall(r'\d+\.\d+а?', m.group(1)):
        if ref not in ost_items:
            problems.append(f'нет пункта ОСТАЛОСЬ {ref}')

# --- ТД, И, Д, К
td_items = set(re.findall(r'^ТД-(\d+)\.', TD, re.M))
for ref in set(re.findall(r'ТД-(\d+)', KARTA)):
    if ref not in td_items:
        problems.append(f'нет ТД-{ref}')
i_items = set(re.findall(r'И-(\d+)\.', IDEI))
for ref in set(re.findall(r'И-(\d+)', KARTA)):
    if ref not in i_items:
        problems.append(f'нет И-{ref}')
d_items = set(re.findall(r'^\| Д(\d+) \|', KARTA, re.M))
for ref in set(re.findall(r'\bД(\d+)\b', KARTA)):
    if ref not in d_items:
        problems.append(f'нет Д{ref}')
k_items = set(re.findall(r'^\| К(\d+) \|', KARTA, re.M))
for ref in set(re.findall(r'\bК(\d+)\b', KARTA)):
    if ref not in k_items:
        problems.append(f'нет К{ref}')

# --- покрытие: каждый ТД и И упомянут в плане
for ref in sorted(td_items, key=int):
    if f'ТД-{ref}' not in plan:
        problems.append(f'ТД-{ref} не упомянут в плане')
for ref in sorted(i_items, key=int):
    if not re.search(rf'И-{ref}\b', plan):
        problems.append(f'И-{ref} не упомянут в плане')
# --- покрытие ОСТАЛОСЬ: пункт не помечен как сделанный и не упомянут в плане
mentioned = set()
for m in re.finditer(r'ОСТ п\. ([\d.,– а-я]+)', KARTA):
    mentioned.update(re.findall(r'\d+\.\d+а?', m.group(1)))
for a, x, y in re.findall(r'(\d+)\.(\d+)–\d+\.(\d+)', KARTA):
    mentioned.update(f'{a}.{n}' for n in range(int(x), int(y) + 1))
for item in sorted(ost_items, key=lambda s: [int(p) for p in re.findall(r'\d+', s)]):
    block = OST[OST.index(f'{item}. '):][:200]
    done = re.search(r'\[(ИСПРАВЛЕНО|СНЯТО|ПЕРЕНЕСЕНО)', block)
    if not done and item not in mentioned:
        problems.append(f'ОСТАЛОСЬ {item} не упомянут в плане: {block[:90]!r}')

print('задач плана:', len(tasks))
print('проблем:', len(problems))
print('\n'.join(problems))
