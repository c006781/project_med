# app/network/ya_dop.py
"""
Функции работы с Яндекс.Диском (без Qt): скачивание/загрузка файла, проверки токена и путей.

Модуль — основа синхронизации БД: им пользуются потоки окна (`app.network.thread_network`),
сервис синхронизации (`app.services.sync_service.SyncService`, командная строка) и экран
настроек (проверка токена и папки). Подробности, решения и журнал проверок —
`app/network/IMPLEMENTATION.md`.

Договорённости всех функций:

* Коды результата — :class:`YaDiskResult` (наследник ``int``: ``0`` — успех, отрицательные —
  ошибки; прежние числа ``0/-1/-2/-3`` не изменились). Текст для пользователя —
  ``YaDiskResult(code).message``.
* ``if_err=True`` — при ошибке исключение с понятным русским текстом
  (``ConnectionError``, ``FileNotFoundError``, ``IsADirectoryError``, ``FileExistsError``
  или исходное исключение библиотеки); ``if_err=False`` — возвращается код, исключений нет
  (в том числе при обрыве сети).
* Пути на Диске проходят :func:`normalize_remote_path` (``\\`` → ``/``).
* Клиент ``yadisk.YaDisk`` открывается на одну операцию и закрывается (:func:`_open_client`).

Как добавить новую операцию (например, удаление файла на Диске)::

    def yadisk_remove_file(
        ya_token: str,      # OAuth-токен
        ya_file_path: str,  # путь на Диске
        if_err: bool = False,  # исключение (True) или код (False)
    ) -> int:
        ya_file_path = normalize_remote_path(ya_file_path)
        with _open_client(ya_token) as client:
            ok, message = _token_status(client)
            if not ok:
                return _fail(YaDiskResult.NO_CONNECTION, message, ConnectionError, if_err)
            try:
                client.remove(ya_file_path)
                return YaDiskResult.OK
            except Exception:
                if if_err:
                    raise
                return YaDiskResult.FAILED

Пример::

    >>> from app.network.ya_dop import yadisk_download_file, YaDiskResult
    >>> code = yadisk_download_file(          # doctest: +SKIP
    ...     ya_token='y0_...',                # токен из настроек
    ...     ya_file_path='Папка/clinic.db',   # файл на Диске
    ...     local_file_path='./clinic.db',    # куда сохранить
    ... )
    >>> YaDiskResult(code).message            # doctest: +SKIP
    'Готово'
"""

# Стандартные библиотеки Python
import os
import posixpath # пути на Диске — всегда с '/', независимо от ОС
from contextlib import contextmanager
from enum import IntEnum
from typing import Callable, Iterator, Optional, Tuple, Type

# Сторонние библиотеки
import yadisk # pip install yadisk requests
from yadisk.exceptions import DirectoryExistsError, PathExistsError, YaDiskError

# Колбэк прогресса: (сколько байт передано, сколько всего)
ProgressCallback = Callable[[int, int], None]

# Расширения файла БД: путь на Диске без них считается папкой (remote_db_file_path)
DB_EXTENSIONS: Tuple[str, ...] = ('.db', '.sqlite', '.sqlite3')

# Схема пути Яндекс.Диска ('disk:/папка'); у корня без схемы — '/'
_DISK_SCHEMA = 'disk:'


