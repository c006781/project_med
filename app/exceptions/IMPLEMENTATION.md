# Исключения (app/exceptions) — заметки о реализации

> Файл для разработчиков: что делает модуль, как устроен, почему так и журнал проверок.
> Обновляется вместе с кодом.
> Последнее обновление: 2026-10-31, проход 4 — три уровня текста (Ф1.6.8а, ветка
> `rework_work/w1-exceptions`).

| Файл | Назначение |
|---|---|
| [exceptions_all.py](exceptions_all.py) | Все исключения приложения (иерархия — в описании модуля) |
| [\_\_init\_\_.py](__init__.py) | Экспорт; `__all__` без `ConnectionError` (прежнее имя — присваиванием) |
| [tests/test_exceptions.py](../../tests/test_exceptions.py), [tests/test_exceptions_review_pass1.py](../../tests/test_exceptions_review_pass1.py), [tests/test_exceptions_review_pass3.py](../../tests/test_exceptions_review_pass3.py), [tests/test_exceptions_details.py](../../tests/test_exceptions_details.py) | Тесты |

---

## 1. Как устроено

```
AppException (message, code; details, original, original_text, log_text(); __str__ → "[code] message" / message при code=None; __reduce__ → pickle/copy)
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
* **Три уровня текста** (Ф1.6.8а, 2026-10-31; решение владельца В-1): `message` — текст
  пользователю (`str(exc)` — как раньше); `details` — что делали (строка или словарь:
  файл, таблица, параметры, SQL) — только для журнала; `original` — исходная ошибка: явная
  (`original=exc`, как есть) или первопричина цепочки (`__cause__`, без него — `__context__`;
  `raise … from None` — нет; как `startup_error_text` в `app/database/migrate.py`);
  `original_text` — `'<тип>: <текст>'` (тип не встроенной ошибки — с модулем:
  `sqlalchemy.exc.IntegrityError`); `log_text()` — `str(exc)`, затем `  Подробности: …`,
  `  Исходная ошибка: …` (пустое не выводится). Пишет в журнал тот, кто ловит и показывает
  (трассировка — `exc_info`), не само исключение.

### 1.1 Решения

| Решение | Почему |
|---|---|
| Исключения таблиц — наследники общих `EntityNotFoundError` / `EntityValidationError` | Один `except` на «не найдено»/«ошибку поля» любой таблицы; поле и причина доступны окну (`exc.field`) |
| `ConnectionError` → `DatabaseConnectionError`, старое имя — псевдоним вне `__all__` | `from app.exceptions import *` перекрывал встроенный `ConnectionError` — `except ConnectionError` переставал ловить сетевые ошибки (их бросает, например, `app.network`) |
| `__reduce__` в `AppException` | `__init__` наследников принимает данные, а не текст: `pickle` падал (`PhotoFileError`) |
| Неиспользуемые исключения синхронизации и БД оставлены | Публичный API; кандидаты на удаление — `_dev/ИДЕИ.md` И-9 |
| `details`, `original` — только именованные и необязательные | Прежние вызовы `AppException(message, code)` и наследников не меняются; позиционные параметры наследников разные — именованные не путаются |
| `original` — свойство, а не атрибут | `__cause__` появляется только после `raise … from`, то есть после `__init__`: цепочку читаем при обращении |
| Явная `original` — как есть, без спуска по её цепочке | Явно передали — значит, нужна именно она |
| `pickle`/`copy`: исходная ошибка — текстом, значения словаря `details` — простые или `repr` | Ошибки драйверов часто не сериализуются (соединение, блокировка внутри), цепочку `pickle` не переносит вовсе; без исходной ошибки и словаря `__dict__` копии — как раньше (тест E8) |
| Умолчания `details`, `_original`, `_original_text` — на уровне класса | Экземпляр из старого `pickle` (без этих ключей) не падает при чтении |

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

`tests/test_exceptions_details.py` (проход 4, 2026-10-31, Ф1.6.8а): старые вызовы как
раньше, `details` (строка, словарь, пустые), `original` явно / из цепочки до первопричины /
из `__context__` / `from None` / зацикленная цепочка, `log_text`, `pickle`/`copy` с
несериализуемой исходной ошибкой и значениями подробностей. До правки — 20 из 21 падали.

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

### Проход 4 (2026-10-31) — три уровня текста (Ф1.6.8а)

| # | Что было | Почему плохо | Исправление |
|---|---|---|---|
| F1 | У исключения — только текст пользователю | Для разбора нет «что делали» и исходной ошибки (И-9, В-1); текст пользователю нельзя загромождать подробностями | `AppException`: `details`, `original` (явно / из цепочки), `original_text`, `log_text()`; помощники `_exception_text`, `_details_text`, `_root_cause` |
| F2 | `__reduce__` переносил `__dict__` целиком | С исходной ошибкой (часто несериализуемой) `pickle` падал бы | Исходная — текстом, значения словаря подробностей — простые или `repr` (старый код — комментарием) |

---

## 4. Дальше

### 4.1 Неиспользуемые исключения (И-9) — предложение владельцу (2026-10-25)

Проверено поиском по `app/`, `interfaces/`, `parsers/`, `tests/` (2026-10-25): ниже —
классы, которые **нигде не бросаются и не ловятся** (только тесты этого модуля). Решения
нет — ничего не удалено и не подключено.

| Исключение | Где можно использовать (что там сейчас) | Или убрать — почему |
|---|---|---|
| `SyncError`, `DownloadError`, `UploadError`, `TokenError` (5000–5003) | `app/network/ya_dop.py` — `yadisk_download_file` / `yadisk_upload_file` при `if_err=True` бросают встроенные `ConnectionError` (токен/связь), `FileNotFoundError`, `IsADirectoryError`, `FileExistsError` и исходные ошибки `yadisk`; при `if_err=False` — коды `YaDiskResult`. `YaDiskThread.run` (`thread_network.py`) показывает `str(exc)`. Можно: `TokenError` — вместо `ConnectionError` при недействительном токене; `DownloadError` / `UploadError` — обёртка прочих сбоев передачи (`raise DownloadError(str(exc)) from exc`) | У сети уже своя проверенная схема (коды `YaDiskResult` + встроенные исключения, T1); перевод потребует двойного наследования (`TokenError(SyncError, ConnectionError)`), иначе сломаются `except ConnectionError` / `FileNotFoundError` у вызывающих и тесты `tests/test_network`; пользователь увидит префикс `[5001]`. `interfaces/cli/cli.py` импортирует `DownloadError`, `UploadError` без использования (pyflakes) |
| `DatabaseError`, `IntegrityError`, `DatabaseConnectionError` (6000–6002) | `DatabaseConnectionError` — `app/database/database.py` `Database.__init__`: отказ открыть базу (занята / только чтение / нет файла) сейчас уходит исключением SQLAlchemy, текст для пользователя строит `app/database/migrate.py` `startup_error_text` (обходит `__cause__` — `raise DatabaseConnectionError(...) from exc` его не сломает). `IntegrityError` — `Database.session_scope`: `sqlalchemy.exc.IntegrityError` (UNIQUE, внешний ключ) сейчас логируется и пробрасывается как есть; можно переводить в `IntegrityError(detail) from exc`, чтобы командная строка и окно ловили одно исключение приложения (сейчас `sqlalchemy.exc.IntegrityError` нигде не ловят) | Если перевод ошибок SQLAlchemy не нужен — убрать (комментарием): имена совпадают с `sqlalchemy.exc.DatabaseError` / `IntegrityError` и путают |
| `PhotoStoragePermissionError`, `PhotoStorageNoSpaceError` (4003, errno 13 / 28) | Копирование файла в хранилище: `app/services/services_all.py` (`_new_file_field` → `app/utils/file_deletions.copy_file_to_temp_dir`, `add_photo_to_appointment`) — сейчас сырой `OSError`; по `errno` `EACCES` / `ENOSPC` — эти классы. Они — `PhotoFileError`, который `interfaces/cli/cli.py` уже ловит | Убрать, если понятного текста для «нет прав» / «нет места» не нужно |
| `ConnectionError` (псевдоним `DatabaseConnectionError`) | Не импортируется по старому имени нигде (кроме тестов модуля) | Можно убрать в конце переработки (Ф4.8); пока — совместимость |

Варианты решения:

* **А — использовать по месту** (рекомендую для базы и хранилища фото): подключать в заходах
  своих модулей — `DatabaseConnectionError` / `IntegrityError` в М8 (`app/database`),
  `PhotoStorage*Error` в М11 (`app/services`); тексты для пользователя — короткие,
  `from exc` сохраняет исходную ошибку.
* **Б — убрать комментарием** с пометкой `↑ до <дата> (И-9)` (рекомендую для синхронизации:
  схема `YaDiskResult` + встроенные исключения уже есть и покрыта тестами); вместе — убрать
  неиспользуемый импорт в `interfaces/cli/cli.py` (М20) и строки в `__init__.py`, тестах.
* **В — оставить как есть** до Ф4 (финальная шлифовка) — заглушка без вреда, но мёртвый код.

**Решение владельца 2026-10-26:** база и фото — **А** (подключить в М8 / М11); синхронизация —
не убирать, а сделать свои подробные исключения Яндекс.Диска (М13). До подключения —
доработка `AppException` (`_dev/ПЛАН.md` Ф1.6.8а): три уровня текста в `AppException`: `message` — понятный текст пользователю
(`str(exc)`, как сейчас); `details` — необязательное поле, что делали (файл, таблица,
параметры, SQL) — для журнала; `original` — исходная ошибка «из глубины» как есть (тип и
текст): сама из цепочки `raise … from exc` (до первопричины) или явно `original=exc`;
`original_text` — её текст; `log_text()` — код + текст + подробности + исходная ошибка
для журнала (трассировка — `exc_info`). Пишет в журнал тот, кто ловит и показывает
(окно, командная строка, `session_scope`), — не само исключение (без дублей).
`__reduce__` — с `details` и `original` (текстом). Обратная совместимость: новые поля
необязательны.

* ~~Сервисы: `BaseService._validation_error` для таблицы без своего класса —
  `EntityValidationError`~~ — сделано 2026-10-21 (app/services/IMPLEMENTATION.md §3.3, SE1).
