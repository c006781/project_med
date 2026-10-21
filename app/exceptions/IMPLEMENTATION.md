# Исключения (app/exceptions) — заметки о реализации

> Файл для разработчиков: что делает модуль, как устроен, почему так и журнал проверок.
> Обновляется вместе с кодом.
> Последнее обновление: 2026-10-21, проходы 1–2 (ветка `rework-exceptions`).

| Файл | Назначение |
|---|---|
| [exceptions_all.py](exceptions_all.py) | Все исключения приложения (иерархия — в описании модуля) |
| [\_\_init\_\_.py](__init__.py) | Экспорт; `__all__` без `ConnectionError` |
| [tests/test_exceptions.py](../../tests/test_exceptions.py), [tests/test_exceptions_review_pass1.py](../../tests/test_exceptions_review_pass1.py) | Тесты |

---

## 1. Как устроено

```
AppException (message, code; __str__ → "[code] message"; __reduce__ → pickle/copy)
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
  (у таблиц без класса пока `ValueError` — см. §4).
* Тексты и коды исключений конкретных таблиц не менялись (на них опираются тесты и
  командная строка).

### 1.1 Решения

| Решение | Почему |
|---|---|
| Исключения таблиц — наследники общих `EntityNotFoundError` / `EntityValidationError` | Один `except` на «не найдено»/«ошибку поля» любой таблицы; поле и причина доступны окну (`exc.field`) |
| `ConnectionError` → `DatabaseConnectionError`, старое имя — псевдоним вне `__all__` | `from app.exceptions import *` перекрывал встроенный `ConnectionError` — `except ConnectionError` переставал ловить сетевые ошибки (их бросает, например, `app.network`) |
| `__reduce__` в `AppException` | `__init__` наследников принимает данные, а не текст: `pickle` падал (`PhotoFileError`) |
| Неиспользуемые исключения синхронизации и БД оставлены | Публичный API; кандидаты на удаление — ИДЕИ.txt И-9 |

---

## 2. Тесты

`tests/test_exceptions.py` (7, прежние) и `tests/test_exceptions_review_pass1.py` (76):
тексты/коды, иерархия, атрибуты, `import *`, экспорт каждого класса, `pickle`/`copy`
каждого класса, примеры из докстрингов. На старом модуле: 44 падают, 32 проходят (тесты
неизменных текстов/кодов и `copy`, который работал и раньше).

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

---

## 4. Дальше

* Сервисы: `BaseService._validation_error` для таблицы без своего класса — бросать
  `EntityValidationError(field, reason, entity=<модель>)` вместо `ValueError` (шаг
  «сервисы»).
