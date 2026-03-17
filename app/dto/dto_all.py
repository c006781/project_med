from dataclasses import dataclass
from datetime import date, time
from typing import Optional, TypeVar, Type, Dict, Any




# Обобщённый тип для модели и DTO (для type hints)
ModelType = TypeVar('ModelType')
DTOType = TypeVar('DTOType')

class BaseDTO:
    """
    Базовый класс DTO.
    Для преобразования модели в DTO достаточно определить метод `from_orm`,
    но можно также использовать dataclass и передавать значения через конструктор.
    """

    @classmethod
    def from_orm(cls: Type[DTOType], model: ModelType) -> DTOType:
        """
        Создаёт DTO (Data Transfer Object) из экземпляра SQLAlchemy-модели.
        
        Это статический метод, который берёт экземпляр модели SQLAlchemy 
        и преобразует его в экземпляр DTO (класс, унаследованный от BaseDTO).
        
        Метод должен быть переопределён в наследниках, чтобы обеспечить 
        корректное преобразование модели в DTO.
        """
        raise NotImplementedError("Метод from_orm должен быть реализован в наследнике")

    def to_dict(self) -> Dict[str, Any]:
        """
        Преобразует DTO в словарь. Можно использовать, например, для сериализации.
        """
        return self.__dict__



@dataclass
class PatientDTO(BaseDTO):
    """
    DTO для передачи данных пациента.
    Все поля соответствуют полям модели Patient, но без ORM-специфики.
    """
    id: Optional[int]  # id может быть None для нового пациента
    first_name: str
    last_name: str
    birth_date: Optional[date]   = None  # Может быть None, если не указано
    phone: Optional[str]  = None 
    email: Optional[str]  = None 
    # created_at: Optional[datetime]  # Можно добавить, если нужно в интерфейсе

    @classmethod
    def from_orm(cls, model):
        """
        Создаёт DTO из модели SQLAlchemy.
        
        Этот метод берёт модель SQLAlchemy и преобразует ее в DTO.
        Он просто копирует значения полей модели в соответствующие поля DTO.
        """
        return cls(
            id=model.id,  # id может быть None, если модель не сохранена в БД
            first_name=model.first_name,  # имя
            last_name=model.last_name,  # фамилия
            birth_date=model.birth_date,  # дата рождения
            phone=model.phone,  # телефон
            email=model.email,  # электронная почта
        )
    
@dataclass
class AppointmentDTO(BaseDTO):
    id: Optional[int]
    patient_id: int
    date: date
    time: Optional[time]
    note_id: Optional[int]
    # Можно добавить поля для отображения в GUI, например, имя пациента
    patient_name: Optional[str] = None  # Это поле заполняется отдельно
    note_text: Optional[str] = None # поле для текста заметки

    @classmethod
    # def from_orm(cls, model: Appointment) -> AppointmentDTO:
    def from_orm(cls, model):
        """
        Создаёт DTO из модели Appointment.

        DTO будет содержать id, patient_id, date, time, note_id,
        а также имя пациента и текст заметки (если они есть).

        :param model: экземпляр модели Appointment
        :return: экземпляр DTO с данными из модели
        """
        # Создаём DTO с данными из модели
        # id - это id приёма
        # patient_id - это id пациента, к которому относится приём
        # date - это дата приёма
        # time - это время приёма (может быть None, если не указано)
        # note_id - это id заметки, если она есть (может быть None, если нет)
        # patient_name - это имя пациента, к которому относится приём (если он есть)
        # note_text - это текст заметки, если она есть (может быть None, если нет)
        return cls(
            id=model.id,
            patient_id=model.patient_id,
            date=model.date,
            time=model.time,
            note_id=model.note_id,
            patient_name=f"{model.patient.last_name} {model.patient.first_name}" if model.patient else None,
            note_text=model.note.text if model.note else None,
        )
    

@dataclass
class AppointmentNoteDTO(BaseDTO):
    id: Optional[int]
    text: str

    @classmethod
    def from_orm(cls, model):
        """
        Создаёт DTO из модели AppointmentNote.

        model - это экземпляр модели AppointmentNote, а не DTO.
        DTO будет содержать id и текст заметки.
        """
        return cls(
            id=model.id,
            text=model.text,
        )
    

@dataclass
class PhotoDTO(BaseDTO):
    id: Optional[int]
    appointment_id: int
    file_path: str
    description: Optional[str]

    @classmethod
    # def from_orm(cls, model: Photo) -> PhotoDTO:
    def from_orm(cls, model) :
        """
        Создаёт DTO из модели Photo.
        model - это экземпляр модели Photo, а не DTO.
        """
        # Создаём DTO с значениями из модели
        return cls(
            id=model.id,  # id может быть None для нового фото
            appointment_id=model.appointment_id,  # id приёма, к которому привязано фото
            file_path=model.file_path,  # путь к файлу с фотографией
            description=model.description,  # описание фотографии
        )



  