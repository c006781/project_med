# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).

from typing import List, Optional, Any, Dict, TypeVar, Generic
from abc import ABC, abstractmethod


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
except ImportError as e:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 3)
        from ...models.bd.models import AppointmentNote, Appointment, Patient, Photo
    except ImportError as e:
        pass #  raise # e # pass

try:
    from ...utils.logger.logger import AppLogger
except ImportError as e:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 3)
        from ...utils.logger.logger import AppLogger
    except ImportError as e:
        pass #  raise # e # pass

try:
    from ...utils.filtering import apply_filters
except ImportError as e:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 3)
        from ...utils.filtering import apply_filters
    except ImportError as e:
        pass #  raise # e # pass

# Сторонние библиотеки

from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from sqlalchemy import select

ModelType = TypeVar('ModelType')

class BaseRepository(Generic[ModelType], ABC):
    """Все репозитории должны наследовать этот класс."""
    def __init__(self, session: Session):
        self._session = session

        self.logger = AppLogger.get_instance(self.__class__.__name__)

    def get_by_id(self, entity_id: int) -> Optional[ModelType]:
        self.logger.debug(f"get_by_id: {entity_id}")
        return self._session.get(self.model_class, entity_id)
    
    # def get_all(self) -> List[ModelType]:
    #     self.logger.debug(f"get_all")
    #     return self._session.get(self.model_class).all()
    
    def get_all(self) -> List[ModelType]:
        self.logger.debug(f"get_all")
        return self._session.query(self.model_class).all()

    def add(self, entity: ModelType) -> ModelType:
        self.logger.debug(f"add: {entity}")
        self._session.add(entity)
        return entity

    def delete(self, entity: ModelType) -> None:
        self.logger.debug(f"delete: {entity}")
        self._session.delete(entity)

    # # Метод update – если мы хотим его оставить
    # def update(self, entity: ModelType) -> ModelType:
    #     # Предполагаем, что объект уже прикреплён к сессии (получен через get_by_id)
    #     # Если же объект может быть detached, используем merge:
    #     # return self._session.merge(entity)
    #     # Но тогда он должен возвращать обновлённый объект.
    #     # Для простоты можно оставить без тела, просто зафиксировать, что изменения отслеживаются.
    #     self.logger.debug(f"update: {entity} (изменения отслеживаются автоматически)")
    #     return self._session.merge(entity)  

    @property
    @abstractmethod
    def model_class(self):
        """Должен быть переопределён в наследниках."""
        raise NotImplementedError("Подклассы должны определить model_class")
    
    def get_unique_values(self, column_name: str) -> List[Any]:
        """
        Возвращает список уникальных значений для указанного столбца.
        """
        self.logger.debug(f"get_unique_values: column_name = {column_name}")
        if self.model_class is None:
            raise NotImplementedError("model_class не определён в репозитории")
        try:
            column = getattr(self.model_class, column_name, None)
            if column is None:
                self.logger.warning(f"Столбец '{column_name}' не найден в модели {self.model_class.__name__}")
                return []
            stmt = select(column).distinct()
            return self._session.execute(stmt).scalars().all()
        except Exception as e:
            self.logger.exception(f"Ошибка в get_unique_values (столбец '{column_name}'): {e}")
            raise  # пробрасываем исключение, чтобы не скрывать проблемы 

    def get_page(self, offset: int, limit: int,
                 filters: Optional[List[Dict[str, Any]]] = None,
                 order_by: Optional[List] = None) -> List[ModelType]:
        """
        Возвращает страницу записей.
        :param offset: смещение
        :param limit: размер страницы
        :param filters: список фильтров (без fuzzy)
        :param order_by: список условий сортировки (например, [Patient.last_name.asc()])
        """
        query = self._session.query(self.model_class)
        if filters:
            # Отфильтровываем fuzzy-операторы, они не поддерживаются на уровне SQL
            sql_filters = [f for f in filters if f.get('operator') != 'fuzzy']
            if sql_filters:
                query, _  = apply_filters(query, self.model_class, sql_filters)
        if order_by:
            query = query.order_by(*order_by)
        return query.offset(offset).limit(limit).all()

    def count(self, filters: Optional[List[Dict[str, Any]]] = None) -> int:
        """Возвращает общее количество записей с учётом SQL-фильтров."""
        query = self._session.query(self.model_class)
        if filters:
            sql_filters = [f for f in filters if f.get('operator') != 'fuzzy']
            if sql_filters:
                query, _  = apply_filters(query, self.model_class, sql_filters)
        return query.count()



