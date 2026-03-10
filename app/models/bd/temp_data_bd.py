# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).


def _add_package_name(
    file_module: str = None,
    levels_up: int = 3,           # <-- сколько уровней вверх до корня проекта
) -> None:
    
    """
    Что это (кратко): Добавляет корень проекта в sys.path и устанавливает правильный __package__.

    Что это (максимально подробно): Эта функция настраивает окружение Python таким образом, чтобы можно было использовать относительные импорты (например, from .module import something) без необходимости запускать скрипт с флагом "-m" (как модуль). Она работает только если скрипт запущен напрямую (не импортирован). Функция получает абсолютный путь к текущему файлу, добавляет родительскую директорию в sys.path (список путей для поиска модулей), и устанавливает глобальную переменную __package__ как имя текущей директории. Это полезно в проектах с nested папками, где импорты могут сломаться.

    Как работает: Сначала объявляется global __package__ для изменения системной переменной. Затем os.path.abspath(__file__) дает полный путь к скрипту, os.path.dirname убирает имя файла, оставляя папку. sys.path.append добавляет родительскую папку (dirname еще раз). Наконец, __package__ = basename(package_dir) — имя папки. Вызывается только в if __name__ == '__main__', чтобы не мешать, если скрипт импортирован.

    Примеры запуска:
    # В скрипте: if __name__ == '__main__': _add_package_name()
    # После вызова: sys.path включает родительскую папку (например, '/path/to/modules'), __package__ = 'parsers_sheregeh'. Теперь относительные импорты работают.
    # Если запустить как модуль (python -m script), функция не нужна, но она не навредит.
    # Если не вызвать: относительный импорт from .module... может вызвать ImportError: attempted relative import with no known parent package.

    :param file_module: (str) = обычно __file__  - указатель на путь к модулю, папку которого делаем пакетом для относительных импортов (содержит путь к текущему скрипту)
    :param levels_up: (int) - на сколько уровней подниматься вверх до корня проекта
                       (подберите под структуру вашего проекта)
                       Примеры:
                         2 → до папки app
    """
    if file_module is None:
        file_module = __file__

    # Получаем директорию текущего файла
    current_dir = os.path.dirname(os.path.abspath(file_module))

    # Поднимаемся на levels_up уровней вверх — это и будет корень проекта
    project_root = current_dir
    for _ in range(levels_up):
        project_root = os.path.dirname(project_root)

    # Добавляем корень проекта в начало sys.path (высокий приоритет)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Вычисляем правильное значение __package__
    # Пример: /project_med/app/models/bd → "app.models.bd"
    rel_path = os.path.relpath(current_dir, project_root)
    
    if rel_path == '.':
        package_name = ''
    else:
        package_name = rel_path.replace(os.sep, '.').strip('.')

    # Устанавливаем __package__
    global __package__
    if package_name:
        __package__ = package_name
    else:
        # Если мы в корне — можно оставить None или пустую строку
        __package__ = None

# if True:
# # if not 'app.models' in sys.modules.keys():
#     try:
#         from .models import Patient, Appointment, AppointmentNote, Photo
#     except ImportError:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(
#             file_module = __file__,
#             levels_up = 0
#         )

#         from .models import Patient, Appointment, AppointmentNote, Photo

temp_from = 'app.models.bd.models'.split('.')
temp_from = {
    '.'.join(temp_from[x:]) for x in range(len(temp_from))
}
# if not 'get_getenv' in sys.modules.keys():
if len(
    set(sys.modules.keys()).intersection(temp_from)
) == 0:
    try:
        from .models import Patient, Appointment, AppointmentNote, Photo
        # from . import models
    except ImportError:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(
            file_module = __file__,
            levels_up = 0
        )

        from .models import Patient, Appointment, AppointmentNote, Photo
        # from . import models

del temp_from


from datetime import date, datetime, time
# Сторонние библиотеки

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def populate_test_data(session):
    """
    Заполняет БД тестовыми данными.
    Предполагается, что БД уже создана и таблицы существуют.
    """
    # Проверяем, есть ли уже данные (чтобы не дублировать)
    if session.query(Patient).count() > 0:
        print("База данных уже содержит данные. Пропускаем заполнение.")
        return

    print("Заполнение базы тестовыми данными...")

    # Пациенты
    patient1 = Patient(
        first_name="Иван", 
        last_name="Петров",
        birth_date=date(1985, 5, 12), 
        phone="+7 123 456-78-90",
        email="ivan@example.com", 
        # address="Москва, ул. Ленина, д.1"
    )
    patient2 = Patient(
        first_name="Мария", 
        last_name="Сидорова",
        birth_date=date(1990, 10, 3), 
        phone="+7 987 654-32-10",
        email="maria@example.com", 
        # address="Санкт-Петербург, Невский пр., д.2"
    )
    patient3 = Patient(
        first_name="Петр", 
        last_name="Иванов",
        birth_date=date(1978, 2, 20), 
        phone="+7 555 123-45-67",
        email="petr@example.com", 
        # address="Новосибирск, ул. Советская, д.3"
    )
    session.add_all(
        [patient1, patient2, patient3]
    )
    session.flush()  # теперь у patient1.id есть значение
    # session.commit()

    # Заметки
    note1 = AppointmentNote(text="Первичный осмотр. Жалобы на головную боль.")
    note2 = AppointmentNote(text="Повторный приём. Назначены анализы.")
    note3 = AppointmentNote(text="Плановый осмотр.")
    note4 = AppointmentNote(text="Консультация по результатам МРТ.")
    session.add_all(
        [note1, note2, note3, note4]
    )
    session.flush()  # теперь у patient1.id есть значение
    # session.commit()

    # Приёмы
    app1 = Appointment(
        patient_id=patient1.id, note_id=note1.id,
        date=date(2025, 3, 10), 
        # time="10:30"
        time=time(
            hour=10, 
            minute=30
        ),
    )
    app2 = Appointment(
        patient_id=patient1.id, note_id=note2.id,
        date=date(2025, 3, 17), 
        # time="11:00"
        time=time(
            hour=11, 
            minute=00
        ),
    )
    app3 = Appointment(
        patient_id=patient2.id, note_id=note3.id,
        date=date(2025, 3, 12), 
        # time="14:15"
        time=time(
            hour=14, 
            minute=15
        ),
    )
    app4 = Appointment(
        patient_id=patient3.id, note_id=note4.id,
        date=date(2025, 3, 15), 
        # time="09:00"
        time=time(
            hour=9, 
            minute=00
        ),
    )
    session.add_all(
        [app1, app2, app3, app4]
    )
    session.flush()  # теперь у patient1.id есть значение
    # session.commit()

    # Фотографии
    photo1 = Photo(
        appointment_id=app1.id, 
        file_path="photos/app1/face.jpg", 
        description="Лицо"
    )

    photo2 = Photo(
        appointment_id=app1.id, 
        file_path="photos/app1/neck.jpg", 
        description="Шея"
        )
    session.add_all(
        [photo1, photo2]
    )
    session.flush()  # теперь у patient1.id есть значение


    session.commit()

    print("Тестовые данные добавлены.")

def generate_test_data(db_path="clinic.db"):
    """
    Создаёт сессию и вызывает populate_test_data.
    """
    from sqlalchemy import create_engine
    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        populate_test_data(session)
    finally:
        session.close()

if __name__ == "__main__":
    generate_test_data()