# Исключения (app/exceptions) — заметки о реализации

> Файл для разработчиков: что делает модуль, как устроен, почему так и журнал проверок.
> Обновляется вместе с кодом.
> Последнее обновление: 2026-10-25, проход 3 — сверка М9 (ветка `rework-w1-exceptions`).

| Файл | Назначение |
|---|---|
| [exceptions_all.py](exceptions_all.py) | Все исключения приложения (иерархия — в описании модуля) |
| [\_\_init\_\_.py](__init__.py) | Экспорт; `__all__` без `ConnectionError` (прежнее имя — присваиванием) |
| [tests/test_exceptions.py](../../tests/test_exceptions.py), [tests/test_exceptions_review_pass1.py](../../tests/test_exceptions_review_pass1.py), [tests/test_exceptions_review_pass3.py](../../tests/test_exceptions_review_pass3.py) | Тесты |

---

## 1. Как устроено

```
AppException (message, code; __str__ → "[code] message" / message при code=None; __reduce__ → pickle/copy)
├── EntityNotFoundError (+LookupError): entity, entity_id      9001 / по таблицам 1001…4001
├── EntityValidationError (+ValueError): entity, field, reason 9002 / по таблицам 1002…4002
├── PhotoFileError: path, operation, reason, errno             4003 (+ Permission/NoSpace)
├── SyncError → Download/Upload/TokenError                     5000–5003 (не используются)
└── DatabaseError → IntegrityError, DatabaseConnectionError    6000–6002 (не используются)
```

* Таблица без своего класса — общие `EntityNotFoundError(entity, id)` и
  `EntityValidationError(field, reason, entity=...)`. Свой класс — если нужен свой код или
  текст (`super().__init__(..., code=, message=)`).
* Сервисы выбирают исключение так: «не найдено» — `BaseService._not_found_exception`
  (по умолчанию `EntityNotFoundError`), проверка — `_validation_exception` у сервиса
  (у таблицы без своего класса — `EntityValidationError`).
* Тексты и коды исключений конкретных таблиц не менялись (на них опираются тесты и
  командная строка).

### 1.1 Решения

| Решение | Почему |
|---|---|
| Исключения таблиц — наследники общих `EntityNotFoundError` / `EntityValidationError` | Один `except` на «не найдено»/«ошибку поля» любой таблицы; поле и причина доступны окну (`exc.field`) |
| `ConnectionError` → `DatabaseConnectionError`, старое имя — псевдоним вне `__all__` | `from app.exceptions import *` перекрывал встроенный `ConnectionError` — `except ConnectionError` переставал ловить сетевые ошибки (их бросает, например, `app.network`) |
| `__reduce__` в `AppException` | `__init__` наследников принимает данные, а не текст: `pickle` падал (`PhotoFileError`) |
| Неиспользуемые исключения синхронизации и БД оставлены | Публичный API; кандидаты на удаление — `_dev/ИДЕИ.md` И-9 |

---

## 2. Тесты

`tests/test_exceptions.py` (7, прежние) и `tests/test_exceptions_review_pass1.py` (76):
тексты/коды, иерархия, атрибуты, `import *`, экспорт каждого класса, `pickle`/`copy`
каждого класса, примеры из докстрингов. На старом модуле: 44 падают, 32 проходят (тесты
неизменных текстов/кодов и `copy`, который работал и раньше).

`tests/test_exceptions_review_pass3.py` (25, проход 3, 2026-10-25): E9–E11 (до исправления
падали `test_e9_zero_code_is_shown`, `test_e10_non_string_message_without_code`,
`test_e11_pyflakes_clean`) и непокрытое: свой код/текст `EntityValidationError`, пустая
таблица, коды по умолчанию `SyncError`/`DatabaseError`, ловля по базовым классам групп,
`reason` скачивания/загрузки, `TokenError`, `args`, `errno=0`, лишние атрибуты при
`pickle`, примеры описания пакета. Всего по модулю — 108.

---

## 3. Журнал проверок

### Проход 1 (2026-10-21)

