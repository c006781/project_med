#!/bin/bash
# Запуск из любой текущей папки и по ссылке: venv и main_gui_window.py ищутся рядом со скриптом
cd -- "$(dirname -- "$(readlink -f -- "$0")")" || exit 1
# cd "$(dirname "$0")"
# ↑ до 2026-11-07 (U26): при запуске по символьной ссылке (ярлык) переход шёл в папку ссылки

# Обновление прервано сбоем или выключением: вернуть прежнюю версию (update.sh, app/UPDATER.md)
if [ -f .update_in_progress ]; then
    if [ -f update.sh ]; then
        if ! bash ./update.sh --recover; then
            echo "Обновление не завершено, программа не запущена. Подробности: update.log" >&2
            exit 1
        fi
    else
        echo "Предупреждение: обновление было прервано, а update.sh нет. Прежний код: backup_*" >&2
    fi
fi

if [ ! -x venv_project_med/bin/python ]; then
    echo "Нет окружения venv_project_med: сначала выполните ./install.sh" >&2
    exit 1
fi

# Интерпретатор окружения — напрямую: скрипт activate хранит прежний путь и после переименования
# папки установки молча подставил бы системный python
exec venv_project_med/bin/python main_gui_window.py "$@"
# source venv_project_med/bin/activate
# python main_gui_window.py
# ↑ до 2026-11-07 (U26): после переноса папки запускался чужой python из PATH