class YaDiskResult(IntEnum):
    """
    Код результата операции с Яндекс.Диском.

    Наследник ``int``: сравнивается с прежними числами (``code == 0``, ``code == -2``),
    поэтому вызывающий код и сигналы ``Signal(int)`` менять не нужно. Новые коды
    добавляются сюда же — с текстом в :attr:`message`.

    Attributes:
        OK: Успех.
        NO_CONNECTION: Токен недействителен или нет связи с Диском.
        NOT_FOUND: Файла нет (на Диске — при скачивании, локально — при загрузке).
        FAILED: Прочая ошибка (сеть оборвалась во время передачи, нет места и т. п.).
        NOT_A_FILE: Путь на Диске ведёт к папке, а не к файлу.
        ALREADY_EXISTS: Файл на Диске уже есть, а перезапись выключена.

    Example:
        >>> YaDiskResult(-2) is YaDiskResult.NOT_FOUND
        True
        >>> YaDiskResult.OK == 0
        True
        >>> YaDiskResult.NOT_A_FILE.message
        'Путь на Яндекс.Диске ведёт к папке, а не к файлу'
    """

    OK = 0
    NO_CONNECTION = -1
    NOT_FOUND = -2
    FAILED = -3
    NOT_A_FILE = -4
    ALREADY_EXISTS = -5

    @property
    def message(self) -> str:
        """
        Текст результата для пользователя (окно, командная строка).

        Returns:
            str: Короткое описание на русском.

        Example:
            >>> YaDiskResult.NO_CONNECTION.message
            'Токен Яндекс.Диска недействителен или нет соединения'
        """
        return _RESULT_MESSAGES[self]

    @classmethod
    def describe(
        cls,
        code: int, # код, который вернула функция модуля (или поток в сигнале finished)
    ) -> str:
        """
        Текст для любого кода, в том числе неизвестного.

        Args:
            code (int): Код результата.

        Returns:
            str: Текст из :attr:`message`; для неизвестного кода — ``'Неизвестный код N'``.

        Example:
            >>> YaDiskResult.describe(0)
            'Готово'
            >>> YaDiskResult.describe(42)
            'Неизвестный код 42'
        """
        try:
            return cls(code).message
        except ValueError:
            return f'Неизвестный код {code}'


# Тексты кодов (отдельно от перечисления — IntEnum не хранит доп. полей без хитростей)
_RESULT_MESSAGES = {
    YaDiskResult.OK: 'Готово',
    YaDiskResult.NO_CONNECTION: 'Токен Яндекс.Диска недействителен или нет соединения',
    YaDiskResult.NOT_FOUND: 'Файл не найден',
    YaDiskResult.FAILED: 'Ошибка при обмене с Яндекс.Диском',
    YaDiskResult.NOT_A_FILE: 'Путь на Яндекс.Диске ведёт к папке, а не к файлу',
    YaDiskResult.ALREADY_EXISTS: 'Файл на Яндекс.Диске уже есть (перезапись выключена)',
}


# ----------------------------------------------------------------------------------------
# Пути
# ----------------------------------------------------------------------------------------

def normalize_remote_path(
    ya_path: Optional[str], # путь на Диске из настроек/вызова (None — корень)
) -> str:
    """
    Приводит путь на Яндекс.Диске к одному виду.

    * ``None`` и ``''`` → ``''`` (корень Диска — так его понимает ``yadisk``);
    * ``\\`` → ``/`` (путь, набранный в Windows: иначе обратная косая черта уходит на Диск
      как часть имени);
    * повторные ``/`` схлопываются, завершающий ``/`` убирается (кроме корня ``'/'``);
    * схема ``disk:`` и начальный ``/`` сохраняются как есть (``yadisk`` сам добавляет
      ``disk:/`` к пути без схемы).

    Args:
        ya_path (Optional[str]): Путь на Диске.

    Returns:
        str: Нормализованный путь.

    Example:
        >>> normalize_remote_path('Папка\\\\база\\\\')
        'Папка/база'
        >>> normalize_remote_path('/a//b/')
        '/a/b'
        >>> normalize_remote_path('disk:/a/')
        'disk:/a'
        >>> normalize_remote_path(None)
        ''
        >>> normalize_remote_path('/')
        '/'
    """
    if not ya_path:
        return ''
    schema = ''
    path = ya_path.replace('\\', '/')
    if path.startswith(_DISK_SCHEMA):
        schema, path = _DISK_SCHEMA, path[len(_DISK_SCHEMA):]
    # Схлопываем повторные '/', сохраняя начальный
    leading = '/' if path.startswith('/') else ''
    parts = [part for part in path.split('/') if part]
    path = leading + '/'.join(parts)
    return schema + (path or '/') if (schema or leading) else path


