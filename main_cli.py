# main_cli.py

"""
Точка входа консольного интерфейса.

Без аргументов запускает интерактивное меню, с аргументами — команды click.

Пример:
    python main_cli.py              # меню
    python main_cli.py --help       # список команд
"""

import sys
import interfaces.cli.cli as cli
from app.config.logging_setup import setup_logging


if __name__ == '__main__':
    # Логгеры не читают конфиг сами: передаём его до любой работы.
    # См. app/utils/logger/IMPLEMENTATION.md §7.1.
    setup_logging()

    cli.start_cli(len(sys.argv) == 1)
