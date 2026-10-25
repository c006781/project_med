# app/utils/__init__.py

"""
Утилиты приложения, не зависящие от конкретных таблиц.

Модули (подробнее — ``app/utils/IMPLEMENTATION.md``): ``file_deletions`` — удаление файлов
сразу или после COMMIT/ROLLBACK, поиск файла фото; ``deferred_actions`` — действия после
COMMIT/ROLLBACK; ``virtual_fields`` — вычисляемые поля DTO; ``colors`` — цвета строк
таблиц; ``qt_meta`` — метакласс ``QObject`` + ``ABC``. Подпакеты ``dataset``, ``dataset_qt``,
``drafts``, ``drafts_qt``, ``filtering``, ``logger`` — со своими ``IMPLEMENTATION.md``.

Пакет ничего не импортирует сам (импорт ``app.utils`` не тянет Qt и SQLAlchemy).

Пример:
    >>> from app.utils.file_deletions import resolve_photo_path
"""