def remote_parent_dir(
    ya_path: str, # путь к файлу на Диске (нормализованный или нет)
) -> Optional[str]:
    """
    Родительская папка файла на Диске — та, которую нужно создать перед загрузкой.

    Args:
        ya_path (str): Путь к файлу на Диске.

    Returns:
        Optional[str]: Путь папки; ``None`` — файл лежит в корне (создавать нечего).

    Example:
        >>> remote_parent_dir('/Папка/база/clinic.db')
        '/Папка/база'
        >>> remote_parent_dir('Папка\\\\clinic.db')
        'Папка'
        >>> remote_parent_dir('/clinic.db') is None
        True
        >>> remote_parent_dir('disk:/clinic.db') is None
        True
    """
    path = normalize_remote_path(ya_path)
    parent = posixpath.dirname(path)
    if parent in ('', '/', _DISK_SCHEMA, _DISK_SCHEMA + '/'):
        return None
    return parent


def remote_db_file_path(
    remote_path: Optional[str], # путь на Диске из настроек: файл БД или папка (None — корень)
    local_path: str, # локальный путь к БД — из него берётся имя файла
) -> str:
    """
    Путь к файлу БД на Яндекс.Диске по настройкам.

    В настройках (``database_remote_path``) можно указать файл или папку. Путь без
    расширения из :data:`DB_EXTENSIONS` считается папкой — к нему дописывается имя
    локального файла БД. Им пользуются окно, сервис синхронизации и командная строка,
    чтобы файл на Диске был один и тот же.

    Args:
        remote_path (Optional[str]): Путь на Диске из настроек.
        local_path (str): Локальный путь к файлу БД (разделители любой ОС).

    Returns:
        str: Нормализованный путь к файлу БД на Диске.

    Example:
        >>> remote_db_file_path('Папка/база', './clinic.db')
        'Папка/база/clinic.db'
        >>> remote_db_file_path('Папка\\\\база\\\\', 'C:\\\\data\\\\clinic.db')
        'Папка/база/clinic.db'
        >>> remote_db_file_path('/Папка/main.SQLite', './clinic.db')
        '/Папка/main.SQLite'
        >>> remote_db_file_path(None, './clinic.db')
        '/clinic.db'
    """
    remote = normalize_remote_path(remote_path)
    if remote.lower().endswith(DB_EXTENSIONS):
        return remote
    file_name = posixpath.basename(local_path.replace('\\', '/'))
    remote_dir = remote.rstrip('/')
    return f'{remote_dir}/{file_name}'


# ----------------------------------------------------------------------------------------
# Общие части операций
# ----------------------------------------------------------------------------------------

@contextmanager
def _open_client(
    ya_token: str, # OAuth-токен
) -> Iterator[yadisk.YaDisk]:
    """
    Клиент Яндекс.Диска на одну операцию; закрывается (HTTP-сессия) при выходе.

    Args:
        ya_token (str): OAuth-токен.

    Yields:
        yadisk.YaDisk: Клиент.

    Example:
        >>> with _open_client('y0_...') as client:   # doctest: +SKIP
        ...     client.exists('/clinic.db')
    """
    client = yadisk.YaDisk(token=ya_token)
    try:
        yield client
    finally:
        client.close()


def _token_status(
    client: yadisk.YaDisk, # открытый клиент
) -> Tuple[bool, str]:
    """
    Проверка токена без исключений.

    ``YaDisk.check_token`` при обрыве сети бросает ``YaDiskConnectionError`` — здесь это
    превращается в ``(False, текст)``, чтобы ``if_err=False`` действительно означало «без
    исключений».

    Args:
        client (yadisk.YaDisk): Клиент.

    Returns:
        Tuple[bool, str]: ``(True, '')`` — токен действителен; иначе ``(False, причина)``.
    """
    try:
        valid = client.check_token()
    except YaDiskError as exc: # нет сети, таймаут, сбой сервера Диска
        return False, f'Нет соединения с Яндекс.Диском: {exc}'
    if not valid:
        return False, 'Токен Яндекс.Диска недействителен'
    return True, ''


def _fail(
    code: YaDiskResult, # код, который вернуть при if_err=False
    message: str, # текст ошибки (на русском — его увидит пользователь)
    exc_type: Type[Exception], # тип исключения при if_err=True
    if_err: bool, # True — бросить исключение, False — вернуть код
) -> YaDiskResult:
    """
    Единая обработка ожидаемой ошибки: исключение или код.

    Args:
        code (YaDiskResult): Код ошибки.
        message (str): Текст ошибки.
        exc_type (Type[Exception]): Тип исключения.
        if_err (bool): Режим ошибок.

    Returns:
        YaDiskResult: ``code`` (только при ``if_err=False``).

    Raises:
        Exception: ``exc_type(message)`` при ``if_err=True``.
    """
    if if_err:
        raise exc_type(message)
    return code


