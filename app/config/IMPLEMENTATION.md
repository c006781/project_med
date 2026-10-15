# Конфигурация приложения — заметки о реализации

> Файл для разработчиков: что делает модуль, как он устроен, где проблемы и почему он
> устроен именно так. Обновляется вместе с кодом.
> Последнее обновление: 2026-10-15, рефакторинг E1/E2/E6, M1–M5, A1/A2 (ветка `rework-config`).

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

С 2026-10-15 настройки применяет **только `ConfigApplier`** (решение владельца):

```
SettingsPage._save:
  old = manager.get_all().copy()                    # снимок ДО сохранения
  manager.set(...)…; manager.save()                 # атомарно; слушателей нет
  new = manager.get_all()
  blocks = ConfigApplier().apply_changes(old, new)  # только изменившиеся блоки
  main_window.on_settings_changed(blocks)           # обновление страниц/виджетов
```

* `database` — `reload_config()` у сервисов из кэша `dependencies` (те же объекты, что у
  страниц GUI; кэш не очищается);
* `photos` — новая папка в сервисе фото; `sync` — токен и пути в `SyncService`;
* `logging_*` — `AppLogger.configure(new)`; `backup` — только запись в лог.

`apply_*(new, old=None)`: без снимка — принудительно (CLI `apply_settings` после ручной
правки файла).

**Как было до 2026-10-15:** сервисы подписывались на `save()` и при ЛЮБОМ сохранении
переоткрывали БД; `ConfigApplier.apply_*` сравнивали с уже сохранённым менеджером и ничего
не делали. API слушателей (`add_change_listener`) оставлен — подписчиков в приложении нет.

---

## 2. Замеры (2026-10-14, копия реальных `config.msgpack`/`clinic.db`, старт GUI offscreen)

| Что | Сколько |
|---|---|
| Чтений `.env` (`get_getenv`) за старт | 34 |
| Перезаписей `.env` (`set_key`) за старт | 17 |
| Вызовов `get_config_env()` за старт | 12 |
| Одно `save()` без изменений | 5 сервисов переоткрывают БД, 8 перезаписей `.env` |
| Слушателей `save()` | 6 после старта → 11 после пересоздания сервисов |

После рефакторинга (2026-10-15): чтений `.env` за старт — **2**, перезаписей — **0**;
`save()` без изменений — **0** переоткрытий БД и **0** перезаписей `.env`; слушателей — **0**.

---

## 3. Известные проблемы

Статусы: ✅ — исправлено (тест рядом), ⏳ — отложено.

### 3.1 `.env`

| # | Проблема |
|---|---|
| ✅ E1 |`get_getenv` считает пустое значение (`GITHUB_TOKEN=''`) отсутствующим и при каждом вызове переписывает `.env` (`set_key`) — 17 раз за старт |
| ✅ E2 |Если `.env` недоступен для записи (установка в `Program Files`, папка только для чтения, антивирус) — `PermissionError` при старте, **приложение не запускается** |
| ⏳ E3 (решение отложено владельцем) |`get_dotenv_path()` → `find_dotenv()` ищет `.env` от папки МОДУЛЯ вверх, а не от текущей папки: при разработке находится `.env` проекта независимо от того, откуда запущена программа; в собранном exe — не находится, берётся `.env` в текущей папке. Поведение разное в разработке и в exe |
| ⏳ E4 (оставлено: .env создаётся с умолчаниями — так задумано) |Чтение конфига создаёт пустой `.env`, если его нет (`crete_env_file`) — побочный эффект чтения |
| ⏳ E5 |`load_dotenv` при каждом чтении загружает ВСЕ ключи `.env` в `os.environ` |
| ✅ E6 |`AppConfigManager.get_instance()` без пути при каждом вызове заново читает `.env` (через `_old_get_config_env`), хотя путь к конфигу за время работы не меняется |

### 3.2 `config.msgpack`

| # | Проблема |
|---|---|
| ✅ M1 |Повреждённый `config.msgpack` → исключение в `_load()` → приложение не запускается (обработка ошибок закомментирована; тест фиксирует исключение) |
| ✅ M2 |`save()` не атомарный: файл открывается на запись (обнуляется) до `msgpack.pack`; сбой посередине → пустой/битый файл → M1 при следующем запуске |
| ✅ M3 |Слушатели — общий классовый список `BaseConfigManager._listeners`: общий для всех менеджеров и путей; не очищается — каждый новый экземпляр сервиса добавляет слушателя, старые остаются (утечка: 6 → 11) и продолжают переоткрывать БД |
| ✅ M4 |Любой `save()` перезагружает все сервисы (закрыть/открыть БД), даже если менялись только настройки логирования или ничего |
| ✅ M5 |Ошибка в слушателе печатается `print` в stdout, а не в лог |
| ⏳ M6 |Типы значений смешаны: умолчания — строки (`'False'`, `'10485760'`), экран настроек сохраняет `bool`/`int` |

### 3.3 `ConfigApplier`

| # | Проблема |
|---|---|
| ✅ A1 |`apply_database`, `apply_photos_storage`, `apply_sync`, `apply_backup` сравнивают новый конфиг с менеджером, который к моменту вызова уже сохранён → изменений «нет», методы ничего не делают (та же ошибка, что R1 у логирования, исправленная там через `AppLogger.current_app_config()`). На деле путь к БД/фото и токен применяются через слушателей `save()` (M4) — двойной механизм |
| ✅ A2 |`apply_sync`: `_thec_update_key_config` возвращает `(changed, value)`, а распаковывается как `rez, changed_` — после исправления A1 в `sync_service.token` записался бы `True` вместо токена |
| ✅ A3 | `apply_photos_storage` пишет `_storage_path` сервиса фото — это свойство с сеттером, проблемы нет |

---

## 4. Решения и детали

* **E1.** Возвращаемое значение не изменилось: пустое → значение по умолчанию.
  Изменилось условие ЗАПИСИ: дописывается только ключ, которого нет в самом файле
  (`_key_in_file`, через `dotenv_values`).
* **E2.** Ошибка записи/создания .env → предупреждение в stderr (`_report`), значение по
  умолчанию в памяти. Логгер не используется: .env читается до настройки логирования.
* **E6.** `AppConfigManager._default_config_path()` читает `APP_CONFIG_PATH` один раз;
  `reset_default_config_path()` — перечитать.
* **M1.** Битый файл или «не словарь» → `config.msgpack.broken-<ГГГГММДД_ЧЧММСС>`, новый
  файл с умолчаниями, ERROR в лог; `broken_config_backup` / `broken_config_message` у
  менеджера; `MainWindow` показывает окно «Конфигурация восстановлена» и открывает
  настройки. Переименовать не удалось → новый файл НЕ пишется (битый не затирается).
* **M3.** Слушатели-методы — `weakref.WeakMethod`; функции/лямбды — обычные ссылки.

## 5. План / что дальше

1. ✅ Характеризующие тесты, изоляция (`tests/test_config/conftest.py`).
2. ✅ `.env`: E1, E2, E6.
3. ✅ `config.msgpack`: M1–M5.
4. ✅ Только `ConfigApplier`: A1, A2, M4.
5. ✅ Докстринги и типизация всех функций модуля.
6. ⏳ E3 — где искать .env (отложено владельцем), M6 — единые типы значений.

Замечено вне модуля: `TextEditPopupDelegate.eventFilter` обращается к `self.logger`,
которого нет (`interfaces/gui/gui_window/widgets/delegate/type_delegate.py:400`) —
AttributeError в обработчике событий Qt.
