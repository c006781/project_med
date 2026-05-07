# app/dto/compute_fields.py

from app.utils.logger.logger import AppLogger 
from app.dependencies import get_patient_service

@AppLogger.get_instance(
    name = 'compute_fields.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, # 'system',
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def get_patient_full_name(patient_id: int) -> str:
    """
    Возвращает ФИО пациента по его ID.

    :param patient_id: ID пациента
    :type patient_id: int
    :return: ФИО пациента
    :rtype: str
    """
    logger = AppLogger.get_instance(
        name = 'compute_fields.py',
        enable_file_logging = 'user',
        use_name_in_filename = False, 
    )


    # Если пациент не указан, то возвращаем пустую строку
    if patient_id is None:
        logger.debug(
                f"patient_id is None"
                # f"compute_virtual_fields: вычисление виртуального поля {field_name}: args = {args}, kwargs = {kwargs}, value = {value}"
        )
        return ""

    try:
        # Получаем сервис для работы с пациентами
        # from app.dependencies import get_patient_service
        patient_service = get_patient_service()

        # Получаем пациента по его ID
        patient = patient_service.get_patient_by_id(patient_id)

        # Если пациент найден, то возвращаем ФИО
        if patient:
            # return f"{patient.last_name} {patient.first_name}"
            return " ".join(
                [
                    patient.last_name, 
                    patient.first_name, 
                    patient.middle_name
                ]
            ).strip()
        
        else:
            # Если пациент не найден, то возвращаем сообщение об ошибке
            logger.debug(
                f"Если пациент не найден."
                )
            return "Пациент не найден"
        
    except Exception as e:
        logger.debug(
                f"Ошибка загрузки: {e}"
        )

        # Если произошла ошибка, то возвращаем сообщение об ошибке
        return "Ошибка загрузки"
