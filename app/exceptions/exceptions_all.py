# app/exceptions/exceptions_all.py
"""
Исключения приложения.

Иерархия::

    AppException (message, code)
    ├── EntityNotFoundError (+ LookupError)      entity, entity_id      код 9001
    │   ├── PatientNotFoundError                                       1001
    │   ├── AppointmentNotFoundError                                   2001
    │   ├── AppointmentNoteNotFoundError                               3001
    │   └── PhotoNotFoundError                                         4001
    ├── EntityValidationError (+ ValueError)     entity, field, reason  код 9002
    │   ├── PatientValidationError                                     1002
    │   ├── AppointmentValidationError                                 2002
    │   ├── AppointmentNoteValidationError                             3002
    │   └── PhotoValidationError                                       4002
    ├── PhotoFileError                            path, operation, reason, errno  4003
    │   ├── PhotoStoragePermissionError
    │   └── PhotoStorageNoSpaceError
    ├── SyncError → DownloadError, UploadError, TokenError             5000–5003
    └── DatabaseError → IntegrityError, DatabaseConnectionError        6000–6002

Новой таблице свой класс не нужен: ``EntityNotFoundError('Назначение', 5)`` и
``EntityValidationError('Доза', 'обязательное поле', entity='Назначение')``. Свой класс —
только если нужен свой код или текст: наследник с ``super().__init__(..., code=, message=)``.

Ловить «не найдено» любой таблицы — ``except EntityNotFoundError`` (или ``LookupError``),
ошибку проверки любого поля — ``except EntityValidationError`` (или ``ValueError``); поле и
причина — ``exc.field``, ``exc.reason`` (подсветить поле в окне).

Подробности и журнал проверок — ``app/exceptions/IMPLEMENTATION.md``.

Example:
    >>> str(PatientNotFoundError(42))
    '[1001] Пациент с идентификатором 42 не найден.'
    >>> isinstance(PatientNotFoundError(42), EntityNotFoundError)
    True
    >>> err = PhotoValidationError('file_path', 'пустой путь')
    >>> (err.entity, err.field, err.reason, isinstance(err, ValueError))
    ('Фотография', 'file_path', 'пустой путь', True)
"""

from typing import Any, Dict, Optional, Tuple, Type


def _restore_exception(
    cls: Type['AppException'], # класс исключения
    state: Dict[str, Any], # атрибуты экземпляра (__dict__)
) -> 'AppException':
    """
    Восстановление исключения при ``pickle``/``copy`` без вызова ``__init__``.

    ``__init__`` наследников принимает не текст, а данные (``patient_id``, ``path`` …),
    поэтому стандартное восстановление ``cls(*args)`` у них ломается.

    Args:
        cls (Type[AppException]): Класс.
        state (Dict[str, Any]): Атрибуты.

    Returns:
        AppException: Копия исключения.
    """
    exc = cls.__new__(cls)
    Exception.__init__(exc, state.get('message', ''))
    exc.__dict__.update(state)
    return exc


class AppException(Exception):
    """
    Базовое исключение для всех ошибок приложения.

    Все исключения приложения наследуют этот класс.

    Attributes:
        message (str): Текст ошибки.
        code (Optional[int]): Код ошибки для программной обработки.

    Example:
        >>> str(AppException('сбой', code=7))
        '[7] сбой'
        >>> str(AppException('сбой'))
        'сбой'
    """

    def __init__(
        self,
        message: str, # текст ошибки
        code: Optional[int] = None, # код ошибки (None — без кода)
    ):
        """
        Args:
            message (str): Текст ошибки.
            code (Optional[int]): Код ошибки.
        """
        # Вызываем конструктор родителя с сообщением
        super().__init__(message)
        # Сохраняем сообщение и код как атрибуты экземпляра
        self.message = message
        self.code = code

    def __str__(self) -> str:
        """
        Текст исключения: ``[код] сообщение`` или только сообщение.

        Returns:
            str: Текст.
        """
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message

    def __reduce__(self) -> Tuple[Any, Tuple[Type['AppException'], Dict[str, Any]]]:
        """
        Поддержка ``pickle``/``copy`` для наследников с любой сигнатурой ``__init__``.

        Returns:
            tuple: Функция восстановления и её аргументы.

        Example:
            >>> import pickle
            >>> str(pickle.loads(pickle.dumps(PhotoFileError('a.png', 'чтения', 'нет файла'))))
            "[4003] Ошибка чтения файла 'a.png': нет файла"
        """
        return _restore_exception, (type(self), dict(self.__dict__))