def _remote_kind(
    client: yadisk.YaDisk, # открытый клиент
    ya_path: str, # путь на Диске
) -> Optional[str]:
    """
    Что лежит по пути на Диске.

    Args:
        client (yadisk.YaDisk): Клиент.
        ya_path (str): Путь на Диске.

    Returns:
        Optional[str]: ``'file'``, ``'dir'`` или ``None`` (ничего нет).

    Raises:
        YaDiskError: Сбой запроса (нет сети и т. п.).
    """
    if client.is_file(ya_path):
        return 'file'
    if client.exists(ya_path):
        return 'dir'
    return None


# ----------------------------------------------------------------------------------------
# Операции
# ----------------------------------------------------------------------------------------

def yadisk_download_file(
    ya_token: str, # OAuth-токен
    ya_file_path: str, # путь к файлу на Диске (например, 'Папка/clinic.db')
    local_file_path: str, # куда сохранить локально (папка создаётся при необходимости)
    if_err: bool = False, # True — исключение при ошибке, False — код YaDiskResult
    progress_callback: Optional[ProgressCallback] = None, # прогресс (передано, всего)
) -> int:
    """
    Скачивает файл с Яндекс.Диска.

    Порядок: токен → путь на Диске (файл ли это) → локальная папка → скачивание.

    Args:
        ya_token (str): OAuth-токен.
        ya_file_path (str): Путь к файлу на Диске.
        local_file_path (str): Локальный путь файла (``'clinic.db'`` без папки — тоже можно).
        if_err (bool): Режим ошибок (см. описание модуля).
        progress_callback (Optional[ProgressCallback]): Колбэк прогресса.

    Returns:
        int: :class:`YaDiskResult` — ``OK``, ``NO_CONNECTION``, ``NOT_FOUND``,
        ``NOT_A_FILE`` или ``FAILED``.

    Raises:
        ConnectionError: Токен/связь (``if_err=True``).
        FileNotFoundError: Файла на Диске нет (``if_err=True``).
        IsADirectoryError: Путь ведёт к папке (``if_err=True``).
        Exception: Исходная ошибка скачивания/файловой системы (``if_err=True``).

    Example:
        >>> yadisk_download_file(                 # doctest: +SKIP
        ...     ya_token='y0_...',                # токен
        ...     ya_file_path='Папка/clinic.db',   # файл на Диске
        ...     local_file_path='./clinic.db',    # куда
        ... )
        <YaDiskResult.OK: 0>
    """
    ya_file_path = normalize_remote_path(ya_file_path)
    with _open_client(ya_token) as client:
        ok, message = _token_status(client)
        if not ok:
            return _fail(YaDiskResult.NO_CONNECTION, message, ConnectionError, if_err)
        try:
            kind = _remote_kind(client, ya_file_path)
        except Exception:
            if if_err:
                raise
            return YaDiskResult.FAILED
        # Ожидаемые ошибки — вне try: их исключения (if_err=True) не путаются со сбоями ниже
        if kind is None:
            return _fail(
                YaDiskResult.NOT_FOUND, # код при if_err=False
                f'Файл {ya_file_path} не найден на Яндекс.Диске', # текст
                FileNotFoundError, # исключение при if_err=True
                if_err, # режим ошибок
            )
        if kind == 'dir':
            return _fail(
                YaDiskResult.NOT_A_FILE, # код при if_err=False
                f'{ya_file_path}: {YaDiskResult.NOT_A_FILE.message.lower()}', # текст
                IsADirectoryError, # исключение при if_err=True
                if_err, # режим ошибок
            )
        try:
            local_dir = os.path.dirname(local_file_path)
            if local_dir: # путь без папки ('clinic.db') — текущая папка, создавать нечего
                os.makedirs(local_dir, exist_ok=True)
            client.download(
                ya_file_path, # откуда
                local_file_path, # куда
                progress_callback=progress_callback, # прогресс
            )
            return YaDiskResult.OK
        except Exception:
            if if_err:
                raise
            return YaDiskResult.FAILED


