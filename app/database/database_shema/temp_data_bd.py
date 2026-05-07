# app/database/database_shema/temp_data_bd.py
# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
# import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).


# def _add_package_name(
#     file_module: str = None,
#     levels_up: int = 3,           # <-- сколько уровней вверх до корня проекта
# ) -> None:
    
#     """
#     Что это (кратко): Добавляет корень проекта в sys.path и устанавливает правильный __package__.

#     Что это (максимально подробно): Эта функция настраивает окружение Python таким образом, чтобы можно было использовать относительные импорты (например, from .module import something) без необходимости запускать скрипт с флагом "-m" (как модуль). Она работает только если скрипт запущен напрямую (не импортирован). Функция получает абсолютный путь к текущему файлу, добавляет родительскую директорию в sys.path (список путей для поиска модулей), и устанавливает глобальную переменную __package__ как имя текущей директории. Это полезно в проектах с nested папками, где импорты могут сломаться.

#     Как работает: Сначала объявляется global __package__ для изменения системной переменной. Затем os.path.abspath(__file__) дает полный путь к скрипту, os.path.dirname убирает имя файла, оставляя папку. sys.path.append добавляет родительскую папку (dirname еще раз). Наконец, __package__ = basename(package_dir) — имя папки. Вызывается только в if __name__ == '__main__', чтобы не мешать, если скрипт импортирован.

#     Примеры запуска:
#     # В скрипте: if __name__ == '__main__': _add_package_name()
#     # После вызова: sys.path включает родительскую папку (например, '/path/to/modules'), __package__ = 'parsers_sheregeh'. Теперь относительные импорты работают.
#     # Если запустить как модуль (python -m script), функция не нужна, но она не навредит.
#     # Если не вызвать: относительный импорт from .module... может вызвать ImportError: attempted relative import with no known parent package.

#     :param file_module: (str) = обычно __file__  - указатель на путь к модулю, папку которого делаем пакетом для относительных импортов (содержит путь к текущему скрипту)
#     :param levels_up: (int) - на сколько уровней подниматься вверх до корня проекта
#                        (подберите под структуру вашего проекта)
#                        Примеры:
#                          2 → до папки app
#     """
#     if file_module is None:
#         file_module = __file__

#     # Получаем директорию текущего файла
#     current_dir = os.path.dirname(os.path.abspath(file_module))

#     # Поднимаемся на levels_up уровней вверх — это и будет корень проекта
#     project_root = current_dir
#     for _ in range(levels_up):
#         project_root = os.path.dirname(project_root)

#     # Добавляем корень проекта в начало sys.path (высокий приоритет)
#     if project_root not in sys.path:
#         sys.path.insert(0, project_root)

#     # Вычисляем правильное значение __package__
#     # Пример: /project_med/app/models/bd → "app.models.bd"
#     rel_path = os.path.relpath(current_dir, project_root)
    
#     if rel_path == '.':
#         package_name = ''
#     else:
#         package_name = rel_path.replace(os.sep, '.').strip('.')

#     # Устанавливаем __package__
#     global __package__
#     if package_name:
#         __package__ = package_name
#     else:
#         # Если мы в корне — можно оставить None или пустую строку
#         __package__ = None

# try:
from app.utils.logger import AppLogger
# except ImportError as e:
#     # try:
#     # Попытка абсолютного импорта, если модуль запущен как скрипт
#     _add_package_name(file_module = __file__,levels_up = 3)
#     from ...utils.logger import AppLogger
#     # except ImportError as e:
#     #     pass #  raise # e # pass

# try:
# Относительный импорт моделей — это и разрывает цикл!
from .clinic import Patient, Appointment, AppointmentNote, Photo
# from app.backend.bd.clinic import Patient, Appointment, AppointmentNote, Photo
    # from . import models
# except ImportError as e:
    # try:
    #     # Попытка абсолютного импорта, если модуль запущен как скрипт
    #     _add_package_name(file_module = __file__,levels_up = 1)

    #     from .clinic import Patient, Appointment, AppointmentNote, Photo
    #     # from . import models
    # except ImportError as e:
    #     pass #  raise # e # pass

