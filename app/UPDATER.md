# Автообновление (app/updater.py) — заметки о реализации

> Файл для разработчиков: что делает модуль, как устроен, почему так и журнал проверок.
> Обновляется вместе с кодом.
> Последнее обновление: 2026-10-21, проходы 1–3 (ветка `rework-updater`).

| Что | Где |
|---|---|
| Модуль | [updater.py](updater.py) |
| Окно (`UpdateMixin`, автопроверка при старте) | [main_window.py](../interfaces/gui/gui_window/main_window.py) |
| Переименование нового exe после замены (`--rename-to`) | [main_gui_window.py](../main_gui_window.py) |
| Версия программы / репозиторий | [VERSION](../VERSION), `app/config/__init__.py` (`APP_VERSION`, `GITHUB_REPO_SLUG`) |
| Тесты | [tests/test_updater/](../tests/test_updater/) |

---

## 1. Как устроено

```
AppUpdater.check_for_updates()
  └─ UpdateChecker (QThread): GET api.github.com/repos/<slug>/releases/latest
       └─ is_newer_version(APP_VERSION, tag) → update_available(tag, url) | no_update | check_error
окно: «Скачать и установить» → AppUpdater.apply_update_from_release(pending_release_data)
  └─ UpdateApplier.start()
       ├─ auto_update_unavailable_reason(ОС, собран?) → error ДО скачивания
       ├─ select_release_asset(assets, ОС) → нет файла → error
       └─ UpdateDownloader (QThread): <exe_dir>/MedicalApp_new_<t>.exe.part → проверка
          размера → os.replace → UpdateApplier._apply_update()
            └─ build_windows_update_script → update.ps1 (ждёт выхода, удаляет старый exe,
               запускает новый с --rename-to <старое имя>) → выход из программы
```

Логика без Qt — функции модуля: `normalize_version`, `parse_version`, `is_newer_version`,
`mask_token`, `github_headers`, `current_system`, `select_release_asset`, `update_file_name`,
`build_windows_update_script`, `auto_update_unavailable_reason`. Справочники:
`ASSET_RULES`, `UPDATE_FILE_EXTENSIONS`, `AUTO_UPDATE_SYSTEMS`, `DOWNLOAD_CHUNK_SIZE`.

### 1.1 Как добавить ОС

1. `ASSET_RULES[<ос>] = ((слова в имени,), (окончания,))` — выбор файла релиза.
2. `UPDATE_FILE_EXTENSIONS[<ос>]` — расширение скачанного файла.
3. Замена файла — ветка в `UpdateApplier._apply_update` (по образцу
   `build_windows_update_script` — отдельная функция-генератор скрипта) и ОС в
   `AUTO_UPDATE_SYSTEMS`.

Тест `test_u2_rules_cover_extensions` проверяет, что справочники согласованы.

### 1.2 Решения

| Решение | Почему |
|---|---|
| Версии сравниваются кортежами чисел, завершающие нули отбрасываются | `1.10 > 1.9`, `1.0 == 1.0.0`; непонятный номер (`1.0-beta`) — «обновления нет»: безопаснее, чем предложить откат |
| Проверка «можно ли установить» — до скачивания | Раньше из исходников и на Linux файл скачивался, а потом ошибка (на Linux — `AttributeError`) |
| Скачивание во временный `.part`, проверка `Content-Length` | Оборванное скачивание раньше давало «успех» и недокачанный exe запускался скриптом замены |
| Токен в журнале — `mask_token` | Раньше токен GitHub целиком писался в журнал (DEBUG) |
| `verify=False` для приватного репозитория оставлен | Без проверки на собранном exe нельзя убедиться, что с certifi `SSLEOFError` ушёл — ТЕХДОЛГ ТД-4 |
| Скрипт PowerShell — функция `build_windows_update_script` | Текст не изменился (тест сравнения со старым выводом при переносе); теперь проверяется тестами |
| Имена классов, сигналов, `UpdateChecker._parse_version` сохранены | Окно и `main_gui_window.py` менять не нужно; `_parse_version` вызывает `is_newer_version` |
| Прежний код — в комментарии внизу файла | Правило проекта |