def yadisk_upload_file(
    ya_token: str, # OAuth-токен
    local_file_path: str, # локальный файл (например, './clinic.db')
    ya_file_path: str, # путь файла на Диске (родительские папки создаются)
    if_err: bool = False, # True — исключение при ошибке, False — код YaDiskResult
    progress_callback: Optional[ProgressCallback] = None, # прогресс (передано, всего)
    overwrite: bool = False, # заменить файл на Диске, если он уже есть
) -> int:
    """
    Загружает файл на Яндекс.Диск.

    Порядок: локальный файл → токен → родительские папки на Диске (``makedirs``) → загрузка.

    Args:
        ya_token (str): OAuth-токен.
        local_file_path (str): Локальный файл.
        ya_file_path (str): Путь файла на Диске.
        if_err (bool): Режим ошибок (см. описание модуля).
        progress_callback (Optional[ProgressCallback]): Колбэк прогресса.
        overwrite (bool): Заменять существующий файл на Диске.

    Returns:
        int: :class:`YaDiskResult` — ``OK``, ``NO_CONNECTION``, ``NOT_FOUND`` (нет
        локального файла), ``NOT_A_FILE`` (по пути на Диске — папка), ``ALREADY_EXISTS``
        или ``FAILED``.

    Raises:
        FileNotFoundError: Нет локального файла (``if_err=True``).
        ConnectionError: Токен/связь (``if_err=True``).
        IsADirectoryError: По пути на Диске — папка (``if_err=True``).
        FileExistsError: Файл на Диске есть, ``overwrite=False`` (``if_err=True``).
        Exception: Исходная ошибка загрузки (``if_err=True``).

    Example:
        >>> yadisk_upload_file(                   # doctest: +SKIP
        ...     ya_token='y0_...',                # токен
        ...     local_file_path='./clinic.db',    # что
        ...     ya_file_path='Папка/clinic.db',   # куда
        ...     overwrite=True,                   # заменить
        ... )
        <YaDiskResult.OK: 0>
    """
    if not os.path.isfile(local_file_path):
        return _fail(
            YaDiskResult.NOT_FOUND, # код при if_err=False
            f'Локальный файл {local_file_path} не найден', # текст
            FileNotFoundError, # исключение при if_err=True
            if_err, # режим ошибок
        )
    ya_file_path = normalize_remote_path(ya_file_path)
    with _open_client(ya_token) as client:
        ok, message = _token_status(client)
        if not ok:
            return _fail(YaDiskResult.NO_CONNECTION, message, ConnectionError, if_err)
        try:
            parent_dir = remote_parent_dir(ya_file_path)
            if parent_dir and not client.exists(parent_dir):
                client.makedirs(parent_dir) # с родителями (у mkdir 3.x нет parents)
            client.upload(
                local_file_path, # что
                ya_file_path, # куда
                progress_callback=progress_callback, # прогресс
                overwrite=overwrite, # заменить существующий
            )
            return YaDiskResult.OK
        except DirectoryExistsError: # подкласс PathExistsError — проверять раньше него
            return _fail(
                YaDiskResult.NOT_A_FILE, # код при if_err=False
                f'{ya_file_path}: {YaDiskResult.NOT_A_FILE.message.lower()}', # текст
                IsADirectoryError, # исключение при if_err=True
                if_err, # режим ошибок
            )
        except PathExistsError:
            return _fail(
                YaDiskResult.ALREADY_EXISTS, # код при if_err=False
                f'{ya_file_path}: {YaDiskResult.ALREADY_EXISTS.message.lower()}', # текст
                FileExistsError, # исключение при if_err=True
                if_err, # режим ошибок
            )
        except Exception:
            if if_err:
                raise
            return YaDiskResult.FAILED


def check_token(
    ya_token: str, # OAuth-токен
) -> bool:
    """
    Проверяет токен Яндекс.Диска (без исключений — и при обрыве сети).

    Args:
        ya_token (str): OAuth-токен.

    Returns:
        bool: ``True`` — токен действителен; ``False`` — недействителен или нет связи.

    Example:
        >>> check_token('неверный')   # doctest: +SKIP
        False
    """
    with _open_client(ya_token) as client:
        ok, _message = _token_status(client)
        return ok