class AppointmentNoteRepository(BaseRepository):
    model_class =  AppointmentNote

    # def get_by_id(self, note_id: int) -> Optional[AppointmentNote]:
    #     self.logger.debug(f"get_by_id: note_id = {note_id}")
    #     return self._session.get(AppointmentNote, note_id)

    # def add(self, note: AppointmentNote) -> AppointmentNote:
    #     self.logger.debug(f"add: note = {note}")
    #     self._session.add(note)
    #     return note

    # def update(self, note: AppointmentNote) -> AppointmentNote:
    #     self.logger.debug(f"update: note = {note}")
    #     self._session.merge(note)
    #     return note

    # def delete(self, note: AppointmentNote) -> None:
    #     self.logger.debug(f"delete: note = {note}")
    #     self._session.delete(note)

    # def get_unique_values(self, column_name: str) -> List[Any]:
    #     """
    #     Возвращает список уникальных значений для указанного столбца таблицы appointments_notes.
        
    #     Аргументы:
    #         column_name (str): имя столбца модели AppointmentNote (например, 'text', 'created_at').
        
    #     Возвращает:
    #         List[Any]: список уникальных значений. Если столбец не найден или произошла ошибка,
    #                    возвращается пустой список.
    #     """
    #     self.logger.debug(f"get_unique_values: column_name = {column_name}")
    #     # try:
    #     #     column = getattr(AppointmentNote, column_name, None)
    #     #     if column is None:
    #     #         return []
    #     #     # Выполняем запрос: SELECT DISTINCT column_name FROM appointments_notes
    #     #     return self._session.query(column).distinct().scalars().all()
    #     # except Exception:
    #     #     # В реальном приложении здесь должно быть логирование ошибки
    #     #     return []
        
    #     try:
    #         # column = getattr(Patient, column_name, None)
    #         column = getattr(AppointmentNote, column_name, None)   # <-- исправлено
            
    #         if column is None:
    #             return []
    #         stmt = select(column).distinct()
    #         return self._session.execute(stmt).scalars().all()
    #     except AttributeError:
    #         AppLogger.get_instance('system').exception(f"Ошибка наличия столбца в AppointmentNoteRepository.get_unique_values (столбец '{column_name} ненайден'): {e}")
    #         return []  # столбец не найден – возвращаем пустой список
    #     except Exception as e:
    #         AppLogger.get_instance('system').exception(f"Ошибка в AppointmentNoteRepository.get_unique_values (столбец '{column_name}'): {e}")
    #         raise  # пробрасываем дальше
        
    # def get_all(self) -> List[AppointmentNote]:
    #     self.logger.debug(f"get_all")
    #     """Возвращает все заметки."""
    #     return self._session.query(AppointmentNote).all()
    
    def get_by_text_exact(self, text: str):
        """
        Возвращает заметку с точно таким же текстом (чувствительно к регистру).
        Если не найдено, возвращает None.
        """
        self.logger.debug(f"get_by_text_exact: text = {text}")
        return self._session.query(AppointmentNote).filter(AppointmentNote.text == text).first()



