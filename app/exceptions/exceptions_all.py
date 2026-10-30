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
    │   ├── PhotoStoragePermissionError                                errno 13
    │   └── PhotoStorageNoSpaceError                                   errno 28
    ├── SyncError → DownloadError, UploadError, TokenError             5000–5003
    └── DatabaseError → IntegrityError, DatabaseConnectionError        6000–6002

Сейчас нигде не бросаются ``PhotoStorage*Error``, исключения синхронизации и базы данных
(``_dev/ИДЕИ.md`` И-9; варианты — ``app/exceptions/IMPLEMENTATION.md`` §4).

Новой таблице свой класс не нужен: ``EntityNotFoundError('Назначение', 5)`` и
``EntityValidationError('Доза', 'обязательное поле', entity='Назначение')``. Свой класс —
только если нужен свой код или текст: наследник с ``super().__init__(..., code=, message=)``.

Ловить «не найдено» любой таблицы — ``except EntityNotFoundError`` (или ``LookupError``),
ошибку проверки любого поля — ``except EntityValidationError`` (или ``ValueError``); поле и
причина — ``exc.field``, ``exc.reason`` (подсветить поле в окне).

Подробности и журнал проверок — ``app/exceptions/IMPLEMENTATION.md``.

Пример:
    >>> str(PatientNotFoundError(42))
    '[1001] Пациент с идентификатором 42 не найден.'
    >>> isinstance(PatientNotFoundError(42), EntityNotFoundError)
    True
    >>> err = PhotoValidationError('file_path', 'пустой путь')
    >>> (err.entity, err.field, err.reason, isinstance(err, ValueError))
    ('Фотография', 'file_path', 'пустой путь', True)
