# Яндекс.Диск (app/network) — заметки о реализации

> Файл для разработчиков: что делает модуль, как устроен, почему так и журнал проверок.
> Обновляется вместе с кодом.
> Последнее обновление: 2026-10-21, проходы 1–3 (ветка `rework-yadisk`).

| Файл | Назначение |
|---|---|
| [ya_dop.py](ya_dop.py) | Функции без Qt: `yadisk_download_file`, `yadisk_upload_file`, `check_token`, `check_and_create_path`, `check_remote_file_exists`; коды `YaDiskResult`; пути `normalize_remote_path`, `remote_parent_dir`, `remote_db_file_path`, `DB_EXTENSIONS` |
| [thread_network.py](thread_network.py) | Потоки Qt: `YaDiskThread` (база), `DownloadThread`, `UploadThread` |
| [\_\_init\_\_.py](__init__.py) | Публичный API пакета (`__all__`) |
| [tests/test_network/](../../tests/test_network/) | Тесты: прежние (`test_ya_dop.py`, `test_thread_network.py`) и проходов (`test_network_review_pass<N>.py`) |

Кто пользуется: окно (`interfaces/gui/gui_window/main_window.py`, `SyncMixin` — потоки),
сервис синхронизации (`app/services/sync_service.py` — командная строка), экран настроек
(`pages/settings_page.py` — `check_token`, `check_and_create_path`).

---

## 1. Как устроено

```
окно (SyncMixin)            командная строка             экран настроек
   │ DownloadThread/          │ SyncService.download_sync/   │ check_token,
   │ UploadThread             │ upload_sync                  │ check_and_create_path
   ▼                          ▼                              ▼
YaDiskThread.run ──► ya_dop: yadisk_download_file / yadisk_upload_file / check_*
   finished(code)            ├─ normalize_remote_path (путь с '/')
   error(text)               ├─ _open_client (YaDisk на одну операцию, close())
                             ├─ _token_status (без исключений, и при обрыве сети)
                             ├─ _remote_kind ('file' | 'dir' | None)
                             └─ _fail (код или исключение — по if_err)
```

### 1.1 Договорённости

* **Коды** — `YaDiskResult(IntEnum)`: `OK=0`, `NO_CONNECTION=-1`, `NOT_FOUND=-2`,
  `FAILED=-3`, `NOT_A_FILE=-4`, `ALREADY_EXISTS=-5`. Наследник `int` — прежние сравнения
  (`code == 0`) и `Signal(int)` работают. Текст — `.message`, для любого числа —
  `YaDiskResult.describe(code)`.
* **`if_err`**: `True` — исключение с русским текстом (`ConnectionError`,
  `FileNotFoundError`, `IsADirectoryError`, `FileExistsError` или исходное); `False` — код,
  без исключений (в том числе без сети). Потоки вызывают с `if_err=True` — текст уходит
  в сигнал `error`.
