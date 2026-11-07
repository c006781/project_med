# tests/test_main_window/window_scenario.py
"""
Сценарии настоящего окна; запускается только подпроцессом из ``test_main_window_startup.py``.

Не тест и не импортируется набором тестов. Настройки, база, журналы — на временных путях, которые
задаёт запускающий тест через переменные окружения. Сеть запрещена на уровне сокетов: любая попытка
записывается и выводится. Клиент Диска подменён. Последняя строка вывода — итог в JSON.

Запуск: ``python window_scenario.py <сценарий> <рабочая папка>`` (сценарии — ``SCENARIOS``).
"""
import json
import os
import runpy
import socket
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable, Dict, List
from unittest.mock import MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

NETWORK_CALLS : List[str] = []
MESSAGES      : List[List[str]] = []


# запрет сети: попытка записывается и падает
def _block_network() -> None:
    """Заменяет соединение сокета и разрешение имён записью попытки и ошибкой."""
    def refuse(*args: Any, **kwargs: Any) -> Any:
        NETWORK_CALLS.append(repr(args[1:] if args else ()))
        raise OSError('сеть запрещена в проверке')

    socket.socket.connect = refuse
    socket.socket.connect_ex = refuse
    socket.getaddrinfo = refuse


# окна сообщений записываются; на вопрос — «да»
def _record_messages() -> None:
    """Подменяет окна сообщений записью."""
    from PySide6.QtWidgets import QMessageBox

    def record(kind: str) -> Any:
        def show(parent: Any, title: str, text: str, *args: Any, **kwargs: Any) -> Any:
            MESSAGES.append([kind, title, text])
            return QMessageBox.StandardButton.Yes if kind == 'question' else QMessageBox.StandardButton.Ok
        return staticmethod(show)

    for kind in ('question', 'warning', 'information', 'critical'):
        setattr(QMessageBox, kind, record(kind))


# прокрутка событий: таймеры окна срабатывают
def _pump(seconds: float, until: Callable[[], bool] = lambda: False) -> None:
    """Обрабатывает события Qt указанное время или до выполнения условия."""
    from PySide6.QtWidgets import QApplication
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and not until():
        QApplication.processEvents()
        time.sleep(0.01)


# окно на временной базе
def _create_window() -> Any:
    """Создаёт настоящее окно так же, как точка входа."""
    from PySide6.QtWidgets import QApplication
    from app.config.logging_setup import setup_logging
    setup_logging()
    QApplication.instance() or QApplication([])
    from interfaces.gui.gui_window.main_window import MainWindow
    return MainWindow()


def start(work: str) -> Dict[str, Any]:
    """Окно стартует, таймер проверки срабатывает; нет ни запроса к GitHub, ни вопроса."""
    _block_network()
    _record_messages()
    import app.updater as updater
    with patch.object(updater, 'is_github_reachable', MagicMock()) as reachable, \
         patch.object(updater.AppUpdater, 'check_for_updates', MagicMock()) as check:
        window = _create_window()
        _pump(2.0)
        result = {
            'page'      : window.page_manager.current_page_id,      # открытая страница
            'reachable' : reachable.call_count,                     # обращений к проверке связи
            'check'     : check.call_count,                         # запусков проверки обновлений
            'db_is_temp': _db_path().startswith(work),              # база временная
            'closed'    : window.close(),                           # закрылось без вопросов
        }
    return result


def _db_path() -> str:
    """Путь открытой общей базы."""
    from app.dependencies import get_db
    return os.path.abspath(get_db().engine.url.database)


def entry_point(work: str) -> Dict[str, Any]:
    """Настоящая точка входа ``main_gui_window.py`` без цикла событий."""
    _block_network()
    _record_messages()
    from PySide6.QtWidgets import QApplication
    QApplication.exec = lambda *args: 0
    code = 0
    try:
        runpy.run_path(os.path.join(ROOT, 'main_gui_window.py'), run_name='__main__')
    except SystemExit as exc:
        code = exc.code or 0
    return {'code': code}


def cli_help(work: str) -> Dict[str, Any]:
    """Настоящая точка входа ``main_cli.py --help``."""
    _block_network()
    sys.argv = ['main_cli.py', '--help']
    code = 0
    try:
        runpy.run_path(os.path.join(ROOT, 'main_cli.py'), run_name='__main__')
    except SystemExit as exc:
        code = exc.code or 0
    return {'code': code}


def _patient_names() -> List[str]:
    """Фамилии пациентов через сервис окна."""
    from app.dependencies import get_patient_service
    return sorted(p.last_name for p in get_patient_service().get_all_patients())


def _add_patient(name: str) -> None:
    """Добавляет пациента через сервис."""
    from app.dependencies import get_patient_service
    from app.dto.dto_all import PatientDTO
    get_patient_service().create(
        PatientDTO(
            last_name   =   name,                   # фамилия
            first_name  =   'Тест',                 # имя
            birth_date  =   date(1980, 1, 1),       # дата рождения
        ),
    )


# образ базы «на Диске»: копия рабочей с другим пациентом
def _remote_bytes(work: str, name: str, revision: str = '') -> bytes:
    """Создаёт файл базы с другим пациентом и возвращает его байты; рабочая база не меняется."""
    from app.dependencies import get_db
    path = os.path.join(work, 'remote-source.db')
    source = sqlite3.connect(_db_path())
    target = sqlite3.connect(path)
    with target:
        source.backup(target)
    source.close()
    with target:
        target.execute('UPDATE patients SET last_name = ?', (name,))
        if revision:
            target.execute('UPDATE alembic_version SET version_num = ?', (revision,))
    target.close()
    get_db()
    with open(path, 'rb') as file:
        data = file.read()
    os.remove(path)
    return data


