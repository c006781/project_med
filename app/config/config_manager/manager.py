# app/controllers/config_manager/manager.py

"""
Модуль управления конфигурацией приложения с использованием MessagePack.

Содержит:
- BaseConfigManager: базовый класс для работы с конфигурацией (загрузка, сохранение, кеширование).
- AppConfigManager: наследник с конкретными настройками приложения и значениями по умолчанию.
- get_instance(): фабрика для получения единственного экземпляра менеджера.
- get_config_env(): функция для получения словаря конфигурации (совместимость со старым кодом).

Пример использования:
    manager = AppConfigManager.get_instance()
    token = manager.get('YANDEX_TOKEN')
    manager.set('LOG_LEVEL', 'DEBUG')
    manager.save()  # сохранить изменения в файл
"""

# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).

# import tempfile   # до M12a: mkstemp давал права 0600 — см. save()
import threading
import time
import uuid
import weakref
from typing import Any, Callable, Dict, Optional


# Импорты модулей
from app.config.conf.get_config import get_config_env as _old_get_config_env
# Логгер не читает конфиг (развязка 2026-10-14), поэтому импорт безопасен:
# зависимость только в сторону config → logger.
from app.utils.logger.logger import AppLogger

# До настройки логирования (setup_logging) логгер пишет только в консоль — сообщения
# о битом конфиге при старте видны в консоли и дублируются окном в MainWindow.
_log = AppLogger.get_instance('config.manager', enable_file_logging='system')




# Сторонние библиотеки

import msgpack # pip install msgpack

# from cryptography.fernet import Fernet # pip install cryptography



