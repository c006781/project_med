# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).

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
    # from ...controllers.conf.get_config import get_config_env as get_config_env
from app.config.config_manager.manager import get_config_env
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(
#             file_module = __file__,
#             levels_up = 3
#         )
#         # from ...controllers.conf.get_config import get_config_env as get_config_env
#         from ...config.config_manager.manager import get_config_env
#     except ImportError as e:
#         pass #  raise # e # pass

# try:

# from app.backend.bd.temp_data_bd import generate_test_data as generate_test_data
# from .temp_data_bd import generate_test_data as generate_test_data
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(
#             file_module = __file__,
#             levels_up = 1
#         )
#         from .temp_data_bd import generate_test_data as generate_test_data
#     except ImportError as e:
#         pass #  raise # e # pass





from datetime import date, datetime, time

# Сторонние библиотеки
from sqlalchemy import create_engine, Column, Integer, String, Date, DateTime, ForeignKey, Text, Time
# from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy import event, Index, func

Base = declarative_base()

class Patient(Base):
    """
    Таблица пациентов.
    Хранит персональные данные пациентов.
    """

    __tablename__ = 'patients'

    id = Column(
        Integer, 
        primary_key=True , 
        autoincrement=True, 
        comment='Уникальный идентификатор пациента',
    )
    first_name = Column(
        String(50), 
        nullable=False,
        comment='Имя пациента',
    )
    last_name = Column(
        String(50), 
        nullable=False,
        comment='Фамилия пациента',
    )
    birth_date = Column(
        Date, 
        nullable=True,
        comment='Дата рождения',
    )
    phone = Column(
        String(20), 
        nullable=True,
        comment='Номер телефона',
    )
    email = Column(
        String(100), 
        nullable=True,
        comment='Электронная почта',
    )
    # address = Column(String(200), nullable=True)
    created_at = Column(
        DateTime, 
        default=datetime.now,
        comment='Электронная почта',
    )

    # Отношение к приёмам (каскадное удаление)
    appointments = relationship(
        "Appointment", 
        back_populates="patient", 
        cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index('ix_patient_last_name', 'last_name'),
        {
            'comment': 'Таблица пациентов', 
            'sqlite_autoincrement': True,
        }
    )
    
    def __repr__(self):
        """
        Возвращает строку-representation объекта Patient в виде "<Patient(id=1, name=Ivan Ivanov)>"
        """

        try:
            return f"<Patient(id={self.id}, name={self.last_name} {self.first_name})>"
        except Exception as e:
            # tt = str(e)
            AppLogger.get_instance(
                name='system',
            ).exception(f'Err: {str(e)}')
            raise e

        # return result

class AppointmentNote(Base):
    """
    Таблица заметок к приёмам.
    Заметки могут быть общими для нескольких приёмов.
    """

    __tablename__ = 'appointments_notes'

    id = Column(
        Integer, 
        primary_key=True , 
        autoincrement=True,
        comment='Уникальный идентификатор заметки',
    )
    
    text = Column( # содержимое заметки (рекомендации, описание)
        Text, 
        nullable=False,
        comment='Текст заметки',
    )   

    created_at = Column(
        DateTime, 
        default=datetime.now,
        comment='Дата и время создания заметки',
    )

    # Обратная связь: заметка может использоваться в нескольких приёмах (если нужно)
    appointments = relationship(
        "Appointment", 
        back_populates="note"
    )
    
    __table_args__ = (
        {
            'comment': 'Таблица заметок приёмов', 
            'sqlite_autoincrement': True,
        }
    )

    def __repr__(self):
        """
        Возвращает строку-representation объекта Note в виде "<Note(id=1, text_preview=Note text...)>"
        """
        return f"<Note(id={self.id}, text_preview={self.text[:30]}...)>"
    
class Appointment(Base):
    """
    Таблица приёмов.
    Связывает пациента с датой, временем и опциональной заметкой.
    """

    __tablename__ = 'appointments'

    id = Column(
        Integer, 
        primary_key=True , 
        autoincrement=True,
        comment='Уникальный идентификатор приёма',
    )

    patient_id = Column(
        Integer, 
        ForeignKey('patients.id'), 
        nullable=False,
        comment='ID пациента (внешний ключ)',
    )

    date = Column(
        Date, 
        nullable=False,
        comment='Дата приёма',
    )

    # time = Column(Time, nullable=True, default=time.now)  
    # time = Column(Time, nullable=True, default=lambda: datetime.now().time())
    time = Column(
        Time, 
        nullable=True, 
        default=func.current_time(),
        comment='Время приёма',
    )
    # time = Column(Time, nullable=True, server_default=func.current_time())

    # notes = Column(Text, nullable=True)      # заметки / рекомендации
    note_id = Column(
        Integer, 
        ForeignKey('appointments_notes.id'), 
        nullable=True,
        comment='ID заметки (внешний ключ)',
    )   # внешний ключ на заметку

    created_at = Column(
        DateTime, 
        default=datetime.now,
        comment='Дата и время создания записи',
    )


    # Отношение к пациенту
    patient = relationship(
        "Patient", 
        back_populates="appointments",
        )

    # доступ к заметке
    note = relationship(
        "AppointmentNote", 
        back_populates="appointments",
    )
   
    # Отношение к фотографиям
    photos = relationship(
        "Photo", 
        back_populates="appointment", 
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index('ix_appointment_date', 'date'),
        {
            'comment': 'Таблица приёмов', 
            'sqlite_autoincrement': True,
        }
    )

    def __repr__(self):
        """
        Возвращает строку-representation объекта Appointment в виде "<Appointment(id=1, patient_id=1, date=2025-01-01)>"
        """
        return f"<Appointment(id={self.id}, patient_id={self.patient_id}, date={self.date})>"

class Photo(Base):
    """
    Таблица фотографий, прикреплённых к приёмам.
    Файлы хранятся в файловой системе, в таблице хранится путь.
    """

    __tablename__ = 'photos'

    id = Column(
        Integer, 
        primary_key=True , 
        autoincrement=True,
        comment='Уникальный идентификатор фотографии',
    )

    appointment_id = Column(
        Integer, 
        ForeignKey('appointments.id'), nullable=False,
        comment='ID приёма, к которому относится фото',
    )

    file_path = Column( # путь к файлу на диске
        String(500), 
        nullable=False,
        comment='Относительный путь к файлу на диске',
    )  

    description = Column(
        String(200), 
        nullable=True,
        comment='Описание фотографии',
    )

    uploaded_at = Column(
        DateTime, 
        default=datetime.now,
        comment='Дата и время загрузки',
    )


    # Отношение к приёму
    appointment = relationship(
        "Appointment", 
        back_populates="photos"
    )

    __table_args__ = (
        Index('ix_photo_appointment', 'appointment_id'),
        {
            'comment': 'Таблица фотографий приёмов', 
            'sqlite_autoincrement': True,
        }
    )

    def __repr__(self):
        """
        Возвращает строку-representation объекта Photo в виде "<Photo(id=1, appointment_id=1, file=photo.jpg)>"
        """
        return f"<Photo(id={self.id}, appointment_id={self.appointment_id}, file={self.file_path})>"


# Функция для инициализации БД и создания тестовых данных
@AppLogger.get_instance(
    name = 'system',
).log_execution_time(
    level = AppLogger._parse_log_level(
        # 'INFO'
        'DEBUG'
    )
)
def create_db(
        db_path="clinic.db",
        recreate=False,
    ):
    """
    Создаёт файл БД (если не существует), таблицы и заполняет тестовыми данными.

    :param db_path: путь к файлу БД
    :param recreate: если True и файл существует, он будет удалён перед созданием таблиц
    """

    abs_path = os.path.abspath(db_path)

    if recreate and os.path.exists(abs_path):
        AppLogger.get_instance(
            name = 'db',
            enable_file_logging = 'user',
            use_name_in_filename = 'user',
        ).debug(
            f"Удаление существующего файла БД: {abs_path}"
            # level = AppLogger._parse_log_level(
            #     # 'INFO'
            #     'DEBUG'
            # )
        )
        # print(f"Удаление существующего файла БД: {abs_path}")
        os.remove(abs_path)


    if os.path.exists(abs_path):
        AppLogger.get_instance(
            name = 'db',
            enable_file_logging = 'user',
            use_name_in_filename = 'user',
        ).debug(
            f"Файл БД {abs_path} уже существует. Таблицы будут созданы, если их нет."
            # level = AppLogger._parse_log_level(
            #     # 'INFO'
            #     'DEBUG'
            # )
        )
        # print(f"Файл БД {db_path} уже существует. Таблицы будут созданы, если их нет.")
    else:

        AppLogger.get_instance(
            name = 'db',
            enable_file_logging = 'user',
            use_name_in_filename = 'user',
        ).debug(
            f"Создание нового файла БД: {abs_path}"
            # level = AppLogger._parse_log_level(
            #     # 'INFO'
            #     'DEBUG'
            # )
        )
        # print(f"Создание нового файла БД: {db_path}")

    # Создаём движок (будет использовать SQLite)
    # Движок SQLAlchemy: если файл не существует, он будет создан автоматически
    engine = create_engine(
        f"sqlite:///{db_path}", 
        echo=False, # echo=True для отладки SQL
        connect_args={
            "check_same_thread": False, 
        },
    )
    # engine = create_engine(f"sqlite:///{abs_path}", echo=False)  # echo=True для отладки SQL

    # Создаём таблицы, если их нет
    
    Base.metadata.create_all(engine)

    AppLogger.get_instance(
            name = 'db',
            enable_file_logging = 'user',
            use_name_in_filename = 'user',
    ).debug(
        f"Таблицы успешно созданы (или уже существовали): {abs_path}"
        # level = AppLogger._parse_log_level(
        #     # 'INFO'
        #     'DEBUG'
        # )
    )

    # print("Таблицы успешно созданы (или уже существовали).")

    return engine

@AppLogger.get_instance(
        name = 'system',
).log_execution_time(
    # description="Содание и заполнение БД",
    level = AppLogger._parse_log_level(
        # 'INFO'
        'DEBUG'
    )
)
def init_db(
    db_path="clinic.db"
):

    create_db(
        db_path = db_path ,  
        # recreate=False, 
        recreate=True, 
    )
    
    from .temp_data_bd import generate_test_data   # локальный импорт
    generate_test_data(
        db_path = db_path    
    )



if __name__ == "__main__":
    # При запуске этого файла напрямую создаём БД с тестовыми данными
    # env_key = get_config_env()
    db_path = get_config_env()['database_local_path']
    # db_path = "clinic.db"
    
    # Можно проверить, существует ли файл, но create_all всё равно создаст таблицы,
    # если их нет. А данные добавим только если таблицы пусты.
    init_db(db_path)
    print(f"База данных создана: {os.path.abspath(db_path)}")