# ----------------------------------------------------------------------------------------
# Записи: не найдено / ошибка проверки
# ----------------------------------------------------------------------------------------

class EntityNotFoundError(AppException, LookupError):
    """
    Запись не найдена — общее исключение для любой таблицы (DYN9, 2026-10-16).

    Новая таблица, подключённая описанием, не обязана заводить свой класс исключения.
    Исключения конкретных таблиц (``PatientNotFoundError`` …) — наследники.

    Attributes:
        entity (str): Что не найдено (имя модели или по-русски).
        entity_id (Any): Идентификатор.

    Example:
        >>> raise EntityNotFoundError('Prescription', 5)  # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
        EntityNotFoundError: [9001] Prescription с идентификатором 5 не найден(а).
        >>> str(EntityNotFoundError('Prescription', 5))
        '[9001] Prescription с идентификатором 5 не найден(а).'
    """

    def __init__(
        self,
        entity: str, # что не найдено
        entity_id: Any, # идентификатор записи
        code: int = 9001, # код ошибки (у наследников — свой)
        message: Optional[str] = None, # свой текст (None — общий)
    ):
        """
        Args:
            entity (str): Что не найдено.
            entity_id (Any): Идентификатор.
            code (int): Код ошибки.
            message (Optional[str]): Текст; по умолчанию —
                ``'<entity> с идентификатором <id> не найден(а).'``.
        """
        if message is None:
            message = f"{entity} с идентификатором {entity_id} не найден(а)."
        super().__init__(message, code=code)
        self.entity = entity
        self.entity_id = entity_id


class EntityValidationError(AppException, ValueError):
    """
    Ошибка проверки поля записи — общее исключение для любой таблицы.

    Наследник ``ValueError``: интерфейс, ловящий ``ValueError``, ловит и его. Исключения
    конкретных таблиц (``PatientValidationError`` …) — наследники.

    Attributes:
        field (str): Поле (или перечень названий полей).
        reason (str): Причина.
        entity (Optional[str]): Таблица/запись (``None`` — не указана).

    Example:
        >>> str(EntityValidationError('Доза', 'обязательное поле', entity='Назначение'))
        "[9002] Ошибка валидации Назначение, поле 'Доза': обязательное поле."
        >>> str(EntityValidationError('Доза', 'обязательное поле'))
        "[9002] Ошибка валидации, поле 'Доза': обязательное поле."
    """

    def __init__(
        self,
        field: str, # поле с ошибкой
        reason: str, # причина
        entity: Optional[str] = None, # таблица/запись
        code: int = 9002, # код ошибки (у наследников — свой)
        message: Optional[str] = None, # свой текст (None — общий)
    ):
        """
        Args:
            field (str): Поле.
            reason (str): Причина.
            entity (Optional[str]): Таблица/запись.
            code (int): Код ошибки.
            message (Optional[str]): Текст; по умолчанию —
                ``"Ошибка валидации <entity>, поле '<field>': <reason>."``.
        """
        if message is None:
            where = f" {entity}" if entity else ""
            message = f"Ошибка валидации{where}, поле '{field}': {reason}."
        super().__init__(message, code=code)
        self.field = field
        self.reason = reason
        self.entity = entity