# подменённый Диск с этими байтами
def _disk_client(data: bytes, fail_after: Any = None) -> MagicMock:
    """Клиент Диска: отдаёт байты или обрывает скачивание."""
    import hashlib

    def download(src: str, dst: str, progress_callback: Any = None) -> None:
        with open(dst, 'wb') as file:
            if fail_after is not None:
                file.write(data[:fail_after])
                raise ConnectionError('обрыв соединения')
            file.write(data)

    client = MagicMock(name='YaDisk')
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.check_token.return_value = True
    client.get_meta.return_value = SimpleNamespace(
        type        =   'file',                                     # файл
        size        =   len(data),                                  # размер
        md5         =   hashlib.md5(data).hexdigest(),              # контрольная сумма
        modified    =   datetime.now(timezone.utc) + timedelta(hours=1),  # новее рабочей
    )
    client.download.side_effect = download
    return client


# скачивание настоящим потоком до конца
def _run_download(window: Any, client: MagicMock) -> None:
    """Запускает скачивание окна с подменённым клиентом и ждёт конца передачи."""
    import app.network.ya_dop as ya_module
    with patch.object(ya_module.yadisk, 'YaDisk', return_value=client):
        window._start_download()
        _pump(20.0, lambda: not window._transfer_running)
        window.download_thread.wait(5000)
        _pump(0.1)


def db_replace(work: str) -> Dict[str, Any]:
    """Обрыв не меняет базу; успешное скачивание заменяет её, страницы и сервисы видят новую."""
    _block_network()
    _record_messages()
    os.environ['PROJECT_MED_NO_UPDATE_CHECK'] = '1'
    window = _create_window()
    _add_patient('Локальный')
    remote = _remote_bytes(work, 'СДиска')
    db_path = _db_path()
    folder = os.path.dirname(db_path)

    _run_download(window, _disk_client(remote, fail_after=500))
    after_break = _patient_names()
    files_after_break = sorted(os.listdir(folder))
    message_after_break = MESSAGES[-1][1]
    backups_after_break = len(os.listdir(os.path.join(work, 'копии')))

    # Экран наборов данных открыт, на нём несохранённая правка; вопрос о потере — ответ «да»
    pilot = window.dataset_pilot_page
    pilot.open_data()
    pilot.clinic.patients.set_value('phone', '+7 000')
    pilot.clinic.patients.post()
    drafts_before = window.drafts.store.is_empty

    _run_download(window, _disk_client(remote))
    after_replace = _patient_names()
    pilot_name = pilot.clinic.patients.value('last_name')
    model = window.patient_list_page.table.model
    table_text = [
        str(model.index(row, column).data())
        for row in range(model.rowCount())
        for column in range(model.columnCount())
    ]
    backups = sorted(os.listdir(os.path.join(work, 'копии')))
    copy = sqlite3.connect(os.path.join(work, 'копии', backups[-1]))
    in_copy = [row[0] for row in copy.execute('SELECT last_name FROM patients')]
    copy.close()
    return {
        'after_break'   : after_break,                  # база после обрыва
        'break_files'   : files_after_break,            # файлы рядом с базой
        'break_title'   : message_after_break,          # сообщение
        'break_backups' : backups_after_break,          # копия до передачи
        'after_replace' : after_replace,                # база после замены
        'drafts_before' : drafts_before,                # черновики до замены пусты
        'drafts_after'  : window.drafts.store.is_empty, # черновики после замены пусты
        'can_undo'      : window.drafts.store.can_undo, # отмена после замены
        'pilot_name'    : pilot_name,                   # экран наборов данных
        'questions'     : [m[1] for m in MESSAGES if m[0] == 'question'],   # вопросы
        'in_copy'       : in_copy,                      # пациенты в копии
        'backups'       : len(backups),                 # всего копий
        'table_text'    : table_text,                   # ячейки страницы пациентов
        'files'         : sorted(os.listdir(folder)),   # файлы рядом с базой
        'closed'        : window.close(),               # окно закрывается
    }


def db_newer_revision(work: str) -> Dict[str, Any]:
    """Скачанная база новее программы: прежняя возвращается и работает, пользователь знает причину."""
    _block_network()
    _record_messages()
    os.environ['PROJECT_MED_NO_UPDATE_CHECK'] = '1'
    window = _create_window()
    _add_patient('Локальный')
    remote = _remote_bytes(work, 'СДиска', revision='future_revision')
    _run_download(window, _disk_client(remote))
    _add_patient('ПослеОтката')
    return {
        'patients' : _patient_names(),                              # рабочая база
        'titles'   : [message[1] for message in MESSAGES],          # заголовки сообщений
        'files'    : sorted(os.listdir(os.path.dirname(_db_path()))),   # файлы рядом с базой
        'closed'   : window.close(),                                # окно закрывается
    }


SCENARIOS : Dict[str, Callable[[str], Dict[str, Any]]] = {
    'start'             : start,                # старт и таймер
    'entry_point'       : entry_point,          # main_gui_window.py
    'cli_help'          : cli_help,             # main_cli.py --help
    'db_replace'        : db_replace,           # обрыв и замена базы
    'db_newer_revision' : db_newer_revision,    # база новее программы
}


if __name__ == '__main__':
    outcome = SCENARIOS[sys.argv[1]](sys.argv[2])
    outcome['network'] = NETWORK_CALLS
    print('\n' + json.dumps(outcome, ensure_ascii=False, default=str))
    sys.stdout.flush()
    os._exit(0)  # без уборки Qt при выходе: итог уже выведен
