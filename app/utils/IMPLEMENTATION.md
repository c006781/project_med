# Утилиты (app/utils/*.py) — заметки о реализации

> Файл для разработчиков: что делают отдельные модули `app/utils/*.py`, почему так и журнал
> проверок. У подпакетов (`dataset`, `drafts`, `drafts_qt`, `filtering`, `logger`) — свои
> IMPLEMENTATION.md.
> Последнее обновление: 2026-10-21 (ветка `rework-file-deletions`).

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
проверка префикса хранилища строкой (ИДЕИ.txt И-10).

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

### Проход 2 — не выполнялся (colors, qt_meta — не проверены)
