# Утилиты (app/utils/*.py) — заметки о реализации

> Файл для разработчиков: что делают отдельные модули `app/utils/*.py`, почему так и журнал
> проверок. У подпакетов (`dataset`, `drafts`, `drafts_qt`, `filtering`, `logger`) — свои
> IMPLEMENTATION.md.
> Последнее обновление: 2026-10-25 (ветка `rework-windows-baseline`).

| Файл | Назначение | Проверен |
|---|---|---|
| [file_deletions.py](file_deletions.py) | Удаление файлов/папок сразу или после COMMIT/ROLLBACK сессии (`DeletionContext`, `schedule_deletion`), копирование во временную папку, поиск файла фото | 2026-10-21, проход 1 |
| [deferred_actions.py](deferred_actions.py) | Действия после COMMIT/ROLLBACK сессии (`ActionContext`, `add_deferred_action`, `execute_actions` — в цикле событий Qt) | 2026-10-21, проход 1 |
| [virtual_fields.py](virtual_fields.py) | Виртуальные поля DTO: `compute_virtual_fields` (по `compute` в конфигурации), `enrich_dto_with_computed_fields` | 2026-10-21, проход 1 |
| [colors.py](colors.py), [qt_meta.py](qt_meta.py) | Цвета интерфейса; метакласс Qt + ABC | нет |

Обработчики `after_commit`/`after_rollback`, которые выполняют накопленные удаления и
действия, регистрирует `app/database/database.py`.

## Журнал проверок

### Проход 1 (2026-10-21)

| # | Файл | Что было | Почему плохо | Исправление |
|---|---|---|---|---|
| FD1 | `file_deletions.py` | `DeletionContext.logger` — свойство экземпляра, вызывалось из метода класса; `_logger` не в `__slots__` | `DeletionContext.create(None, …)` — `AttributeError` вместо `None` («удалить сразу»): документированный `_del_file(path)` без сессии и очистка временной папки без сессии падали | Журнал класса `_get_logger()`; свойство экземпляра возвращает его |
| FD4 | `file_deletions.py` | Описания возвращаемых значений: `(False, Exception)` | Возвращается текст ошибки или `None` | Описания исправлены |
| FD6 | `file_deletions.py` | `copy_file_to_temp_dir` не создавал папку, хотя описание обещает | `FileNotFoundError` при отсутствии временной папки | `os.makedirs(..., exist_ok=True)` |
| DA1 | `deferred_actions.py` | Без журнала — `print` и вызов `print.debug`/`print.exception` | Выполненное действие — ошибка, затем `AttributeError` в таймере Qt | Журнал модуля по умолчанию |
| DA2 | `deferred_actions.py` | `f.__name__` в журнале | У `functools.partial`/объекта нет — успешное действие записывалось как ошибка | `action_name` |
| DA3 | `deferred_actions.py` | Всегда `QTimer.singleShot` | Без приложения Qt (командная строка, тесты) действия не выполнялись никогда | Без `QCoreApplication` — сразу |

Проверено и оставлено: неиспользуемые импорты (`weakref`, `QMetaObject`, `Qt`, `Q_ARG` —
были раньше, правило проекта); `del_file_and_parent_dir` для несуществующего пути —
`(False, None)` с предупреждением (вызывающие опираются на это); `resolve_photo_path` —
проверка префикса хранилища строкой (_dev/ИДЕИ.md И-10).

Тесты: `tests/test_file_deletions_review_pass1.py` (20; на старом коде 5 падают — FD1, FD6),
`tests/test_deferred_actions_review_pass1.py` (12, с настоящим циклом событий Qt; на
старом коде DA-тесты падают). Полный набор: 1745 прошли, 10 известных падений.

### virtual_fields.py, проход 1 (2026-10-21, ветка `rework-virtual-fields`)

| # | Что было | Почему плохо | Исправление |
|---|---|---|---|
| VF1 | Журнал в цикле проверял `arg_name in extra_data` до проверки на `None` | `compute_virtual_fields(data, configs)` без `extra_data` (по умолчанию) — `TypeError` на первом поле с аргументами | `extra_data = extra_data or {}` |