class AppointmentRepository(BaseRepository):
    model_class =  Appointment

    # def get_all(self) -> List[Appointment]:
    #     self.logger.debug(f"get_all")
    #     return self._session.query(Appointment).all()

    # def get_by_id(self, appointment_id: int) -> Optional[Appointment]:
    #     self.logger.debug(f"get_by_id: appointment_id = {appointment_id}")
    #     return self._session.get(Appointment, appointment_id)

    # def get_by_patient(self, patient_id: int) -> List[Appointment]:
    #     self.logger.debug(f"get_by_patient: patient_id = {patient_id}")
    #     return self._session.query(Appointment).filter_by(patient_id=patient_id).all()

    # def add(self, appointment: Appointment) -> Appointment:
    #     self.logger.debug(f"add: appointment = {appointment}")
    #     self._session.add(appointment)
    #     return appointment

    # def update(self, appointment: Appointment) -> Appointment:
    #     self.logger.debug(f"update: appointment = {appointment}")
    #     self._session.merge(appointment)
    #     return appointment

    # def delete(self, appointment: Appointment) -> None:
    #     self.logger.debug(f"delete: appointment = {appointment}")
    #     self._session.delete(appointment)

    # def get_unique_values(self, column_name: str) -> List[Any]:
    #     """
    #     Возвращает список уникальных значений для указанного столбца таблицы appointments.
        
    #     Аргументы:
    #         column_name (str): имя столбца модели Appointment (например, 'date', 'time', 'patient_id').
        
    #     Возвращает:
    #         List[Any]: список уникальных значений.
    #     """
    #     self.logger.debug(f"get_unique_values: column_name = {column_name}")
    #     # try:
    #     #     column = getattr(Appointment, column_name, None)
    #     #     if column is None:
    #     #         return []
    #     #     return self._session.query(column).distinct().scalars().all()
    #     # except Exception:
    #     #     return []

    #     try:
    #         column = getattr(Appointment, column_name, None)
    #         if column is None:
    #             return []
    #         stmt = select(column).distinct()
    #         return self._session.execute(stmt).scalars().all()
    #     except AttributeError:
    #         AppLogger.get_instance('system').exception(f"Ошибка наличия столбца в AppointmentRepository.get_unique_values (столбец '{column_name} ненайден'): {e}")
    #         return []  # столбец не найден – возвращаем пустой список
    #     except Exception as e:
    #         AppLogger.get_instance('system').exception(f"Ошибка в AppointmentRepository.get_unique_values (столбец '{column_name}'): {e}")
    #         raise  # пробрасываем дальше

    # def get_all(self) -> List[Appointment]:
    #     self.logger.debug(f"get_all")
    #     """Возвращает все записи приёмов."""
    #     return self._session.query(Appointment).all()
    
    def get_all_with_note(self):
        self.logger.debug(f"get_all_with_note")
        return self._session.query(Appointment).options(joinedload(Appointment.note)).all()

    def get_all_with_relations(self) -> List[Appointment]:
        """Возвращает все приёмы с подгруженными пациентом и заметкой."""
        self.logger.debug("get_all_with_relations")
        return self._session.query(Appointment).options(
            joinedload(Appointment.patient),
            joinedload(Appointment.note)
        ).all()

    def get_by_patient_with_relations(self, patient_id: int) -> List[Appointment]:
        """Возвращает приёмы пациента с подгруженными пациентом и заметкой."""
        self.logger.debug(f"get_by_patient_with_relations: patient_id={patient_id}")
        return self._session.query(Appointment).filter_by(patient_id=patient_id).options(
            joinedload(Appointment.patient),
            joinedload(Appointment.note)
        ).all()

    def get_by_id_with_relations(self, appointment_id: int) -> Optional[Appointment]:
        """Возвращает приём по ID с подгруженными связями."""
        self.logger.debug(f"get_by_id_with_relations: appointment_id={appointment_id}")
        return self._session.query(Appointment).options(
            joinedload(Appointment.patient),
            joinedload(Appointment.note)
        ).filter(Appointment.id == appointment_id).first()   

    def get_page(self, offset: int, limit: int,
                 filters: Optional[List[Dict[str, Any]]] = None,
                 order_by: Optional[List] = None) -> List[Appointment]:
        """Возвращает страницу приёмов с подгруженными пациентом и заметкой."""
        query = self._session.query(Appointment).options(
            joinedload(Appointment.patient),
            joinedload(Appointment.note)
        )
        if filters:
            sql_filters = [f for f in filters if f.get('operator') != 'fuzzy']
            if sql_filters:
                query = apply_filters(query, Appointment, sql_filters)
        if order_by:
            query = query.order_by(*order_by)
        return query.offset(offset).limit(limit).all()

    def get_page_by_patient(self, patient_id: int, offset: int, limit: int,
                            filters: Optional[List[Dict[str, Any]]] = None,
                            order_by: Optional[List] = None) -> List[Appointment]:
        """Возвращает страницу приёмов конкретного пациента с подгрузкой связей."""
        base_filters = [{'column': 'patient_id', 'operator': 'eq', 'value': patient_id}]
        if filters:
            all_filters = base_filters + filters
        else:
            all_filters = base_filters
        return self.get_page(offset, limit, filters=all_filters, order_by=order_by)
    
    def count_by_patient(self, patient_id: int, filters: Optional[List[Dict[str, Any]]] = None) -> int:
        """Количество приёмов пациента с учётом дополнительных фильтров."""
        base_filters = [{'column': 'patient_id', 'operator': 'eq', 'value': patient_id}]
        if filters:
            all_filters = base_filters + filters
        else:
            all_filters = base_filters
        return self.count(filters=all_filters)