| # | Что было | Почему плохо | Исправление |
|---|---|---|---|
| E1 | Класс `ConnectionError` в `__all__` | `import *` перекрывал встроенный `ConnectionError` | `DatabaseConnectionError`; псевдоним вне `__all__` |
| E2 | `PatientNotFoundError` и др. — не наследники `EntityNotFoundError`, не `LookupError` | Ловить «не найдено» — перечислять все классы | Наследники; `entity`, `entity_id` |
| E4 | `PhotoStoragePermissionError`, `PhotoStorageNoSpaceError` не экспортировались | Импорт только из внутреннего модуля | Экспорт; тест «каждый класс в `__all__`» |
| E5 | Ошибки проверки не хранили поле и причину; общего класса нет | Окно не может подсветить поле; новая таблица — голый `ValueError` | `EntityValidationError` (`field`, `reason`, `entity`) |
| E6 | `PhotoFileError`, `IntegrityError` и др. не хранили данные | Только текст | `path`, `operation`, `reason`, `detail` |
| E7 | Пример в докстринге `EntityNotFoundError` не проходил `doctest` | Документация врала | `IGNORE_EXCEPTION_DETAIL`, пример `str()` |
| E8 | `pickle` исключений с данными в `__init__` | `TypeError` (`PhotoFileError`), текст склеивался | `AppException.__reduce__` |
| D1 | Докстрингов/типов у большинства классов нет | — | Добавлены, описание модуля с иерархией |

### Проход 2 (2026-10-21) — замечаний нет

Полный набор: 1633 прошли, 10 известных падений, новых нет.

### Проход 3 (2026-10-25) — сверка М9 (Ф1.6.8)

| # | Что было | Почему плохо | Исправление |
|---|---|---|---|
| D2 | 18 `__init__` без докстринга; у классов и `__init__` нет примеров; нет `-> None`; параметры и вызовы — не по формату skill п. 7; описание пакета (`__init__.py`) устарело | Правило проекта: докстринг с примером и полная типизация у всего | Весь модуль переформатирован (параметр на строку с комментарием, выравнивание) и задокументирован: докстринги с «Пример:» (все проверяются `doctest`, тест E7), `-> None`, точный тип `__reduce__`; в описании модуля и заголовках разделов — что не используется (И-9). Поведение не менялось |
| E9 | `AppException.__str__`: `if self.code:` — код `0` считался «без кода» | Расходилось с описанием «`None` — без кода»; код 0 терялся в тексте | `if self.code is not None` (старый код — комментарием) |
| E10 | `__str__` без кода возвращал `self.message` как есть | Текст не строкой (`AppException(OSError(...))`) — `TypeError: __str__ returned non-string`: падал бы журнал / окно ошибки | `str(self.message)`; атрибут `message` — как передан |
| E11 | `__init__.py`: прежнее имя `ConnectionError` импортировалось, но не входило в `__all__` | `pyflakes`: «imported but unused» — шум в проверке модуля | Присваивание `ConnectionError = DatabaseConnectionError` после импорта (тот же объект; импорт по имени работает; тест `pyflakes` по пакету) |
| E12 | `tests/test_exceptions.py`: неиспользуемый `import pytest` | `pyflakes` | Импорт закомментирован с пометкой |

Не исправлялось (вне модуля или нужен ответ владельца — `_dev/agents/M9.md`):

* **N1.** Вызывающие передают `operation` не в родительном падеже: `app/services/services_all.py`
  (`add_photo_to_appointment`) — `PhotoFileError(path, "проверка", "файл не существует")` →
  «Ошибка проверка файла …» (и в `tests/test_exceptions.py` — «копирование»). Править
  вызов (`"проверки"`) — вне территории М9 (М11); текст модуля не трогали.
* **N2.** `entity` у заметки разный: «не найдено» — `'Заметка приёма'`, проверка —
  `'Заметка'`; у общих исключений из сервисов `entity` — имя модели (`'Prescription'`), у
  таблиц со своим классом — по-русски. Сейчас `entity` никто не читает; менять — по решению
  владельца (атрибут — публичный, тесты прохода 1 его проверяют).
* **N3.** `errno=0` в `PhotoFileError` в текст не попадает (`if errno:`) — оставлено: 0 не
  код ошибки ОС; закреплено тестом.

---

## 4. Дальше

* ~~Сервисы: `BaseService._validation_error` для таблицы без своего класса —
  `EntityValidationError`~~ — сделано 2026-10-21 (app/services/IMPLEMENTATION.md §3.3, SE1).
