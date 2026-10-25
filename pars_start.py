# pars_start.py

"""
Ручной запуск импорта данных из Word-документов (.docx) в базу.

Папка с документами — параметром командной строки ``--folder`` (обязателен); без
``--files`` обрабатываются все ещё не обработанные ``.docx`` папки (по журналу
``<папка>/logs_parser/parser.log``). В конце печатаются итоги: число файлов, ошибки,
предупреждения (например, нераспознанный телефон — не записан), путь к журналу.

Пишет в рабочую базу из настроек программы (``config.msgpack``).

Пример:
    python pars_start.py --folder "C:/Документы/Пациенты"
    python pars_start.py --folder ./doc --files тест1.docx,тест2.docx
    python pars_start.py --help
"""

from parsers.word_importer import format_results, pars_start_args
from app.config.logging_setup import setup_logging


if __name__ == "__main__":
    # Логгеры не читают конфиг сами: передаём его до любой работы.
    # См. app/utils/logger/IMPLEMENTATION.md §7.1.
    setup_logging()

    # Папка и файлы — из командной строки (--folder, --files)
    results = pars_start_args()

    # pars_start_args(
    #     folder = '/home/admin-rkc/Git/My_cods/project_med/doc',
    #     # files = [
    #     #     'тест1.docx',
    #     # ],
    # )
    # ↑ до 2026-10-25 (Ф1.1.7): папка была зашита (путь Linux — на Windows её нет) и
    #   перекрывала --folder; итоги не печатались.

    print(
        format_results(results),
    )