---

## 2. Тесты

`tests/test_updater/` — 93 теста (2026-10-21): функции, потоки (`run` с подменённым
`urlopen`/`requests.get`), `AppUpdater`, `UpdateApplier` (подмена ОС и `sys.frozen`),
примеры из докстрингов. Тесты прохода 1 проверены на старом модуле: 80 падают, 10
проходят — это тесты на поведение, которое не должно было измениться.

---

## 3. Журнал проверок

### Проход 1 (2026-10-21)

| # | Что было | Почему плохо | Исправление |
|---|---|---|---|
| U1 | `_apply_update` — только Windows (`subprocess.STARTUPINFO`) | На Linux после скачивания — `AttributeError` в обработчике | `auto_update_unavailable_reason`: на не-Windows — понятное сообщение, до скачивания |
| U2 | Имя нового файла всегда `….exe` | На Linux архив `.tar.gz` сохранялся как `.exe` | `update_file_name` по ОС |
| U3 | Выбор файла релиза — два копипаст-цикла с вложенной функцией | Новую ОС не добавить без правки логики | `select_release_asset` по `ASSET_RULES` |
| U4 | `_parse_version`: сравнение только «меньше» по частям | `2.0 → 1.5` и `1.0 → 1.0.0` — «есть обновление»: предлагался откат на старую версию | `is_newer_version` (кортежи чисел) |
| U5 | Проверка «собранная ли программа» — после скачивания | Из исходников файл качался зря | Проверка до скачивания |
| U6 | Скачивание прямо в целевой файл, размер не проверялся, ответ не закрывался | Обрыв — «успех», недокачанный exe запускался; висящие соединения | `.part` → проверка размера → `os.replace`; при ошибке `.part` удаляется; `with requests.get(...)` |
| U7 | Токен GitHub целиком в журнале (`_build_request`, `_get_headers`) | Утечка токена через файлы журнала | `mask_token` |
| U8 | `_pending_release_data` появлялся только после проверки; `KeyError` при отсутствии `tag_name`/`html_url`; повторный «Скачать» запускал второе скачивание | Окно проверяло приватный атрибут через `hasattr` | `pending_release_data` (свойство), `.get`, `UpdateApplier.is_running` |
| U9 | `download_update` передавал папку как путь файла | `open(папка, 'wb')` — ошибка | Путь файла в `MedicalAppUpdates` |
| U12 | `applier.finished()` (без аргументов) подключён к `download_finished(str)` | Сигнал не испускается; связь ложная | Связь убрана (в комментарии) |
| U13 | Ответ не объект (`list`) | `AttributeError` в потоке | `ValueError` → `error` |

### Проход 2 (2026-10-21)

| # | Что было | Почему плохо | Исправление |
|---|---|---|---|
| U10 | `'assets': null` в ответе | `TypeError` в `select_release_asset` | `assets or []` |
| U11 | `UpdateApplier(None)` | Окно проверяет `hasattr(_pending_release_data)` — теперь атрибут есть всегда (`None`) → `AttributeError` | `release_data or {}` → «нет файла обновления» |

Проверено и оставлено: порядок `except` в `UpdateDownloader.run` (`requests.ConnectionError`
— подкласс `OSError`, ловится раньше); неиспользуемые импорты `shutil`, `tempfile`,
`AppConfigManager` (были раньше — правило проекта).

### Проход 3 (2026-10-21) — замечаний нет

Полный набор: 1557 прошли, 10 известных падений, новых нет.

---

## 4. Дальше

* Окно (`UpdateMixin`): обработчики `_on_download_finished`/`_on_download_error`
  перекрыты одноимёнными `SyncMixin` (_dev/ОСТАЛОСЬ.md п. 1.4); `pending_release_data` вместо
  `hasattr`; `is_github_reachable()` при старте блокирует окно до 3 с.
* ТЕХДОЛГ: ТД-4 (`verify=False`), ТД-5 (автообновление на Linux).
