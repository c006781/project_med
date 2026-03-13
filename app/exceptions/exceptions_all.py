class AppException(Exception):
    """
    Базовое исключение для всех ошибок приложения.
    Все пользовательские исключения должны наследовать этот класс.
    
    Атрибуты:
        message (str): Текст ошибки.
        code (int, optional): Код ошибки для программной обработки.
    """
    def __init__(self, message: str, code: int = None):
        # Вызываем конструктор родителя с сообщением
        super().__init__(message)
        # Сохраняем сообщение и код как атрибуты экземпляра
        self.message = message
        self.code = code

    def __str__(self):
        # Представление исключения при выводе
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message

class PatientNotFoundError(AppException):
    """
    Выбрасывается, когда пациент с указанным идентификатором не найден в базе данных.
    """
    def __init__(self, patient_id: int):
        # Формируем сообщение с подстановкой id
        message = f"Пациент с идентификатором {patient_id} не найден."
        # Код ошибки можно задать, например, 1001
        super().__init__(message, code=1001)

class PatientValidationError(AppException):
    """
    Выбрасывается при ошибке валидации данных пациента (например, пустое имя).
    """
    def __init__(self, field: str, reason: str):
        message = f"Ошибка валидации поля '{field}': {reason}."
        super().__init__(message, code=1002)



class AppointmentNotFoundError(AppException):
    def __init__(self, appointment_id: int):
        message = f"Приём с идентификатором {appointment_id} не найден."
        super().__init__(message, code=2001)

class AppointmentValidationError(AppException):
    def __init__(self, field: str, reason: str):
        message = f"Ошибка валидации приёма, поле '{field}': {reason}."
        super().__init__(message, code=2002)



class AppointmentNoteNotFoundError(AppException):
    def __init__(self, note_id: int):
        message = f"Заметка приёма с идентификатором {note_id} не найдена."
        super().__init__(message, code=3001)

class AppointmentNoteValidationError(AppException):
    def __init__(self, field: str, reason: str):
        message = f"Ошибка валидации заметки, поле '{field}': {reason}."
        super().__init__(message, code=3002)



class PhotoNotFoundError(AppException):
    def __init__(self, photo_id: int):
        message = f"Фотография с идентификатором {photo_id} не найдена."
        super().__init__(message, code=4001)

class PhotoValidationError(AppException):
    def __init__(self, field: str, reason: str):
        message = f"Ошибка валидации фотографии, поле '{field}': {reason}."
        super().__init__(message, code=4002)

# class PhotoFileError(AppException):
#     """
#     Ошибка при работе с файлом фотографии (не найден, не удалось скопировать и т.д.).
#     """
#     def __init__(self, path: str, operation: str, reason: str):
#         message = f"Ошибка {operation} файла '{path}': {reason}."
#         super().__init__(message, code=4003)

class PhotoFileError(AppException):
    def __init__(self, path: str, operation: str, reason: str, errno: int = None):
        message = f"Ошибка {operation} файла '{path}': {reason}"
        if errno:
            message += f" (код ошибки: {errno})"
        super().__init__(message, code=4003)
        self.errno = errno

class PhotoStoragePermissionError(PhotoFileError):
    def __init__(self, path: str, operation: str):
        super().__init__(path, operation, "недостаточно прав доступа", errno=13)

class PhotoStorageNoSpaceError(PhotoFileError):
    def __init__(self, path: str, operation: str):
        super().__init__(path, operation, "недостаточно места на диске", errno=28)




class SyncError(AppException):
    """Базовое исключение для ошибок синхронизации."""
    def __init__(self, message: str, code: int = 5000):
        super().__init__(message, code)

class DownloadError(SyncError):
    """Ошибка при скачивании файла."""
    def __init__(self, reason: str):
        message = f"Ошибка скачивания: {reason}"
        super().__init__(message, code=5001)

class UploadError(SyncError):
    """Ошибка при загрузке файла."""
    def __init__(self, reason: str):
        message = f"Ошибка загрузки: {reason}"
        super().__init__(message, code=5002)

class TokenError(SyncError):
    """Ошибка, связанная с токеном Яндекс.Диска."""
    def __init__(self):
        message = "Неверный или отсутствующий токен Яндекс.Диска."
        super().__init__(message, code=5003)




class DatabaseError(AppException):
    """Базовое исключение для ошибок базы данных."""
    def __init__(self, message: str, code: int = 6000):
        super().__init__(message, code)

class IntegrityError(DatabaseError):
    """Нарушение целостности данных (дубликат, внешний ключ и т.д.)."""
    def __init__(self, detail: str):
        message = f"Нарушение целостности данных: {detail}"
        super().__init__(message, code=6001)

class ConnectionError(DatabaseError):
    """Ошибка подключения к базе данных."""
    def __init__(self, detail: str):
        message = f"Ошибка подключения к БД: {detail}"
        super().__init__(message, code=6002)



