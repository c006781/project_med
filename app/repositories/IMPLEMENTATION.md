# app/repositories — устройство и решения

Слой доступа к данным: по репозиторию на таблицу, общие запросы — в `BaseRepository`
(`repositories_all.py`). Файл заведён 2026-10-31 (сверка модуля, Ф1.6.9); прежние находки
REPO1–REPO3 (2026-10-16) описаны в `app/services/IMPLEMENTATION.md` §3.2 — здесь кратко в §3.

## 1. Что делает модуль

| Класс | Таблица | Свои методы |
|---|---|---|
| `BaseRepository` | `model_class` наследника | `get_by_id`, `get_all`, `get_all_with_relations`, `get_by_id_with_relations`, `get_with_relations`, `add`, `delete`, `get_unique_values`, `get_page`, `count` |
| `PatientRepository` | `Patient` | — |
| `AppointmentRepository` | `Appointment` | `get_by_patient_with_relations`, `get_page` (= базовый), `get_page_by_patient`, `count_by_patient` |
| `AppointmentNoteRepository` | `AppointmentNote` | `get_by_text_exact` |
| `PhotoRepository` | `Photo` | `get_by_appointment` |

Кто пользуется: `app/services/services_all.py` (сервисы — основной потребитель), `parsers/word_importer.py`,
`tests/conftest.py`, `tests/test_services/test_new_table_by_config.py` (`BaseRepository` для новой
таблицы по описанию); `scripts/build_win.py` — скрытый импорт `repositories_all` для PyInstaller.
Слои `app/schema`, `app/dto` пакет не импортируют (тесты слоёв).

## 2. Как устроено

* **Сессия — снаружи.** Репозиторий получает открытую сессию и только строит запросы: `add` /
  `delete` не делают `flush` / `commit` (до фиксации у новой записи `id is None`). Транзакцией
  управляет вызывающий (`Database.session_scope`, сервисы). Ошибки базы проходят как есть;
  нарушение целостности при фиксации `session_scope` превращает в `DbIntegrityError`
  (`app/database/IMPLEMENTATION.md` §9).
* **Модель — атрибутом класса** `model_class = Patient`; в базе — абстрактное свойство (без
  модели класс не создать). `model_class = None` — `get_unique_values` даёт понятный
  `NotImplementedError` (REPO1).
* **Три вида «со связями»:** `get_all_with_relations` и `get_by_id_with_relations` принимают
  готовые опции загрузки (`selectinload(...)`, `joinedload(...)`), `get_with_relations` — имена
  связей (строки, из `source_attr` описаний полей); неизвестное имя — предупреждение и пропуск
  (REPO2). Имена исторические, интерфейс не меняли (им пользуются сервисы).
* **Фильтры** — формат `app.utils.filtering.apply_filters`: плоский список листьев
  `{'column', 'operator', 'value'}` (через «И») или дерево `{'and': […]}` / `{'or': […]}`.
  `get_page` / `count` передают их в `apply_filters` как есть (`_apply_sql_filters`).
  `get_page_by_patient` / `count_by_patient` добавляют условие по пациенту через
  `_with_patient_filter` (дерево — одним узлом списка).
* **Нечёткий отбор (`'fuzzy'`) репозиторий не делает:** `apply_filters` переводит такой узел в
  «истину» и возвращает его отдельно, а применять его к готовому списку здесь нельзя — сломались
  бы `offset` / `limit` и `count`. Поэтому пропуск — с предупреждением в журнал (R2). Страницы
  приложения (заметки, fuzzy, `sql_compute`, сортировка по заметкам) собирает
  `BaseService.get_page`; `BaseRepository.get_page` — простой путь для тестов и скриптов.
* **Сортировка страниц:** `'поле'` / `'-поле'` → `asc()` / `desc()`, готовые выражения — как
  есть, неизвестное поле — предупреждение и пропуск (REPO3). Последним ключом всегда `id`
  (`_id_tiebreaker`, R3): без него порядок строк в SQL не задан, и соседние страницы могли
  повторять и терять записи.
* **Журнал.** Замер времени — декораторы `log_execution_time` (журнал `system`, DEBUG); свой
  журнал у экземпляра — по имени класса (файл `user`). В журнал не пишутся значения полей:
  `add` / `delete` — `Класс id=N` (`_log_ref`), `get_by_text_exact` — длина текста (R6), как
  значения запросов в ошибках базы (`LOG_SQL_PARAMS`).

## 3. Журнал проверок

### REPO1–REPO3 (2026-10-16, проход по сервисам)

| # | Что было | Исправление |
|---|---|---|
| REPO1 | `get_unique_values` без модели — `err_.message` → `AttributeError` | понятный `NotImplementedError` |
| REPO2 | `get_with_relations`: неизвестная связь молча пропускалась | предупреждение в журнал |
| REPO3 | `get_page` / `order_by`: `'-date'` шёл в SQL строкой (ошибка); `AppointmentRepository.get_page` — копия базового | `_order_clauses`; копия — вызов базового |

