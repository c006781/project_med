# Конфигурация приложения — заметки о реализации

> Файл для разработчиков: что делает модуль, как он устроен, где проблемы и почему он
> устроен именно так. Обновляется вместе с кодом.
> Последнее обновление: 2026-10-14, анализ перед рефакторингом (ветка `rework-config`).

| Файл | Назначение |
|---|---|
| [conf/getenv.py](conf/getenv.py) | Чтение/запись `.env` через `python-dotenv`: `get_getenv`, `save_env_file`, `crete_env_file`, `get_dotenv_path` |
| [conf/get_config.py](conf/get_config.py) | «Старый» конфиг: `get_config_env()` → `APP_CONFIG_PATH`, `GITHUB_TOKEN` из `.env` |
| [config_manager/manager.py](config_manager/manager.py) | `BaseConfigManager`/`AppConfigManager` — настройки в `config.msgpack`; `get_config_env()` — словарь всех настроек |
| [config_applier.py](config_applier.py) | `ConfigApplier` — применение изменённых настроек после сохранения |
| [logging_setup.py](logging_setup.py) | `setup_logging()` — передать конфиг логгерам (см. `app/utils/logger/IMPLEMENTATION.md`) |
| [\_\_init\_\_.py](__init__.py) | `APP_VERSION` (из файла `VERSION`), `GITHUB_REPO_SLUG` |
| [tests/test_config/](../../tests/test_config/) | Тесты |

---

## 1. Два уровня конфигурации

```
.env (python-dotenv)                 config.msgpack (MessagePack)
├─ APP_CONFIG_PATH  ── путь к ──▶    ├─ database_local_path, database_remote_path
└─ GITHUB_TOKEN (для обновлений)     ├─ YANDEX_TOKEN, PHOTOS_STORAGE_PATH, BACKUP_*
                                     └─ LOG_*, system_*, user_*, show_call_depth …
```

* `.env` — «загрузочный» уровень: где лежит основной конфиг, плюс токен GitHub.
* `config.msgpack` — все настройки приложения; его редактирует экран настроек.
  Если файла нет — значения по умолчанию из `AppConfigManager._defaults`, файл
  создаётся при первом `save()`.

### 1.1 Чтение

```
get_config_env(path=None)                         # manager.py — им пользуется всё приложение
└─ AppConfigManager.get_instance(config_path=path)
   ├─ path is None → _old_get_config_env()        # conf/get_config.py — КАЖДЫЙ раз
   │                 ├─ get_getenv('APP_CONFIG_PATH', start_value='config.msgpack')
   │                 └─ get_getenv('GITHUB_TOKEN',   start_value='')
   │                    └─ find_dotenv() → load_dotenv() → (если пусто) set_key() → load_dotenv()
   └─ экземпляр по пути (Multiton) → manager.get_all() (копия)
```

### 1.2 Сохранение и применение (экран настроек)

```
SettingsPage._save:
  old = manager.get_all().copy()
  manager.set(...)…; manager.save()                 # → _notify_change() → ВСЕ слушатели
  new = manager.get_all()
  blocks = ConfigApplier.get_changed_blocks(old, new)
  applier.apply_database/photos/sync/logging/backup(new) — по изменённым блокам
```

Слушатели `save()` (`add_change_listener`): каждый сервис (`BaseService.__init__`) и
`SyncService.__init__`. Сервис при уведомлении закрывает и заново открывает БД
(`reload_config`), `PhotoService` — ещё и папку фото, `SyncService` перечитывает токен и пути.

---

## 2. Замеры (2026-10-14, копия реальных `config.msgpack`/`clinic.db`, старт GUI offscreen)

| Что | Сколько |
|---|---|
| Чтений `.env` (`get_getenv`) за старт | 34 |
| Перезаписей `.env` (`set_key`) за старт | 17 |
| Вызовов `get_config_env()` за старт | 12 |
| Одно `save()` без изменений | 5 сервисов переоткрывают БД, 8 перезаписей `.env` |
| Слушателей `save()` | 6 после старта → 11 после пересоздания сервисов |

---

## 3. Известные проблемы

### 3.1 `.env`

| # | Проблема |
|---|---|
| E1 | `get_getenv` считает пустое значение (`GITHUB_TOKEN=''`) отсутствующим и при каждом вызове переписывает `.env` (`set_key`) — 17 раз за старт |
| E2 | Если `.env` недоступен для записи (установка в `Program Files`, папка только для чтения, антивирус) — `PermissionError` при старте, **приложение не запускается** |
| E3 | `get_dotenv_path()` → `find_dotenv()` ищет `.env` от папки МОДУЛЯ вверх, а не от текущей папки: при разработке находится `.env` проекта независимо от того, откуда запущена программа; в собранном exe — не находится, берётся `.env` в текущей папке. Поведение разное в разработке и в exe |
| E4 | Чтение конфига создаёт пустой `.env`, если его нет (`crete_env_file`) — побочный эффект чтения |
| E5 | `load_dotenv` при каждом чтении загружает ВСЕ ключи `.env` в `os.environ` |
| E6 | `AppConfigManager.get_instance()` без пути при каждом вызове заново читает `.env` (через `_old_get_config_env`), хотя путь к конфигу за время работы не меняется |

### 3.2 `config.msgpack`

| # | Проблема |
|---|---|
| M1 | Повреждённый `config.msgpack` → исключение в `_load()` → приложение не запускается (обработка ошибок закомментирована; тест фиксирует исключение) |
| M2 | `save()` не атомарный: файл открывается на запись (обнуляется) до `msgpack.pack`; сбой посередине → пустой/битый файл → M1 при следующем запуске |
| M3 | Слушатели — общий классовый список `BaseConfigManager._listeners`: общий для всех менеджеров и путей; не очищается — каждый новый экземпляр сервиса добавляет слушателя, старые остаются (утечка: 6 → 11) и продолжают переоткрывать БД |
| M4 | Любой `save()` перезагружает все сервисы (закрыть/открыть БД), даже если менялись только настройки логирования или ничего |
| M5 | Ошибка в слушателе печатается `print` в stdout, а не в лог |
| M6 | Типы значений смешаны: умолчания — строки (`'False'`, `'10485760'`), экран настроек сохраняет `bool`/`int` |

### 3.3 `ConfigApplier`

| # | Проблема |
|---|---|
| A1 | `apply_database`, `apply_photos_storage`, `apply_sync`, `apply_backup` сравнивают новый конфиг с менеджером, который к моменту вызова уже сохранён → изменений «нет», методы ничего не делают (та же ошибка, что R1 у логирования, исправленная там через `AppLogger.current_app_config()`). На деле путь к БД/фото и токен применяются через слушателей `save()` (M4) — двойной механизм |
| A2 | `apply_sync`: `_thec_update_key_config` возвращает `(changed, value)`, а распаковывается как `rez, changed_` — после исправления A1 в `sync_service.token` записался бы `True` вместо токена |
| A3 | `apply_photos_storage` пишет приватный атрибут сервиса (`_storage_path`) |

---

## 4. План

1. Характеризующие тесты (поведение «как есть», баги — `xfail(strict=True)`), изоляция от
   `.env` проекта и реального `config.msgpack`.
2. `.env`: E1–E6.
3. `config.msgpack`: M1–M6.
4. `ConfigApplier`: A1–A3 и выбор одного механизма применения (слушатели или applier).
5. Докстринги и типизация (правило проекта), старый код — в комментариях.