* **Пути на Диске** — всегда через `normalize_remote_path`: `\` → `/`, повторные и
  завершающий `/` убираются, схема `disk:` сохраняется. Путь без начального `/` `yadisk`
  понимает от корня (`disk:/…`) — проверено на запросе библиотеки.
* **Путь к файлу БД** по настройкам — `remote_db_file_path(remote, local)`: путь без
  `.db/.sqlite/.sqlite3` — папка, дописывается имя локального файла. Одна реализация для
  окна, сервиса и командной строки.
* **Клиент** — новый `YaDisk` на каждую операцию и `close()` в `finally`.

### 1.2 Как добавить операцию

1. Функция в `ya_dop.py` по образцу (пример — в описании модуля): `normalize_remote_path` →
   `with _open_client(...)` → `_token_status` → работа в `try` → код `YaDiskResult`.
   Новый код результата — в `YaDiskResult` и `_RESULT_MESSAGES`.
2. Поток — наследник `YaDiskThread` с одним методом `_operation()` (пример — в описании
   `thread_network.py`).
3. Экспорт в `__init__.py` (`__all__`), тесты в `tests/test_network/`.

### 1.3 Решения

| Решение | Почему |
|---|---|
| Сигнал `finished(int)` объявлен поверх `QThread.finished()` | Так было; окно подключается к нему. Проверено настоящим запуском потока: обработчик получает ровно один вызов с кодом (`test_finished_signal_emitted_once_with_code`). Переименование — только вместе с окном |
| `DownloadThread` не вызывает `check_remote_file_exists` | Проверки токена, наличия и типа файла делает `yadisk_download_file`; раньше токен проверялся дважды (5 лишних запросов) |
| `makedirs`, не `mkdir` | У `yadisk` 3.x `mkdir` создаёт только последнюю папку, аргумент `parents` молча отбрасывается |
| Тип пути — `is_file`, затем `exists` | Без `get_meta` и разбора ответа; два запроса только для папки |
| `DirectoryExistsError` ловится раньше `PathExistsError` | Подкласс: иначе «папка на месте файла» выдавалось как «файл уже есть» |
| Прежний код — в комментариях внизу файлов | Правило проекта |

---

## 2. Тесты

`tests/test_network/` — 111 тестов (2026-10-21), сеть не нужна (клиент подменяется).
Есть тесты с настоящим запуском потока (`QThread.start`) и прогон примеров из докстрингов
(`doctest`). Тесты проходов проверены на коде до исправлений: тесты исправлений падают,
проходят только тесты на неизменное поведение.

---

## 3. Журнал проверок

Порядок: проверка → исправление → запись → тесты → новая проверка с начала, пока
замечаний нет.

### Проход 0 (2026-10-21) — первые исправления

| # | Файл | Что было | Исправление |
|---|---|---|---|
| N0a | `thread_network.py` | `check_remote_file_exists` не импортирована — «Скачать БД с сервера» падало с `NameError` | Импорт (в проходе 1 вызов убран совсем, T1) |
| N0b | `ya_dop.py` | Скачивание в путь без папки (`clinic.db`) — `makedirs('')` | Папка создаётся, только если есть |
| N0c | `ya_dop.py` | `mkdir(..., parents=True)` / `mkdir(parent)` | `makedirs` |
| N0d | тесты | Ждали прежний набор параметров (`overwrite`) | Обновлены |

### Проход 1 (2026-10-21)

| # | Файл | Что было | Почему плохо | Исправление |
|---|---|---|---|---|
| N1 | `ya_dop.py` | `YaDisk.check_token` без сети бросает `YaDiskConnectionError` | `if_err=False` не спасал — функции падали; на экране настроек поток проверки токена/папки падал, кнопка оставалась выключенной навсегда | `_token_status`: `(False, текст)`; все функции возвращают код/кортеж; сбои после проверки токена — `FAILED` |
| N2 | `ya_dop.py` | `YaDisk` не закрывался | Незакрытая HTTP-сессия на каждую операцию | `_open_client` — `close()` в `finally` |
| N3 | `ya_dop.py` | `\` в пути уходил на Диск как часть имени | Путь `Папка\база` из Windows — файл с именем `Папка\база` в корне | `normalize_remote_path`, `remote_parent_dir` (`posixpath`) |
| N4 | `ya_dop.py` | Коды `-1/-2/-3` числами, тексты исключений на английском | Окно показывало «код -3» и английские сообщения | `YaDiskResult` с `.message`/`describe`, русские тексты |
| N5 | `ya_dop.py` | Скачивание по пути к папке | Невнятная ошибка библиотеки | `NOT_A_FILE` / `IsADirectoryError` |
| N5a | `ya_dop.py` | (найдено при проверке черновика) `except FileNotFoundError: raise` | Ошибка локальной ФС при `if_err=False` вылетала бы исключением | Ожидаемые ошибки — вне `try` |
| N6 | `ya_dop.py` | Загрузка без перезаписи на существующий файл — `-3` | Причина не видна | `ALREADY_EXISTS` / `FileExistsError` |
| T1 | `thread_network.py` | Два потока — копии; скачивание проверяло токен и файл дважды | Новую операцию — только копированием; лишние запросы | `YaDiskThread` (сигналы, `run`, ошибки), наследники — `_operation()` |
| P1 | `sync_service.py` → `ya_dop.py` | `remote_db_file_path` в сервисе | Основа — в сетевом модуле; `\` не нормализовался | Перенесена, сервис импортирует (прежний адрес работает) |
| D1 | `__init__.py` | Описание про несуществующий `dop_yadisk/`, экспорт только 4 имён | Вводит в заблуждение | Описание и `__all__` обновлены |

Тесты: `test_network_review_pass1.py` (94). Полный набор: 1461 прошли, 10 известных падений
(7 CLI, 3 миграции — SQLite 3.34), новых нет.

### Проход 2 (2026-10-21)

| # | Файл | Что было | Почему плохо | Исправление |
|---|---|---|---|---|
| N7 | `ya_dop.py` | `except PathExistsError` (проход 1) ловил и `DirectoryExistsError` | Загрузка на место папки — «файл уже есть (перезапись выключена)», даже при `overwrite=True` (ошибка внесена в проходе 1) | `DirectoryExistsError` раньше: `NOT_A_FILE` / `IsADirectoryError` |

Проверено и оставлено: соответствие «ресурс уже есть» → `PathExistsError` в `yadisk.utils`
(`DiskResourceAlreadyExistsError`); неиспользуемые импорты в прежних тестах (правило проекта).
Тесты: `test_network_review_pass2.py` (3).

### Проход 3 (2026-10-21) — замечаний нет

Перечитаны `ya_dop.py`, `thread_network.py`, `__init__.py`, вызовы из `sync_service.py`;
тесты модуля и полный набор — без новых падений.

---

## 4. Техдолг и дальше

* Скачивание пишет прямо в рабочий файл БД — см. `_dev/ТЕХДОЛГ.md` (ТД-1).
* Окно: `MainWindow._correct_remote_path` → `remote_db_file_path`; текст кода в
  `_on_download_finished`/`_on_upload_finished` → `YaDiskResult.describe` (шаг «окно»).