### Сверка (2026-10-31, Ф1.6.9)

Тесты — `tests/test_repositories/test_repositories_check.py`: на коде до исправления падают 9
из 12 (R1 — 2, R2 — 1, R3 — 2, R4 — 1, R5 — 1, R6 — 2; R5 — по тексту SQL: SQLite и без
`ORDER BY` отдаёт `DISTINCT` по возрастанию); 3 — характеризующие (плоский список, список с
узлом-деревом, нет предупреждения без `fuzzy`).

| # | Что было | Почему плохо | Исправление |
|---|---|---|---|
| R1 | `get_page`, `count` перебирали фильтры как список словарей (`f.get(...)`); `get_page_by_patient`, `count_by_patient` — `base_filters + filters` | Дерево `{'and'/'or': …}`, которое понимает `apply_filters`, роняло запрос: `AttributeError` / `TypeError` (list + dict) | Фильтры — в `apply_filters` как есть (`_apply_sql_filters`); пациент — `_with_patient_filter` |
| R2 | `'fuzzy'` молча отбрасывался | Страница и счёт шире ожидаемого без следа в журнале | Предупреждение со списком столбцов (без значений) |
| R3 | `get_page` без `order_by` — без `ORDER BY`; при равных ключах порядок не задан | Соседние страницы `offset` / `limit` могли повторять и терять записи | `id` последним ключом (`_id_tiebreaker`) |
| R4 | `get_with_relations(relations=None)`; строка отладки | `TypeError`; части склеены без пробелов, на каждую связь собирался текст SQL | `relations or []`; одна строка отладки до цикла |
| R5 | `get_unique_values` — `DISTINCT` без `ORDER BY` | Подсказки и списки фильтра — в порядке, выбранном базой | `ORDER BY` столбца (`None` в SQLite — первым) |
| R6 | `add` / `delete` писали строку модели (`<Patient(..., name=Фамилия Имя)>`), `get_by_text_exact` — текст заметки | Личные данные в файле журнала при уровне DEBUG | `_log_ref` (`Класс id=N`), длина текста |
| R7 | pyflakes: f-string без подстановок (`get_all`) | Шум проверок | Обычная строка |
| R8 | Докстринги reST, неверный (`count_by_patient` «с подгрузкой связей»), без аннотации возврата — `get_with_relations`, `model_class`, `get_by_text_exact`; `__init__` без `-> None`; `relations` без типа | Документация расходилась с кодом | Google с `Example:` по всему модулю, типы, формат параметров и вызовов (skill п. 7) |

## 4. Углы и ограничения

* `offset` / `limit` не проверяются: в SQLite отрицательный `offset` — как 0, отрицательный
  `limit` — без ограничения; `limit=0` — пустой список.
* `get_all`, `get_all_with_relations`, `get_by_patient_with_relations`, `get_by_appointment` —
  без `ORDER BY` (порядок не задан); для страниц — `get_page*`.
* `get_unique_values` возвращает и `None` (пустые ячейки). Вызывающий, который делает строки
  (`str(v)`), получит `'None'` — например, подсказки описаний фото в
  `appointment_list_page.py` (вопрос владельцу — `_dev/ВОПРОСЫ.md` В-16, не в этом модуле).
* `'fuzzy'` внутри `'or'` — `ValueError` из `apply_filters` (DATA4b): нечёткий отбор возможен
  только на уровне «И».
* Сортировка — только по столбцам модели; по заметкам и `sql_compute` — `BaseService`.

## 5. Тесты

`tests/test_repositories/`: `test_repositories.py`, `test_repositories_full.py` (CRUD,
уникальные значения, выборки по пациенту и приёму), `test_repositories_page.py` (страницы,
фильтры, связи, счёт), `test_repositories_review.py` (REPO1–REPO3, характеризующие),
`test_repositories_check.py` (R1–R6). Фикстуры — `tests/conftest.py` (`db_session` с откатом
транзакции, `sample_*`, `*_repo`). В старых файлах `test_repositories*.py` pyflakes видит
неиспользуемые импорты (`pytest`, `time`, репозитории) — безвредно, убрать при случае
(2026-10-31).

## 6. Журнал

| Дата | Что | Зачем |
|---|---|---|
| 2026-10-16 | REPO1–REPO3 | понятные ошибки, предупреждения, сортировка `'-поле'` (`app/services/IMPLEMENTATION.md` §3.2) |
| 2026-10-31 | R1–R5: фильтры-деревья, предупреждение о `fuzzy`, `id` последним ключом страниц, `relations=None`, порядок уникальных значений | края фильтров и пагинации падали или давали неустойчивый результат |
| 2026-10-31 | R6–R8: личные данные вне журнала, pyflakes, докстринги Google с примерами и типы по всему модулю; заведён этот файл | итоговая перепроверка модуля |
