# pars_start.py

"""
Ручной запуск импорта данных из Word-документов (.docx) в базу.

Папка с документами задаётся в вызове pars_start_args() ниже.

Пример:
    python pars_start.py
"""

from parsers.word_importer import pars_start_args
from app.config.logging_setup import setup_logging


if __name__ == "__main__":
    # Логгеры не читают конфиг сами: передаём его до любой работы.
    # См. app/utils/logger/IMPLEMENTATION.md §7.1.
    setup_logging()

    pars_start_args(
        folder = '/home/admin-rkc/Git/My_cods/project_med/doc',
        # files = [
        #     'тест1.docx',
        # ],
    )