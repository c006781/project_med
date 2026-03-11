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
        Создаёт DTO из экземпляра SQLAlchemy-модели.
        Должен быть переопределён в наследниках.
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
    birth_date: Optional[date]  # Может быть None, если не указано
    phone: Optional[str]
    email: Optional[str]
    # created_at: Optional[datetime]  # Можно добавить, если нужно в интерфейсе

    @classmethod
    def from_orm(cls, model):
        """
        Создаёт DTO из модели SQLAlchemy.
        """
        return cls(
            id=model.id,
            first_name=model.first_name,
            last_name=model.last_name,
            birth_date=model.birth_date,
            phone=model.phone,
            email=model.email,
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

    @classmethod
    def from_orm(cls, model):
        return cls(
            id=model.id,
            patient_id=model.patient_id,
            date=model.date,
            time=model.time,
            note_id=model.note_id,
            patient_name=f"{model.patient.last_name} {model.patient.first_name}" if model.patient else None,
        )
    

@dataclass
class AppointmentNoteDTO(BaseDTO):
    id: Optional[int]
    text: str

    @classmethod
    def from_orm(cls, model):
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
    def from_orm(cls, model):
        return cls(
            id=model.id,
            appointment_id=model.appointment_id,
            file_path=model.file_path,
            description=model.description,
        )



  