class PhotoRepository(BaseRepository):
    model_class =  Photo

    def get_by_appointment(self, appointment_id: int) -> List[Photo]:
        self.logger.debug(f"get_by_appointment: appointment_id = {appointment_id}")
        try:
            return self._session.query(Photo).filter_by(appointment_id=appointment_id).all()
        except Exception as e:
            self.logger.exception(f"Ошибка в get_by_appointment: {e}")
            raise   

    # def get_by_id(self, photo_id: int) -> Optional[Photo]:
    #     self.logger.debug(f"get_by_id: photo_id = {photo_id}")
    #     try:
    #         return self._session.get(Photo, photo_id)
    #     except Exception as e:
    #         self.logger.exception(f"Ошибка в get_by_id: {e}")
    #         raise   

    # def add(self, photo: Photo) -> Photo:
    #     self.logger.debug(f"add: photo = {photo}")
    #     try:
    #         self._session.add(photo)
    #     except Exception as e:
    #         self.logger.exception(f"Ошибка в add: {e}")
    #         raise 

    #     return photo  

    # def delete(self, photo: Photo) -> None:
    #     self.logger.debug(f"delete: photo = {photo}")
    #     try:
    #         self._session.delete(photo)
    #     except Exception as e:
    #         self.logger.exception(f"Ошибка в delete: {e}")
    #         raise   
    
    # def get_all(self) -> List[Photo]:
    #     """Возвращает все фотографии."""
    #     self.logger.debug(f"get_all")
    #     try:
    #         return self._session.query(Photo).all()
    #     except Exception as e:
    #         self.logger.exception(f"Ошибка в delete: {e}")
    #         raise    
          
    # def get_unique_values(self, column_name: str) -> List[Any]:
    #     """
    #     Возвращает список уникальных значений для указанного столбца таблицы photos.
        
    #     Аргументы:
    #         column_name (str): имя столбца модели Photo (например, 'file_path', 'description').
        
    #     Возвращает:
    #         List[Any]: список уникальных значений.
    #     """
    #     self.logger.debug(f"get_unique_values: column_name = {column_name}")
    #     # try:
    #     #     column = getattr(Photo, column_name, None)
    #     #     if column is None:
    #     #         return []
    #     #     return self._session.query(column).distinct().scalars().all()
    #     # except Exception:
    #     #     return []
    #     try:
    #         column = getattr(Photo, column_name, None)
    #         if column is None:
    #             return []
    #         stmt = select(column).distinct()
    #         return self._session.execute(stmt).scalars().all()
    #     except AttributeError:
    #         AppLogger.get_instance('system').exception(f"Ошибка наличия столбца в PhotoRepository.get_unique_values (столбец '{column_name} ненайден'): {e}")
    #         return []  # столбец не найден – возвращаем пустой список
    #     except Exception as e:
    #         AppLogger.get_instance('system').exception(f"Ошибка в PhotoRepository.get_unique_values (столбец '{column_name}'): {e}")
    #         raise  # пробрасываем дальше

        