"""

from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Type, Union

# Подробности для журнала: текст или словарь «что — значение» (файл, таблица, параметры, SQL)
Details = Union[str, Mapping[str, Any]]

# Значения подробностей, которые pickle/copy переносят как есть (остальные — их repr)
_PLAIN_TYPES = (str, int, float, bool, type(None))


def _exception_text(
    exc : BaseException,   # ошибка
) -> str: # тип и текст ошибки одной строкой
    """
    Возвращает тип и текст ошибки: ``'<тип>: <текст>'`` или только тип, если текста нет.

    Тип встроенной ошибки — без модуля (``ValueError``), остальных — с модулем
    (``sqlite3.IntegrityError``, ``sqlalchemy.exc.IntegrityError``): в журнале видно, откуда
    ошибка пришла.

    Args:
        exc : (BaseException) Ошибка.

    Returns:
        (str) Тип и текст.

    Example:
        >>> _exception_text(ValueError('плохое число'))
        'ValueError: плохое число'
        >>> import sqlite3
        >>> _exception_text(sqlite3.IntegrityError('UNIQUE constraint failed'))
        'sqlite3.IntegrityError: UNIQUE constraint failed'
        >>> _exception_text(KeyError())
        'KeyError'
    """
    cls = type(exc)
    name = cls.__qualname__
    if cls.__module__ != 'builtins': # не встроенная — с модулем
        name = f"{cls.__module__}.{name}"
    text = str(exc)
    return f"{name}: {text}" if text else name


def _details_text(
    details : Optional[Details],   # подробности
) -> str: # подробности одной строкой для журнала
    """
    Возвращает подробности одной строкой: текст — как есть, словарь — ``ключ=значение``
    через ``'; '`` в порядке ключей; пустые (``None``, ``''``, ``{}``) — ``''``.

    Args:
        details : (str/Mapping/None) Подробности; None — нет.

    Returns:
        (str) Строка для журнала (``''`` — подробностей нет).

    Example:
        >>> _details_text({'таблица': 'patients', 'id': 5})
        'таблица=patients; id=5'
        >>> _details_text('путь a.png'), _details_text(None)
        ('путь a.png', '')
    """
    if not details:
        return ''
    if isinstance(details, Mapping):
        return '; '.join(f"{key}={value}" for key, value in details.items())
    return str(details)


def _root_cause(
    exc : BaseException,   # ошибка, с которой начинается спуск
) -> Optional[BaseException]: # первопричина цепочки
    """
    Возвращает первопричину цепочки ошибок — самую глубокую.

    Спуск — по ``__cause__`` (``raise … from exc``), а без него — по ``__context__``
    (ошибка поднята при обработке другой), как в ``app/database/migrate.py``
    ``startup_error_text``. ``raise … from None`` (``__suppress_context__``) обрывает спуск:
    исходную ошибку скрыли намеренно. Зацикленная цепочка (собранная вручную) не зависает —
    каждая ошибка проходится один раз.

    Args:
        exc : (BaseException) Ошибка, с которой начинается спуск.

    Returns:
        (BaseException/None) Первопричина; None — цепочки нет.

    Example:
        >>> try:
        ...     try:
        ...         raise KeyError('id')
        ...     except KeyError as key_exc:
        ...         raise OSError('нет файла') from key_exc
        ... except OSError as os_exc:
        ...     root = _root_cause(os_exc)
        >>> root
        KeyError('id')
        >>> _root_cause(ValueError('без цепочки')) is None
        True
    """
    seen = {id(exc)}
    current = exc
    while True:
        if current.__cause__ is not None:
            deeper = current.__cause__
        elif not current.__suppress_context__: # без from — неявная цепочка
            deeper = current.__context__
        else:
            deeper = None
        if deeper is None or id(deeper) in seen:
            break
        seen.add(
            id(deeper),   # пройдена
        )
        current = deeper
    return None if current is exc else current


def _restore_exception(
    cls   : Type['AppException'],  # класс исключения
    state : Dict[str, Any],        # атрибуты экземпляра (__dict__)
) -> 'AppException':
    """
    Восстановление исключения при ``pickle``/``copy`` без вызова ``__init__``.

    ``__init__`` наследников принимает не текст, а данные (``patient_id``, ``path`` …),
    поэтому стандартное восстановление ``cls(*args)`` у них ломается. Здесь экземпляр
    создаётся через ``__new__``, ``args`` — как у ``Exception(message)``, атрибуты
    переносятся из ``state``.

    Args:
        cls (Type[AppException]): Класс.
        state (Dict[str, Any]): Атрибуты.

    Returns:
        AppException: Копия исключения.

    Пример:
        >>> exc = _restore_exception(PatientNotFoundError, {'message': 'нет', 'code': 1001})
        >>> (type(exc).__name__, str(exc), exc.args)
        ('PatientNotFoundError', '[1001] нет', ('нет',))
    """
    exc = cls.__new__(cls)
    # args — как после AppException.__init__ (Exception(message))
    Exception.__init__(
        exc,                         # экземпляр
        state.get('message', ''),    # текст ошибки
    )
    exc.__dict__.update(state)
    return exc


class AppException(Exception):
    """
    Базовое исключение для всех ошибок приложения.

    Все исключения приложения наследуют этот класс. Три уровня текста:

    * ``message`` — понятный текст пользователю (``str(exc)`` — ``[код] текст``);
    * ``details`` — что делали (файл, таблица, параметры, SQL) — только для журнала;
    * ``original`` — исходная ошибка «из глубины» как есть: явная (``original=exc``) или
      первопричина цепочки ``raise … from``; ``original_text`` — её тип и текст.

    ``log_text()`` собирает всё для журнала. Само исключение в журнал не пишет — пишет тот,
    кто его ловит и показывает (окно, командная строка, ``session_scope``), трассировку — через
    ``exc_info``: так записи не дублируются.

    Attributes:
        message : (str) Текст ошибки для пользователя.
        code    : (int/None) Код ошибки для программной обработки; None — без кода.
        details : (str/Mapping/None) Подробности для журнала; None — нет.

    Example:
        >>> str(AppException('сбой', code=7))
        '[7] сбой'
        >>> str(AppException('сбой'))
        'сбой'
        >>> print(AppException(
        ...     'Не удалось сохранить',                 # текст пользователю
        ...     code     =   7,                         # код
        ...     details  =   {'таблица': 'patients'},   # что делали
        ...     original =   OSError('диск занят'),     # исходная ошибка
        ... ).log_text())
        [7] Не удалось сохранить
          Подробности: таблица=patients
          Исходная ошибка: OSError: диск занят
    """

    # Умолчания на уровне класса: экземпляр, восстановленный из старого pickle или
    # через _restore_exception без этих ключей, читает их отсюда
    details        : Optional[Details]       = None   # подробности для журнала
    _original      : Optional[BaseException] = None   # явная исходная ошибка
    _original_text : Optional[str]           = None   # её текст после pickle/copy

    def __init__(
        self,
        message  : str,                               # текст ошибки для пользователя
        code     : Optional[int] = None,              # код ошибки (None — без кода)
        *,
        details  : Optional[Details] = None,          # что делали (для журнала)
        original : Optional[BaseException] = None,    # исходная ошибка (None — из цепочки)
    ) -> None:
        """
        Создаёт исключение с текстом, кодом и (по желанию) подробностями и исходной ошибкой.

        ``details`` и ``original`` — только именованные и необязательные: прежние вызовы
        ``AppException(message, code)`` работают как раньше. ``args`` — ``(message,)``, как
        у ``Exception(message)``.

        Args:
            message  : (str) Текст ошибки для пользователя.
            code     : (int/None) Код ошибки; None — без кода.
            details  : (str/Mapping/None) Что делали: файл, таблица, параметры, SQL; None — нет.
            original : (BaseException/None) Исходная ошибка; None — первопричина цепочки
                ``raise … from`` (если её нет — исходной ошибки нет).

        Example:
            >>> exc = AppException('сбой', code=7)
            >>> (exc.message, exc.code, exc.args, exc.details, exc.original)
            ('сбой', 7, ('сбой',), None, None)
        """
        # Вызываем конструктор родителя с сообщением
        super().__init__(message)
        # Сохраняем сообщение и код как атрибуты экземпляра
        self.message = message
        self.code = code
        self.details = details
        self._original = original

    @property
    def original(self) -> Optional[BaseException]: # исходная ошибка
        """
        Исходная ошибка: явная (``original=exc``) как есть, иначе — первопричина цепочки.

        Цепочка читается в момент обращения (``__cause__`` появляется после ``raise … from``),
        поэтому свойство, а не атрибут. После ``pickle``/``copy`` — ``None`` (сама ошибка не
        переносится), текст остаётся в ``original_text``.

        Returns:
            (BaseException/None) Исходная ошибка; None — её нет.

        Example:
            >>> try:
            ...     try:
            ...         raise KeyError('id')
            ...     except KeyError as key_exc:
            ...         raise AppException('Нет записи') from key_exc
            ... except AppException as exc:
            ...     found = exc.original
            >>> found
            KeyError('id')
        """
        if self._original is not None:
            return self._original
        return _root_cause(self)

    @property
    def original_text(self) -> Optional[str]: # тип и текст исходной ошибки
        """
        Тип и текст исходной ошибки (``'sqlite3.IntegrityError: UNIQUE …'``).

        Returns:
            (str/None) Текст; None — исходной ошибки нет.

        Example:
            >>> AppException('сбой', original=ValueError('плохо')).original_text
            'ValueError: плохо'
            >>> AppException('сбой').original_text is None
            True
        """
        original = self.original
        if original is not None:
            return _exception_text(original)
        return self._original_text   # после pickle/copy

    def log_text(self) -> str: # полный текст для журнала
        """
        Возвращает полный текст для журнала: ``str(exc)``, затем подробности и исходная
        ошибка — по строке с отступом; пустые части не выводятся.

        Трассировку не добавляет — её даёт ``logger.error(…, exc_info=exc)`` у того, кто
        пишет в журнал. Без подробностей и исходной ошибки — то же, что ``str(exc)``.

        Returns:
            (str) Текст для журнала.

        Example:
            >>> print(AppException('сбой', details='путь a.png').log_text())
            сбой
              Подробности: путь a.png
            >>> AppException('сбой', code=7).log_text()
            '[7] сбой'
        """
        lines = [str(self)]
        details_text = _details_text(self.details)
        if details_text:
            lines.append(f"  Подробности: {details_text}")
        original_text = self.original_text
        if original_text:
            lines.append(f"  Исходная ошибка: {original_text}")
        return '\n'.join(lines)

    def __str__(self) -> str:
        """
        Текст исключения: ``[код] сообщение`` или только сообщение.

        Код ``0`` — тоже код (без кода — только ``None``, как в ``__init__``). Текст не
        строкой (``AppException(OSError(...))``) приводится к строке: ``__str__`` не должен
        падать — его зовут журналы и окна ошибок.

        Returns:
            str: Текст.

        Пример:
            >>> str(AppException('сбой', code=7))
            '[7] сбой'
            >>> str(AppException('сбой', code=0))
            '[0] сбой'
            >>> str(AppException(OSError('нет файла')))
            'нет файла'
        """
        # if self.code:
        #     return f"[{self.code}] {self.message}"
        # return self.message
        # ↑ до 2026-10-25 (E9, E10): код 0 считался «без кода» (вопреки «None — без кода»);
        #   текст не строкой давал TypeError «__str__ returned non-string».
        if self.code is not None:
            return f"[{self.code}] {self.message}"
        return str(self.message)

    def __reduce__(self) -> Tuple[
        Callable[..., 'AppException'],
        Tuple[Type['AppException'], Dict[str, Any]],
    ]:
        """
        Поддержка ``pickle``/``copy`` для наследников с любой сигнатурой ``__init__``.

        Переносится копия ``__dict__``, кроме того, что может не сериализоваться:

        * исходная ошибка (явная или из цепочки — цепочку ``pickle`` не переносит) — только
          текстом (``original_text``); у копии ``original`` — ``None``;
        * значения словаря ``details`` сложнее ``str``/``int``/``float``/``bool``/``None`` —
          их ``repr``.

        Без исходной ошибки и словаря подробностей ``__dict__`` копии равен исходному.

        Returns:
            (Tuple[Callable, tuple]) Функция восстановления (``_restore_exception``) и её
                аргументы — класс и атрибуты.

        Example:
            >>> import pickle
            >>> str(pickle.loads(pickle.dumps(PhotoFileError('a.png', 'чтения', 'нет файла'))))
            "[4003] Ошибка чтения файла 'a.png': нет файла"
            >>> copied = pickle.loads(pickle.dumps(AppException('сбой', original=OSError('занят'))))
            >>> (copied.original, copied.original_text)
            (None, 'OSError: занят')
        """
        # return (
        #     _restore_exception,         # функция восстановления
        #     (
        #         type(self),             # класс
        #         dict(self.__dict__),    # атрибуты (копия)
        #     ),
        # )
        # ↑ до 2026-10-31 (Ф1.6.8а): __dict__ целиком — исходная ошибка (часто не
        #   сериализуется, например с соединением внутри) и значения подробностей ломали бы pickle.
        state = dict(self.__dict__)
        original_text = self.original_text
        if original_text is not None: # исходная ошибка — только текстом
            state['_original'] = None
            state['_original_text'] = original_text
        if isinstance(self.details, Mapping): # значения подробностей — простые или repr
            state['details'] = {
                key: value if isinstance(value, _PLAIN_TYPES) else repr(value)
                for key, value in self.details.items()
            }
        return (
            _restore_exception,     # функция восстановления
            (
                type(self),         # класс
                state,              # атрибуты (копия без несериализуемого)
            ),
        )


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

    Пример:
        >>> raise EntityNotFoundError('Prescription', 5)  # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
        EntityNotFoundError: [9001] Prescription с идентификатором 5 не найден(а).
        >>> str(EntityNotFoundError('Prescription', 5))
        '[9001] Prescription с идентификатором 5 не найден(а).'
    """

    def __init__(
        self,
        entity    : str,                    # что не найдено
        entity_id : Any,                    # идентификатор записи
        code      : int = 9001,             # код ошибки (у наследников — свой)
        message   : Optional[str] = None,   # свой текст (None — общий)
    ) -> None:
        """
        Создание «не найдено» с общим или своим текстом.

        Args:
            entity (str): Что не найдено.
            entity_id (Any): Идентификатор.
            code (int): Код ошибки.
            message (Optional[str]): Текст; по умолчанию —
                ``'<entity> с идентификатором <id> не найден(а).'``.

        Пример:
            >>> exc = EntityNotFoundError('X', 1, code=77, message='нет X')
            >>> (str(exc), exc.entity, exc.entity_id)
            ('[77] нет X', 'X', 1)
        """
        if message is None:
            message = f"{entity} с идентификатором {entity_id} не найден(а)."
        super().__init__(
            message,        # текст
            code = code,    # код
        )
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

    Пример:
        >>> str(EntityValidationError('Доза', 'обязательное поле', entity='Назначение'))
        "[9002] Ошибка валидации Назначение, поле 'Доза': обязательное поле."
        >>> str(EntityValidationError('Доза', 'обязательное поле'))
        "[9002] Ошибка валидации, поле 'Доза': обязательное поле."
    """

    def __init__(
        self,
        field   : str,                    # поле с ошибкой
        reason  : str,                    # причина
        entity  : Optional[str] = None,   # таблица/запись
        code    : int = 9002,             # код ошибки (у наследников — свой)
        message : Optional[str] = None,   # свой текст (None — общий)
    ) -> None:
        """
        Создание ошибки проверки поля с общим или своим текстом.

        Args:
            field (str): Поле.
            reason (str): Причина.
            entity (Optional[str]): Таблица/запись.
            code (int): Код ошибки.
            message (Optional[str]): Текст; по умолчанию —
                ``"Ошибка валидации <entity>, поле '<field>': <reason>."``.

        Пример:
            >>> exc = EntityValidationError('Доза', 'пусто', entity='Назначение')
            >>> (exc.field, exc.reason, exc.entity, exc.code)
            ('Доза', 'пусто', 'Назначение', 9002)
        """
        if message is None:
            where = f" {entity}" if entity else ""
            message = f"Ошибка валидации{where}, поле '{field}': {reason}."
        super().__init__(
            message,        # текст
            code = code,    # код
        )
        self.field = field
        self.reason = reason
        self.entity = entity


class PatientNotFoundError(EntityNotFoundError):
    """
    Пациент с указанным идентификатором не найден в базе данных.

    Пример:
        >>> str(PatientNotFoundError(7))
        '[1001] Пациент с идентификатором 7 не найден.'
    """

    def __init__(
        self,
        patient_id : Any,   # идентификатор пациента
    ) -> None:
        """
        Создание «пациент не найден» (код 1001, прежний текст).

        Args:
            patient_id (Any): Идентификатор пациента.

        Пример:
            >>> exc = PatientNotFoundError(7)
            >>> (exc.entity, exc.entity_id, exc.code)
            ('Пациент', 7, 1001)
        """
        super().__init__(
            'Пациент',                                                  # что не найдено
            patient_id,                                                 # идентификатор
            code    = 1001,                                             # код пациентов
            message = f"Пациент с идентификатором {patient_id} не найден.",  # прежний текст
        )


# class PatientValidationError(AppException):
# ↑ до DATA9 (2026-10-16): только AppException. Теперь и ValueError — общая проверка
#   полей бросает это исключение, а интерфейс по-прежнему ловит ValueError.
class PatientValidationError(EntityValidationError):
    """
    Ошибка проверки данных пациента (например, пустое имя).

    Пример:
        >>> str(PatientValidationError('first_name', 'пусто'))
        "[1002] Ошибка валидации поля 'first_name': пусто."
    """

    def __init__(
        self,
        field  : str,   # поле с ошибкой
        reason : str,   # причина
    ) -> None:
        """
        Создание ошибки проверки пациента (код 1002, прежний текст).

        Args:
            field (str): Поле.
            reason (str): Причина.

        Пример:
            >>> exc = PatientValidationError('first_name', 'пусто')
            >>> (exc.entity, exc.field, exc.reason, exc.code)
            ('Пациент', 'first_name', 'пусто', 1002)
        """
        super().__init__(
            field,                                                    # поле
            reason,                                                   # причина
            entity  = 'Пациент',                                      # таблица
            code    = 1002,                                           # код пациентов
            message = f"Ошибка валидации поля '{field}': {reason}.",  # прежний текст
        )


class AppointmentNotFoundError(EntityNotFoundError):
    """
    Приём с указанным идентификатором не найден.

    Пример:
        >>> str(AppointmentNotFoundError(3))
        '[2001] Приём с идентификатором 3 не найден.'
    """

    def __init__(
        self,
        appointment_id : Any,   # идентификатор приёма
    ) -> None:
        """
        Создание «приём не найден» (код 2001, прежний текст).

        Args:
            appointment_id (Any): Идентификатор приёма.

        Пример:
            >>> exc = AppointmentNotFoundError(3)
            >>> (exc.entity, exc.entity_id, exc.code)
            ('Приём', 3, 2001)
        """
        super().__init__(
            'Приём',                                                     # что не найдено
            appointment_id,                                              # идентификатор
            code    = 2001,                                              # код приёмов
            message = f"Приём с идентификатором {appointment_id} не найден.",  # прежний текст
        )


# class AppointmentValidationError(AppException):
# ↑ до DATA9 (2026-10-16): только AppException. Теперь и ValueError — общая проверка
#   полей бросает это исключение, а интерфейс по-прежнему ловит ValueError.
class AppointmentValidationError(EntityValidationError):
    """
    Ошибка проверки данных приёма.

    Пример:
        >>> str(AppointmentValidationError('date', 'в будущем'))
        "[2002] Ошибка валидации приёма, поле 'date': в будущем."
    """

    def __init__(
        self,
        field  : str,   # поле с ошибкой
        reason : str,   # причина
    ) -> None:
        """
        Создание ошибки проверки приёма (код 2002, прежний текст).

        Args:
            field (str): Поле.
            reason (str): Причина.

        Пример:
            >>> exc = AppointmentValidationError('date', 'в будущем')
            >>> (exc.entity, exc.field, exc.code)
            ('Приём', 'date', 2002)
        """
        super().__init__(
            field,                                                            # поле
            reason,                                                           # причина
            entity  = 'Приём',                                                # таблица
            code    = 2002,                                                   # код приёмов
            message = f"Ошибка валидации приёма, поле '{field}': {reason}.",  # прежний текст
        )


class AppointmentNoteNotFoundError(EntityNotFoundError):
    """
    Заметка приёма с указанным идентификатором не найдена.

    Пример:
        >>> str(AppointmentNoteNotFoundError(5))
        '[3001] Заметка приёма с идентификатором 5 не найдена.'
    """

    def __init__(
        self,
        note_id : Any,   # идентификатор заметки
    ) -> None:
        """
        Создание «заметка не найдена» (код 3001, прежний текст).

        Args:
            note_id (Any): Идентификатор заметки.

        Пример:
            >>> exc = AppointmentNoteNotFoundError(5)
            >>> (exc.entity, exc.entity_id, exc.code)
            ('Заметка приёма', 5, 3001)
        """
        super().__init__(
            'Заметка приёма',                                                 # что не найдено
            note_id,                                                          # идентификатор
            code    = 3001,                                                   # код заметок
            message = f"Заметка приёма с идентификатором {note_id} не найдена.",  # прежний текст
        )


# class AppointmentNoteValidationError(AppException):
# ↑ до DATA9 (2026-10-16): только AppException. Теперь и ValueError — общая проверка
#   полей бросает это исключение, а интерфейс по-прежнему ловит ValueError.
class AppointmentNoteValidationError(EntityValidationError):
    """
    Ошибка проверки данных заметки.

    Пример:
        >>> str(AppointmentNoteValidationError('text', 'пусто'))
        "[3002] Ошибка валидации заметки, поле 'text': пусто."
    """

    def __init__(
        self,
        field  : str,   # поле с ошибкой
        reason : str,   # причина
    ) -> None:
        """
        Создание ошибки проверки заметки (код 3002, прежний текст).

        Args:
            field (str): Поле.
            reason (str): Причина.

        Пример:
            >>> exc = AppointmentNoteValidationError('text', 'пусто')
            >>> (exc.entity, exc.field, exc.code)
            ('Заметка', 'text', 3002)
        """
        super().__init__(
            field,                                                             # поле
            reason,                                                            # причина
            entity  = 'Заметка',                                               # таблица
            code    = 3002,                                                    # код заметок
            message = f"Ошибка валидации заметки, поле '{field}': {reason}.",  # прежний текст
        )


class PhotoNotFoundError(EntityNotFoundError):
    """
    Фотография с указанным идентификатором не найдена.

    Пример:
        >>> str(PhotoNotFoundError(9))
        '[4001] Фотография с идентификатором 9 не найдена.'
    """

    def __init__(
        self,
        photo_id : Any,   # идентификатор фотографии
    ) -> None:
        """
        Создание «фотография не найдена» (код 4001, прежний текст).

        Args:
            photo_id (Any): Идентификатор фотографии.

        Пример:
            >>> exc = PhotoNotFoundError(9)
            >>> (exc.entity, exc.entity_id, exc.code)
            ('Фотография', 9, 4001)
        """
        super().__init__(
            'Фотография',                                                 # что не найдено
            photo_id,                                                     # идентификатор
            code    = 4001,                                               # код фото
            message = f"Фотография с идентификатором {photo_id} не найдена.",  # прежний текст
        )


# class PhotoValidationError(AppException):
# ↑ до DATA9 (2026-10-16): только AppException. Теперь и ValueError — общая проверка
#   полей бросает это исключение, а интерфейс по-прежнему ловит ValueError.
class PhotoValidationError(EntityValidationError):
    """
    Ошибка проверки данных фотографии.

    Пример:
        >>> str(PhotoValidationError('file_path', 'пустой путь'))
        "[4002] Ошибка валидации фотографии, поле 'file_path': пустой путь."
    """

    def __init__(
        self,
        field  : str,   # поле с ошибкой
        reason : str,   # причина
    ) -> None:
        """
        Создание ошибки проверки фотографии (код 4002, прежний текст).

        Args:
            field (str): Поле.
            reason (str): Причина.

        Пример:
            >>> exc = PhotoValidationError('file_path', 'пустой путь')
            >>> (exc.entity, exc.field, exc.code)
            ('Фотография', 'file_path', 4002)
        """
        super().__init__(
            field,                                                                # поле
            reason,                                                               # причина
            entity  = 'Фотография',                                               # таблица
            code    = 4002,                                                       # код фото
            message = f"Ошибка валидации фотографии, поле '{field}': {reason}.",  # прежний текст
        )


# ----------------------------------------------------------------------------------------
# Файлы фотографий
# ----------------------------------------------------------------------------------------

class PhotoFileError(AppException):
    """
    Ошибка работы с файлом фотографии.

    Attributes:
        path (str): Файл.
        operation (str): Операция в родительном падеже (``'копирования'``, ``'удаления'`` …)
            — она подставляется в «Ошибка <operation> файла».
        reason (str): Причина.
        errno (Optional[int]): Код ошибки ОС.

    Пример:
        >>> str(PhotoFileError('a.png', 'чтения', 'нет файла', errno=2))
        "[4003] Ошибка чтения файла 'a.png': нет файла (код ошибки: 2)"
    """

    def __init__(
        self,
        path      : str,                    # файл
        operation : str,                    # операция (в родительном падеже: 'копирования')
        reason    : str,                    # причина
        errno     : Optional[int] = None,   # код ошибки ОС
    ) -> None:
        """
        Создание ошибки файла фотографии (код 4003).

        Args:
            path (str): Файл.
            operation (str): Операция в родительном падеже.
            reason (str): Причина.
            errno (Optional[int]): Код ошибки ОС; добавляется в текст, если задан.

        Пример:
            >>> exc = PhotoFileError('a.png', 'копирования', 'занят')
            >>> (exc.path, exc.operation, exc.reason, exc.errno, exc.code)
            ('a.png', 'копирования', 'занят', None, 4003)
        """
        message = f"Ошибка {operation} файла '{path}': {reason}"
        if errno:
            message += f" (код ошибки: {errno})"
        super().__init__(
            message,        # текст
            code = 4003,    # код файлов фото
        )
        self.path = path
        self.operation = operation
        self.reason = reason
        self.errno = errno


class PhotoStoragePermissionError(PhotoFileError):
    """
    Нет прав на файл/папку хранилища фото (errno 13).

    Пример:
        >>> str(PhotoStoragePermissionError('a.png', 'записи'))
        "[4003] Ошибка записи файла 'a.png': недостаточно прав доступа (код ошибки: 13)"
    """

    def __init__(
        self,
        path      : str,   # файл
        operation : str,   # операция (в родительном падеже)
    ) -> None:
        """
        Создание ошибки прав хранилища (причина и errno 13 — заданы).

        Args:
            path (str): Файл.
            operation (str): Операция в родительном падеже.

        Пример:
            >>> PhotoStoragePermissionError('a.png', 'записи').errno
            13
        """
        super().__init__(
            path,                           # файл
            operation,                      # операция
            "недостаточно прав доступа",    # причина
            errno = 13,                     # EACCES
        )


class PhotoStorageNoSpaceError(PhotoFileError):
    """
    Нет места на диске хранилища фото (errno 28).

    Пример:
        >>> str(PhotoStorageNoSpaceError('a.png', 'записи'))
        "[4003] Ошибка записи файла 'a.png': недостаточно места на диске (код ошибки: 28)"
    """

    def __init__(
        self,
        path      : str,   # файл
        operation : str,   # операция (в родительном падеже)
    ) -> None:
        """
        Создание ошибки нехватки места (причина и errno 28 — заданы).

        Args:
            path (str): Файл.
            operation (str): Операция в родительном падеже.

        Пример:
            >>> PhotoStorageNoSpaceError('a.png', 'записи').errno
            28
        """
        super().__init__(
            path,                             # файл
            operation,                        # операция
            "недостаточно места на диске",    # причина
            errno = 28,                       # ENOSPC
        )


# ----------------------------------------------------------------------------------------
# Синхронизация (сейчас не используются: Яндекс.Диск — коды YaDiskResult, app/network;
# _dev/ИДЕИ.md И-9)
# ----------------------------------------------------------------------------------------

class SyncError(AppException):
    """
    Базовое исключение для ошибок синхронизации.

    Пример:
        >>> str(SyncError('сбой'))
        '[5000] сбой'
    """

    def __init__(
        self,
        message : str,          # текст ошибки
        code    : int = 5000,   # код ошибки
    ) -> None:
        """
        Создание ошибки синхронизации.

        Args:
            message (str): Текст ошибки.
            code (int): Код ошибки (наследники задают свой).

        Пример:
            >>> SyncError('сбой', code=5999).code
            5999
        """
        super().__init__(message, code)


class DownloadError(SyncError):
    """
    Ошибка при скачивании файла.

    Пример:
        >>> str(DownloadError('нет сети'))
        '[5001] Ошибка скачивания: нет сети'
    """

    def __init__(
        self,
        reason : str,   # причина
    ) -> None:
        """
        Создание ошибки скачивания (код 5001).

        Args:
            reason (str): Причина.

        Пример:
            >>> DownloadError('нет сети').reason
            'нет сети'
        """
        message = f"Ошибка скачивания: {reason}"
        super().__init__(
            message,        # текст
            code = 5001,    # код скачивания
        )
        self.reason = reason


class UploadError(SyncError):
    """
    Ошибка при загрузке файла.

    Пример:
        >>> str(UploadError('нет места'))
        '[5002] Ошибка загрузки: нет места'
    """

    def __init__(
        self,
        reason : str,   # причина
    ) -> None:
        """
        Создание ошибки загрузки (код 5002).

        Args:
            reason (str): Причина.

        Пример:
            >>> UploadError('нет места').reason
            'нет места'
        """
        message = f"Ошибка загрузки: {reason}"
        super().__init__(
            message,        # текст
            code = 5002,    # код загрузки
        )
        self.reason = reason


class TokenError(SyncError):
    """
    Ошибка, связанная с токеном Яндекс.Диска.

    Пример:
        >>> str(TokenError())
        '[5003] Неверный или отсутствующий токен Яндекс.Диска.'
    """

    def __init__(self) -> None:
        """
        Создание ошибки токена (код 5003, текст постоянный).

        Пример:
            >>> TokenError().code
            5003
        """
        message = "Неверный или отсутствующий токен Яндекс.Диска."
        super().__init__(
            message,        # текст
            code = 5003,    # код токена
        )


# ----------------------------------------------------------------------------------------
# База данных (сейчас не используются: ошибки SQLAlchemy идут как есть, текст для
# пользователя — app/database/migrate.py startup_error_text; _dev/ИДЕИ.md И-9)
# ----------------------------------------------------------------------------------------

class DatabaseError(AppException):
    """
    Базовое исключение для ошибок базы данных.

    Не путать с ``sqlalchemy.exc.DatabaseError`` (ошибка драйвера).

    Пример:
        >>> str(DatabaseError('сбой'))
        '[6000] сбой'
    """

    def __init__(
        self,
        message : str,          # текст ошибки
        code    : int = 6000,   # код ошибки
    ) -> None:
        """
        Создание ошибки базы данных.

        Args:
            message (str): Текст ошибки.
            code (int): Код ошибки (наследники задают свой).

        Пример:
            >>> DatabaseError('сбой', code=6999).code
            6999
        """
        super().__init__(message, code)


class IntegrityError(DatabaseError):
    """
    Нарушение целостности данных (дубликат, внешний ключ и т. д.).

    Не путать с ``sqlalchemy.exc.IntegrityError`` (ошибка драйвера).

    Пример:
        >>> str(IntegrityError('дубликат'))
        '[6001] Нарушение целостности данных: дубликат'
    """

    def __init__(
        self,
        detail : str,   # подробности
    ) -> None:
        """
        Создание ошибки целостности (код 6001).

        Args:
            detail (str): Подробности.

        Пример:
            >>> IntegrityError('дубликат').detail
            'дубликат'
        """
        message = f"Нарушение целостности данных: {detail}"
        super().__init__(
            message,        # текст
            code = 6001,    # код целостности
        )
        self.detail = detail


class DatabaseConnectionError(DatabaseError):
    """
    Ошибка подключения к базе данных.

    Пример:
        >>> str(DatabaseConnectionError('файл занят'))
        '[6002] Ошибка подключения к БД: файл занят'
        >>> issubclass(DatabaseConnectionError, OSError)
        False
    """

    def __init__(
        self,
        detail : str,   # подробности
    ) -> None:
        """
        Создание ошибки подключения к базе (код 6002).

        Args:
            detail (str): Подробности.

        Пример:
            >>> DatabaseConnectionError('файл занят').detail
            'файл занят'
        """
        message = f"Ошибка подключения к БД: {detail}"
        super().__init__(
            message,        # текст
            code = 6002,    # код подключения
        )
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
