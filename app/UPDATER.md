# Автообновление (app/updater.py) — заметки о реализации

> Файл для разработчиков: что делает модуль, как устроен, почему так и журнал проверок.
> Обновляется вместе с кодом.
> Последнее обновление: 2026-10-31, проход 4 — проверка файла релиза по SHA-256
> (ветка `rework_work/updater`); проходы 1–3 — 2026-10-21 (ветка `rework-updater`).

| Что | Где |
|---|---|
| Модуль | [updater.py](updater.py) |
| Окно (`UpdateMixin`, автопроверка при старте) | [main_window.py](../interfaces/gui/gui_window/main_window.py) |
| Переименование нового exe после замены (`--rename-to`) | [main_gui_window.py](../main_gui_window.py) |
| Версия программы / репозиторий | [VERSION](../VERSION), `app/config/__init__.py` (`APP_VERSION`, `GITHUB_REPO_SLUG`) |
| Публикация хешей SHA-256 в описании релиза | [release.yml](../.github/workflows/release.yml) (задача `create-release`) |
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
       ├─ release_asset_sha256(release, имя файла) → нет хеша → warning (журнал + сигнал), дальше
       └─ UpdateDownloader (QThread): <exe_dir>/MedicalApp_new_<t>.exe.part → проверка
          размера → file_sha256(.part) == хеш релиза? (нет → error, .part удаляется)
          → os.replace → UpdateApplier._apply_update()
            └─ build_windows_update_script → update.ps1 (ждёт выхода, удаляет старый exe,
               запускает новый с --rename-to <старое имя>) → выход из программы