class PatientNotFoundError(EntityNotFoundError):
    """
    Пациент с указанным идентификатором не найден в базе данных.

    Example:
        >>> PatientNotFoundError(7).entity_id
        7
    """

    def __init__(
        self,
        patient_id: Any, # идентификатор пациента
    ):
        super().__init__(
            'Пациент', # что не найдено
            patient_id, # идентификатор
            code=1001, # код пациентов
            message=f"Пациент с идентификатором {patient_id} не найден.", # прежний текст
        )


# class PatientValidationError(AppException):
# ↑ до DATA9 (2026-10-16): только AppException. Теперь и ValueError — общая проверка
#   полей бросает это исключение, а интерфейс по-прежнему ловит ValueError.
class PatientValidationError(EntityValidationError):
    """
    Ошибка проверки данных пациента (например, пустое имя).

    Example:
        >>> str(PatientValidationError('first_name', 'пусто'))
        "[1002] Ошибка валидации поля 'first_name': пусто."
    """

    def __init__(
        self,
        field: str, # поле с ошибкой
        reason: str, # причина
    ):
        super().__init__(
            field, # поле
            reason, # причина
            entity='Пациент', # таблица
            code=1002, # код пациентов
            message=f"Ошибка валидации поля '{field}': {reason}.", # прежний текст
        )


class AppointmentNotFoundError(EntityNotFoundError):
    """Приём с указанным идентификатором не найден."""

    def __init__(
        self,
        appointment_id: Any, # идентификатор приёма
    ):
        super().__init__(
            'Приём', # что не найдено
            appointment_id, # идентификатор
            code=2001, # код приёмов
            message=f"Приём с идентификатором {appointment_id} не найден.", # прежний текст
        )


# class AppointmentValidationError(AppException):
# ↑ до DATA9 (2026-10-16): только AppException. Теперь и ValueError — общая проверка
#   полей бросает это исключение, а интерфейс по-прежнему ловит ValueError.
class AppointmentValidationError(EntityValidationError):
    """Ошибка проверки данных приёма."""

    def __init__(
        self,
        field: str, # поле с ошибкой
        reason: str, # причина
    ):
        super().__init__(
            field, # поле
            reason, # причина
            entity='Приём', # таблица
            code=2002, # код приёмов
            message=f"Ошибка валидации приёма, поле '{field}': {reason}.", # прежний текст
        )


class AppointmentNoteNotFoundError(EntityNotFoundError):
    """Заметка приёма с указанным идентификатором не найдена."""

    def __init__(
        self,
        note_id: Any, # идентификатор заметки
    ):
        super().__init__(
            'Заметка приёма', # что не найдено
            note_id, # идентификатор
            code=3001, # код заметок
            message=f"Заметка приёма с идентификатором {note_id} не найдена.", # прежний текст
        )


# class AppointmentNoteValidationError(AppException):
# ↑ до DATA9 (2026-10-16): только AppException. Теперь и ValueError — общая проверка
#   полей бросает это исключение, а интерфейс по-прежнему ловит ValueError.
class AppointmentNoteValidationError(EntityValidationError):
    """Ошибка проверки данных заметки."""

    def __init__(
        self,
        field: str, # поле с ошибкой
        reason: str, # причина
    ):
        super().__init__(
            field, # поле
            reason, # причина
            entity='Заметка', # таблица
            code=3002, # код заметок
            message=f"Ошибка валидации заметки, поле '{field}': {reason}.", # прежний текст
        )


class PhotoNotFoundError(EntityNotFoundError):
    """Фотография с указанным идентификатором не найдена."""

    def __init__(
        self,
        photo_id: Any, # идентификатор фотографии
    ):
        super().__init__(
            'Фотография', # что не найдено
            photo_id, # идентификатор
            code=4001, # код фото
            message=f"Фотография с идентификатором {photo_id} не найдена.", # прежний текст
        )


