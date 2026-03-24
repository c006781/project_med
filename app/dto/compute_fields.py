
# app/dto/compute_fields.py
from app.utils.logger.logger import AppLogger 



@AppLogger.get_instance(
    name = 'system',
).log_execution_time(
    level = AppLogger._parse_log_level(
        # 'INFO'
        'DEBUG'
    )
)
def get_patient_full_name(patient_id: int) -> str:
    """
    Возвращает ФИО пациента по его ID.

    :param patient_id: ID пациента
    :type patient_id: int
    :return: ФИО пациента
    :rtype: str
    """

    # Если пациент не указан, то возвращаем пустую строку
    if patient_id is None:
        return ""

    try:
        # Получаем сервис для работы с пациентами
        from app.dependencies import get_patient_service
        patient_service = get_patient_service()

        # Получаем пациента по его ID
        patient = patient_service.get_patient_by_id(patient_id)

        # Если пациент найден, то возвращаем ФИО
        if patient:
            return f"{patient.last_name} {patient.first_name}"
        else:
            # Если пациент не найден, то возвращаем сообщение об ошибке
            return "Пациент не найден"
    except Exception:
        # Если произошла ошибка, то возвращаем сообщение об ошибке
        return "Ошибка загрузки"