def check_and_create_path(
    ya_token: str, # OAuth-токен
    ya_path: str, # папка на Диске (например, 'Проекты/test/bd')
    create_if_missing: bool = True, # создать (с родителями), если её нет
) -> Tuple[bool, str]:
    """
    Проверяет папку на Диске; при необходимости создаёт её со всеми родительскими.

    Ошибок не бросает — результат и текст для пользователя в кортеже.

    Args:
        ya_token (str): OAuth-токен.
        ya_path (str): Путь на Диске.
        create_if_missing (bool): Создавать ли путь при отсутствии.

    Returns:
        Tuple[bool, str]: ``(успех, сообщение)``.

    Example:
        >>> check_and_create_path('y0_...', 'Папка/база')   # doctest: +SKIP
        (True, 'Путь успешно создан: Папка/база')
    """
    ya_path = normalize_remote_path(ya_path)
    with _open_client(ya_token) as client:
        ok, message = _token_status(client)
        if not ok:
            return False, message
        try:
            if client.exists(ya_path):
                return True, 'Путь существует'
            if not create_if_missing:
                return False, f'Путь не существует: {ya_path}'
            client.makedirs(ya_path) # с родителями (у mkdir 3.x нет parents)
            return True, f'Путь успешно создан: {ya_path}'
        except Exception as exc:
            return False, f'Ошибка при проверке/создании пути: {exc}'


def check_remote_file_exists(
    ya_token: str, # OAuth-токен
    ya_file_path: str, # путь к файлу на Диске
) -> Tuple[bool, str]:
    """
    Проверяет, что по пути на Диске лежит файл (не папка). Ошибок не бросает.

    Args:
        ya_token (str): OAuth-токен.
        ya_file_path (str): Путь к файлу на Диске.

    Returns:
        Tuple[bool, str]: ``(существует, сообщение)``.

    Example:
        >>> check_remote_file_exists('y0_...', 'Папка/clinic.db')   # doctest: +SKIP
        (True, 'Файл существует')
    """
    ya_file_path = normalize_remote_path(ya_file_path)
    with _open_client(ya_token) as client:
        ok, message = _token_status(client)
        if not ok:
            return False, message
        try:
            kind = _remote_kind(client, ya_file_path)
        except Exception as exc:
            return False, f'Ошибка при проверке файла: {exc}'
        if kind == 'file':
            return True, 'Файл существует'
        if kind == 'dir':
            return False, YaDiskResult.NOT_A_FILE.message
        return False, f'Файл {ya_file_path} не найден на Яндекс.Диске'


# ↓ Самая первая реализация (до добавления прогресса) — оставлена для истории.
# def yadisk_download_file(
#         ya_token:str,
#         ya_file_path:str,
#         local_file_path:str,
#         if_err:bool = False,
# ):
#     """
#     Скачивание файла с yadisk.

#     :param ya_token: Токен к диску
#     :param ya_file_path: Положение файла на диске
#         пример: '/Проекты/отчётн 1/Внесение/пример 1.xlsx',
#     :param local_file_path: Путь куда сохранять файл + его название
#         пример: './пример.xlsx',
#     :param if_err: Выводить ошибки (True) или метки на ошибки (False)
#     """
    
#     y = yadisk.YaDisk(token=ya_token)
#     if not y.check_token():
#         if if_err:
#             raise("Connection to Yandex.Disk could not be established.")
#         else:
#             return -1


#     if y.check_token():
#         if y.exists(ya_file_path):
#             y.download(ya_file_path, local_file_path)
#         else:
#             if if_err:
#                 raise(f"Err: The {ya_file_path} file does not exist on Yandex.Disk")
#                 # print(f'Файл {ya_file_path} не существует на Яндекс.Диске.')
#             else:
#                 return -2

#         return 0
    

# def yadisk_upload_file(
#         ya_token: str,
#         local_file_path: str,
#         ya_file_path: str,
#         if_err: bool = False,
# ):
#     """
#     Загрузка файла на Яндекс.Диск.