class BaseConfigManager:
    """
    Базовый класс менеджера конфигурации.

    Атрибуты:
        _config_path (str): путь к файлу конфигурации (формат MessagePack).
        _defaults (dict): словарь со значениями по умолчанию.
        _config (dict): кеш текущих настроек (объединение defaults и загруженных из файла).
    """

    _config_path = 'config.msgpack'
    _defaults = {}

    _listeners = []   # список callable-функций

    # @classmethod
    # def add_change_listener(cls, callback):
    #     """Добавляет слушатель, вызываемый при сохранении конфигурации."""
    #     if callback not in cls._listeners:
    #         cls._listeners.append(callback)
    #
    # @classmethod
    # def remove_change_listener(cls, callback):
    #     """Удаляет слушатель."""
    #     if callback in cls._listeners:
    #         cls._listeners.remove(callback)
    #
    # @classmethod
    # def _notify_change(cls):
    #     """Оповещает всех зарегистрированных слушателей об изменении конфига."""
    #     for cb in cls._listeners:
    #         try:
    #             cb()
    #         except Exception as e:
    #             # Логируем ошибку, но не прерываем цепочку
    #             print(f"Ошибка в слушателе конфигурации: {e}")
    # ↑ до M3/M5 (2026-10-14): слушатели-методы держали объекты сервисов вечно (сервис
    #   пересоздан — старый продолжал реагировать на save(): 6 → 11 в приложении);
    #   ошибки печатались print в stdout.

    @staticmethod
    def _make_ref(callback: Callable[[], Any]) -> Callable[[], Optional[Callable[[], Any]]]:
        """
        Ссылка на слушателя: слабая для связанного метода, обычная для функции.

        Связанный метод (``service.reload_config``) хранится через ``weakref.WeakMethod`` —
        когда объект удалён, слушатель исчезает сам (M3). Функции и лямбды хранятся
        обычной ссылкой: слабая на лямбду умерла бы сразу.

        Args:
            callback: Функция или связанный метод без аргументов.

        Returns:
            Вызываемый объект без аргументов, возвращающий слушателя или ``None``.

        Пример:
            >>> ref = BaseConfigManager._make_ref(print)
            >>> ref() is print
            True
        """
        if hasattr(callback, '__self__') and hasattr(callback, '__func__'):
            return weakref.WeakMethod(callback)
        return lambda: callback

    @classmethod
    def _live_listeners(cls) -> list:
        """
        Живые слушатели; ссылки на удалённые объекты по пути выбрасываются.

        Returns:
            Список вызываемых объектов.

        Пример:
            >>> AppConfigManager._live_listeners()
            []
        """
        alive, refs = [], []
        for ref in cls._listeners:
            cb = ref()
            if cb is not None:
                alive.append(cb)
                refs.append(ref)
        cls._listeners[:] = refs
        return alive

    @classmethod
    def add_change_listener(cls, callback: Callable[[], Any]) -> None:
        """
        Подписывает функцию на сохранение конфигурации (``save()``).

        Повторная подписка того же слушателя ничего не меняет. Связанные методы
        хранятся по слабой ссылке и отписываются сами, когда объект удалён (M3).

        Список слушателей общий для всех менеджеров (классовый).

        Args:
            callback: Функция или метод без аргументов.

        Returns:
            None

        Пример:
            >>> AppConfigManager.add_change_listener(lambda: print('сохранено'))
        """
        if callback not in cls._live_listeners():
            cls._listeners.append(cls._make_ref(callback))

    @classmethod
    def remove_change_listener(cls, callback: Callable[[], Any]) -> None:
        """
        Отписывает функцию от сохранения конфигурации. Неизвестная — ничего не делает.

        Args:
            callback: Ранее подписанная функция или метод.

        Returns:
            None

        Пример:
            >>> AppConfigManager.remove_change_listener(handler)
        """
        cls._listeners[:] = [ref for ref in cls._listeners if ref() is not None and ref() != callback]

    @classmethod
    def _notify_change(cls) -> None:
        """
        Вызывает всех живых слушателей после ``save()``.

        Ошибка одного слушателя не прерывает остальных; она пишется в лог с traceback
        (до M5 — ``print`` в stdout).

        Returns:
            None

        Пример:
            Вызывается из ``save()``.
        """
        for cb in cls._live_listeners():
            try:
                cb()
            except Exception as e:
                _log.exception(f"Ошибка в слушателе конфигурации {cb!r}: {e}")

                
    def __init__(
        self,
        config_path: Optional[str] = None,
        defaults: Optional[Dict[str, Any]] = None,
        # logger:logging = None,
        encrypt: bool = True, # по умолчанию включено шифрование
    ) -> None:
        """
        Создаёт менеджер: умолчания + значения из файла (если он есть).

        Напрямую обычно не вызывается — используйте ``AppConfigManager.get_instance()``.
        Повреждённый файл не роняет создание: см. ``_recover_broken_file`` (M1).

        Args:
            config_path: Путь к файлу MessagePack; ``None`` — ``_config_path`` класса.
            defaults: Значения по умолчанию; ``None`` — ``_defaults`` класса (копируются).
            encrypt: Не используется (шифрование закомментировано).

        Returns:
            None

        Пример:
            >>> m = BaseConfigManager('my.msgpack', defaults={'theme': 'dark'})
            >>> m.get('theme')
            'dark'
        """
        self._config_path = config_path or self._config_path
        # self._defaults = (defaults or self._defaults).copy() # копируем, чтобы не изменять оригинал
        # ↑ до M7 (проверка 2026-10-15): явный defaults={} заменялся умолчаниями класса
        self._defaults = (self._defaults if defaults is None else defaults).copy() # копируем, чтобы не изменять оригинал
        self._config = self._defaults.copy()  # начинаем с умолчаний

        # M1: если файл оказался повреждён — путь к его копии и текст сообщения
        # (заполняет _recover_broken_file; MainWindow показывает их пользователю)
        self.broken_config_backup: Optional[str] = None
        self.broken_config_message: Optional[str] = None

        # # Определяем, нужно ли шифрование
        # self._encrypt_enabled = encrypt

        # # Инициализируем шифратор
        # self._cipher = None
        # if self._encrypt_enabled:
        #     self._setup_cipher()

        self._load()  # загружаем из файла, если он существует
    
    def _load(self) -> None:
        """
        Читает файл и накладывает его значения на умолчания.

        Файла нет — остаются умолчания (файл создастся при первом ``save()``).
        Содержимое не разбирается или это не словарь — ``_recover_broken_file()`` (M1).
        Файл не открывается/не читается (``OSError``: заблокирован, нет прав) —
        ``_report_unreadable_file()``: файл НЕ трогается (M15).

        Returns:
            None

        Пример:
            Вызывается из ``__init__`` и ``load()``.
        """
        if not os.path.exists(self._config_path):
            # Файла нет – используем defaults, файл не создаём до первого сохранения
            return

        # # try:
        # with open(self._config_path, 'rb') as f:
        #     data = msgpack.unpack(f, raw=False)  # raw=False для получения строк, а не байт
        #
        # if not isinstance(data, dict):
        #     # Если файл содержит не словарь, игнорируем его
        #     return
        # ↑ до M1 (2026-10-14): битый файл — исключение, приложение не запускалось;
        #   «не словарь» молча игнорировался. Теперь оба случая — _recover_broken_file().
        try:
            with open(self._config_path, 'rb') as f:
                data = msgpack.unpack(f, raw=False)  # raw=False для получения строк, а не байт
        except OSError as e:
            # M15 (проверка 3, 2026-10-15): ошибка ЧТЕНИЯ (файл заблокирован другим
            # процессом или антивирусом, нет прав) — это не повреждение. Раньше она
            # попадала в except Exception ниже: исправный файл объявлялся «повреждённым»
            # и переименовывался в .broken-…. Теперь файл не трогаем.
            self._report_unreadable_file(e)
            return
        except Exception as e:  # msgpack бросает разные исключения на мусор
            detail = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            self._recover_broken_file(f"не читается — {detail}")
            return

        if not isinstance(data, dict):
            self._recover_broken_file(f"содержит не словарь, а {type(data).__name__}")
            return
        # Обновляем кеш: значения из файла перезаписывают defaults
        self._config.update(data)
        # 0==0
        # except (msgpack.UnpackException, EOFError, OSError) as e:
        #     # В случае ошибки чтения (повреждённый файл) оставляем defaults
        #     self.logger.error(f"Ошибка при чтении файла конфигурации: {e}")
        #     pass

    def _report_unreadable_file(self, error: OSError) -> None:
        """
        Файл конфигурации есть, но прочитать его не удалось (M15).

        В отличие от ``_recover_broken_file`` файл не переименовывается и не
        перезаписывается: он может быть исправен (заблокирован антивирусом или другим
        процессом, временно нет прав). Работа идёт на значениях по умолчанию в памяти;
        сообщение — в лог и в ``broken_config_message`` (главное окно его покажет).

        Args:
            error: Исключение чтения.

        Returns:
            None

        Пример:
            >>> m = AppConfigManager.get_instance()     # config.msgpack заблокирован
            >>> m.broken_config_backup is None, bool(m.broken_config_message)
            (True, True)
        """
        self.broken_config_backup = None
        message = (f"Не удалось прочитать файл конфигурации {os.path.abspath(self._config_path)} "
                   f"({type(error).__name__}: {error}). Файл не тронут, используются значения "
                   f"по умолчанию. Закройте программу и проверьте доступ к файлу: сохранение "
                   f"настроек сейчас перезапишет его.")
        _log.error(message)
        self.broken_config_message = message

    def _recover_broken_file(self, reason: str) -> None:
        """
        Восстановление после повреждённого файла конфигурации (M1).

        Шаги:
            1. Битый файл переименовывается в ``<путь>.broken-<ГГГГММДД_ЧЧММСС>``
               (ничего не теряется — можно разобрать вручную); если такое имя уже
               есть — ``…-1``, ``…-2`` и т. д. (M11).
            2. Остаются значения по умолчанию; по ним создаётся новый файл.
            3. Сообщение в лог (до настройки логирования — в консоль). Путь к копии —
               в ``broken_config_backup``: главное окно показывает его пользователю и
               открывает настройки.

        Если переименовать не удалось (нет прав) — новый файл НЕ создаётся, чтобы не
        затереть битый; работа идёт на значениях по умолчанию в памяти.

        Args:
            reason: Что не так с файлом (для сообщения).

        Returns:
            None

        Пример:
            >>> m = AppConfigManager.get_instance()         # config.msgpack испорчен
            >>> m.broken_config_backup
            'config.msgpack.broken-20261014_230512'
        """
        # backup = f"{self._config_path}.broken-{time.strftime('%Y%m%d_%H%M%S')}"
        # ↑ до M11 (проверка 2026-10-15): вторая поломка в ту же секунду перезаписывала
        #   первую копию. Теперь при совпадении добавляется номер.
        backup = f"{self._config_path}.broken-{time.strftime('%Y%m%d_%H%M%S')}"
        n = 1
        while os.path.exists(backup):
            backup = f"{self._config_path}.broken-{time.strftime('%Y%m%d_%H%M%S')}-{n}"
            n += 1
        try:
            os.replace(self._config_path, backup)
        except OSError as e:
            self.broken_config_backup = None
            message = (f"Файл конфигурации повреждён: {os.path.abspath(self._config_path)} "
                       f"({reason}). Переименовать не удалось ({e}) — файл не тронут, "
                       f"используются значения по умолчанию.")
            _log.error(message)
            self.broken_config_message = message
            return

        self.broken_config_backup = os.path.abspath(backup)
        try:
            self.save()
            created = f"Создан новый файл со значениями по умолчанию: {os.path.abspath(self._config_path)}."
        except OSError as e:
            created = f"Создать новый файл не удалось ({e}) — используются значения по умолчанию."
        message = (f"Файл конфигурации повреждён ({reason}). "
                   f"Повреждённый файл сохранён как: {self.broken_config_backup}. {created}")
        _log.error(message)
        self.broken_config_message = message

    def save(self) -> None:
        """
        Сохраняет текущие значения в файл и уведомляет слушателей.

        Атомарно (M2): запись в уникальный временный файл рядом (M12) и подмена
        ``os.replace`` — сбой посередине не портит конфиг. Родительские папки создаются.

        Returns:
            None

        Raises:
            OSError: Записать не удалось (старый файл остаётся целым).

        Пример:
            >>> m.set('LOG_LEVEL', 'DEBUG'); m.save()
        """
        # # # Создаём директорию, если не существует
        # os.makedirs(os.path.dirname(self._config_path), exist_ok=True)

        """Сохраняет текущий кеш конфигурации в файл."""
        dirname = os.path.dirname(self._config_path)
        if dirname:  # только если есть директория
            os.makedirs(dirname, exist_ok=True)

        # # Сохраняем в бинарном режиме
        # with open(self._config_path, 'wb') as f:
        #     msgpack.pack(self._config, f)
        # ↑ до M2 (2026-10-14): файл обнулялся до записи — сбой посередине (диск,
        #   питание) оставлял пустой/битый конфиг. Теперь: пишем во временный файл
        #   рядом и подменяем им старый одной операцией (os.replace).
        # tmp_path = f"{self._config_path}.tmp"
        # ↑ до M12 (проверка 2026-10-15): одно имя на всех — два окна программы,
        #   сохраняющие одновременно, писали в один временный файл. Теперь имя уникальное
        #   (в той же папке — os.replace атомарен только в пределах одного диска).
        # fd, tmp_path = tempfile.mkstemp(
        #     prefix=os.path.basename(self._config_path) + '.', suffix='.tmp',
        #     dir=os.path.dirname(os.path.abspath(self._config_path)),
        # )
        # ↑ до M12a (проверка 2, 2026-10-15): mkstemp создаёт файл с правами 0600, и после
        #   os.replace они доставались config.msgpack — на Linux конфиг становился
        #   недоступен другим пользователям/группе. Обычный open() берёт права по umask,
        #   как до M2; 'x' — ошибка, если такое имя вдруг уже есть (не перезапишем чужой).
        tmp_path = f"{self._config_path}.{os.getpid()}-{uuid.uuid4().hex[:12]}.tmp"
        try:
            # with os.fdopen(fd, 'wb') as f:
            with open(tmp_path, 'xb') as f:
                msgpack.pack(self._config, f)
            os.replace(tmp_path, self._config_path)
        except BaseException:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise
        
        # Уведомляем всех подписчиков
        self.__class__._notify_change()

    def load(self) -> Dict[str, Any]:
        """
        Перечитывает файл (например, после ручной правки) и возвращает копию значений.

        Значения строятся заново: умолчания + файл. Изменения в памяти без ``save()``
        теряются; ключ, удалённый из файла, возвращается к умолчанию.

        Returns:
            Копия всех значений.

        Пример:
            >>> m.load()['LOG_LEVEL']
            'INFO'
        """
        # self._load()
        # ↑ до M9/M10 (проверка 2026-10-15): значения из файла накладывались на текущие в
        #   памяти — ключ, удалённый из файла, оставался; при битом файле «восстановление»
        #   сохраняло значения из памяти, а сообщение говорило «по умолчанию»; флаги
        #   битого файла от прошлой загрузки не сбрасывались.
        self._config = self._defaults.copy()
        self.broken_config_backup = None
        self.broken_config_message = None
        self._load()
        return self.get_all()

    def get(self, key: str, default: Any = None) -> Any:
        """
        Значение по ключу.

        Args:
            key: Ключ.
            default: Значение, если ключа нет.

        Returns:
            Значение или ``default``.

        Пример:
            >>> m.get('database_local_path')
            '.\\clinic.db'
        """
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Меняет значение в памяти. В файл — только после ``save()``.

        Args:
            key: Ключ.
            value: Новое значение.

        Returns:
            None

        Пример:
            >>> m.set('YANDEX_TOKEN', 'y0_...'); m.save()
        """
        self._config[key] = value

    def update(self, data: Dict[str, Any]) -> None:
        """
        Меняет несколько значений в памяти (как ``dict.update``). В файл — после ``save()``.

        Args:
            data: Ключи и значения.

        Returns:
            None

        Пример:
            >>> m.update({'LOG_LEVEL': 'INFO', 'LOG_DIR': 'logs'})
        """
        self._config.update(data)

    def reset_to_defaults(self) -> None:
        """
        Сбрасывает значения в памяти к умолчаниям (файл не меняется до ``save()``).

        Returns:
            None

        Пример:
            >>> m.reset_to_defaults(); m.save()
        """
        self._config = self._defaults.copy()

    def get_all(self) -> Dict[str, Any]:
        """
        Копия всех текущих значений (изменения копии не влияют на менеджер).

        Returns:
            Словарь значений.

        Пример:
            >>> old = m.get_all()      # снимок до save() для ConfigApplier.apply_changes
        """
        return self._config.copy()
    
    @property
    def config_exists(self) -> bool:
        """
        Есть ли файл конфигурации на диске (нет — первый запуск).

        Returns:
            ``True``, если файл существует.

        Пример:
            >>> AppConfigManager.get_instance().config_exists
            True
        """
        return os.path.exists(self._config_path)

class AppConfigManager(BaseConfigManager):
    """
    Менеджер конфигурации приложения: значения по умолчанию (``_defaults``) + файл
    ``config.msgpack``. Путь к файлу по умолчанию берётся из .env (``APP_CONFIG_PATH``)
    один раз (E6). Значения из файла имеют приоритет над умолчаниями.

    (До 2026-10-15 здесь было написано, что умолчания «берутся из .env» — это давно
    не так: .env хранит только путь к файлу и токен GitHub.)

    Атрибуты класса:
        _config_path (str): Путь к файлу конфигурации (по умолчанию 'config.msgpack').
        _defaults (dict): Словарь со значениями по умолчанию (логирование, пути, токен и т.д.).
        _instances (dict): Хранилище экземпляров для паттерна Multiton.

    Методы:
        get_instance(force_new=False, config_path=None, create_if_missing=False) -> AppConfigManager
        get(key, default=None) -> Any
        set(key, value) -> None
        save() -> None
        load() -> Dict[str, Any]
        reset_to_defaults() -> None
        add_change_listener(callback) -> None
    """

    _config_path = 'config.msgpack'

    # _defaults = {}
    # Значения по умолчанию (копия того, что сейчас возвращает get_config_env)
    # _defaults = {
    #     'YANDEX_TOKEN': '----',
    #     # 'database_local_path': './clinic.db',
    #     'database_local_path': os.path.join(
    #         '.',
    #         'clinic.db'
    #     ),
    #     'database_remote_path': 'Проекты/test/bd/clinic.db',
    #     # 'database_remote_path': 'Проекты/test/bd/clinic.db',
    #     'LOG_LEVEL': 'DEBUG',
    #     # 'LOG_LEVEL': 'INFO',
    #     # 'LOG_FILE': './logs/app.log',
    #     'LOG_FILE': os.path.join(
    #         '.',
    #         'logs',
    #         'app.log'
    #     ),
    #     'LOG_MAX_BYTES': str(10 * 1024 * 1024),  # 10 MB
    #     'LOG_BACKUP_COUNT': '5',
    #     # 'PHOTOS_STORAGE_PATH': './photos',
    #     'PHOTOS_STORAGE_PATH': os.path.join(
    #         '.', 
    #         'photos'
    #     ),
    #     # 'APP_CONFIG_PATH': 'config.msgpack',  # путь по умолчанию для файла конфигурации
    #     'LOG_ARGS': 'False',   # или False, но в msgpack можно хранить bool
    # }

    _defaults = {
        'YANDEX_TOKEN': '----',
        'database_local_path': os.path.join('.', 'clinic.db'),
        'database_remote_path': 'Проекты/test/bd/clinic.db',
        
        # === НАСТРОЙКИ ЛОГИРОВАНИЯ ===
        'LOG_DIR': os.path.join('.', 'logs'),          # вместо LOG_FILE
        # 'LOG_LEVEL': 'DEBUG',
        'LOG_LEVEL': 'INFO',
        'LOG_MAX_BYTES': str(10 * 1024 * 1024),       # 10 MB
        'LOG_BACKUP_COUNT': '5',
        'LOG_ARGS': 'False',
        
        
        # Для системного логгера
        # 'system_enabled': 'True',
        'system_enabled': 'False',
        # 'system_console_enabled': 'True',
        'system_console_enabled': 'False',
        # 'system_file_enabled': 'True',
        'system_file_enabled': 'False',
        'system_LEVEL': 'DEBUG',
        # 'system_enabled': 'False', 
        # 'system_console_enabled': 'False',
        # 'system_file_enabled': 'False',
        # 'system_LEVEL': 'INFO',
        
        # Для пользовательского логгера
        # 'user_enabled': 'True',
        'user_enabled': 'False',
        # 'user_console_enabled': 'True',
        'user_console_enabled': 'False',
        # 'user_file_enabled': 'True',
        'user_file_enabled': 'False',
        'user_LEVEL': 'DEBUG',
        # 'user_enabled': 'False',
        # 'user_console_enabled': 'False',
        # 'user_file_enabled': 'False',
        # 'user_LEVEL': 'INFO',
        
        # Общие флаги (могут быть переопределены специфичными)
        'enabled': 'True',
        'console_enabled': 'True',
        'file_enabled': 'True',
        # 'enabled': 'False',
        # 'console_enabled': 'False',
        # 'file_enabled': 'False',

        'use_timestamp': 'False',      # добавлять ли дату в имя файла лога
        
        # Остальные настройки
        'PHOTOS_STORAGE_PATH': os.path.join('.', 'photos'),
        'APP_CONFIG_PATH': 'config.msgpack', # путь по умолчанию для файла конфигурации

        # 'show_call_depth': 'True',  # или False, но с возможностью переключения
        'show_call_depth': 'False',  # или False, но с возможностью переключения

        # # === НАСТРОЙКИ РАБОТЫ С ГИТХАБОМ (разработка) ===
        # 'GITHUB_TOKEN': '',
    }

    # Хранилище для экземпляров (Multiton)
    _instances = {}
    # M13 (проверка 2026-10-15): get_instance вызывается и из фоновых потоков —
    # без блокировки два потока создавали два менеджера для одного файла.
    _instances_lock = threading.RLock()

    # Путь к конфигу из .env (APP_CONFIG_PATH), прочитанный один раз (E6)
    _resolved_default_path: Optional[str] = None

    @classmethod
    def _default_config_path(cls) -> str:
        """
        Путь к файлу конфигурации по умолчанию: ``APP_CONFIG_PATH`` из ``.env``.

        Читается из ``.env`` при первом вызове и запоминается (E6): раньше ``.env``
        перечитывался при каждом ``get_instance()`` без пути.

        Returns:
            Путь к файлу конфигурации.

        Пример:
            >>> AppConfigManager._default_config_path()
            'config.msgpack'
        """
        if cls._resolved_default_path is None:
            cls._resolved_default_path = _old_get_config_env().get('APP_CONFIG_PATH', cls._config_path)
        return cls._resolved_default_path

    @classmethod
    def reset_default_config_path(cls) -> None:
        """
        Забывает запомненный путь к конфигу — следующий ``get_instance()`` перечитает ``.env``.

        Нужен тестам и случаям, когда ``.env`` изменили во время работы.

        Returns:
            None

        Пример:
            >>> AppConfigManager.reset_default_config_path()
        """
        cls._resolved_default_path = None

    def __init__(self, config_path: Optional[str] = None) -> None:
        """
        Менеджер с умолчаниями приложения (``_defaults``).

        Напрямую не вызывайте — используйте ``get_instance()`` (один экземпляр на путь).

        Args:
            config_path: Путь к файлу; ``None`` — ``'config.msgpack'``.

        Returns:
            None

        Пример:
            >>> AppConfigManager.get_instance(config_path='config.msgpack')
        """
        super().__init__(config_path or self._config_path, self._defaults)

    @classmethod
    def get_instance(
        cls, 
        force_new: bool = False, 
        config_path: Optional[str] = None,
        create_if_missing: bool = False
    ) -> 'AppConfigManager':
        """
        Возвращает экземпляр менеджера конфигурации (паттерн Multiton).

        Параметры:
            force_new (bool): Если True, создаёт новый экземпляр даже если уже есть.
            config_path (Optional[str]): Путь к файлу конфигурации. Если не указан,
                берётся из старой функции get_config_env() по ключу 'APP_CONFIG_PATH'.
            create_if_missing (bool): Если True и файл конфигурации не существует,
                создаёт его со значениями по умолчанию.

        Возвращает:
            AppConfigManager: Экземпляр менеджера.

        Пример:
            >>> manager = AppConfigManager.get_instance()
            >>> token = manager.get('YANDEX_TOKEN')
        """

        with cls._instances_lock:  # M13
            if config_path is None:
                # # Получаем путь из старой конфигурации (там он уже должен быть)
                # config_path = _old_get_config_env().get('APP_CONFIG_PATH', cls._config_path)
                # ↑ до E6 (2026-10-14): .env перечитывался при КАЖДОМ вызове (34 чтения за старт
                #   GUI). Путь к конфигу за время работы не меняется — читаем один раз.
                config_path = cls._default_config_path()

            # Если не требуем новый экземпляр и такой уже есть – возвращаем его
            if not force_new and config_path in cls._instances:
                return cls._instances[config_path]

            # Создаём новый экземпляр
            instance = cls(config_path)
            cls._instances[config_path] = instance

            if create_if_missing and not instance.config_exists:  # config_exists добавим позже
                instance.save()  # сохраняем умолчания

            return instance

# ----------------------------------------------------------------------
# Функция для обратной совместимости со старым кодом
# ----------------------------------------------------------------------

def get_config_env(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Все настройки приложения одним словарём (копия).

    Совместимость со старым кодом: раньше настройки читались из .env, теперь — из
    ``config.msgpack`` через ``AppConfigManager``. Путь к файлу по умолчанию берётся из
    .env один раз (E6).

    Args:
        config_path: Путь к файлу; ``None`` — по умолчанию.

    Returns:
        Копия всех настроек.

    Пример:
        >>> get_config_env()['database_local_path']
        '.\\clinic.db'
    """
    manager = AppConfigManager.get_instance(
        config_path=config_path,
    )
    return manager.get_all()

if __name__ == '__main__':

    global env_key
    env_key = get_config_env()

    # 0==0
    pass