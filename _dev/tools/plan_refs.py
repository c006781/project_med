# _dev/tools/plan_refs.py

"""
Проверка ссылок плана переработки — только чтение.

Где что определено:
    * задачи (``Ф1.3.2``), модули захода (``М7``), требования ``Доработки.txt`` (``Д5``) —
      ``_dev/ПЛАН.md``;
    * находки описи (``К2``) — ``_dev/КАРТА.md`` §5;
    * пункты ``ОСТАЛОСЬ`` (``ОСТ п. 4.1``), техдолг (``ТД-3``), идеи (``И-7``) — свои файлы.

Что проверяет:
    1. висящие ссылки во всех служебных файлах (``_dev/*.md``, ``tests/КАРТА_ТЕСТОВ.md``,
       ``IMPLEMENTATION.md`` модулей): ``Ф…``, ``М…``, ``Д…``, ``К…`` — в плане и карте,
       ``ОСТ п. …``, ``ТД-…``, ``И-…`` — в плане и карте;
    2. покрытие: каждый ``ТД`` и ``И`` упомянут в плане; каждый открытый пункт ``ОСТАЛОСЬ``
       (без ``[ИСПРАВЛЕНО]``, ``[СНЯТО]``, ``[ПЕРЕНЕСЕНО]``) упомянут в плане как ``ОСТ п.``.

Запуск (из корня проекта):
    .venv310/Scripts/python.exe -I -X utf8 _dev/tools/plan_refs.py     # Windows
    <venv>/bin/python -I -X utf8 _dev/tools/plan_refs.py               # Linux

Вывод: число задач, число проблем и список; «проблем: 0» — ссылки целы.
Создан 2026-10-25 (тогда план был в КАРТА.md §6), переделан под ``_dev/ПЛАН.md`` в тот же день.
"""

import glob
import re
from typing import List, Set


def read(path: str) -> str:
    """
    Текст файла (UTF-8, переводы строк как есть).

    Args:
        path: Путь от корня проекта.

    Returns:
        Содержимое.

    Пример:
        >>> read('_dev/ПЛАН.md')[:6]
        '# План'
    """
    with open(path, encoding='utf-8') as f:
        return f.read()


PLAN: str = read('_dev/ПЛАН.md')
KARTA: str = read('_dev/КАРТА.md')
OST: str = read('_dev/ОСТАЛОСЬ.md')
TD: str = read('_dev/ТЕХДОЛГ.md')
IDEI: str = read('_dev/ИДЕИ.md')

# --- что определено
tasks: Set[str] = set()
tasks.update(re.findall(r'^\* (\d+(?:\.\d+)+а?)\b', PLAN, re.M))          # «* 1.1.3 …», «* 4.2а …»
tasks.update(re.findall(r'^\*\*(\d+(?:\.\d+)*)\*\*', PLAN, re.M))          # «**1.7.1** · …», «**2.0**»
tasks.update(re.findall(r'^\*\*(\d+\.\d+) ', PLAN, re.M))                  # «**1.1 Импорт …»
tasks.update({'0', '1', '2', '3', '4', '0.1', '0.2', '0.3', '0.4', '0.5', '0.6'})  # фазы; 0.1–0.6 — диапазоном
modules: Set[str] = set(re.findall(r'^### М(\d+)\.', PLAN, re.M))
d_items: Set[str] = set(re.findall(r'^\| Д(\d+) \|', PLAN, re.M))
k_items: Set[str] = set(re.findall(r'^\| К(\d+) \|', KARTA, re.M))
ost_items: Set[str] = set(re.findall(r'^(\d+\.\d+а?)\. ', OST, re.M))
td_items: Set[str] = set(re.findall(r'^ТД-(\d+)\.', TD, re.M))
i_items: Set[str] = set(re.findall(r'И-(\d+)\.', IDEI))

problems: List[str] = []

# --- 1. висящие ссылки во всех служебных файлах
# Пути — с «/» (glob на Windows отдаёт «\»: сравнение с '_dev/ПЛАН.md' иначе не совпадало,
# и проверки Д, К, ОСТ, ТД, И для плана и карты молча не выполнялись — найдено подкладкой
# битых ссылок 2026-10-25)
files = sorted({p.replace(chr(92), '/') for p in
                glob.glob('_dev/*.md') + ['tests/КАРТА_ТЕСТОВ.md']
                + glob.glob('app/**/IMPLEMENTATION.md', recursive=True)})
for path in files:
    text = read(path)
    if path.endswith('ПРОГРЕСС.md'):
        # журнал — история: номера и разделы на момент записи; проверяется только «Где остановились»
        text = text[:text.find('ТОЧКИ ОТКАТА')] if 'ТОЧКИ ОТКАТА' in text else text
    for m in re.finditer(r'\bФ(\d+(?:\.\d+){0,2}а?)', text):
        if m.group(1) not in tasks:
            problems.append(f'{path}: нет задачи Ф{m.group(1)}')
    for m in re.finditer(r'\bМ(\d+)\b', text):
        if m.group(1) not in modules:
            problems.append(f'{path}: нет модуля М{m.group(1)}')
    if path in ('_dev/ПЛАН.md', '_dev/КАРТА.md'):
        for ref in set(re.findall(r'\bД(\d+)\b', text)):
            if ref not in d_items:
                problems.append(f'{path}: нет требования Д{ref}')
        for ref in set(re.findall(r'\bК(\d+)\b', text)):
            if ref not in k_items:
                problems.append(f'{path}: нет находки К{ref}')
        for m in re.finditer(r'ОСТ п\. ([\d.,– а-я]+)', text):
            for ref in re.findall(r'\d+\.\d+а?', m.group(1)):
                if ref not in ost_items:
                    problems.append(f'{path}: нет пункта ОСТАЛОСЬ {ref}')
        for ref in set(re.findall(r'ТД-(\d+)', text)):
            if ref not in td_items:
                problems.append(f'{path}: нет ТД-{ref}')
        for ref in set(re.findall(r'И-(\d+)', text)):
            if ref not in i_items:
                problems.append(f'{path}: нет И-{ref}')

# --- 2. покрытие
for ref in sorted(td_items, key=int):
    if f'ТД-{ref}' not in PLAN:
        problems.append(f'ТД-{ref} не упомянут в плане')
for ref in sorted(i_items, key=int):
    if not re.search(rf'И-{ref}\b', PLAN):
        problems.append(f'И-{ref} не упомянут в плане')
mentioned: Set[str] = set()
for m in re.finditer(r'ОСТ п\. ([\d.,– а-я]+)', PLAN):
    mentioned.update(re.findall(r'\d+\.\d+а?', m.group(1)))
for a, x, y in re.findall(r'(\d+)\.(\d+)–\d+\.(\d+)', PLAN):
    mentioned.update(f'{a}.{n}' for n in range(int(x), int(y) + 1))
for item in sorted(ost_items, key=lambda s: [int(p) for p in re.findall(r'\d+', s)]):
    block = OST[OST.index(f'{item}. '):][:200]
    done = re.search(r'\[(ИСПРАВЛЕНО|СНЯТО|ПЕРЕНЕСЕНО)', block)
    if not done and item not in mentioned:
        problems.append(f'ОСТАЛОСЬ {item} не упомянут в плане: {block[:80]!r}')

print('задач плана:', len(tasks), '| модулей:', len(modules), '| служебных файлов:', len(files))
print('проблем:', len(problems))
print('\n'.join(problems))