#     :param ya_token: Токен доступа к Яндекс.Диску
#     :param local_file_path: Путь к локальному файлу, который нужно загрузить
#                            (например, './отчёт.xlsx')
#     :param ya_file_path: Путь на Яндекс.Диске, куда сохранить файл
#                         (например, '/Проекты/отчёты/отчёт.xlsx')
#     :param if_err: Если True — при ошибках выбрасываются исключения,
#                    если False — возвращаются коды ошибок
#     :return: 0 при успехе,
#              -1 если токен недействителен или нет соединения,
#              -2 если локальный файл не существует,
#              -3 при другой ошибке (например, недостаточно места, ошибка сети)
#     """
#     # Проверяем существование локального файла
#     if not os.path.isfile(local_file_path):
#         if if_err:
#             raise FileNotFoundError(f"Локальный файл {local_file_path} не существует.")
#         return -2

#     # Создаём объект Яндекс.Диска и проверяем токен
#     y = yadisk.YaDisk(token=ya_token)
#     if not y.check_token():
#         if if_err:
#             raise ConnectionError("Не удалось подключиться к Яндекс.Диску. Проверьте токен.")
#         return -1

#     try:
#         # Создаём родительские папки на Яндекс.Диске, если их нет
#         parent_dir = os.path.dirname(ya_file_path)
#         if parent_dir and not y.exists(parent_dir):
#             y.mkdir(parent_dir)

#         # Загружаем файл (если файл уже существует, он будет перезаписан)
#         y.upload(local_file_path, ya_file_path)
#         return 0
#     except Exception as e:
#         if if_err:
#             # Пробрасываем исключение дальше
#             raise e
#         else:
#             # Возвращаем общий код ошибки
#             return -3