Проверено: аргументы вычислений клиники — связи (`description_note`, `patient` …), а не id
заметок — исключение id из `model_dump` (app/schema SC1) их не задевает.
Тесты: `tests/test_virtual_fields_review_pass1.py` (8; на старом коде 4 падают).

### Windows (2026-10-25, ветка `rework-windows-baseline`)

Первый полный прогон на Windows после правок 21.10 (эталон машины): кроме известных 7
падений командной строки упали 2 теста проходов 1 — на Linux проходили.

| # | Файл | Что было | Почему плохо | Исправление |
|---|---|---|---|---|
| FD-W1 | `file_deletions.py` | `resolve_photo_path` возвращал `os.path.join(папка, путь_из_БД)` как есть | На Windows путь из БД с `/` давал смешанные разделители (`…\photos\app_1/a.png`): один файл — два написания; кэш миниатюр `ImageThumbnailDelegate` (ключ — путь) загружал и держал его дважды, сравнение путей строкой — не совпадало | Результат — `os.path.normpath` (на Linux без изменений) |
| DA3-W | `tests/test_deferred_actions_review_pass1.py` | Подпроцесс с окружением `{'QT_QPA_PLATFORM', 'PATH': ''}` | На Windows Python без `SYSTEMROOT` не запускается («failed to get random numbers») — пустой вывод, `IndexError`; ошибка теста, не программы | Копия окружения `{**os.environ, …}` (как в `tests/test_logger`) — проверка та же, подпроцесс получает и временные `.env`/конфиг из `tests/conftest.py` |

Тесты: `test_resolve_photo_path`, `test_da3_with_qt_app_runs_in_event_loop` — на старом коде
на Windows падали, теперь проходят (32 из 32 в двух файлах).

### Проход 2 (2026-10-25, ветка `rework-w1-utils`, заход М5)

#### file_deletions.py

| # | Что было | Почему плохо | Исправление |
|---|---|---|---|
| FD7 | `del_file_and_parent_dir`: родитель удалялся `delete_empty_directory(parent, force=force)` | При `force=True` (папка черновика «со всем содержимым») и `remove_parent_if_empty=True` родитель удалялся **рекурсивно** — вместе с соседними файлами и папками; описание (и `_del_file` страниц/сервисов) обещает «только если стала пустой». Сейчас вызывающих с обоими флагами нет — ошибка скрытая | Родитель — всегда `force=False`; `force` действует только на сам объект |
| FD8 | `copy_file_to_temp_dir` при ошибке копирования вызывал `schedule_deletion(dest_path, remove_parent_if_empty=…)` | Копия не успела появиться (нет исходного файла, нет прав) — `del_file_and_parent_dir` выходит на «объекта нет» и до родителя не доходит: только что созданная (`makedirs`) пустая папка оставалась, хотя `remove_parent_if_empty` обещает её убрать | Копия есть — удалить её (с родителем, если пуст); копии нет и `remove_parent_if_empty` — удалить саму папку, если пуста (тоже через `schedule_deletion`, с `ctx` — отложенно) |
| FD9 | Списки `session._deletions[COMMIT/ROLLBACK]` очищаются только своим событием (обработчики `app/database/database.py`) | `Database.Session` — `scoped_session`: одна и та же сессия на поток, `close()` её не заменяет. Удаление «после коммита» из **откатившейся** транзакции выполняется следующим чужим коммитом; удаление «при откате» из **закоммиченной** транзакции (новый файл фото) — следующим чужим откатом: удаляется уже сохранённый файл. Воспроизведено (`tests/test_file_deletions_review_pass2.py`, xfail strict) | **Не исправлено — вне территории**: обработчики `after_commit`/`after_rollback` в `database.py` должны очищать и список противоположного типа (то же для отложенных действий — DA5) |

Проверено и оставлено: `schedule_deletion` с контекстом COMMIT и неактивной сессией
(`is_active=False` — после ошибки flush, транзакция будет откачена) удаляет **сразу**, хотя
коммита не будет (FD10 — вопрос владельцу; поведение старое).

Тесты: `tests/test_file_deletions_review_pass2.py` — FD7 (2), FD8 (4; на старом коде падают 3:
FD7 — 1, FD8 — 2), FD9 (2, xfail strict).