# class PhotoValidationError(AppException):
# ↑ до DATA9 (2026-10-16): только AppException. Теперь и ValueError — общая проверка
#   полей бросает это исключение, а интерфейс по-прежнему ловит ValueError.
class PhotoValidationError(EntityValidationError):
    """Ошибка проверки данных фотографии."""

    def __init__(
        self,
        field: str, # поле с ошибкой
        reason: str, # причина
    ):
        super().__init__(
            field, # поле
            reason, # причина
            entity='Фотография', # таблица
            code=4002, # код фото
            message=f"Ошибка валидации фотографии, поле '{field}': {reason}.", # прежний текст
        )


# ----------------------------------------------------------------------------------------
# Файлы фотографий
# ----------------------------------------------------------------------------------------

class PhotoFileError(AppException):
    """
    Ошибка работы с файлом фотографии.

    Attributes:
        path (str): Файл.
        operation (str): Операция (``'копирования'``, ``'удаления'`` …).
        reason (str): Причина.
        errno (Optional[int]): Код ошибки ОС.

    Example:
        >>> str(PhotoFileError('a.png', 'чтения', 'нет файла', errno=2))
        "[4003] Ошибка чтения файла 'a.png': нет файла (код ошибки: 2)"
    """

    def __init__(
        self,
        path: str, # файл
        operation: str, # операция (в родительном падеже: 'копирования')
        reason: str, # причина
        errno: Optional[int] = None, # код ошибки ОС
    ):
        message = f"Ошибка {operation} файла '{path}': {reason}"
        if errno:
            message += f" (код ошибки: {errno})"
        super().__init__(message, code=4003)
        self.path = path
        self.operation = operation
        self.reason = reason
        self.errno = errno


class PhotoStoragePermissionError(PhotoFileError):
    """Нет прав на файл/папку хранилища фото (errno 13)."""

    def __init__(
        self,
        path: str, # файл
        operation: str, # операция
    ):
        super().__init__(path, operation, "недостаточно прав доступа", errno=13)


class PhotoStorageNoSpaceError(PhotoFileError):
    """Нет места на диске хранилища фото (errno 28)."""

    def __init__(
        self,
        path: str, # файл
        operation: str, # операция
    ):
        super().__init__(path, operation, "недостаточно места на диске", errno=28)


# ----------------------------------------------------------------------------------------
# Синхронизация (сейчас не используются: Яндекс.Диск — коды YaDiskResult, app/network)
# ----------------------------------------------------------------------------------------

class SyncError(AppException):
    """Базовое исключение для ошибок синхронизации."""

    def __init__(
        self,
        message: str, # текст ошибки
        code: int = 5000, # код ошибки
    ):
        super().__init__(message, code)


class DownloadError(SyncError):
    """Ошибка при скачивании файла."""

    def __init__(
        self,
        reason: str, # причина
    ):
        message = f"Ошибка скачивания: {reason}"
        super().__init__(message, code=5001)
        self.reason = reason


class UploadError(SyncError):
    """Ошибка при загрузке файла."""

    def __init__(
        self,
        reason: str, # причина
    ):
        message = f"Ошибка загрузки: {reason}"
        super().__init__(message, code=5002)
        self.reason = reason


class TokenError(SyncError):
    """Ошибка, связанная с токеном Яндекс.Диска."""

    def __init__(self):
        message = "Неверный или отсутствующий токен Яндекс.Диска."
        super().__init__(message, code=5003)


# ----------------------------------------------------------------------------------------
# База данных
# ----------------------------------------------------------------------------------------

class DatabaseError(AppException):
    """Базовое исключение для ошибок базы данных."""

    def __init__(
        self,
        message: str, # текст ошибки
        code: int = 6000, # код ошибки
    ):
        super().__init__(message, code)