# ↓ до rework-yadisk, проход 1 (2026-10-21): прежняя реализация функций модуля.
#   Заменена: N1 — check_token без сети бросал исключение (if_err=False не спасал);
#   N2 — клиент YaDisk не закрывался; N3 — '\\' в пути уходил на Диск буквально;
#   N4 — голые коды -1/-2/-3 и английские тексты; N5 — скачивание папки; N6 — нет
#   кода «файл уже есть». Подробно — app/network/IMPLEMENTATION.md, «Журнал проверок».
# def yadisk_download_file(
#     ya_token: str,
#     ya_file_path: str,
#     local_file_path: str,
#     if_err: bool = False,
#     progress_callback=None,
# ):
#     """
#     Скачивание файла с yandex.disk с поддержкой прогресса.
#
#     :param ya_token: Токен к диску
#     :param ya_file_path: Положение файла на диске (например, '/Проекты/отчёт.xlsx')
#     :param local_file_path: Путь куда сохранять файл + его название (например, './отчёт.xlsx')
#     :param if_err: Выводить ошибки (True) или возвращать коды ошибок (False)
#     :param progress_callback: Функция, вызываемая для обновления прогресса.
#                               Принимает два аргумента: (already_done, total)
#     :return: 0 при успехе, -1 при проблеме с токеном, -2 если файл не существует на диске,
#              -3 при другой ошибке.
#     """
#     y = yadisk.YaDisk(token=ya_token)
#     if not y.check_token():
#         if if_err:
#             raise ConnectionError("Connection to Yandex.Disk could not be established.")
#         return -1
#
#     if not y.exists(ya_file_path):
#         if if_err:
#             raise FileNotFoundError(f"The file {ya_file_path} does not exist on Yandex.Disk")
#         return -2
#
#     try:
#         local_dir = os.path.dirname(local_file_path)
#         if local_dir:
#             os.makedirs(local_dir, exist_ok=True)
#         # os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
#         # ↑ до rework-yadisk (2026-10-21): путь без папки ('clinic.db') давал makedirs('')
#         #   → FileNotFoundError, скачивание падало.
#         y.download(ya_file_path, local_file_path, progress_callback=progress_callback)
#         return 0
#     except Exception as e:
#         if if_err:
#             raise e
#         return -3
#
#
# def yadisk_upload_file(
#     ya_token: str,
#     local_file_path: str,
#     ya_file_path: str,
#     if_err: bool = False,
#     progress_callback=None,
#     overwrite = False,
# ):
#     """
#     Загрузка файла на yandex.disk с поддержкой прогресса.
#
#     :param ya_token: Токен к диску
#     :param local_file_path: Путь к локальному файлу (например, './отчёт.xlsx')
#     :param ya_file_path: Путь на диске, куда сохранять файл (например, '/Проекты/отчёт.xlsx')
#     :param if_err: Выводить ошибки (True) или возвращать коды ошибок (False)
#     :param progress_callback: Функция, вызываемая для обновления прогресса.
#                               Принимает два аргумента: (already_done, total)
#     :return: 0 при успехе, -1 при проблеме с токеном, -2 если локальный файл не существует,
#              -3 при другой ошибке.
#     """
#     if not os.path.isfile(local_file_path):
#         if if_err:
#             raise FileNotFoundError(f"Local file {local_file_path} does not exist.")
#         return -2
#
#     y = yadisk.YaDisk(token=ya_token)
#     if not y.check_token():
#         if if_err:
#             raise ConnectionError("Connection to Yandex.Disk could not be established.")
#         return -1
#
#     try:
#         parent_dir = os.path.dirname(ya_file_path)
#         if parent_dir and not y.exists(parent_dir):
#             y.makedirs(parent_dir)
#             # y.mkdir(parent_dir)
#             # ↑ до rework-yadisk (2026-10-21): mkdir создаёт только последнюю папку —
#             #   при отсутствии родительской Диск отвечал ParentNotFoundError.
#
#         y.upload(
#             local_file_path, 
#             ya_file_path, 
#             progress_callback=progress_callback,
#             overwrite=overwrite,
#         )
#         return 0
#     except Exception as e:
#         if if_err:
#             raise e
#         return -3
#     
#
# def check_token(ya_token: str) -> bool:
#     """
#     Проверяет валидность токена Яндекс.Диска.
#
#     Args:
#         ya_token: OAuth-токен.
#
#     Returns:
#         True если токен действителен, иначе False.
#     """
#     y = yadisk.YaDisk(token=ya_token)
#     return y.check_token()
#
#
# def check_and_create_path(
#     ya_token: str, 
#     ya_path: str, 
#     create_if_missing: bool = True
# ) -> Tuple[bool, str]:
#     """
#     Проверяет существование пути на Яндекс.Диске.
#     Если create_if_missing=True и путь не существует, создаёт его (включая все родительские папки).
#
#     Args:
#         ya_token: OAuth-токен.
#         ya_path: Путь на Яндекс.Диске (например, '/Проекты/test/bd').
#         create_if_missing: Создавать ли путь при отсутствии.
#
#     Returns:
#         Кортеж (успех_операции, сообщение).
#     """
#     y = yadisk.YaDisk(token=ya_token)
#     if not y.check_token():
#         return False, "Неверный токен или нет соединения"
#     try:
#         if y.exists(ya_path):
#             return True, "Путь существует"
#         elif create_if_missing:
#             y.makedirs(ya_path)
#             # y.mkdir(ya_path, parents=True)
#             # ↑ до rework-yadisk (2026-10-21): у yadisk 3.x mkdir нет parents — аргумент
#             #   молча отбрасывался, создавалась только последняя папка (ParentNotFoundError).
#             return True, f"Путь успешно создан: {ya_path}"
#         else:
#             return False, f"Путь не существует: {ya_path}"
#     except Exception as e:
#         return False, f"Ошибка при проверке/создании пути: {e}"
#
#
# def check_remote_file_exists(ya_token: str, ya_file_path: str) -> Tuple[bool, str]:
#     """
#     Проверяет существование файла на Яндекс.Диске.
#
#     Args:
#         ya_token: OAuth-токен.
#         ya_file_path: Путь к файлу на Яндекс.Диске.
#
#     Returns:
#         Tuple[bool, str]: (существует, сообщение)
#     """
#     # import yadisk
#     y = yadisk.YaDisk(token=ya_token)
#     if not y.check_token():
#         return False, "Неверный токен или нет соединения"
#     
#     if y.exists(ya_file_path):
#         # Проверим, что это файл, а не папка
#         try:
#             info = y.get_meta(ya_file_path)
#             if info.get('type') == 'file':
#                 return True, "Файл существует"
#             else:
#                 return False, "Указанный путь ведёт к папке, а не к файлу"
#         except:
#             return True, "Файл существует (не удалось определить тип)"
#     else:
#         return False, f"Файл {ya_file_path} не найден на Яндекс.Диске"