class PatientRepository(BaseRepository):
    model_class =  Patient
    
    # def get_all(self) -> List[Patient]:
    #     self.logger.debug(f"get_all")
        
    #     try:
    #         return self._session.query(Patient).all()
    #     except Exception as e:
    #         AppLogger.get_instance('system').exception(f"Ошибка в PatientRepository.get_all: {e}")
    #         raise #e  # пробрасываем исключение выше
        
    # def get_by_id(self, patient_id: int) -> Optional[Patient]:
    #     self.logger.debug(f"get_by_id: patient_id = {patient_id}")

    #     try:
    #         return self._session.get(Patient, patient_id)
    #     except Exception as e:
    #         AppLogger.get_instance('system').exception(f"Ошибка в PatientRepository.get_by_id: {e}")
    #         raise #e  # пробрасываем исключение выше
        

    # def add(self, patient: Patient) -> Patient:
    #     self.logger.debug(f"add: patient = {patient}")

    #     try:
    #         self._session.add(patient)
    #         # self._session.flush()
    #     except Exception as e:
    #         AppLogger.get_instance('system').exception(f"Ошибка в PatientRepository.add: {e}")
    #         raise #e  # пробрасываем исключение выше
        
    #     # без commit – commit выполняется на уровне session_scope
    #     return patient

    # def update(self, patient: Patient) -> Patient:
    #     # Если объект уже в сессии, изменения отслеживаются автоматически.
    #     # Используем merge для случая, если объект пришёл извне.
    #     self.logger.debug(f"update: patient = {patient}")
        
    #     try:
    #         self._session.merge(patient)
    #     except Exception as e:
    #         AppLogger.get_instance('system').exception(f"Ошибка в PatientRepository.update: {e}")
    #         raise #e  # пробрасываем исключение выше
        

    #     return patient

    # def delete(self, patient: Patient) -> None:
    #     self.logger.debug(f"delete: patient = {patient}")
        
    #     try:   
    #         self._session.delete(patient)
    #     except Exception as e:
    #         AppLogger.get_instance('system').exception(f"Ошибка в PatientRepository.delete: {e}")
    #         raise #e  # пробрасываем исключение выше
        


    # def get_unique_values(self, column_name: str) -> List[Any]:
    #     """
    #     Возвращает список уникальных значений для указанного столбца таблицы patients.
        
    #     Аргументы:
    #         column_name (str): имя столбца модели Patient (например, 'last_name', 'birth_date', 'phone').
        
    #     Возвращает:
    #         List[Any]: список уникальных значений.
    #     """
    #     self.logger.debug(f"get_unique_values: column_name = {column_name}")
    #     # try:
    #     #     column = getattr(Patient, column_name, None)
    #     #     if column is None:
    #     #         return []
    #     #     return self._session.query(column).distinct().scalars().all()
    #     # except Exception as e:
    #     #     AppLogger.get_instance('system').exception(f"Ошибка в PatientRepository.get_unique_values (столбец '{column_name}: {e}")
    #     #     return []

    #     try:
    #         column = getattr(Patient, column_name, None)
    #         if column is None:
    #             return []
    #         stmt = select(column).distinct()
    #         return self._session.execute(stmt).scalars().all()
    #     except AttributeError:
    #         AppLogger.get_instance('system').exception(f"Ошибка наличия столбца в PatientRepository.get_unique_values (столбец '{column_name} ненайден'): {e}")
    #         return []  # столбец не найден – возвращаем пустой список
    #     except Exception as e:
    #         AppLogger.get_instance('system').exception(f"Ошибка в PatientRepository.get_unique_values (столбец '{column_name}'): {e}")
    #         raise  # пробрасываем дальше


    # def get_all(self) -> List[Patient]:
    #     """Возвращает всех Пациентов."""
    #     self.logger.debug(f"get_all")
    #     return self._session.query(Patient).all()
        
# 0==0