# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).

from typing import List, Optional



# Импорты модулей
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

try:
    from ...models.bd.models import AppointmentNote, Appointment, Patient, Photo
except ImportError:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 3)
        from ...models.bd.models import AppointmentNote, Appointment, Patient, Photo
    except ImportError:
        pass

# Сторонние библиотеки

from sqlalchemy.orm import Session

class BaseRepository:
    """Все репозитории должны наследовать этот класс."""
    def __init__(self, session: Session):
        self._session = session




class AppointmentNoteRepository(BaseRepository):
    def get_by_id(self, note_id: int) -> Optional[AppointmentNote]:
        return self._session.get(AppointmentNote, note_id)

    def add(self, note: AppointmentNote) -> AppointmentNote:
        self._session.add(note)
        return note

    def update(self, note: AppointmentNote) -> AppointmentNote:
        self._session.merge(note)
        return note

    def delete(self, note: AppointmentNote) -> None:
        self._session.delete(note)


class AppointmentRepository(BaseRepository):
    def get_all(self) -> List[Appointment]:
        return self._session.query(Appointment).all()

    def get_by_id(self, appointment_id: int) -> Optional[Appointment]:
        return self._session.get(Appointment, appointment_id)

    def get_by_patient(self, patient_id: int) -> List[Appointment]:
        return self._session.query(Appointment).filter_by(patient_id=patient_id).all()

    def add(self, appointment: Appointment) -> Appointment:
        self._session.add(appointment)
        return appointment

    def update(self, appointment: Appointment) -> Appointment:
        self._session.merge(appointment)
        return appointment

    def delete(self, appointment: Appointment) -> None:
        self._session.delete(appointment)




class BaseRepositoryPatientRepository(BaseRepository):
    def get_all(self) -> List[Patient]:
        return self._session.query(Patient).all()

    def get_by_id(self, patient_id: int) -> Optional[Patient]:
        return self._session.get(Patient, patient_id)

    def add(self, patient: Patient) -> Patient:
        self._session.add(patient)
        # без commit – commit выполняется на уровне session_scope
        return patient

    def update(self, patient: Patient) -> Patient:
        # Если объект уже в сессии, изменения отслеживаются автоматически.
        # Используем merge для случая, если объект пришёл извне.
        self._session.merge(patient)
        return patient

    def delete(self, patient: Patient) -> None:
        self._session.delete(patient)




class PhotoRepository(BaseRepository):
    def get_by_appointment(self, appointment_id: int) -> List[Photo]:
        return self._session.query(Photo).filter_by(appointment_id=appointment_id).all()

    def get_by_id(self, photo_id: int) -> Optional[Photo]:
        return self._session.get(Photo, photo_id)

    def add(self, photo: Photo) -> Photo:
        self._session.add(photo)
        return photo

    def delete(self, photo: Photo) -> None:
        self._session.delete(photo)





class PatientRepository(BaseRepository):
    def get_all(self) -> List[Patient]:
        return self._session.query(Patient).all()

    def get_by_id(self, patient_id: int) -> Optional[Patient]:
        return self._session.get(Patient, patient_id)

    def add(self, patient: Patient) -> Patient:
        self._session.add(patient)
        # без commit – commit выполняется на уровне session_scope
        return patient

    def update(self, patient: Patient) -> Patient:
        # Если объект уже в сессии, изменения отслеживаются автоматически.
        # Используем merge для случая, если объект пришёл извне.
        self._session.merge(patient)
        return patient

    def delete(self, patient: Patient) -> None:
        self._session.delete(patient)



        
# 0==0