class IntegrityError(DatabaseError):
    """
    Нарушение целостности данных (дубликат, внешний ключ и т. д.).

    Не путать с ``sqlalchemy.exc.IntegrityError`` (ошибка драйвера).
    """

    def __init__(
        self,
        detail: str, # подробности
    ):
        message = f"Нарушение целостности данных: {detail}"
        super().__init__(message, code=6001)
        self.detail = detail


class DatabaseConnectionError(DatabaseError):
    """
    Ошибка подключения к базе данных.

    Example:
        >>> str(DatabaseConnectionError('файл занят'))
        '[6002] Ошибка подключения к БД: файл занят'
        >>> issubclass(DatabaseConnectionError, OSError)
        False
    """

    def __init__(
        self,
        detail: str, # подробности
    ):
        message = f"Ошибка подключения к БД: {detail}"
        super().__init__(message, code=6002)
        self.detail = detail


# Прежнее имя (совместимость импорта). Перекрывает встроенный ConnectionError в модуле,
# который его импортирует, — в новом коде использовать DatabaseConnectionError.
ConnectionError = DatabaseConnectionError


# ↓ до rework-exceptions, проход 1 (2026-10-21): прежняя реализация модуля
#   (E1–E8 — app/exceptions/IMPLEMENTATION.md, «Журнал проверок»).
#
# class AppException(Exception):
#     """
#     Базовое исключение для всех ошибок приложения.
#     Все пользовательские исключения должны наследовать этот класс.
#     
#     Атрибуты:
#         message (str): Текст ошибки.
#         code (int, optional): Код ошибки для программной обработки.
#     """
#     def __init__(self, message: str, code: int = None):
#         # Вызываем конструктор родителя с сообщением
#         super().__init__(message)
#         # Сохраняем сообщение и код как атрибуты экземпляра
#         self.message = message
#         self.code = code
#
#     def __str__(self):
#         # Представление исключения при выводе
#         if self.code:
#             return f"[{self.code}] {self.message}"
#         return self.message
#
# class EntityNotFoundError(AppException, LookupError):
#     """
#     Запись не найдена — общее исключение для сущностей без своего (DYN9, 2026-10-16):
#     новая таблица, подключённая описанием, не обязана заводить свой класс исключения.
#
#     Пример:
#         >>> raise EntityNotFoundError('Prescription', 5)
#         Traceback (most recent call last):
#         EntityNotFoundError: [9001] Prescription с идентификатором 5 не найден(а).
#     """
#     def __init__(self, entity: str, entity_id: int):
#         super().__init__(f"{entity} с идентификатором {entity_id} не найден(а).", code=9001)
#
#
# class PatientNotFoundError(AppException):
#     """
#     Выбрасывается, когда пациент с указанным идентификатором не найден в базе данных.
#     """
#     def __init__(self, patient_id: int):
#         # Формируем сообщение с подстановкой id
#         message = f"Пациент с идентификатором {patient_id} не найден."
#         # Код ошибки можно задать, например, 1001
#         super().__init__(message, code=1001)
#
# # class PatientValidationError(AppException):
# # ↑ до DATA9 (2026-10-16): только AppException. Теперь и ValueError — общая проверка
# #   полей бросает это исключение, а интерфейс по-прежнему ловит ValueError.
# class PatientValidationError(AppException, ValueError):
#     """
#     Выбрасывается при ошибке валидации данных пациента (например, пустое имя).
#     """
#     def __init__(self, field: str, reason: str):
#         message = f"Ошибка валидации поля '{field}': {reason}."
#         super().__init__(message, code=1002)
#
#
#
# class AppointmentNotFoundError(AppException):
#     def __init__(self, appointment_id: int):
#         message = f"Приём с идентификатором {appointment_id} не найден."
#         super().__init__(message, code=2001)
#
# # class AppointmentValidationError(AppException):
# # ↑ до DATA9 (2026-10-16): только AppException. Теперь и ValueError — общая проверка
# #   полей бросает это исключение, а интерфейс по-прежнему ловит ValueError.
# class AppointmentValidationError(AppException, ValueError):
#     def __init__(self, field: str, reason: str):
#         message = f"Ошибка валидации приёма, поле '{field}': {reason}."
#         super().__init__(message, code=2002)
#
#
#
# class AppointmentNoteNotFoundError(AppException):
#     def __init__(self, note_id: int):
#         message = f"Заметка приёма с идентификатором {note_id} не найдена."
#         super().__init__(message, code=3001)
#
# # class AppointmentNoteValidationError(AppException):
# # ↑ до DATA9 (2026-10-16): только AppException. Теперь и ValueError — общая проверка
# #   полей бросает это исключение, а интерфейс по-прежнему ловит ValueError.
# class AppointmentNoteValidationError(AppException, ValueError):
#     def __init__(self, field: str, reason: str):
#         message = f"Ошибка валидации заметки, поле '{field}': {reason}."
#         super().__init__(message, code=3002)
#
#
#
# class PhotoNotFoundError(AppException):
#     def __init__(self, photo_id: int):
#         message = f"Фотография с идентификатором {photo_id} не найдена."
#         super().__init__(message, code=4001)
#
# # class PhotoValidationError(AppException):
# # ↑ до DATA9 (2026-10-16): только AppException. Теперь и ValueError — общая проверка
# #   полей бросает это исключение, а интерфейс по-прежнему ловит ValueError.
# class PhotoValidationError(AppException, ValueError):
#     def __init__(self, field: str, reason: str):
#         message = f"Ошибка валидации фотографии, поле '{field}': {reason}."
#         super().__init__(message, code=4002)
#
# class PhotoFileError(AppException):
#     def __init__(self, path: str, operation: str, reason: str, errno: int = None):
#         message = f"Ошибка {operation} файла '{path}': {reason}"
#         if errno:
#             message += f" (код ошибки: {errno})"
#         super().__init__(message, code=4003)
#         self.errno = errno
#
# class PhotoStoragePermissionError(PhotoFileError):
#     def __init__(self, path: str, operation: str):
#         super().__init__(path, operation, "недостаточно прав доступа", errno=13)
#
# class PhotoStorageNoSpaceError(PhotoFileError):
#     def __init__(self, path: str, operation: str):
#         super().__init__(path, operation, "недостаточно места на диске", errno=28)
#
#
#
#
# class SyncError(AppException):
#     """Базовое исключение для ошибок синхронизации."""
#     def __init__(self, message: str, code: int = 5000):
#         super().__init__(message, code)
#
# class DownloadError(SyncError):
#     """Ошибка при скачивании файла."""
#     def __init__(self, reason: str):
#         message = f"Ошибка скачивания: {reason}"
#         super().__init__(message, code=5001)
#
# class UploadError(SyncError):
#     """Ошибка при загрузке файла."""
#     def __init__(self, reason: str):
#         message = f"Ошибка загрузки: {reason}"
#         super().__init__(message, code=5002)
#
# class TokenError(SyncError):
#     """Ошибка, связанная с токеном Яндекс.Диска."""
#     def __init__(self):
#         message = "Неверный или отсутствующий токен Яндекс.Диска."
#         super().__init__(message, code=5003)
#
#
#
#
# class DatabaseError(AppException):
#     """Базовое исключение для ошибок базы данных."""
#     def __init__(self, message: str, code: int = 6000):
#         super().__init__(message, code)
#
# class IntegrityError(DatabaseError):
#     """Нарушение целостности данных (дубликат, внешний ключ и т.д.)."""
#     def __init__(self, detail: str):
#         message = f"Нарушение целостности данных: {detail}"
#         super().__init__(message, code=6001)
#
# class ConnectionError(DatabaseError):
#     """Ошибка подключения к базе данных."""
#     def __init__(self, detail: str):
#         message = f"Ошибка подключения к БД: {detail}"
#         super().__init__(message, code=6002)
#
#
#
