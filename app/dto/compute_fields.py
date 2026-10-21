# app/dto/compute_fields.py
"""
Вычисляемые значения для DTO (виртуальные поля, заполняемые не из БД).

Сейчас нигде не вызывается (ФИО пациента считает описание таблицы —
``app.schema.clinic.patient_full_name``); оставлено как публичная функция и скрытый
импорт сборки (``scripts/build_win.py``).
"""

from typing import Any, Iterable, Optional

from app.utils.logger.logger import AppLogger
from app.dependencies import get_patient_service
from app.exceptions import EntityNotFoundError

# Тексты вместо ФИО
PATIENT_NOT_FOUND_TEXT = "Пациент не найден"
PATIENT_LOAD_ERROR_TEXT = "Ошибка загрузки"


def join_name_parts(
    parts: Iterable[Optional[Any]], # части имени (фамилия, имя, отчество …), None/'' — пропуск
) -> str:
    """
    Склеивает части имени через пробел, пропуская пустые.

    Args:
        parts (Iterable[Optional[Any]]): Части имени.

    Returns:
        str: Имя без лишних пробелов.

    Example:
        >>> join_name_parts(['Петров', 'Иван', None])
        'Петров Иван'
        >>> join_name_parts([' Петров ', '', 'Иванович'])
        'Петров Иванович'
        >>> join_name_parts([None, None])
        ''
    """
    return " ".join(str(part).strip() for part in parts if part is not None and str(part).strip())


@AppLogger.get_instance(
    name = 'compute_fields.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, # 'system',
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def get_patient_full_name(
    patient_id: Optional[int], # ID пациента (None — пустая строка)
) -> str:
    """
    ФИО пациента по его ID: «Фамилия Имя Отчество» (пустые части пропускаются).

    Args:
        patient_id (Optional[int]): ID пациента.

    Returns:
        str: ФИО; ``''`` — ID не задан; ``'Пациент не найден'`` — нет такой записи;
        ``'Ошибка загрузки'`` — сбой чтения.

    Example:
        >>> get_patient_full_name(None)
        ''
    """
    logger = AppLogger.get_instance(
        name = 'compute_fields.py',
        enable_file_logging = 'user',
        use_name_in_filename = False, 
    )

    if patient_id is None:
        logger.debug("patient_id is None")
        return ""

    try:
        patient = get_patient_service().get_patient_by_id(patient_id)
    except EntityNotFoundError: # PatientNotFoundError — наследник
        logger.debug(f"Пациент {patient_id} не найден")
        return PATIENT_NOT_FOUND_TEXT
    except Exception as e:
        logger.debug(f"Ошибка загрузки: {e}")
        return PATIENT_LOAD_ERROR_TEXT

    if not patient:
        logger.debug(f"Пациент {patient_id} не найден")
        return PATIENT_NOT_FOUND_TEXT
    return join_name_parts([
        patient.last_name, # фамилия
        patient.first_name, # имя
        getattr(patient, 'middle_name', None), # отчество (может не быть)
    ])


# ↓ до rework-dto (2026-10-21): прежняя реализация. DT1 — " ".join([...]) с отчеством None
#   падал TypeError → «Ошибка загрузки» вместо ФИО у каждого пациента без отчества;
#   DT2 — get_patient_by_id бросает PatientNotFoundError (не None) → «Ошибка загрузки»
#   вместо «Пациент не найден».
#
# from app.utils.logger.logger import AppLogger 
# from app.dependencies import get_patient_service
#
# @AppLogger.get_instance(
#     name = 'compute_fields.py',
#     enable_file_logging = 'system',
#     use_name_in_filename = False, # 'system',
# ).log_execution_time(
#     level=AppLogger._parse_log_level('DEBUG')
# )
# def get_patient_full_name(patient_id: int) -> str:
#     """
#     Возвращает ФИО пациента по его ID.
#
#     :param patient_id: ID пациента
#     :type patient_id: int
#     :return: ФИО пациента
#     :rtype: str
#     """
#     logger = AppLogger.get_instance(
#         name = 'compute_fields.py',
#         enable_file_logging = 'user',
#         use_name_in_filename = False, 
#     )
#
#
#     # Если пациент не указан, то возвращаем пустую строку
#     if patient_id is None:
#         logger.debug(
#                 f"patient_id is None"
#                 # f"compute_virtual_fields: вычисление виртуального поля {field_name}: args = {args}, kwargs = {kwargs}, value = {value}"
#         )
#         return ""
#
#     try:
#         # Получаем сервис для работы с пациентами
#         # from app.dependencies import get_patient_service
#         patient_service = get_patient_service()
#
#         # Получаем пациента по его ID
#         patient = patient_service.get_patient_by_id(patient_id)
#
#         # Если пациент найден, то возвращаем ФИО
#         if patient:
#             # return f"{patient.last_name} {patient.first_name}"
#             return " ".join(
#                 [
#                     patient.last_name, 
#                     patient.first_name, 
#                     patient.middle_name
#                 ]
#             ).strip()
#         
#         else:
#             # Если пациент не найден, то возвращаем сообщение об ошибке
#             logger.debug(
#                 f"Если пациент не найден."
#                 )
#             return "Пациент не найден"
#         
#     except Exception as e:
#         logger.debug(
#                 f"Ошибка загрузки: {e}"
#         )
#
#         # Если произошла ошибка, то возвращаем сообщение об ошибке
#         return "Ошибка загрузки"