```

Логика без Qt — функции модуля: `normalize_version`, `parse_version`, `is_newer_version`,
`mask_token`, `github_headers`, `current_system`, `select_release_asset`, `update_file_name`,
`parse_release_hashes`, `release_asset_sha256`, `file_sha256`, `build_windows_update_script`,
`auto_update_unavailable_reason`. Справочники:
`ASSET_RULES`, `UPDATE_FILE_EXTENSIONS`, `AUTO_UPDATE_SYSTEMS`, `DOWNLOAD_CHUNK_SIZE`.

Сигналы предупреждений (2026-10-31): `UpdateApplier.warning(str)` →
`AppUpdater.download_warning(str)` — установка продолжается (сейчас: в описании релиза нет
хеша выбранного файла). Окно пока не подключает — предупреждение только в журнале.

### Хеш файла релиза (SHA-256)

* `release.yml`, задача `create-release`: после скачивания артефактов шаг «Compute SHA-256»
  пишет `release_hashes.md` — блок с выводом `sha256sum` (`<64 hex>  <имя файла>`, имена без
  пути); `softprops/action-gh-release@v2` берёт его в `body_path`, а с
  `generate_release_notes: true` ставит перед автоматическими заметками (body + notes).
* Программа: `UpdateChecker` уже получает весь JSON релиза (`body` в нём) →
  `AppUpdater.pending_release_data` → `UpdateApplier.start` ищет строку для имени выбранного
  файла (`release_asset_sha256`, без учёта регистра) → `UpdateDownloader(expected_sha256=…)`
  сверяет `.part` после проверки размера, ДО `os.replace`.
* Формат строки: как `sha256sum` — два пробела или ` *` (двоичный режим, так пишет
  `sha256sum` Git Bash); путь перед именем отбрасывается; повтор имени — действует первая
  строка.

### 1.1 Как добавить ОС

1. `ASSET_RULES[<ос>] = ((слова в имени,), (окончания,))` — выбор файла релиза.
2. `UPDATE_FILE_EXTENSIONS[<ос>]` — расширение скачанного файла.
3. Хеш — строка для имени файла новой ОС в `release.yml` (шаг «Compute SHA-256»).
4. Замена файла — ветка в `UpdateApplier._apply_update` (по образцу
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
| Хеш — в описании релиза, а не отдельным файлом релиза | Описание приходит в том же ответе API, что и список файлов (`UpdateChecker`), — второй запрос не нужен; отдельный `.sha256`-файл мог бы попасть под правила выбора файла ОС (`ASSET_RULES`) |
| Описание релиза получено по `urllib` с проверкой сертификата, файл — по `requests` | При токене (`verify=False`, ТД-4) хеш приходит по проверенному каналу — подмена файла при скачивании обнаружится сверкой |
| Релиз без хеша — предупредить и установить | Решение владельца 2026-10-31: старые релизы (до публикации хешей) должны ставиться; предупреждение — журнал и `download_warning` |
| Хеш считается по `.part` после скачивания (`file_sha256`), а не на лету | Проверяется ровно то, что лежит на диске и будет переименовано; файл читается порциями `DOWNLOAD_CHUNK_SIZE`, лишнее чтение ~100 МБ — доли секунды |
| `verify=False` при токене не менялся, добавлено предупреждение в журнал | Решение владельца 2026-10-31 (ТД-4: токен — только для тестирования); проверка на собранном exe — Ф3.5 |
| Ошибка сверки — `ValueError` в `UpdateDownloader.run` | Общая ветка `except` удаляет `.part` и шлёт `error(текст)` — установка не начинается |

---

## 2. Тесты

`tests/test_updater/` — 123 теста (2026-10-31; было 93 — 2026-10-21): функции, потоки (`run` с подменённым
`urlopen`/`requests.get`), `AppUpdater`, `UpdateApplier` (подмена ОС и `sys.frozen`),
примеры из докстрингов. Тесты прохода 1 проверены на старом модуле: 80 падают, 10
проходят — это тесты на поведение, которое не должно было измениться. Тесты прохода 4
(`test_updater_review_pass4.py`, 30) на старом модуле не собираются (нет `file_sha256` и др.);
файлы обоих ОС (`.exe`, `.tar.gz`); `release.yml` проверяется по тексту (шаг хешей,
`body_path`, `generate_release_notes`).

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

### Проход 4 (2026-10-31) — проверка файла релиза по SHA-256

| # | Что было | Почему плохо | Исправление |
|---|---|---|---|
| U14 | Скачанный файл релиза проверялся только по размеру | Подменённый (MITM, особенно при `verify=False` с токеном) или испорченный файл устанавливался | `release.yml` публикует `sha256sum` файлов в описании релиза; `parse_release_hashes`, `release_asset_sha256`, `file_sha256`; `UpdateDownloader(expected_sha256=…)` — сверка до `os.replace`, не совпал — `error`, `.part` удаляется |
| U15 | — (новое) | Релизы без хеша (старые) не должны ломать обновление | Хеша нет — `logger.warning` + `UpdateApplier.warning` → `AppUpdater.download_warning`, установка без сверки |
| U16 | `verify=False` при `GITHUB_TOKEN` — молча | В журнале не видно, что сертификат не проверялся | `logger.warning` (без токена); поведение не изменено (ТД-4) |
| U17 | Описание релиза — только автоматические заметки | Негде взять хеш | Шаг «Compute SHA-256» в `create-release`, `body_path` + `generate_release_notes` |

### Проход 5 (2026-10-31) — итоговая перепроверка модуля

| # | Что было | Почему плохо | Исправление |
|---|---|---|---|
| U18 | Вложенная `_name` в `select_release_asset` без докстринга и комментария параметра; `__init__` `UpdateChecker`, `UpdateApplier` без `-> None` | Правило проекта: докстринги и типы у всего | Докстринг, параметр на строку, `-> None` |
| U19 | Без `Example` — простые `current_system`, `UpdateChecker._parse_version`, `UpdateDownloader._remove_quietly`, `AppUpdater.pending_release_data`, `UpdateApplier.is_running` | Примеры проверяются `test_doctests` | Примеры добавлены |

Проверено и оставлено:
* `pyflakes`: 3 неиспользуемых импорта (`shutil`, `tempfile`, `AppConfigManager`) — были в
  модуле до переработки, оставлены по правилу проекта (проход 2).
* Без `Example` намеренно: методы потоков и сетевые (`is_github_reachable`, `_get_token`,
  `_build_request`, `_process_response`, оба `run`, `_get_headers`, `_download_file`,
  `check_for_updates`, `apply_update_from_release`, `download_update`, `apply_update`,
  `start`, `_apply_update`, обработчики сигналов) — пример ушёл бы в сеть, запустил поток или
  закрыл программу; их поведение проверяют тесты с подменой `urlopen` / `requests.get`.
* Старые докстринги в формате `имя (тип): …` (Google) не переводились в формат образца
  `имя : (тип)` — массово не переводить (решение владельца 2026-10-30).
* `AppUpdater.download_update` скачивает без сверки хеша: у него нет данных релиза (только
  адрес), окно его не вызывает — оставлено.

Полный набор: 2151 прошли, 0 падают, 8 пропущено, 5 xfail (было 2121 / 0 / 8 / 5 — +30
тестов прохода 4).

---

## 4. Дальше

* Окно (`UpdateMixin`): обработчики `_on_download_finished`/`_on_download_error`
  перекрыты одноимёнными `SyncMixin` (_dev/ОСТАЛОСЬ.md п. 1.4); `pending_release_data` вместо
  `hasattr`; `is_github_reachable()` при старте блокирует окно до 3 с.
* Окно: подключить `AppUpdater.download_warning` (показать предупреждение «нет контрольной
  суммы» — не мешая установке); ошибка сверки SHA-256 приходит в `download_error`, как раньше.
* ТЕХДОЛГ: ТД-4 (`verify=False` — проверка на собранном exe, Ф3.5), ТД-5 (автообновление на
  Linux — варианты у владельца).
* Первый релиз после правки — проверить описание (блок SHA-256 перед заметками) и обновление
  с ним; релиз до правки — предупреждение и установка.