# del temp_from
# 

from datetime import (
    date, 
    # datetime, 
    time
)

# Сторонние библиотеки

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@AppLogger.get_instance(
    name = 'temp_data_bd.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    # description="Заполняем БД тестовыми данными",
    level=AppLogger._parse_log_level('DEBUG')
)
def populate_test_data(session):
    """
    Заполняет БД тестовыми данными.
    Предполагается, что БД уже создана и таблицы существуют.
    """
    logger = AppLogger.get_instance(
        name = 'temp_data_bd.py',
        # share_file_with = 'user',
        enable_file_logging = 'user',
        use_name_in_filename = False, # 'user',
    )
    
    # Проверяем, есть ли уже данные (чтобы не дублировать)
    if session.query(Patient).count() > 0:
        logger.debug(
            f"База данных уже содержит данные. Пропускаем заполнение."
        )
        # print("База данных уже содержит данные. Пропускаем заполнение.")
        return

    logger.debug(
        f"Заполнение базы тестовыми данными..."
    )   

    # --- Создаём заметки, которые будут использоваться многократно ---
    # Для пациентов: description и comment
    desc1 = AppointmentNote(text="Аллергия на пенициллин, хронический гастрит")
    desc2 = AppointmentNote(text="Без особенностей")
    desc3 = AppointmentNote(text="Склонность к гипертонии")

    comm1 = AppointmentNote(text="Предпочитает утренние часы")
    comm2 = AppointmentNote(text="Нуждается в напоминании о приёме")
    comm3 = AppointmentNote(text="Инвалид 2-й группы")

    session.add_all(
        [desc1, desc2, desc3, comm1, comm2, comm3]
    )

    logger.debug(
        f"Заполнение ТБ 'Пациенты' тестовыми данными..."
    ) 
    # Пациенты
    patient1 = Patient(
        first_name="Иван",
        middle_name="Петрович",
        last_name="Петров",
        birth_date=date(1985, 5, 12),
        phone="+7 123 456-78-90",
        description_id=desc1.id,
        comment_id=comm1.id,
    )
    patient2 = Patient(
        first_name="Мария",
        middle_name="Ивановна",
        last_name="Сидорова",
        birth_date=date(1990, 10, 3),
        phone="+7 987 654-32-10",
        description_id=desc2.id,
        comment_id=comm2.id,
    )
    patient3 = Patient(
        first_name="Петр",
        middle_name="Алексеевич",
        last_name="Иванов",
        birth_date=date(1978, 2, 20),
        phone="+7 555 123-45-67",
        description_id=desc3.id,
        comment_id=comm3.id,
    )

    session.add_all(
        [patient1, patient2, patient3]
    )

    session.flush()  # чтобы получить id пациентов



    logger.debug(
        f"Заполнение ТБ 'Заметки' тестовыми данными..."
    ) 

    # --- Заметки для приёмов (каждое поле – отдельная заметка) ---
    # Приём 1
    reason1 = AppointmentNote(text="Головная боль, повышенное давление")
    procedure1 = AppointmentNote(text="Измерение давления, назначен Амлодипин")
    recommendations1 = AppointmentNote(text="Контроль давления, диета №10")
    note1 = AppointmentNote(text="Пациент не выспался")
    cost1 = AppointmentNote(text="1500 руб.")

    # Приём 2 (повторный)
    reason2 = AppointmentNote(text="Давление стабилизировалось, но беспокоит изжога")
    procedure2 = AppointmentNote(text="Коррекция терапии, добавлен Омепразол")
    recommendations2 = AppointmentNote(text="Продолжить приём, контроль через месяц")
    note2 = AppointmentNote(text="Жалобы на изжогу после еды")
    cost2 = AppointmentNote(text="1200 руб.")

    # Приём 3
    reason3 = AppointmentNote(text="Плановый осмотр")
    procedure3 = AppointmentNote(text="Осмотр терапевта")
    recommendations3 = AppointmentNote(text="Общий анализ крови, ЭКГ")
    note3 = AppointmentNote(text="Чувствует себя удовлетворительно")
    cost3 = AppointmentNote(text="800 руб.")

    # Приём 4
    reason4 = AppointmentNote(text="Консультация по результатам МРТ")
    procedure4 = AppointmentNote(text="Расшифровка МРТ, направление к неврологу")
    recommendations4 = AppointmentNote(text="Явиться к неврологу с диском")
    note4 = AppointmentNote(text="МРТ от 15.03.2025")
    cost4 = AppointmentNote(text="2000 руб.")

    session.add_all([
        reason1, procedure1, recommendations1, note1, cost1,
        reason2, procedure2, recommendations2, note2, cost2,
        reason3, procedure3, recommendations3, note3, cost3,
        reason4, procedure4, recommendations4, note4, cost4
    ])
    session.flush()

    logger.debug(
        f"Заполнение ТБ 'Приёмы' тестовыми данными..."
    ) 

    # --- Приёмы ---
    app1 = Appointment(
        patient_id=patient1.id,
        date=date(2025, 3, 10),
        date_next=date(2025, 4, 10),
        reason_id=reason1.id,
        procedure_id=procedure1.id,
        recommendations_id=recommendations1.id,
        note_id=note1.id,
        cost_procedure_id=cost1.id,
    )
    app2 = Appointment(
        patient_id=patient1.id,
        date=date(2025, 4, 12),
        date_next=date(2025, 5, 12),
        reason_id=reason2.id,
        procedure_id=procedure2.id,
        recommendations_id=recommendations2.id,
        note_id=note2.id,
        cost_procedure_id=cost2.id,
    )
    app3 = Appointment(
        patient_id=patient2.id,
        date=date(2025, 3, 12),
        date_next=None,
        reason_id=reason3.id,
        procedure_id=procedure3.id,
        recommendations_id=recommendations3.id,
        note_id=note3.id,
        cost_procedure_id=cost3.id,
    )
    app4 = Appointment(
        patient_id=patient3.id,
        date=date(2025, 3, 15),
        date_next=date(2025, 4, 15),
        reason_id=reason4.id,
        procedure_id=procedure4.id,
        recommendations_id=recommendations4.id,
        note_id=note4.id,
        cost_procedure_id=cost4.id,
    )
    session.add_all(
        [app1, app2, app3, app4]
    )
    session.flush()



    logger.debug(
        f"Заполнение ТБ 'Фотографии' тестовыми данными..."
    ) 
    # Фотографии
    photo1 = Photo(
        appointment_id  = app1.id, 
        file_path       = "photos/app1/face.jpg", 
        description     = "Лицо"
    )

    photo2 = Photo(
        appointment_id  =   app1.id, 
        file_path       =   "photos/app1/neck.jpg", 
        description     =   "Шея"
    )
    session.add_all(
        [photo1, photo2]
    )
    session.flush()  


    session.commit()

    logger.debug(
        f"Тестовые данные добавлены и сохранены."
    ) 
    # print("Тестовые данные добавлены.")


@AppLogger.get_instance(
    name = 'temp_data_bd.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    # description="Заполнение БД",
    level=AppLogger._parse_log_level('DEBUG')
)
def generate_test_data(db_path:str="clinic.db"):
    """
    Создаёт сессию и вызывает populate_test_data.
    """

    logger = AppLogger.get_instance(
        name = 'temp_data_bd.py',
        enable_file_logging = 'user',
        use_name_in_filename = False, 
    )

    # from sqlalchemy import create_engine
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    logger.debug(
        f"Создание сессии к БД: {db_path} ({os.path.abspath(db_path)})"
    ) 

    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        populate_test_data(session)

    finally:
        session.close()

if __name__ == "__main__":
    # Пример использования: generate_test_data("clinic.db")
    generate_test_data()