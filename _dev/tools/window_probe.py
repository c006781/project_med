# _dev/tools/window_probe.py

"""
Проверка главного окна без показа (offscreen) на ВРЕМЕННЫХ конфиге и базе.

Что проверяет: окно создаётся (``interfaces.gui.gui_window.main.main``), пилотный экран
«Наборы данных» открывается кнопкой, данные грузятся (пациент → приём), правка через
черновики не пишет в БД до «Сохранить», «Сохранить» пишет одной транзакцией, правка,
не завершённая при закрытии окна, сохраняется по ответу «сохранить» (F7).

Рабочие ``.env``, ``config.msgpack``, ``clinic.db``, журналы — не трогаются: всё во временной
папке (``PROJECT_MED_ENV_DIR``, ``APP_CONFIG_PATH`` задаются до импорта приложения).

Запуск (из корня проекта):
    Windows: .venv310/Scripts/python.exe -X utf8 _dev/tools/window_probe.py
    Linux:   <venv>/bin/python -X utf8 _dev/tools/window_probe.py

Вывод: строки «что — результат»; ожидаемое — в конце каждой строки (True, «Сохранено» …).
Создан 2026-10-18 (сессия Windows), перенесён в _dev/tools 2026-10-25.
"""

import datetime
import os
import sys
import tempfile
from typing import Any, List

import msgpack

# Корень проекта — две папки выше этого файла (_dev/tools/…)
ROOT: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Временные настройки — ДО импорта приложения (импорт читает .env и конфиг)
work: str = tempfile.mkdtemp(prefix='window_probe_')
config: str = os.path.join(work, 'config.msgpack')
with open(config, 'wb') as f:
    msgpack.pack(
        {
            'database_local_path': os.path.join(work, 'clinic.db'),  # временная база
            'PHOTOS_STORAGE_PATH': os.path.join(work, 'photos'),     # временное хранилище фото
            'LOG_DIR':             os.path.join(work, 'logs'),       # журналы — туда же
            'BACKUP_PATH':         os.path.join(work, 'backup'),
        },
        f,
    )
os.environ['APP_CONFIG_PATH'] = config
os.environ['PROJECT_MED_ENV_DIR'] = work
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

# Без цикла событий и без окон-вопросов: «да» / «ок» на всё
QApplication.exec = lambda self=None: 0
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)

from app.config.logging_setup import setup_logging  # noqa: E402

setup_logging()
import interfaces.gui.gui_window.main as gm  # noqa: E402
import interfaces.gui.gui_window.main_window as mw  # noqa: E402

windows: List[Any] = []
original = mw.MainWindow.__init__


def spy(self: Any, *args: Any, **kwargs: Any) -> None:
    """
    Запоминает созданное главное окно (``main()`` его не возвращает).

    Args:
        self: Окно.
        *args: Аргументы конструктора окна.
        **kwargs: Именованные аргументы конструктора.

    Returns:
        None

    Пример:
        >>> mw.MainWindow.__init__ = spy
    """
    original(self, *args, **kwargs)
    windows.append(self)


mw.MainWindow.__init__ = spy
try:
    gm.main()
except SystemExit:
    pass
w = windows[0]
from app.dependencies import get_appointment_service, get_db, get_patient_service  # noqa: E402
from app.dto.dto_all import AppointmentDTO, PatientDTO  # noqa: E402

print('база временная:', get_db().engine.url.database.startswith(work))
p = get_patient_service().create(
    PatientDTO(last_name='Иванов', first_name='Иван', birth_date=datetime.date(1980, 1, 1)),
)
get_appointment_service().create(
    AppointmentDTO(patient_id=p.id, date=datetime.date(2026, 10, 1), reason_text='осмотр'),
)

page = w.dataset_pilot_page
print('пилот создан:', type(page).__name__, '| черновики окна:', page.drafts is w.drafts)
w.dataset_pilot_btn.click()
print('текущая страница — пилот:', w.stacked_widget.currentWidget() is page)
page.open_data()
print('пациентов:', page.models['patients'].rowCount(), '| приёмов:', page.models['appointments'].rowCount(),
      '| ФИО у приёма:', page.clinic.appointments.value('patient_name'))
page.clinic.patients.set_value('phone', '+7 999')
page.clinic.patients.post()
print('статус строки:', page.clinic.patients.row_status(0),
      '| в БД до сохранения (ждём None):', get_patient_service().get_by_id(p.id).phone)
print('сохранено:', page.save(current=False), '| в БД:', get_patient_service().get_by_id(p.id).phone,
      '| черновики пусты:', w.drafts.store.is_empty)
print('строка состояния:', page.status.text())

# F7: правка не завершена → закрытие окна → «сохранить» → в БД
import interfaces.gui.gui_window.drafts_qt as dq  # noqa: E402

dq.ask_on_close = lambda parent: 'save'
phone = next(b.widget for b in page.bindings if b.field == 'phone')
phone.textEdited.emit('+7 777')
print('до закрытия: правка идёт:', page.clinic.patients.state.value, '| черновики пусты:', w.drafts.store.is_empty)
w.close()
print('после закрытия: в БД (ждём +7 777):', get_patient_service().get_by_id(p.id).phone)
print('временная папка:', work)
