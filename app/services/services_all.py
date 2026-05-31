# app/services/services_all.py
"""
Бизнес-логика приложения (сервисный слой).

Содержит абстрактный базовый класс :class:`BaseService` и конкретные сервисы:
- :class:`PatientService` – управление пациентами (заметки description_text, comment_text).
- :class:`AppointmentService` – управление приёмами (заметки reason_text, procedure_text,
  recommendations_text, note_text, cost_procedure_text + фото через PhotoService).
- :class:`NoteService` – управление заметками (обычно не используется напрямую).
- :class:`PhotoService` – управление фотографиями (файлы + БД).

Все сервисы используют репозитории для доступа к БД, автоматически управляют сессиями,
поддерживают фильтрацию, пагинацию и вычисление виртуальных полей.

.. rubric:: Как добавить новый сервис

1. Создайте в `app/dto/field_configs.py` конфигурацию полей.
2. Создайте DTO (в `app/dto/`) и SQLAlchemy модель (в `app/database/database_shema/`).
3. Создайте репозиторий (в `app/repositories/`), унаследовав `BaseRepository`.
4. В этом файле создайте класс, наследующий `BaseService`:

   class NewService(BaseService[Model, DTO, Repository]):
       def __init__(self, db, field_configs=None, logger_name=None):
           super().__init__(db, Repository, Model, DTO, field_configs, logger_name)
           # Если есть поля-заметки, создайте self._note_service = NoteService(...)
           self._note_service = NoteService(db, logger_name=logger_name + ".NoteService")

       def _get_note_service(self) -> Optional[NoteService]:
           return self._note_service   # если есть заметки, иначе верните None

       def _get_child_service(self, relation_name: str) -> Optional[BaseService]:
           # Если сервис управляет дочерними сущностями, верните соответствующий сервис
           # if relation_name == 'documents':
           #     return self._doc_service
           return super()._get_child_service(relation_name)

5. Зарегистрируйте сервис в `app/dependencies.py` с декораторами `@register_service_provider` и `@lru_cache`.
6. Если модель имеет поля `is_note`, добавьте её в `MODEL_CONFIG_MAP` в `field_configs.py`.

Пример для сервиса без заметок и без дочерних:
    class InventoryService(BaseService[Inventory, InventoryDTO, InventoryRepository]):
        pass   # всё наследуется от BaseService

Пример использования:
    >>> from app.dependencies import get_patient_service
    >>> service = get_patient_service()
    >>> patients = service.get_all()
"""

# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
# import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).

import shutil
import uuid

from typing import (
    Type, TypeVar, Generic, 
    List, Optional, Dict, 
    Any, Tuple, Union
)

import time as time_module
# from datetime import time
# import datetime

from contextlib import contextmanager

from app.utils.logger import AppLogger

# from app.dependencies import get_appointment_service
# from app.dependencies import clear_services_cache
# from app.dependencies import _NOTE_USAGE_MODELS


# Импорты модулей
# def _add_package_name(
#     file_module: str = None,
#     levels_up: int = 3,           # <-- сколько уровней вверх до корня проекта
# ) -> None:
    
#     """
#     Что это (кратко): Добавляет корень проекта в sys.path и устанавливает правильный __package__.

#     Что это (максимально подробно): Эта функция настраивает окружение Python таким образом, чтобы можно было использовать относительные импорты (например, from .module import something) без необходимости запускать скрипт с флагом "-m" (как модуль). Она работает только если скрипт запущен напрямую (не импортирован). Функция получает абсолютный путь к текущему файлу, добавляет родительскую директорию в sys.path (список путей для поиска модулей), и устанавливает глобальную переменную __package__ как имя текущей директории. Это полезно в проектах с nested папками, где импорты могут сломаться.

#     Как работает: Сначала объявляется global __package__ для изменения системной переменной. Затем os.path.abspath(__file__) дает полный путь к скрипту, os.path.dirname убирает имя файла, оставляя папку. sys.path.append добавляет родительскую папку (dirname еще раз). Наконец, __package__ = basename(package_dir) — имя папки. Вызывается только в if __name__ == '__main__', чтобы не мешать, если скрипт импортирован.

#     Примеры запуска:
#     # В скрипте: if __name__ == '__main__': _add_package_name()
#     # После вызова: sys.path включает родительскую папку (например, '/path/to/modules'), __package__ = 'parsers_sheregeh'. Теперь относительные импорты работают.
#     # Если запустить как модуль (python -m script), функция не нужна, но она не навредит.
#     # Если не вызвать: относительный импорт from .module... может вызвать ImportError: attempted relative import with no known parent package.

#     :param file_module: (str) = обычно __file__  - указатель на путь к модулю, папку которого делаем пакетом для относительных импортов (содержит путь к текущему скрипту)
#     :param levels_up: (int) - на сколько уровней подниматься вверх до корня проекта
#                        (подберите под структуру вашего проекта)
#                        Примеры:
#                          2 → до папки app
#     """
#     if file_module is None:
#         file_module = __file__

#     # Получаем директорию текущего файла
#     current_dir = os.path.dirname(os.path.abspath(file_module))

#     # Поднимаемся на levels_up уровней вверх — это и будет корень проекта
#     project_root = current_dir
#     for _ in range(levels_up):
#         project_root = os.path.dirname(project_root)

#     # Добавляем корень проекта в начало sys.path (высокий приоритет)
#     if project_root not in sys.path:
#         sys.path.insert(0, project_root)

#     # Вычисляем правильное значение __package__
#     # Пример: /project_med/app/models/bd → "app.models.bd"
#     rel_path = os.path.relpath(current_dir, project_root)
    
#     if rel_path == '.':
#         package_name = ''
#     else:
#         package_name = rel_path.replace(os.sep, '.').strip('.')

#     # Устанавливаем __package__
#     global __package__
#     if package_name:
#         __package__ = package_name
#     else:
#         # Если мы в корне — можно оставить None или пустую строку
#         __package__ = None

# try:
from app.config.config_manager.manager import AppConfigManager
# from app.dependencies import get_db
# from app.dependencies import get_note_service, get_photo_service
# except ImportError as e:
#     # try:
#     # Попытка абсолютного импорта, если модуль запущен как скрипт
#     _add_package_name(file_module = __file__,levels_up = 2)
#     from ..utils.logger import AppLogger
#     # except ImportError as e:
#     #     pass #  raise # e # pass

# try:
from app.database.database import Database
# except ImportError as e:
#     # try:
#     # Попытка абсолютного импорта, если модуль запущен как скрипт
#     _add_package_name( file_module = __file__,levels_up = 2)
#     from ..backend.database import Database
#     # except ImportError as e:
#     #     AppLogger.get_instance(name='system').critical("Ошибка from database import")
#         # pass #  raise # e # pass

# try:
from app.database.database_shema.clinic import (
    Patient, Appointment, AppointmentNote, 
    Photo
)
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name( file_module = __file__,levels_up = 2)
#         from ..backend.bd.clinic import Patient, Appointment, AppointmentNote, Photo
#     except ImportError as e:
#         AppLogger.get_instance(name='system').critical("Ошибка from models import")
#         pass #  raise # e # pass

# try:
from app.repositories.repositories_all import (
    BaseRepository,
    # PatientRepository,
    AppointmentRepository,
    PatientRepository,
    AppointmentNoteRepository,
    PhotoRepository
)
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..backend.repositories.repositories_all import BaseRepository, PatientRepository, AppointmentRepository, PatientRepository, AppointmentNoteRepository, PhotoRepository
#     except ImportError as e:
#         AppLogger.get_instance(name='system').critical("Ошибка from repositories_all import")
#         pass #  raise # e # pass

# try:
from app.dto import (
    PatientDTO, AppointmentDTO,
    AppointmentNoteDTO, PhotoDTO
)
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..dto import PatientDTO, AppointmentDTO, AppointmentNoteDTO, PhotoDTO
#     except ImportError as e:
#         AppLogger.get_instance(name='system').critical("Ошибка from dto import")
#         pass #  raise # e # pass

# try:
from app.exceptions import (
    PatientNotFoundError, PatientValidationError, 
    AppointmentNotFoundError, AppointmentNoteNotFoundError, 
    PhotoNotFoundError, PhotoFileError, 
    #   AppException
)
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..exceptions import PatientNotFoundError, PatientValidationError, AppointmentNotFoundError, AppointmentNoteNotFoundError, PhotoNotFoundError, PhotoFileError, AppException
#     except ImportError as e:
#         AppLogger.get_instance(name='system').critical("Ошибка from exceptions import")
#         pass #  raise # e # pass


from app.utils.file_deletions import (
    schedule_deletion, DeletionContext,
    DeletionType
)

# try:
from app.utils.filtering.filtering import (
    # _build_filter_condition, 
    apply_filters, apply_post_filters
)
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..utils.filtering.filtering import apply_filters, apply_post_filtersception
#     except ImportError as e:
#         AppLogger.get_instance(name='system').critical("Ошибка from exceptions import")
#         pass #  raise # e # pass



from app.utils.virtual_fields import enrich_dto_with_computed_fields

# Сторонние библиотеки

from sqlalchemy import (
    func, or_, #inspect
)

from sqlalchemy.orm import (
    Query, Session,
    joinedload, selectinload
)
# from sqlalchemy.orm import Query, Session
# from sqlalchemy.orm import joinedload
# from sqlalchemy.orm import selectinload




ModelType = TypeVar('ModelType')
DTOType = TypeVar('DTOType')
RepoType = TypeVar('RepoType', bound=BaseRepository)

class BaseService(
    Generic[
        ModelType,
        DTOType,
        RepoType
    ]
):
    """
    Абстрактный базовый сервис, предоставляющий стандартные методы CRUD,
    фильтрацию, пагинацию и управление сессиями.

    Параметры типа:
        ModelType: Класс ORM-модели SQLAlchemy (например, Patient).
        DTOType: Класс Pydantic DTO (например, PatientDTO).
        RepoType: Класс репозитория, унаследованный от BaseRepository.

    Атрибуты:
        _db (Database): Экземпляр Database для получения сессий.
        _repo_class (Type[RepoType]): Класс репозитория.
        _model_class (Type[ModelType]): Класс ORM-модели.
        _dto_class (Type[DTOType]): Класс DTO.
        _field_configs (Dict[str, Dict[str, Any]]): Конфигурация полей (для виртуальных полей).
        logger (AppLogger): Логгер для записи событий.

    Примечания:
        - Подписывается на изменения конфигурации через AppConfigManager.add_change_listener.
        - При изменении настроек (например, пути к БД) вызывается `reload_config()`.
        - Все методы, работающие с БД, используют контекстный менеджер `_session_scope`.

    ## Как создать новый сервис
    1. Определите модель, DTO, репозиторий и конфигурацию полей.
    2. Создайте класс, наследующий `BaseService`.
    3. Реализуйте `_get_note_service()` (если есть поля `is_note`).
    4. Реализуйте `_get_child_service()` (если есть дочерние сервисы, например, фото).
    5. Переопределите `create` и `update`, если нужна дополнительная валидация (обычно достаточно делегировать `_create_entity` / `_update_entity`).
    6. Зарегистрируйте сервис в `dependencies.py` с помощью `register_service_provider` и `lru_cache`.

    В наследниках `BaseService` вы **должны** переопределить следующие методы:
        Переопределяемые методы (обязательные для наследников, если нужна логика):
            1. `_not_found_exception(entity_id: int) -> Exception`  
            Возвращает исключение, соответствующее сущности (например, `PatientNotFoundError`).

            2. `_get_note_service(self) -> Optional['NoteService']`  
            Если модель имеет поля-заметки (`is_note` в конфигурации), верните экземпляр `NoteService`.  
            Если заметок нет, верните `None` (иначе методы `_apply_note_updates` и `_delete_entity` вызовут ошибку).

            3. `_get_child_service(self, relation_name: str) -> Optional[BaseService]`  
            Для дочерних связей (например, фотографии приёма) верните соответствующий сервис.  
            Иначе возвращайте `super()._get_child_service(relation_name)` (базовая реализация возвращает `None`).

        Опциональные переопределения:
            - _post_process_items(items, session) - пост-обработка списка объектов (добавление временных атрибутов).
            - create(dto) / update(dto) - если нужно добавить валидацию, но обычно достаточно делегировать _create_entity/_update_entity.
            - delete(entity_id) - если требуется каскадное удаление дочерних записей.

    ================================================================================
    Как создать новый сервис
    ================================================================================

    1. Определите модель SQLAlchemy в `app/database/database_shema/`.
    2. Определите DTO (Pydantic) в `app/dto/` (например, `MyEntityDTO`).
    3. Определите репозиторий в `app/repositories/`, унаследовав `BaseRepository`.
    4. Создайте конфигурацию полей в `app/dto/field_configs.py` (словарь `MY_ENTITY_CONFIG`).
    5. В этом файле создайте класс, наследующий `BaseService`:

    class MyEntityService(BaseService[MyEntity, MyEntityDTO, MyEntityRepository]):
        def __init__(self, db, field_configs=None, logger_name=None):
            super().__init__(db, MyEntityRepository, MyEntity, MyEntityDTO,
                                field_configs or MY_ENTITY_CONFIG, logger_name)
            # Если у сущности есть поля-заметки (is_note), создайте _note_service:
            self._note_service = NoteService(db, logger_name=logger_name + ".NoteService")

        # Обязательно переопределите _not_found_exception
        def _not_found_exception(self, entity_id: int) -> Exception:
            return MyEntityNotFoundError(entity_id)

        # Если есть поля-заметки, переопределите _get_note_service
        def _get_note_service(self) -> Optional[NoteService]:
            return self._note_service   # или None, если нет заметок

        # Если есть дочерние сервисы (например, фото), переопределите _get_child_service
        def _get_child_service(self, relation_name: str) -> Optional[BaseService]:
            if relation_name == 'documents':
                return self._doc_service
            return super()._get_child_service(relation_name)

    6. Зарегистрируйте сервис в `app/dependencies.py` с декораторами `@register_service_provider` и `@lru_cache`.
    7. Если модель имеет поля `is_note`, добавьте её в `MODEL_CONFIG_MAP` в `field_configs.py`.

    Пример для сущности без заметок и дочерних связей:
        class InventoryService(BaseService[Inventory, InventoryDTO, InventoryRepository]):
            def _not_found_exception(self, entity_id):
                return InventoryNotFoundError(entity_id)

            # _get_note_service и _get_child_service не переопределяются (базовые)
    """

    @staticmethod
    def _update_note_field(
        sess: Session,
        note_repo, 
        old_note_id: Optional[int],
        new_text: Optional[str],
        create_if_missing: bool = True
    ):
        """
        Обновляет или создаёт заметку, возвращает (new_note_id, old_note_id).
        old_note_id – переданный старый ID (может быть None).
        Возвращает (новый ID, старый ID), чтобы вызывающий код мог потом удалить старую заметку.
        """

        # Если текст не передан и не требуется создавать – ничего не меняем
        if new_text is None and not create_if_missing:
            return old_note_id, None
        
        # Если есть старая заметка и текст передан – обновляем её
        if old_note_id is not None:
            note = note_repo.get_by_id(old_note_id)
            if note:
                if new_text is not None:
                    note.text = new_text

                return old_note_id, None  # ID не изменился, старый не нужно удалять
            
        # Создаём новую заметку        
        new_note = AppointmentNote(text=new_text or "")
        note_repo.add(new_note)
        sess.flush()

        return new_note.id, old_note_id   # возвращаем новый ID и старый ID (который может быть None)

    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(        
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self,
        db: Database,
        repo_class: Type[RepoType],
        model_class: Type[ModelType],
        dto_class: Type[DTOType],
        field_configs: Optional[Dict[str, Dict[str, Any]]] = None,
        logger_name: Optional[str] = None
    ):
        """
        Инициализирует экземпляр сервиса.

        Параметры:
            db (Database): Экземпляр Database для получения сессий.
            repo_class (Type[RepoType]): Класс репозитория, с которым работает сервис.
            model_class (Type[ModelType]): Класс ORM-модели (нужен для создания экземпляров).
            dto_class (Type[DTOType]): Класс DTO (нужен для преобразования).
            field_configs (Optional[Dict[str, Dict[str, Any]]]): Конфигурация полей (используется для виртуальных полей).

            logger_name (Optional[str]): Имя логгера. По умолчанию – имя класса сервиса.

        Особенности:
            - Подписывается на изменения конфигурации через
              `AppConfigManager.add_change_listener(self._on_config_changed)`.
              При изменении настроек автоматически вызывается `self.reload_config()`.
        """

        self._db            = db 
        self._repo_class    = repo_class    # репозиторий с которым работает сервис
        self._model_class   = model_class   # ORM-модель для создания экземпляров
        self._dto_class     = dto_class     # DTO класс для преобразования
        self._field_configs = field_configs or {}  # конфигурация полей для сервиса (по умолчанию пустой словарь)

        # Настройка логгера: если имя не передано, используем имя класса сервиса
        if logger_name is None:
            logger_name = self.__class__.__name__

        self.logger = AppLogger.get_instance(
            name = logger_name,
            # share_file_with = 'user',
            enable_file_logging = 'user',
            use_name_in_filename = False,  # 'user',
        )

        # Подписываемся на изменения конфигурации
        AppConfigManager.add_change_listener(self._on_config_changed)


    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _del_file(
        self,
        file_path: str,
        session: Optional[Session] = None,
        if_delete_parent_dir: bool = False
    ):
        """
        Удаляет физический файл, предпочтительно отложенно (после коммита сессии).

        **Алгоритм:**
            1. Если передан `session` и у него есть атрибут `_pending_deletions` (устанавливается в `Database.session_scope`),
            то файл **не удаляется сразу**, а добавляется в список отложенных удалений сессии.
            Фактическое удаление произойдёт после успешного коммита (обработчик `after_commit`).
            2. Если сессия не поддерживает отложенное удаление (или `session is None`), файл удаляется **немедленно**.
            3. Если `if_delete_parent_dir = True`, после удаления файла проверяется родительская папка:
            если она стала пустой, она также удаляется.

        **Важные замечания:**
            - Метод **не выбрасывает исключение** при ошибках удаления – только логирует их.
            Это сделано потому, что удаление файла не должно прерывать транзакцию БД.
            - При отложенном удалении ошибки логируются в обработчике `after_commit` (см. `Database.__init__`).
            - **НЕ вызывайте этот метод повторно** для одного и того же файла в рамках одной транзакции.
            Два вызова приведут к добавлению файла в `_pending_deletions` дважды, но `after_commit` удалит его один раз
            (без ошибки). Однако это нерационально и может маскировать логические ошибки.
            - **НЕ используйте этот метод для файлов, которые ещё не были скопированы в основное хранилище** (например,
            для абсолютных путей во временной папке черновика). Такие файлы удаляются автоматически при очистке
            временной папки (см. `PaginatedListPage._cleanup_temp_dir`).

        **Параметры:**
            file_path (str): Полный абсолютный путь к файлу.
            session (Optional[Session]): Сессия SQLAlchemy, в контексте которой выполняется удаление.
                Если передана и поддерживает отложенное удаление, файл будет удалён после коммита.
                Если `None` или не поддерживает, удаление происходит немедленно.
            if_delete_parent_dir (bool): Если `True`, после удаления файла (успешного) пытается удалить
                родительскую папку, если она стала пустой. Ошибки при удалении папки логируются, но не прерывают выполнение.

        **Возвращает:**
            None

        **Исключения:**
            Никаких исключений не выбрасывает. При ошибках немедленного удаления логирует предупреждение.

        **Примеры использования:**
            >>> # Отложенное удаление в рамках транзакции
            >>> with db.session_scope() as session:
            ...     self._del_file("/path/to/file.jpg", session=session)
            ...     # файл будет удалён после session.commit()

            >>> # Немедленное удаление без сессии
            >>> self._del_file("/path/to/file.jpg")

            >>> # Удалить файл и, если папка опустела, удалить её
            >>> self._del_file("/path/to/file.jpg", session=session, if_delete_parent_dir=True)

        **Примечания:**
            - Для поддержки отложенного удаления сессия должна иметь атрибут `_pending_deletions`, который создаётся
            в `Database.session_scope`. Не используйте этот метод с сессиями, созданными вручную без этого атрибута.
            - Если файл не существует, метод ничего не делает (только логирует отладочное сообщение).
        """
        ctx = DeletionContext.create(session, DeletionType.COMMIT)
        _ , err = schedule_deletion(
            # session = session,
            ctx=ctx,
            path = file_path,
            remove_parent_if_empty = if_delete_parent_dir,
        )
        return err
    
        # if (session is not None) and hasattr(session, '_pending_deletions'):
        #     session._pending_deletions.append(
        #         {
        #             'path': file_path,
        #             'remove_parent': if_delete_parent_dir,
        #         }
        #     )
        #     self.logger.debug(f"Добавлен файл в отложенное удаление: {file_path}")

        #     return None

        # if os.path.exists(file_path):
        #     # Fallback – удаляем немедленно, но с предупреждением
        #     self.logger.warning("Сессия не поддерживает отложенное удаление, удаляю немедленно")
        #     try:
        #         os.remove(file_path)
        #         self.logger.debug(f"Удалён отложенный файл: {file_path}")

        #     except OSError as e:
        #         self.logger.warning(f"Не удалось удалить {file_path}: {e}")
        #         return e
        #         # raise PhotoFileError(file_path, "удаление", str(e))
        # else:
        #     self.logger.debug(f"Файл {file_path} не существует")

        # if not if_delete_parent_dir:
        #     return None
        
        # # удаление род папки при её пустоте
        # try:
        #     # Проверяем, не стала ли родительская папка пустой
        #     parent_dir = os.path.dirname(file_path)
        #     if os.path.exists(parent_dir) and not os.listdir(parent_dir):
        #         try:
        #             os.rmdir(parent_dir)
        #             self.logger.debug(f"Удалена пустая папка: {parent_dir}")

        #         except OSError as e:
        #             self.logger.warning(f"Не удалось удалить папку {parent_dir}: {e}")

        # except OSError as e:
        #     self.logger.warning(f"Не удалось удалить {parent_dir}: {e}")
        #     return e

        # return None

    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _get_note_field_mappings_dict(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает словарь для быстрого доступа к информации о полях-заметках.

        Используется в фильтрации для построения подзапросов EXISTS.
        Структура словаря:
            {
                'reason_text': {
                    'foreign_key': 'reason_id',     # имя колонки внешнего ключа в модели
                    'note_model': AppointmentNote,  # класс модели заметки
                    'text_column': 'text'           # имя колонки с текстом заметки
                },
                ...
            }

        Returns:
            Dict[str, Dict[str, Any]]: Словарь, где ключ – имя поля DTO (например, 'reason_text'),
                                    значение – метаданные для построения подзапроса.
        """
            
        # from app.database.database_shema.clinic import AppointmentNote

        mappings = {}
        for mapping in self._get_note_field_mappings():
            dto_field = mapping['dto_field']
            mappings[dto_field] = {
                'foreign_key': mapping['orm_id_field'],
                'note_model': AppointmentNote,
                'text_column': 'text'   # поле в AppointmentNote, содержащее текст
            }
        return mappings

    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _apply_filters_to_query(
        self,
        query: Query,
        filters: Optional[List[Dict[str, Any]]] = None,
        fuzzy_threshold: int = 60,
    ) -> Tuple[Query, List[Tuple]]:
        """
        Применяет список фильтров к запросу и возвращает кортеж (query, post_filters).

        Этот метод оборачивает вызов внешней функции `apply_filters` из модуля filtering,
        передавая ей предварительно сформированный словарь `note_mappings` (для поддержки
        поиска по полям-заметкам).

        Args:
            query (Query): Исходный запрос SQLAlchemy.
            filters (Optional[List[Dict[str, Any]]]): Список фильтров  (каждый словарь с ключами column, operator, value).
            fuzzy_threshold (int): Порог схожести для нечёткого поиска..

        Returns:
            Tuple[Query, List[Tuple]]: Модифицированный запрос и список пост-фильтров.
        """
        
        if not filters:
            return query, []
        
        # # from app.utils.filtering.filtering import apply_filters
        # return apply_filters(query, self._model_class, filters, fuzzy_threshold)

        note_mappings = self._get_note_field_mappings_dict()
        # from app.utils.filtering.filtering import apply_filters

        return apply_filters(
            query,
            self._model_class,
            filters,
            fuzzy_threshold,
            note_mappings=note_mappings
        )

    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _apply_order_by(
        self,
        query: Query,
        order_by: Optional[List] = None,
    ) -> Query:
        """
        Применяет сортировку к запросу.

        Args:
            query (Query): Исходный запрос SQLAlchemy.
            order_by (Optional[List]): Список имён полей для сортировки.
                Поле может начинаться с '-' для убывания.

        Returns:
            Query: Модифицированный запрос.
        """
        if not order_by:
            return query

        order_clauses = []
        for field_spec in order_by:
            if field_spec.startswith('-'):
                field_name = field_spec[1:]
                order_clauses.append(getattr(self._model_class, field_name).desc())
            else:
                order_clauses.append(getattr(self._model_class, field_spec).asc())
        return query.order_by(*order_clauses)


    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def get_total_count(
        self,
        filters: Optional[List[Dict[str, Any]]] = None,
        session: Optional[Session] = None
    ) -> int:
        """
        Возвращает общее количество записей с учётом фильтров (без загрузки данных).

        Args:
            filters (Optional[List[Dict[str, Any]]]): Список фильтров.
            session (Optional[Session]): Опциональная внешняя сессия.

        Returns:
            int: Количество записей, удовлетворяющих фильтрам.
        """
        
        with self._session_scope(session) as sess:
            query = sess.query(self._model_class)
            # if filters:
            #     # from app.utils.filtering.filtering import _build_filter_condition
            #     condition = _build_filter_condition(filters, self._model_class)
            #     if condition is not True:
            #         query = query.filter(condition)
                    
            # return query.count()

            query = sess.query(self._model_class)

            # Применяем фильтры (включая заметки), игнорируем пост-фильтры (fuzzy), так как они не влияют на количество
            filtered_query, _ = self._apply_filters_to_query(query, filters)

            return filtered_query.count()
        
        # with self._session_scope(session) as sess:
        #     # repo = self._get_repo(sess)
        #     # return repo.count(filters=filters)

        #     query = sess.query(self._model_class)
        #     query, post_filters = self._apply_filters_to_query(query, filters)
        #     # post_filters не влияют на количество (только на выборку после загрузки)
        #     return query.count()


    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def get_page_filtered(
        self,
        offset: int,
        limit: int,
        filters: Optional[List[Dict[str, Any]]] = None,
        order_by: Optional[List] = None,
        relations: Optional[List] = None,
        fuzzy_threshold: int = 60,
        session: Optional[Session] = None,
    ) -> Tuple[List[DTOType], int]:
        """
        Возвращает страницу записей с учётом фильтров, сортировки и подгрузки связей,
        а также общее количество записей (без пагинации).

        Args:
            offset (int): Смещение (сколько записей пропустить).
            limit (int): Максимальное количество записей на странице.
            filters (Optional[List[Dict[str, Any]]]): Список фильтров.
            order_by (Optional[List]): Список полей для сортировки.
            relations (Optional[List]): Список имён отношений для жадной подгрузки.
            fuzzy_threshold (int): Порог схожести для нечёткого поиска.
            session (Optional[Session]): Опциональная внешняя сессия.

        Returns:
            Tuple[List[DTOType], int]: Кортеж (список DTO на странице, общее количество).
        """

        with self._session_scope(session) as sess:
            base_query = sess.query(self._model_class)

            # Применяем фильтры (получаем query и пост-фильтры)
            filtered_query, post_filters = self._apply_filters_to_query(base_query, filters, fuzzy_threshold)

            # Общее количество до применения пагинации
            total = filtered_query.count()

            # Применяем сортировку
            ordered_query = self._apply_order_by(filtered_query, order_by)

            # Применяем жадную подгрузку
            loaded_query = self._apply_eager_loading(ordered_query, relations)

            # Пагинация
            items = loaded_query.offset(offset).limit(limit).all()

            # Пост-фильтры (например, нечёткий поиск) применяем уже к загруженным объектам
            if post_filters:
                # from app.utils.filtering.filtering import apply_post_filters
                items = apply_post_filters(items, post_filters, self._model_class)

            # Пост-обработка (например, добавление временных атрибутов для подсчётов)
            items = self._post_process_items(items, sess)

            # Преобразование в DTO
            dtos = self.get_dtos(items)
            return dtos, total

    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def get_page_filtered_exact(
        self,
        offset: int,
        limit: int,
        filters: Optional[List[Dict[str, Any]]] = None,
        order_by: Optional[List] = None,
        relations: Optional[List] = None,
        fuzzy_threshold: int = 60,
        session: Optional[Session] = None,
    ) -> Tuple[List[DTOType], int]:
        """
        Возвращает страницу записей с точным учётом пост-фильтров (включая fuzzy).

        **Внимание:** этот метод загружает **все** записи, подходящие под SQL-фильтры,
        затем применяет пост-фильтры в памяти и только после этого выполняет пагинацию.
        На больших объёмах данных (тысячи записей) может быть медленным.
        Рекомендуется использовать только для небольших таблиц или когда точное
        количество критично, а объём данных не превышает нескольких тысяч строк.

        Args:
            offset (int): Смещение (сколько записей пропустить).
            limit (int): Максимальное количество записей на странице.
            filters (Optional[List[Dict[str, Any]]]): Список фильтров (может включать fuzzy).
            order_by (Optional[List]): Список полей для сортировки.
            relations (Optional[List]): Список имён отношений для жадной подгрузки.
            fuzzy_threshold (int): Порог схожести для нечёткого поиска.
            session (Optional[Session]): Опциональная внешняя сессия.

        Returns:
            Tuple[List[DTOType], int]: Кортеж (список DTO на странице, точное общее количество).
        """
        with self._session_scope(session) as sess:
            base_query = sess.query(self._model_class)

            # Применяем SQL-фильтры (без пост-фильтров)
            filtered_query, post_filters = self._apply_filters_to_query(base_query, filters, fuzzy_threshold)

            # Если нет пост-фильтров – используем обычный get_page_filtered (быстрее)
            if not post_filters:
                return self.get_page_filtered(offset, limit, filters, order_by, relations, fuzzy_threshold, session)

            # ---------- Точный режим с пост-фильтрами ----------
            # Применяем сортировку (сортировка по SQL-столбцам, но результат после пост-фильтров
            # может быть не полностью отсортирован – это особенность fuzzy)
            ordered_query = self._apply_order_by(filtered_query, order_by)

            # Жадная подгрузка (если нужна для всех записей)
            loaded_query = self._apply_eager_loading(ordered_query, relations)

            # Загружаем все объекты (это может быть дорого)
            all_items = loaded_query.all()

            # Применяем пост-фильтры (например, fuzzy)
            if post_filters:
                # from app.utils.filtering.filtering import apply_post_filters
                all_items = apply_post_filters(all_items, post_filters, self._model_class)

            total = len(all_items)

            # Пагинация в памяти
            paginated_items = all_items[offset:offset + limit]

            # Пост-обработка (добавление временных атрибутов)
            paginated_items = self._post_process_items(paginated_items, sess)

            # Преобразование в DTO
            dtos = self.get_dtos(paginated_items)

            return dtos, total

    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def get_field_metadata(self) -> List[Dict[str, Any]]:
        """
        Возвращает метаданные полей сущности для использования в парсерах и других динамических компонентах.

        Каждый элемент словаря содержит:
            - name (str): Имя поля в DTO.
            - title (str): Заголовок (человекочитаемое имя).
            - widget_type (str): Тип виджета (например, 'textarea', 'date').
            - is_note (str): Связь с заметкой (если есть).
            - required (bool): Обязательное ли поле.
            - editable (bool): Доступно ли редактирование.
            - hidden (bool): Скрыто ли поле в формах.

        Returns:
            List[Dict[str, Any]]: Список метаданных для всех полей, определённых в field_configs.
        """
            
        metadata = []
        for field_name, config in self._field_configs.items():
            metadata.append(
                {
                    'name': field_name,
                    'title': config.get(
                        'title', field_name.replace('_', ' ').title()
                    ),
                    'widget_type': config.get('widget_type'),
                    'is_note': config.get('is_note'),
                    'required': config.get('required', False),
                    'editable': config.get('editable', True),
                    'hidden': config.get('hidden', False),
                    # можно добавить другие параметры по необходимости
                }
            )
        return metadata

    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    ) 
    def _get_count_mappings(self) -> Dict[str, Dict[str, str]]:
        """
        Анализирует field_configs и возвращает словарь:
            отношение -> {'attr_name': '_count_<отношение>', 'extra_key': <имя ключа из args>}.
        """
        mappings = {}
        for field_name, config in self._field_configs.items():
            relation = config.get('counts')
            if not relation:
                continue
            compute = config.get('compute', {})
            args = compute.get('args', [])
            # Берём первый аргумент как ключ для extra_data, либо строим по умолчанию
            extra_key = args[0] if args else f"{relation}_count"
            attr_name = f"_count_{relation}"
            mappings[relation] = {'attr_name': attr_name, 'extra_key': extra_key}
        return mappings

    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    ) 
    def _add_counts_to_items(
        self,
        items: List[ModelType],
        count_mappings: Dict[str, Dict[str, str]],
        session: Session
    ) -> None:
        """
        Добавляет временные атрибуты (attr_name) к каждому объекту в items
        с количеством дочерних записей по указанному отношению.
        """
        if not items:
            return
        
        # from sqlalchemy import func
        for relation_name, cfg in count_mappings.items():
            relation = getattr(self._model_class, relation_name, None)
            if not relation:
                self.logger.warning(f"Отношение {relation_name} не найдено в {self._model_class.__name__}")
                continue

            # Получаем дочернюю модель
            child_model = relation.mapper.class_

            # Ищем внешний ключ в дочерней модели, ссылающийся на родителя
            fk_col = None
            for fk in child_model.__table__.foreign_keys:
                if fk.references(self._model_class.__table__):
                    fk_col = fk.parent
                    break
            if fk_col is None:
                self.logger.warning(f"Не удалось найти внешний ключ для отношения {relation_name}")
                continue

            # # Определяем столбец внешнего ключа из primaryjoin (берём первый)
            # try:
            #     fk_col = list(relation.primaryjoin.columns)[0]
            # except Exception as e:
            #     self.logger.warning(f"Не удалось определить внешний ключ для {relation_name}: {e}")
            #     continue
            
            # if not fk_col:
            #     self.logger.warning(f"Не удалось определить внешний ключ для {relation_name}")
            #     continue

            parent_ids = [item.id for item in items if item.id is not None]
            if not parent_ids:
                continue

            # Запрос к дочерней таблице с группировкой по внешнему ключу
            counts = session.query(
                fk_col, 
                func.count().label('cnt')
            ).filter(
                fk_col.in_(parent_ids)
            ).group_by(
                fk_col
            ).all()

            count_map = {pid: cnt for pid, cnt in counts}

            for item in items:
                setattr(item, cfg['attr_name'], count_map.get(item.id, 0))

    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def _get_item(
        self, 
        item_id: int,
        class_err: Type[Exception] , 
        session: Optional[Session] = None,
    ):
        """
        Возвращает экземпляр репозитория и запись по ID.

        Параметры:
            item_id (int): ID записи.
            class_err (Type[Exception]): Класс исключения, который будет выброшен в случае отсутствия записи.
        """

        repo = self._get_repo(session)

        item = repo.get_by_id_with_relations(
            item_id,
            options=self._get_eager_loading_options()
        )

        if item is None:
            raise class_err(item_id)

        return repo, item 
    
    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def get_children(
        self, 
        parent_id: int, 
        relation_name: str, 
        session=None
    ) -> List[DTOType]:
        """
        Возвращает список дочерних DTO для указанного родителя и имени отношения.

        Параметры:
            parent_id (int): ID родительской записи.
            relation_name (str): Имя отношения (например, 'photos', 'documents').
            session (Optional[Session]): Опциональная сессия для объединения транзакций.

        Возвращает:
            List[DTOType]: Список дочерних DTO (каждый элемент – DTO дочерней сущности).

        Исключения:
            ValueError: если для `relation_name` не зарегистрирован дочерний сервис.

        Пример:
            photos = appointment_service.get_children(appointment_id, 'photos')
            for photo in photos:
                print(photo.description)
        """

        service = self._get_child_service(relation_name)
        if service is None:
            raise ValueError(f"No child service for relation {relation_name}")
        
        # Предполагаем, что у дочернего сервиса есть метод get_by_parent(parent_id)
        return service.get_by_parent(parent_id, session=session)

    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def add_child(
        self, 
        parent_id: int, 
        relation_name: str, 
        child_dto: DTOType, 
        session=None
    ) -> DTOType:
        """
        Добавляет дочернюю сущность к родителю.

        Параметры:
            parent_id (int): ID родительской записи.
            relation_name (str): Имя отношения.
            child_dto (DTOType): DTO дочерней записи (без ID или с временным ID).
            session (Optional[Session]): Опциональная сессия.

        Возвращает:
            DTOType: Созданная дочерняя запись с заполненным ID.

        Исключения:
            ValueError: если дочерний сервис не найден.

        Пример:
            new_photo = appointment_service.add_child(appointment_id, 'photos', photo_dto)
        """

        service = self._get_child_service(relation_name)
        if service is None:
            raise ValueError(f"No child service for relation '{relation_name}'")
        
        return service.add_to_parent(parent_id, child_dto, session=session)

    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def remove_child(
        self, 
        child_id: int, 
        relation_name: str, 
        session=None
    ) -> None:
        """
        Удаляет дочернюю сущность по её ID.

        Параметры:
            child_id (int): ID дочерней записи.
            relation_name (str): Имя отношения.
            session (Optional[Session]): Опциональная сессия.

        Исключения:
            ValueError: если дочерний сервис не найден.

        Пример:
            appointment_service.remove_child(photo_id, 'photos')
        """
        
        service = self._get_child_service(relation_name)
        if service is None:
            raise ValueError(f"No child service for relation '{relation_name}'")
            
        service.delete(child_id, session=session)

    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _get_child_service(
        self, 
        relation_name: str
    ) -> Optional['BaseService']:
        """
        Возвращает сервис для управления дочерними сущностями по имени отношения.

        Базовый метод всегда возвращает None. Наследники должны переопределить его,
        возвращая соответствующий сервис (например, `self._photo_service` для 'photos').

        Параметры:
            relation_name (str): Имя отношения (например, 'photos', 'documents').

        Возвращает:
            Optional[BaseService]: Сервис для работы с дочерними сущностями или None.
        """

        return None

    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def get_by_relation(self, relation_column: str, value: Any, session=None, relations=None):
        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)
            query = sess.query(self._model_class).filter(getattr(self._model_class, relation_column) == value)

            if relations is None:
                relations = self._get_eager_loading_options()

            if relations:
                query = query.options(*relations)

            items = query.all()
            return self.get_dtos(items)

    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _validate_parents(self, dto: DTOType, session: Session) -> None:
        """
        Проверяет существование родительских записей для внешних ключей.
        Переопределяется в наследниках при необходимости.
        """
        pass

    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _create_entity(
        self,
        dto: DTOType,
        # required_kwargs: Dict[str, Any],
        session: Optional[Session] = None
    ) -> DTOType:
        """
        Универсальный метод создания записи в БД на основе DTO и field_configs.

        Алгоритм:
            1. Проверяет обязательные поля (required=True) через `_validate_required_fields`.
            2. Собирает обычные поля (не виртуальные, не `is_note`) в словарь `creation_kwargs`.
            3. Обрабатывает поля-заметки (`is_note`) через `_apply_note_updates(model_obj=None)`.
            4. Создаёт экземпляр модели, объединяя обычные поля и ID заметок.
            5. Сохраняет запись через репозиторий.
            6. Возвращает DTO созданной записи.

        Параметры:
            dto (DTOType): DTO с данными для создания.
            session (Optional[Session]): Внешняя сессия (если не указана, создаётся новая).

        Возвращает:
            DTOType: DTO созданной записи.

        Примечание:
            Поля, помеченные `virtual=True` или `is_note`, исключаются из обычных kwargs.
            Для полей-заметок текст сохраняется/обновляется в таблице `AppointmentNote`,
            а ID заметки присваивается соответствующему полю модели (например, `description_id`).
        """

        with self._session_scope(session) as sess:
            # 1. Проверяем обязательные поля
            self._validate_required_fields(dto)

            self._validate_parents(dto, sess)
            
            # 2. Собираем обычные поля
            creation_kwargs = self._get_creation_kwargs(dto)
            # Репозиторий для заметок (один на все сущности)
            note_repo = AppointmentNoteRepository(sess)
            
            # Обрабатываем заметки (поля с is_note)
            note_ids = self._apply_note_updates(dto, sess, note_repo, model_obj=None)
            
            # Создаём экземпляр модели, объединяя обязательные поля и ID заметок
            model_kwargs = {**creation_kwargs, **note_ids}
            entity = self._model_class(**model_kwargs)
            
            repo = self._get_repo(sess)
            repo.add(entity)
            sess.flush()
            
            return self.get_dto_out(entity)


    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _update_entity(
        self,
        dto: DTOType,
        entity_id: int,
        session: Optional[Session] = None
    ) -> DTOType:
        """
        Универсальный метод обновления записи.

        Алгоритм:
            1. Загружает существующую запись с подгрузкой всех связей, указанных в `_get_relations_for_eager_loading()`.
            2. Если запись не найдена – вызывает `_not_found_exception`.
            3. Обновляет поля-заметки через `_apply_note_updates(model_obj=entity)`.
            При этом старые неиспользуемые заметки автоматически удаляются.
            4. Обновляет простые поля через `_apply_simple_updates`.
            5. Сохраняет изменения (flush).
            6. Возвращает обновлённый DTO.

        Параметры:
            dto (DTOType): DTO с новыми данными.
            entity_id (int): ID обновляемой записи.
            session (Optional[Session]): Опциональная сессия для работы в одной транзакции.

        Возвращает:
            DTOType: DTO обновлённой записи.

        Исключения:
            self._not_found_exception: если запись с `entity_id` не найдена.
        """

        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)

            # Подгружаем все необходимые связи (из field_configs)
            relations = self._get_relations_for_eager_loading()

            entity = repo.get_with_relations(entity_id, relations)
            if entity is None:
                raise self._not_found_exception(entity_id)
            
            note_repo = AppointmentNoteRepository(sess)
            
            # Обновляем заметки
            new_note_ids = self._apply_note_updates(
                dto,
                sess,
                note_repo,
                model_obj=entity
            )
            for orm_field, value in new_note_ids.items():
                setattr(entity, orm_field, value)
            
            # Обновляем простые поля
            self._apply_simple_updates(entity, dto, session = sess)

            self.logger.debug(f"После обновления полей: last_name={entity.last_name}")

            sess.flush()
            return self.get_dto_out(entity)


    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _delete_entity(
        self,
        entity_id: int,
        session: Optional[Session] = None
    ) -> None:
        """
        Универсальный метод удаления записи с очисткой связанных заметок.

        НЕ УДАЛЯЕТ физические файлы! Удаление файлов должно происходить в delete() или в наследниках.

        Алгоритм:
            1. Загружает запись с подгрузкой всех связей (согласно конфигурации).
            2. Если запись не найдена – вызывает `_not_found_exception`.
            3. Собирает ID всех заметок, связанных с этой записью (через `_get_note_field_mappings`).
            4. Удаляет саму запись (каскадные удаления на уровне БД не используются – удаляем явно).
            5. Вызывает `NoteService.cleanup_unused_note` для каждой собранной заметки,
            чтобы удалить заметки, которые больше не используются нигде.

        Параметры:
            entity_id (int): ID удаляемой записи.
            session (Optional[Session]): Опциональная сессия.

        Примечание:
            Дочерние сущности (например, приёмы пациента) не удаляются автоматически.
            Для каскадного удаления нужно вручную удалить их в переопределённом методе `delete` сервиса.
            Пример: в `PatientService.delete_patient` удаляются все приёмы через `AppointmentService`.
        """

        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)

            # Подгружаем все связи, чтобы потом собрать ID заметок
            relations = self._get_relations_for_eager_loading()

            entity = repo.get_with_relations(entity_id, relations)
            if entity is None:
                raise self._not_found_exception(entity_id)
            
            # Собираем ID заметок через field_configs
            note_ids = set()
            for mapping in self._get_note_field_mappings():
                note_id = getattr(entity, mapping['orm_id_field'])
                if note_id is not None:
                    note_ids.add(note_id)
            
            # Удаляем саму запись
            repo.delete(entity)
            sess.flush()
            
            # Очищаем неиспользуемые заметки
            note_service = self._get_note_service()
            if note_service:
                for nid in note_ids:
                    # self._get_note_service().cleanup_unused_note(nid, sess)
                    note_service.cleanup_unused_note(nid, sess)


    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _get_simple_updatable_fields(self) -> List[Dict[str, Any]]:
        """
        Возвращает список полей, которые можно обновлять напрямую (не заметки, не виртуальные).
        Каждый элемент содержит:
            - 'name': имя поля в DTO и модели
            - 'editable': разрешено ли редактирование (по умолчанию True)
        """
        updatable = []

        # Получаем словарь полей DTO (Pydantic v2)
        dto_fields = self._dto_class.model_fields if hasattr(self._dto_class, 'model_fields') else {}

        for field_name, config in self._field_configs.items():
            # Пропускаем ID (первичный ключ)
            if field_name == 'id':
                self.logger.debug(f"Поле {field_name} пропущено (id)")
                continue

            # Пропускаем виртуальные поля и заметки
            if config.get('virtual', False) or config.get('is_note'):
                self.logger.debug(f"Поле {field_name} пропущено (virtual/is_note)")
                continue

            # Пропускаем явно отмеченные как не updatable
            if config.get('updatable') is False:
                self.logger.debug(f"Поле {field_name} пропущено (updatable=False)")
                continue

            # # Проверяем, существует ли поле в DTO (безопасность)
            # if not hasattr(self._dto_class, field_name):
            #     self.logger.debug(f"Поле {field_name} отсутствует в DTO")
            #     continue

            # Проверяем наличие поля в DTO через model_fields (не через hasattr)
            if field_name not in dto_fields:
                self.logger.debug(f"Поле {field_name} отсутствует в DTO (не найдено в model_fields)")
                continue
            
            updatable.append({
                'name': field_name,
                'editable': config.get('editable', True) # для UI, но в сервисе не используется
            })
            self.logger.debug(f"Поле {field_name} добавлено в updatable")

        return updatable

    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _apply_simple_updates(
        self,
        model_obj: ModelType,
        dto: DTOType,
        session: Optional[Session] = None
    ) -> None:
        """
        Обновляет простые поля модели из DTO согласно field_configs.

        **Назначение:**
            Применяет изменения к существующему ORM-объекту, полученному из БД,
            на основе данных из DTO. Метод вызывается внутри `_update_entity` при
            сохранении изменений.

        **Алгоритм:**
            1. Перебирает поля, возвращённые `_get_simple_updatable_fields()`.
            2. Для каждого поля проверяет, изменилось ли значение (сравнивая старое
               из модели с новым из DTO).
            3. **Специальная обработка для полей с фото (`widget_type='image_thumbnail'`):**
               - Если значение изменилось, старый путь относительный и файл существует
                 в основном хранилище – удаляет физический файл (логгирует успех/ошибку).
               - Абсолютные пути (временные файлы черновиков) не удаляются.
            4. Обновляет поле модели новым значением (или None, если поле необязательное
               и в DTO передано None).

        **Параметры:**
            model_obj (ModelType): ORM-объект (уже загружен из БД, с текущими значениями).
            dto (DTOType): DTO, содержащий новые значения полей.
            session  (Optional[Session]): Сессия SQLAlchemy, необходимая для доступа
                к списку отложенных удалений. Должна быть передана из вызывающего метода.

        **Возвращает:**
            None

        **Примечания:**
            - Метод предполагает, что все поля, попадающие в `_get_simple_updatable_fields()`,
              являются обычными столбцами БД (не виртуальными, не `is_note`, не `updatable=False`).
            - Для обязательных полей (`required=True`) попытка установить None вызывает
              `ValueError` с сообщением.
            - Удаление старого файла происходит только при изменении значения и только
              для относительных путей. Это предотвращает случайное удаление файлов,
              которые ещё не были скопированы в основное хранилище (например, во время
              редактирования новой строки до сохранения).

        **Пример:**
            >>> # Внутри _update_entity
            >>> self._apply_simple_updates(entity, dto, session)
            >>> # Теперь entity.last_name обновлён, и если photo_path изменился,
            >>> # старый файл удалён с диска.
        """        

        for field_info in self._get_simple_updatable_fields():

            if not field_info.get('editable', True) or field_info.get('updatable') is False:
                continue

            field_name = field_info['name']
            # if field_info['editable']:
            new_value = getattr(dto, field_name, None)
            old_value = getattr(model_obj, field_name, None)

            config = self._field_configs.get(field_name, {})
            
            # Удаление старого файла для полей с фото (widget_type='image_thumbnail')
            if config.get('widget_type') == 'image_thumbnail':
                
                storage_path = AppConfigManager.get_instance().get(
                    'PHOTOS_STORAGE_PATH',
                    os.path.join('.', 'photos')
                )
                
                # 1. Проверка существования нового файла (если путь относительный)
                if (
                    new_value is not None
                ) and (
                    not os.path.isabs(new_value)
                ):
                    full_new_path = os.path.join(storage_path, new_value)
                    if not os.path.exists(full_new_path):
                        self.logger.warning(
                            f"Новый файл для поля {field_name} не существует: {full_new_path}. "
                            "Обновление поля будет выполнено, но файл отсутствует."
                        )
                
                # Если значение изменилось, старое не пустое и не абсолютный путь (значит файл уже в хранилище)
                if (
                    old_value != new_value
                ) and (
                    old_value is not None
                ) and (
                    not os.path.isabs(old_value)
                ):
                    full_old_path = os.path.join(storage_path, old_value)
                    
                    # Удаляем файл
                    self._del_file(
                        full_old_path, 
                        session = session, 
                        if_delete_parent_dir=True, 
                    )

                    # if os.path.exists(full_old_path):
                    #     if (session is not None) and hasattr(session, '_pending_deletions'):
                    #         session._pending_deletions.append(full_old_path)
                    #         self.logger.debug(f"Добавлен файл в отложенное удаление: {full_old_path}")
                    #     else:
                    #         # fallback – удаляем сразу, но с предупреждением
                    #         self.logger.warning("Сессия не поддерживает отложенное удаление, удаляю немедленно")
                    #
                    #         try:
                    #             os.remove(full_old_path)
                    #             self.logger.debug(f"Удалён старый файл: {full_old_path}")
                    #         except OSError as e:
                    #             self.logger.warning(f"Не удалось удалить {full_old_path}: {e}")
                    # else:
                    #     self.logger.debug(f"Старый файл {full_old_path} не существует, пропуск удаления")

            if new_value is not None:
                # setattr(model_obj, field_name, new_value)
                if old_value != new_value:
                    self.logger.debug(f"Обновление поля {field_name}: {old_value} -> {new_value}")
                    setattr(model_obj, field_name, new_value)
                else:
                    self.logger.debug(f"Поле {field_name} не изменилось: {old_value}")

            else:
                # Проверяем, является ли поле обязательным
                # config = self._field_configs.get(field_name, {})
                if config.get('required', False):
                    # Если поле обязательно, не разрешаем устанавливать None
                    self.logger.warning(f"Попытка установить None в обязательное поле {field_name}")
                    # Вариант 1: пропустить (оставить старое значение)
                    # continue
                    # Вариант 2: выбросить исключение
                    raise ValueError(f"Обязательное поле {field_name} не может быть пустым")
                else:
                    setattr(model_obj, field_name, None)

    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _get_relations_for_eager_loading(self) -> List[str]:
        """
        Возвращает список имён отношений ORM, которые необходимо подгружать
        для корректного заполнения виртуальных полей DTO.

        Алгоритм:
            1. Проходит по всем полям из `self._field_configs`.
            2. Если поле помечено `is_note` (имеет строковое значение), добавляет `source_attr`.
            3. Иначе если поле виртуальное (`virtual=True`) и имеет `source_attr`, проверяет флаг `eager_load`.
            Если `eager_load` не `False`, добавляет `source_attr`.
            4. Возвращает список уникальных имён отношений.

        Особенности:
            - Поле `has_photos` имеет `eager_load=False`, поэтому `'photos'` не подгружается.
            - Связь `patient` (для `patient_name`) подгружается, т.к. `eager_load` не указан.
            - Для заметок `eager_load` не проверяется – они всегда подгружаются.

        Возвращает:
            List[str]: Список имён атрибутов модели, которые нужно подгружать.
        """

        relations = set()
        for config in self._field_configs.values():
            # Поля-заметки
            if config.get('is_note'):
                source_attr = config.get('source_attr')
                if source_attr:
                    relations.add(source_attr)

            # Можно также добавить source_attr для обычных виртуальных полей,
            # если они требуют подгрузки (например, 'patient' для patient_name)
            elif config.get('virtual') and config.get('source_attr'):
                # Например, поле patient_name имеет source_attr='patient'
                # добавляем только если eager_load не False
                if config.get('eager_load') is not False:
                    relations.add(config['source_attr'])
        
        return list(relations)
    
    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _get_creation_kwargs(self, dto: DTOType) -> Dict[str, Any]:
        """
        Собирает словарь аргументов для создания экземпляра модели.
        Включает все поля, которые:
            - не являются виртуальными (virtual=False)
            - не являются заметками (is_none)
            - не являются ID самой модели (поле 'id' пропускаем)
        """

        kwargs = {}
        dto_fields = self._dto_class.model_fields if hasattr(self._dto_class, 'model_fields') else {}

        for field_name, config in self._field_configs.items():
            # Пропускаем ID
            if field_name == 'id':
                continue

            # Пропускаем виртуальные поля
            if config.get('virtual', False):
                continue

            # Пропускаем заметки (они обрабатываются отдельно)
            if config.get('is_note', None) is not None:
                continue

            # if config.get('updatable') is False: # убрал, так как проблема с patient_id у APPOINTMENT
            #     continue

            # Проверяем наличие поля в DTO через model_fields
            if field_name not in dto_fields:
                self.logger.debug(f"Поле {field_name} отсутствует в DTO, пропускаем")
                continue

            # Берём значение из DTO, если оно не None
            value = getattr(dto, field_name, None)
            if value is not None:
                kwargs[field_name] = value
            else:
                self.logger.debug(f"Field {field_name} has no value in DTO")

        return kwargs

    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(        
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _validate_required_fields(self, dto: DTOType) -> None:
        """
        Проверяет, что все поля, помеченные в field_configs как required=True,
        присутствуют в DTO и не пусты (для строк – не пустая строка).
        
        Исключения: поля с is_note и virtual пропускаются (они не хранятся в БД напрямую).
        """
        missing = []
        dto_fields = self._dto_class.model_fields if hasattr(self._dto_class, 'model_fields') else {}

        for field_name, config in self._field_configs.items():
            if not config.get('required', False):
                continue
            # Пропускаем виртуальные поля и заметки – они не являются столбцами БД
            if config.get('virtual', False) or config.get('is_note'):
                continue

            if field_name not in dto_fields:
                # Поле не существует в DTO – пропускаем (не должно быть, но на всякий случай)
                continue
            
            value = getattr(dto, field_name, None)
            if value is None:
                missing.append(field_name)
                
            elif isinstance(value, str) and not value.strip():
                missing.append(field_name)
        
        if missing:
            titles = [self._field_configs.get(f, {}).get('title', f) for f in missing]
            raise ValueError(f"Обязательные поля не заполнены: {', '.join(titles)}")

    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(        
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_note_field_mappings(self) -> List[Dict[str, str]]:
        """
        Анализирует field_configs и возвращает список словарей для полей-заметок.

        Каждый словарь содержит:
            - dto_field (str): имя поля в DTO (текст заметки).
            - id_field (str): имя поля в DTO для ID заметки (скрытое, из `is_note`).
            - relation_name (str): имя атрибута отношения в ORM-модели (source_attr).
            - orm_id_field (str): имя колонки в модели для внешнего ключа (обычно совпадает с id_field).

        Условия отбора:
            - поле должно иметь непустой строковый атрибут `is_note`.
            - поле должно быть виртуальным (`virtual=True`).
            - должна быть указана `source_attr`.
        """

        mappings = []
        for field_name, config in self._field_configs.items():
            # Проверяем, что поле помечено как заметка

            id_field = config.get('is_note', None)
            if not id_field:
                continue # Проверяем, что поле помечено как заметка

            if not isinstance(id_field, str) or not id_field.strip():
                continue  # поле не является заметкой или указан неверно

            # Дополнительная защита: убеждаемся, что поле виртуальное
            if not config.get('virtual', False):
                self.logger.warning(
                    f"Поле {field_name} помечено is_note=True, но virtual=False. Игнорирую."
                )
                continue

            compute = config.get('compute')
            if not compute:
                self.logger.warning(
                    f"Поле {field_name} помечено is_note=True, но не имеет compute. Виртуальное поле не будет заполняться."
                )
                continue

            # args = compute.get('args', [])
            # if not args:
            #     self.logger.warning(
            #         f"Поле {field_name} помечено is_note=True, но args есть. Игнорирую."
            #     )
            #     continue

            source_attr = config.get('source_attr')
            if not source_attr:
                self.logger.warning(
                    f"Для заметки {field_name} не указан source_attr. Игнорирую."
                )
                continue

            # # Определяем ID-поле: отрезаем '_text' и добавляем '_id'
            # if field_name.endswith('_text'):
            #     id_field = field_name[:-5] + '_id'
            # else:
            #     id_field = field_name + '_id'
            
            # Имя внешнего ключа в ORM: обычно совпадает с id_field
            orm_id_field = id_field
            
            mappings.append({
                'dto_field': field_name,
                'id_field': id_field,
                'relation_name': source_attr,
                'orm_id_field': orm_id_field, # в Appointment колонки называются так же
            })

        return mappings
    
    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False,  # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_note_service(self) -> Optional['NoteService']:
        """
        Возвращает экземпляр NoteService, используемый для работы с полями-заметками.

        **Должен быть переопределён в наследниках, если у сущности есть поля `is_note`.**

        Базовый метод выбрасывает `NotImplementedError`. В наследнике нужно вернуть
        свой экземпляр NoteService (обычно создаётся в `__init__` и сохраняется в
        `self._note_service`). Если у сущности нет полей-заметок, этот метод не
        используется (но для единообразия можно вернуть None).

        Пример (NoteService) если не используются, то просто делаем та:
            def _get_note_service(self) -> Optional[NoteService]:
                return self._note_service

        Returns:
            NoteService: экземпляр сервиса заметок.

        Raises:
            NotImplementedError: если метод не переопределён.
        """

        # """Должен быть переопределён в наследниках, возвращая экземпляр NoteService."""
        raise NotImplementedError
        # return None

    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False,  # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _apply_note_updates(self, dto, session, note_repo, model_obj=None) -> Dict[str, Optional[int]]:
        """
        Общая логика создания/обновления заметок.

        Параметры:
            dto (DTOType): DTO, содержащий текст заметок (поля из `_get_note_field_mappings`).
            session (Session): Сессия SQLAlchemy.
            note_repo (AppointmentNoteRepository): Репозиторий для заметок.
            model_obj (Optional[ModelType]): Если передан (режим обновления), используется для получения старых ID.

        Возвращает:
            Dict[str, Optional[int]]: Словарь {orm_id_field: new_id}, где `new_id` может быть None,
                если текст очищен.

        Примечание:
            - В режиме обновления старые заметки, которые больше не используются, удаляются через `NoteService`.
            - Пустой текст приводит к установке None в ID-поле (связь удаляется).
        """

        old_ids = {}
        new_ids = {}

        for mapping in self._get_note_field_mappings():
            orm_field = mapping['orm_id_field']
            text = getattr(dto, mapping['dto_field'], None)

            old_id = getattr(model_obj, orm_field) if model_obj else None
            old_ids[orm_field] = old_id

            if text is not None and text.strip():
                new_id, _ = self._update_note_field(
                    session, 
                    note_repo, 
                    old_id, 
                    text, 
                    create_if_missing=False
                )
                new_ids[orm_field] = new_id
            else:
                # new_ids[orm_field] = old_id

                 # Текст очищен – удаляем связь с заметкой
                new_ids[orm_field] = None
                # Если была старая заметка, она будет удалена позже в блоке очистки

        # если обновление - чистим старые заметки
        if model_obj:
            note_service = self._get_note_service()
            if note_service:
                for orm_field, old_id in old_ids.items():
                    new_id = new_ids.get(orm_field)
                    if old_id is not None and old_id != new_id:
                        # self._get_note_service().cleanup_unused_note(old_id, session)
                        note_service.cleanup_unused_note(old_id, session)


        return new_ids

    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False,  # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_config_changed(self):
        """
        Вызывается при изменении конфигурации приложения  – перезагружает сервис.

        Просто перенаправляет вызов на `self.reload_config()`, который должен быть
        переопределён в наследниках или реализован в базовом классе.
        Этот метод автоматически вызывается `AppConfigManager` при сохранении новых настроек.

        Returns:
            None
        """

        self.reload_config()

    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False,  # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_repo(self, session) -> RepoType:
        """
        Создаёт репозиторий с переданной сессией.

        Parameters:
            session (Session): сессия для работы с БД.

        Returns:
            RepoType: репозиторий с переданной сессией.
        """

        return self._repo_class(session)

    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _post_process_items(
        self, 
        items: List[ModelType], 
        session: Session
    ) -> List[ModelType]:
        """
        Пост-обработка списка ORM-объектов перед конвертацией в DTO.
        По умолчанию добавляет временные атрибуты для полей с ключом 'counts'.
        Может быть переопределён в наследниках для дополнительной логики.
        """
        count_mappings = self._get_count_mappings()
        if count_mappings:
            self._add_counts_to_items(items, count_mappings, session)

        return items

    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _prepare_extra_data(self, obj: ModelType) -> Dict[str, Any]:
        """
        Подготавливает словарь extra_data для enrich_dto_with_computed_fields.
        Собирает все временные атрибуты, созданные в _post_process_items.
        """
        extra = {}
        for mapping in self._get_count_mappings().values():
            attr_name = mapping['attr_name']
            extra_key = mapping['extra_key']
            if hasattr(obj, attr_name):
                extra[extra_key] = getattr(obj, attr_name)

        return extra

    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _modify_query(self, query):
        """
        Хук для модификации запроса перед выполнением.
        Наследники могут переопределить для добавления фильтров, сортировки и т.д.
        """
        return query
    
    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_all(self, session: Optional[Session] = None) -> List[DTOType]:
        """
        Возвращает список всех записей в виде DTO.

        Параметры:
            session (Optional[Session]): Внешняя сессия. Если не указана, создаётся новая.

        Возвращает:
            List[DTOType]: Список DTO.

        Пример:
            >>> patients = patient_service.get_all()
            >>> for p in patients:
            ...     print(p.last_name, p.first_name)
        """

        self.logger.debug(f"Запрос всех записей {self._model_class.__name__}")

        with self._session_scope(session) as sess:
            # repo = self._get_repo(sess)

            # relations = self._get_eager_loading_options() # Получаем список отношений для eager loading

            # if relations and hasattr(repo, 'get_all_with_relations'):# Проверяем, есть ли у репозитория метод get_all_with_relations
            #     items = repo.get_all_with_relations(relations)
            # else:
            #     # fallback – просто загружаем без подгрузки (но такого не должно быть)
            #     items = repo.get_all()

            # Строим базовый запрос
            query = sess.query(self._model_class)

            # Применяем eager loading (joinedload) для всех необходимых отношений
            query = self._apply_eager_loading(query)
            
            query = self._modify_query(query)
            
            items = query.all()

            items = self._post_process_items(items, sess) # Пост-обработка (добавление временных атрибутов, например _count_photos)

            dtos = self.get_dtos(items) # Преобразование в DTO (внутри вызывает enrich_dto_with_computed_fields)
            # self.logger.debug(f"Получено {len(dtos)} записей")

            return dtos

    @AppLogger.get_instance(
    name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _get_extra_rels(self, relations) -> List:
        """
        Возвращает список опций joinedload для одиночных запросов (get_by_id).
        Включает все отношения из _get_relations_for_eager_loading() плюс те,
        у которых в конфигурации установлен флаг eager_load_detail=True.
        """
        # Добавляем отношения, помеченные как eager_load_detail
        extra_rels = []
        for config in self._field_configs.values():
            if config.get('eager_load_detail'):         # флаг для детальных запросов
                source_attr = config.get('source_attr')  # например 'photos'
                if source_attr and source_attr not in relations:
                    extra_rels.append(source_attr)

        return extra_rels

    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False,  # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_by_id(self, entity_id: int, session: Optional[Session] = None) -> DTOType:
        """
        Возвращает запись по ID.

        :param entity_id: ID записи, которую мы хотим получить
        :type entity_id: int
        :param session: сессия для работы с БД (если не указана, то используем сессию из self._db)
        :type session: Optional[Session]
        :return: запись в виде DTO (если не найдено, то возвращаем исключение)
        :rtype: DTOType
        :raises: исключение, возвращаемое методом _not_found_exception(), если не найдено
        """
        # Логируем начинаение операции
        self.logger.debug(f"Запрос {self._model_class.__name__} с id={entity_id}")

        # Создаем сессию для работы с БД (если не указана, то используем сессию из self._db)
        with self._session_scope(session) as sess:
            # Создаем репозиторий с переданной сессией
            repo = self._get_repo(sess)

            # Получаем список отношений для подгрузки
            relations = self._get_relations_for_eager_loading()

            # Добавляем отношения, помеченные как eager_load_detail
            extra_rels = self._get_extra_rels(relations) 

            if extra_rels:
                relations = relations + extra_rels          # добавляем к общему списку

            if relations:
                item = repo.get_with_relations(entity_id, relations)
            else:
                item = repo.get_by_id(entity_id)

            # # Получаем запись по ID
            # item = repo.get_by_id(entity_id)

            # Если запись не найдена, то возвращаем исключение
            if item is None:
                raise self._not_found_exception(entity_id)

            # Применяем пост-обработку (добавление временных атрибутов для подсчётов)
            items = self._post_process_items([item], sess)
            processed_item = items[0] if items else item

            # Конвертируем запись из ORM в DTO
            # dto = self._dto_class.from_orm(item)
            # dto = self._dto_class.model_validate(item)
            # dto = self.get_dtos(item)
            dto = self.get_dtos(processed_item)

            # Логируем конец операции
            # self.logger.debug(f"Найдена запись {dto}")
            return dto

    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False,  # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def create(
        self, 
        dto: DTOType, 
        session: Optional[Session] = None,
    ) -> DTOType:
        """
        Создаёт новую запись из DTO.

        Должен быть переопределён в наследнике, так как логика создания специфична.
        :param dto: DTO, из которого будет создана новая запись
        :return: созданная запись в виде DTO
        :raises: NotImplementedError, если метод не переопределён в наследнике
        """

        raise NotImplementedError("Метод create должен быть переопределён в наследнике")

    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def update(
        self, 
        dto: DTOType,
        session: Optional[Session] = None
    ) -> DTOType:
        """
        Обновляет существующую запись.

        Должен быть переопределён в наследнике, так как обновление специфично.
        :param dto: DTO, из которого будет обновлена запись
        :return: обновленная запись в виде DTO
        :raises: NotImplementedError, если метод не переопределён в наследнике
        """

        raise NotImplementedError("Метод update должен быть переопределён в наследнике")

    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False,  # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def delete(self, entity_id: int, session: Optional[Session] = None) -> None:
        """
        Удаляет запись по ID.

        Логирует операцию.

        :param entity_id: ID записи для удаления
        :param session: сессия для работы с БД (необязательна)
        :raises: self._not_found_exception, если запись не найдена
        :return: None

        **Важно:** Если у сущности есть поля с widget_type='image_thumbnail' (фото, хранящиеся
        как строковые пути в БД, а не как отдельные записи в таблице photos), то физические
        файлы на диске НЕ УДАЛЯЮТСЯ автоматически при вызове этого метода.
        Для удаления таких файлов необходимо обрабатывать их отдельно на уровне GUI
        (например, в PaginatedListPage._delete_entity_and_children) или в переопределённом
        методе delete соответствующего сервиса.
        """


        self.logger.debug(f"Удаление {self._model_class.__name__} с id={entity_id}")
        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)
            item = repo.get_by_id(entity_id)

            if item is None:
                raise self._not_found_exception(entity_id)
            
            # Удаление файлов для полей с фото (widget_type='image_thumbnail')
            # ВНИМАНИЕ: Эта часть НЕ дублируется в _delete_entity, поэтому необходимо
            # вызывать _del_file до _delete_entity. Не переносите этот блок в _delete_entity,
            # иначе при вызове _delete_entity из других мест (например, из PhotoService.delete_photo)
            # файлы будут удаляться повторно.

            # ВНИМАНИЕ: Этот блок удаляет физические файлы, связанные с удаляемой записью.
            # Предполагается, что на файл нет других ссылок в БД (уникальная связь).
            # Для сущностей, где фото может быть переиспользовано, необходимо переопределить delete
            # и не вызывать super().delete (или удалять файлы вручную после проверки использования).
            storage_path = None
            for field_name, config in self._field_configs.items():
                if config.get('widget_type') != 'image_thumbnail':
                    continue
                
                # Получаем значение поля (относительный путь к файлу)
                rel_path = getattr(item, field_name, None)
                if not rel_path or not isinstance(rel_path, str):
                    continue

                # Если путь абсолютный - пропускаем (такие файлы ещё не скопированы в хранилище) # требуеется проверить на нужность!!!
                if os.path.isabs(rel_path):
                    self.logger.debug(f"Поле {field_name} содержит абсолютный путь {rel_path}, пропуск удаления")
                    continue

                # Получаем базовый путь к хранилищу (лениво)
                if storage_path is None:
                    storage_path = AppConfigManager.get_instance().get(
                        'PHOTOS_STORAGE_PATH',
                        os.path.join('.', 'photos')
                    )

                full_path = os.path.join(storage_path, rel_path)

                # Удаляем файл
                self._del_file(
                    full_path,
                    session = sess,
                    if_delete_parent_dir = True,
                )

                # if os.path.exists(full_path):
                #     # Добавляем в список отложенного удаления сессии
                #     if hasattr(sess, '_pending_deletions'):
                #         sess._pending_deletions.append(full_path)
                #         self.logger.debug(f"Добавлен файл в отложенное удаление: {full_path}")
                #     else:
                #         try:
                #             os.remove(full_path)
                #             self.logger.info(f"Удалён файл фото: {full_path}")
                #             # Проверяем, не стала ли родительская папка пустой
                #             parent_dir = os.path.dirname(full_path)
                #             if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                #                 try:
                #                     os.rmdir(parent_dir)
                #                     self.logger.info(f"Удалена пустая папка: {parent_dir}")
                #                 except OSError as e:
                #                     self.logger.warning(f"Не удалось удалить папку {parent_dir}: {e}")
                #         except OSError as e:
                #             self.logger.warning(f"Не удалось удалить файл {full_path}: {e}")
                # else:
                #     self.logger.debug(f"Файл {full_path} не существует, пропуск")

            repo.delete(item)
            self.logger.info(f"Удалена запись {self._model_class.__name__} с id={entity_id}")

    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _not_found_exception(self, entity_id: int) -> Exception:
        """
        Возвращает исключение, которое будет выброшено при отсутствии записи.
        Должно быть переопределено в наследнике.
        :param entity_id: ID записи, которая не была найдена
        :raises: Exception
        :return: Exception
        """
        raise NotImplementedError(
            f"Метод _not_found_exception не реализован для {self.__class__.__name__}"
        )
    
    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_dtos(
        self, 
        item_s: Union[List, Any]  # список объектов или один объект
    ) -> Union[List, Any]:
        """
        Возвращает список DTO из списка объектов или один DTO из объекта.
        Если получен список объектов, то для каждого объекта пытается создать DTO.
        Если объект не может быть конвертирован в DTO, то выбрасывается исключение.
        
        :param item_s: список объектов или один объект
        :type item_s: Union[List, Any]
        :return: список DTO или один DTO
        :rtype: Union[List, Any]
        """
        self.logger.debug(f"item_s: {item_s}")

        if isinstance(item_s, list):
            # данные из ТБ
            dtos = [self.get_dtos(item) for item in item_s] # рекурсивно добавляем DTO в список
            self.logger.debug(f"Получено {len(dtos)} записей")  # логгируем количество полученных DTO

            return dtos
        
        # данные из ТБ
        try:
            dto = self._dto_class.model_validate(item_s)  # создаем DTO из объекта
        except Exception as e:
            self.logger.error(f"Ошибка валидации для объекта: {item_s}")  # логгируем ошибку
            raise e  # выбрасываем исключение
        
        # Обогащаем, если есть конфигурация
        if self._field_configs:

            extra_data = self._prepare_extra_data(item_s)

            dto = enrich_dto_with_computed_fields(
                dto, 
                item_s, 
                self._field_configs,
                extra_data
            )

        # self.logger.debug(f"Получена запись: {dto}")  # логгируем полученную DTO
        return dto
    
    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_dto_out(
        self, 
        item,
    ): 
        """
        Возвращает DTO из объекта.

        :param item: объект, из которого будет создан DTO
        :type item: Any
        :return: DTO, созданный из объекта
        :rtype: DTOType
        """
        dto = self.get_dtos(item)

        # self.logger.debug(f"Получена запись: {dto}")

        return dto
    
    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_eager_loading_options(self, relations: List[str] = None) -> List:
        """
        Возвращает список опций joinedload для отношений, которые необходимо подгрузить.

        Параметры:
            relations (List[str], optional): Список имён отношений. Если не указан,
                используется `self._get_relations_for_eager_loading()`.

        Возвращает:
            List: Список объектов `joinedload`, готовых для передачи в `query.options(*...)`.

        Пример:
            options = self._get_eager_loading_options()
            query = query.options(*options)

        """

        # from sqlalchemy.orm import joinedload
        if relations is None:
            relations = self._get_relations_for_eager_loading()

        if not relations:
            return []
        
        options = []
        for rel_name in relations:
            attr = getattr(self._model_class, rel_name)
            try:
                # Для отношений (relationship) используем property.uselist
                if hasattr(attr, 'property') and hasattr(attr.property, 'uselist'):
                    if attr.property.uselist:
                        options.append(selectinload(attr))
                    else:
                        options.append(joinedload(attr))
                else:
                    # fallback – используем joinedload
                    options.append(joinedload(attr))
            except Exception as e:
                self.logger.warning(f"Не удалось определить тип отношения для {rel_name}: {e}")
                options.append(joinedload(attr))
        
        return options
    
    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _apply_eager_loading(
        self, 
        query, 
        relations: List[str] = None
    ):
        """
        Применяет eager loading к запросу.

        Параметры:
            query (Query): Запрос SQLAlchemy.
            relations (List[str], optional): Список имён отношений (если None – берёт из конфигурации).

        Возвращает:
            Query: Модифицированный запрос с добавленными `options`.

        Пример:
            query = self._apply_eager_loading(query)
        """
        if not relations:
            relations = self._get_relations_for_eager_loading()
        
        options = self._get_eager_loading_options(relations)

        if options:
            return query.options(*options)
        
        return query

    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_filtered(
        self, 
        filters: List[Dict[str, Any]], 
        fuzzy_threshold: int = 60,
        session: Optional[Session] = None
    ) -> List[DTOType]:
        """
        Возвращает записи, отфильтрованные по заданным условиям.

        **Важно:** этот метод автоматически подгружает все отношения, необходимые
        для виртуальных полей (через `_apply_eager_loading`). Это позволяет избежать
        N+1 запросов при обращении к виртуальным полям в DTO.

        Параметры:
            filters (List[Dict[str, Any]]): Список фильтров. Каждый фильтр – словарь с ключами:
                - column (str): имя столбца модели.
                - operator (str): оператор из FilterOperator (eq, ne, gt, ge, lt, le, like, ilike, in, between,
                is_null, is_not_null, fuzzy).
                - value (any): значение для сравнения.
            fuzzy_threshold (int): Порог схожести для нечёткого поиска (0-100). По умолчанию 60.
            session (Optional[Session]): Внешняя сессия, если требуется объединение транзакций.

        Возвращает:
            List[DTOType]: Отфильтрованный список DTO.

        Примечание:
            - SQL-операторы применяются на уровне БД.
            - Оператор 'fuzzy' выполняет поиск в памяти после загрузки всех записей,
            поэтому может быть медленным на больших объёмах данных.
        """


        # """
        # Возвращает записи, отфильтрованные по заданным условиям.
        # filters: список словарей с ключами column, operator, value.
        # fuzzy_threshold: порог схожести для нечеткого поиска.
        # """
        self.logger.debug(
            f"Запрос отфильтрованных записей {self._model_class.__name__} "
            f"с фильтрами {filters}"
        )

        with self._session_scope(session) as sess:

            query = sess.query(self._model_class)

            # Динамически подгружаем связи для виртуальных полей
            # relations = self._get_relations_for_eager_loading()
            query = self._apply_eager_loading(
                query, 
                # relations,
            )
            
            # apply_filters теперь возвращает кортеж
            # query, post_filters = apply_filters(
                # self._model_class, 
            query, post_filters = self._apply_filters_to_query(
                query, 
                filters, 
                fuzzy_threshold
            )
            
            items = query.all()
            if post_filters:
                items = apply_post_filters(
                    items, 
                    post_filters, 
                    self._model_class
                )

            items = self._post_process_items(items, sess)

            # dtos = [self._dto_class.from_orm(item) for item in items]
            dtos = self.get_dtos(items)
            # self.logger.debug(f"Получено {len(dtos)} записей после фильтрации")

            return dtos


    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @contextmanager
    def _session_scope(self, session: Optional[Session] = None):
        """
        Контекстный менеджер для работы с сессией.
        Если передана внешняя сессия, используем её (без commit/rollback).
        Иначе создаём новую через self._db.session_scope().
        """
        if session is not None:
            yield session

        else:
            with self._db.session_scope() as new_session:
                yield new_session


    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_page(
        self, offset: int, 
        limit: int,
        filters: Optional[List[Dict[str, Any]]] = None,
        order_by: Optional[List] = None,
        session: Optional[Session] = None,
        relations: Optional[List] = None,
    ) -> Tuple[List[DTOType], int]:
        """
        Возвращает страницу записей и общее количество (с учётом фильтров).

        Параметры:
            offset (int): Количество пропускаемых записей (смещение).
            limit (int): Размер страницы (максимум записей).
            filters (Optional[List[Dict[str, Any]]]): Фильтры (аналогично `get_filtered`).
            order_by (Optional[List]): Список полей для сортировки, например, ['date', '-time'].
            session (Optional[Session]): Внешняя сессия.

        Возвращает:
            Tuple[List[DTOType], int]:
                - Список DTO на текущей странице.
                - Общее количество записей, удовлетворяющих фильтрам.

        Пример:
            >>> page, total = service.get_page(offset=10, limit=25, order_by=['-date'])
            >>> print(f"Показаны записи 11-35 из {total}")
        """

        return self.get_page_filtered(offset, limit, filters, order_by, relations, session=session)
    
        # self.logger.debug(
        #     f"Запрос страницы {self._model_class.__name__}: "
        #     f"offset={offset}, "
        #     f"limit={limit}, "
        #     f"filters={filters}"
        # )

        # with self._session_scope(session) as sess:
        #     repo = self._get_repo(sess)

        #     items = repo.get_page(
        #         offset, 
        #         limit, 
        #         filters=filters,
        #         order_by=order_by,
        #         relations=relations,
        #     )
        #     total = repo.count(
        #         filters=filters
        #     )

        #     items = self._post_process_items(items, sess) 

        #     # dtos = [self._dto_class.from_orm(item) for item in items]
        #     dtos = self.get_dtos(items)

        #     return dtos, total
        
    @AppLogger.get_instance(
        name = 'BaseService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_unique_values(
        self,
        column_name: str,
        session: Optional[Session] = None
    ) -> List[Any]:
        """
        Возвращает список уникальных значений для указанного столбца.

        Параметры:
            column_name (str): Имя столбца модели (атрибут ORM) (например, 'last_name').
            session (Optional[Session]): Внешняя сессия.

        Возвращает:
            List[Any]: Список уникальных значений (тип зависит от столбца).

        Пример:
            >>> unique_last_names = service.get_unique_values('last_name')
            >>> # ['Петров', 'Иванов', ...]
        """

        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)

            return repo.get_unique_values(column_name)
        
    # в конце класса BaseService, после метода get_unique_values (или перед _session_scope)

    @AppLogger.get_instance(
        name='BaseService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def reload_config(self) -> None:
        """
        Перезагружает конфигурацию сервиса: закрывает старый Database и создаёт новый.

        Вызывается автоматически при изменении настроек (через AppConfigManager.add_change_listener).
        Также может вызываться вручную после ручного обновления конфигурации.

        Примечание:
            Наследники, имеющие зависимости от других сервисов, должны переопределить этот метод
            и перезагрузить те зависимости (например, через `get_xxx_service()`).

        Пример (PatientService):
            def reload_config(self):
                super().reload_config()
                from app.dependencies import get_appointment_service
                self._appointment_service = get_appointment_service()
        """

        from app.dependencies import get_db # оставить тут, так как цикл
        self._db.close()
        self._db = get_db()

        self.logger.info("Конфигурация сервиса перезагружена")        


class PatientService(
    BaseService[
        Patient, 
        PatientDTO, 
        PatientRepository
    ]
):
    """
    Сервис для управления пациентами.

    Особенности:
        - Имеет заметки `description_text` и `comment_text` (поля `is_note`).
        - Для каскадного удаления использует `AppointmentService` (удаляет все приёмы пациента перед удалением самого пациента).
        - Переопределяет `_get_note_service`, возвращая внутренний `_note_service`.
        - Не требует переопределения `get_filtered`, `get_by_id`, `get_all` – они работают через базовый класс.

    Атрибуты (дополнительные):
        _note_service (NoteService): Сервис для работы с заметками.
        _appointment_service (AppointmentService): Сервис приёмов (для удаления).

    Пример:
        service = PatientService(db, field_configs=PATIENT_CONFIG, appointment_service=get_appointment_service())
        patient = service.create_patient(patient_dto)
    """

    @AppLogger.get_instance(
        name = 'PatientService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(        
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self,
        db: Database,
        field_configs: Optional[Dict[str, Dict[str, Any]]] = None,
        logger_name: Optional[str] = None,
        appointment_service: Optional['AppointmentService'] = None, 
    ):
        """
        Инициализирует экземпляр сервиса.

        Parameters:
            db (Database): экземпляр Database для получения сессий.
            logger_name (str, optional): имя логгера. По умолчанию будет использовано имя класса сервиса.
            

        Attributes:
            logger (AppLogger): логгер для записи событий.
        """
        if logger_name is None:
            logger_name = self.__class__.__name__

        # Вызов конструктора базового класса с указанием классов модели, DTO и репозитория
        super().__init__(
            db          = db,
            repo_class  = PatientRepository,
            model_class = Patient,
            dto_class   = PatientDTO,
            field_configs=field_configs,
            logger_name = logger_name,
        )

        self._note_service = NoteService(db, logger_name=logger_name + ".NoteService")
        self._appointment_service = appointment_service   # сохраняем

    # @AppLogger.get_instance(
    #     name = 'PatientService',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # ) 
    # def get_filtered(self, filters, fuzzy_threshold=60, session=None):
    #     with self._session_scope(session) as sess:
    #         # query = sess.query(Patient)
    #         query = sess.query(self._model_class)
    #         relations = self._get_relations_for_eager_loading()

    #         if relations:
    #             query = query.options(*[joinedload(getattr(Patient, rel)) for rel in relations])

    #         query, post_filters = apply_filters(query, Patient, filters, fuzzy_threshold)
    #         items = query.all()

    #         if post_filters:
    #             items = apply_post_filters(items, post_filters, Patient)

    #         return self.get_dtos(items)

    # @AppLogger.get_instance(
    #     name = 'PatientService',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # ) 
    # def get_by_id(self, entity_id: int, session=None) -> PatientDTO:
    #     with self._session_scope(session) as sess:
    #         repo = self._get_repo(sess)
    #         relations = self._get_relations_for_eager_loading()
    #         entity = repo.get_with_relations(entity_id, relations)
    #         if entity is None:
    #             raise self._not_found_exception(entity_id)
    #         return self.get_dtos(entity)

    @AppLogger.get_instance(
        name = 'PatientService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    ) 
    def _get_note_service(self) -> 'NoteService':
        """
        Должен быть переопределён в наследниках, возвращает экземпляр NoteService.

        Используется в `_delete_entity` и `_apply_note_updates` для очистки неиспользуемых заметок.
        Если у сервиса нет полей-заметок, можно вернуть None (но тогда очистка не будет выполняться).

        Raises:
            NotImplementedError: Базовый метод по умолчанию выбрасывает исключение.
        """

        return self._note_service

    # Переопределяем create, так как логика создания специфична
    @AppLogger.get_instance(
        name = 'PatientService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )   
    def create_patient(
        self, 
        patient_dto: PatientDTO, 
        session: Optional[Session] = None
    ) -> PatientDTO:
        """
        Создаёт нового пациента (обёртка над `create` с дополнительной валидацией).

        Параметры:
            patient_dto (PatientDTO): DTO с данными пациента (без id).
            session (Optional[Session]): Внешняя сессия.

        Возвращает:
            PatientDTO: Созданный пациент с заполненным id.

        Исключения:
            PatientValidationError: Если отсутствуют обязательные поля (first_name, last_name).

        Пример:
            >>> new_patient = PatientDTO(first_name="Анна", last_name="Смирнова")
            >>> created = service.create_patient(new_patient)
            >>> print(created.id)
        """

        self.logger.debug(
            f"patient_dto "
            f"{patient_dto} "
            f"session {session} "
            f"result {session}"
        )

        # if not patient_dto.first_name or not patient_dto.last_name:
        #     self.logger.warning("Попытка создания пациента без имени/фамилии")
        #     raise PatientValidationError("first_name/last_name", "Имя и фамилия обязательны")

        # self.logger.debug(
        #     f"Создание пациента: {patient_dto}"
        # )
        # required = {
        #     'first_name': patient_dto.first_name,
        #     'middle_name': patient_dto.middle_name,
        #     'last_name': patient_dto.last_name,
        #     'birth_date': patient_dto.birth_date,
        #     'phone': patient_dto.phone,
        # }
        return self._create_entity(
            patient_dto, 
            # required, 
            session
        )

        # with self._session_scope(session) as sess:
        #     # Репозиторий для заметок
        #     note_repo = AppointmentNoteRepository(sess)   # создаём репозиторий

        #     # # Создаём заметки для description и comment, если они не пустые
        #     # description_note = None
        #     # if patient_dto.description:
        #     #     description_note = AppointmentNote(text=patient_dto.description)
        #     #     note_repo.add(description_note) 

        #     # comment_note = None
        #     # if patient_dto.comment:
        #     #     comment_note = AppointmentNote(text=patient_dto.comment)
        #     #     note_repo.add(comment_note) 
            
        #     new_ids = self._apply_note_updates(
        #         patient_dto, 
        #         sess, 
        #         note_repo, 
        #         model_obj=None
        #     )
           
        #     # sess.flush()  # чтобы получить id заметок   

        #     # Создаём ORM-объект
        #     patient = self._model_class(
        #         first_name=patient_dto.first_name,
        #         middle_name=patient_dto.middle_name,
        #         last_name=patient_dto.last_name,
        #         birth_date=patient_dto.birth_date,
        #         phone=patient_dto.phone,
        #         **new_ids,
        #         # description_id=description_note.id if description_note else None,
        #         # comment_id=comment_note.id if comment_note else None,
        #     )

        #     # Используем репозиторий для добавления пациента
        #     repo = self._get_repo(sess)
        #     repo.add(patient)
        #     sess.flush() # Чтобы получить id, делаем flush (коммит будет в session_scope)

        #     # dto_out = self._dto_class.from_orm(patient)
        #     # dto_out = self._dto_class.model_validate(patient)
        #     dto_out = self.get_dto_out(patient)

        #     self.logger.info(f"Создан пациент с id={dto_out.id}")
        #     self.logger.debug(f"dto_out {dto_out}")

        #     return dto_out
           
    @AppLogger.get_instance(
        name = 'PatientService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )  
    def update_patient(
        self, 
        patient_dto: PatientDTO, 
        session: Optional[Session] = None
    ) -> PatientDTO:
        """
        Обновляет существующего пациента, а также связанные заметки description/comment.
        Использует get_with_relations для подгрузки связей перед обновлением.

        Args:
            patient_dto (PatientDTO): DTO с заполненным id и изменяемыми полями.
            session (Optional[Session]): сессия БД, которая будет использоваться для работы с репозиторием.

        Returns:
            PatientDTO: обновленный объект PatientDTO.

        Raises:
            PatientValidationError: если id не указан.
            PatientNotFoundError: если пациент с указанным id не найден.
        """

        self.logger.debug(
            f"patient_dto {patient_dto} "
            f"session {session} "
            f"result {session}"
        )

        if patient_dto.id is None:
            self.logger.warning("Попытка обновления пациента без id")
            raise PatientValidationError("id", "ID пациента обязателен для обновления")

        self.logger.debug(
            f"Обновление пациента id={patient_dto.id} "
            f"данные: last_name={patient_dto.last_name} "

        )
        return self._update_entity(patient_dto, patient_dto.id, session)

        # with self._session_scope(session) as sess:
        #     # ВАЖНО: используем get_with_relations, чтобы подгрузить description_note и comment_note
        #     # У PatientRepository уже есть метод get_with_relations, унаследованный от BaseRepository

        #     repo = self._get_repo(sess)
        #     # patient = repo.get_by_id(patient_dto.id)
        #     # patient = repo.get_with_relations(
        #     #     patient_dto.id, 
        #     #     ['description_note', 'comment_note']
        #     # )

        #     relations = self._get_relations_for_eager_loading()
        #     patient = repo.get_with_relations(patient_dto.id, relations)

        #     if patient is None:
        #         raise PatientNotFoundError(patient_dto.id)

        #     note_repo = AppointmentNoteRepository(sess) 
        #     # note_service = NoteService(
        #     #     self._db, 
        #     #     logger_name=self.logger.name + ".NoteService"
        #     # )

        #     # # Сохраняем старые ID заметок до изменения
        #     # old_description_id = patient.description_id
        #     # old_comment_id = patient.comment_id

        #     # # Обновляем поля
        #     # patient.first_name = patient_dto.first_name
        #     # patient.middle_name = patient_dto.middle_name
        #     # patient.last_name = patient_dto.last_name
        #     # patient.birth_date = patient_dto.birth_date
        #     # patient.phone = patient_dto.phone
            
        #     # # Обработка заметки description
        #     # if patient_dto.description is not None:
        #     #     if patient.description_id:
        #     #         note = note_repo.get_by_id(patient.description_id)  
        #     #         if note:
        #     #             note.text = patient_dto.description
        #     #             # ID не меняется
        #     #     else:
        #     #         new_note = AppointmentNote(text=patient_dto.description)
        #     #         note_repo.add(new_note)
        #     #         sess.flush()
        #     #         patient.description_id = new_note.id
        #     #         # Старая заметка (old_description_id) будет удалена позже, если она не используется

        #     # # Аналогично для comment
        #     # if patient_dto.comment is not None:
        #     #     if patient.comment_id:
        #     #         note = note_repo.get_by_id(patient.comment_id)
        #     #         if note:
        #     #             note.text = patient_dto.comment
        #     #             # ID не меняется
        #     #     else:
        #     #         new_note = AppointmentNote(text=patient_dto.comment)
        #     #         note_repo.add(new_note)
        #     #         sess.flush()
        #     #         patient.comment_id = new_note.id
        #     #         # Старая заметка (old_comment_id) будет удалена позже, если она не используется

        #     # # === Очистка старых заметок, которые больше не используются ===
        #     # # Если description_id изменился (был и стал другим) – удаляем старую заметку
        #     # if old_description_id is not None and old_description_id != patient.description_id:
        #     #     note_service.cleanup_unused_note(old_description_id, sess)

        #     # if old_comment_id is not None and old_comment_id != patient.comment_id:
        #     #     note_service.cleanup_unused_note(old_comment_id, sess)

        #     # # commit произойдёт автоматически при выходе из session_scope
        #     # # updated_dto = self._dto_class.from_orm(patient)
        #     # # sess.commit()  # Явный коммит

        #     # Применяем изменения заметок через общий метод
        #     new_ids = self._apply_note_updates(
        #         dto=patient_dto,
        #         session=sess,
        #         note_repo=note_repo,
        #         model_obj=patient
        #     )

        #     # Обновляем поля пациента
        #     for orm_field, value in new_ids.items():
        #         setattr(patient, orm_field, value)

        #     # Обновляем простые поля (имя, дата, телефон)
        #     # patient.first_name = patient_dto.first_name
        #     # patient.middle_name = patient_dto.middle_name
        #     # patient.last_name = patient_dto.last_name
        #     # patient.birth_date = patient_dto.birth_date
        #     # patient.phone = patient_dto.phone
        #     self._apply_simple_updates(patient, patient_dto)  # динамическое обновление простых полей

        #     # # Очистка старых заметок
        #     # for orm_field, old_id in old_ids.items():
        #     #     new_id = new_ids.get(orm_field)
        #     #     if old_id is not None and old_id != new_id:
        #     #         self._note_service.cleanup_unused_note(old_id, sess)

        #     updated_dto = self.get_dto_out(patient)

        #     self.logger.info(f"Обновлён пациент id={updated_dto.id}")
        #     self.logger.debug(f"updated_dto {updated_dto}") 

        #     return updated_dto  
        
    @AppLogger.get_instance(
        name = 'PatientService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    # Переопределяем метод для генерации исключения "не найдено"
    def _not_found_exception(self, entity_id: int) -> Exception:
        """
        Генерирует исключение PatientNotFoundError, если пациент с указанным идентификатором не найден в базе данных.
        
        :param entity_id: идентификатор пациента
        :type entity_id: int
        :return: исключение PatientNotFoundError
        :rtype: PatientNotFoundError
        """
        self.logger.error(f"Пациент с идентификатором {entity_id} не найден.'")

        return PatientNotFoundError(entity_id) # Выбрасывается, когда пациент с указанным идентификатором не найден в базе данных.

    # @AppLogger.get_instance(
    #     name = 'PatientService',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )  
    # def get_all(self, session: Optional[Session] = None) -> List[PatientDTO]:
    #     """Возвращает всех пациентов с подгруженными связями (description_note, comment_note)."""
    #     with self._session_scope(session) as sess:
    #         repo = self._get_repo(sess)
    #         relations = self._get_eager_loading_options()
    #         items = repo.get_all_with_relations(relations)
    #         return self.get_dtos(items)

    @AppLogger.get_instance(
        name = 'PatientService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    # Для совместимости с существующим кодом оставляем методы-обёртки,
    # которые вызывают методы базового класса
    def get_all_patients(self, session: Optional[Session] = None) -> List[PatientDTO]:
        """
        Возвращает список всех пациентов в базе данных.
        
        :param session: сессия для работы в одной транзакции
        :type session: Optional[Session]
        :return: список всех пациентов
        :rtype: List[PatientDTO]
        """
        self.logger.debug("Запрос всех пациентов")

        return self.get_all(
            session=session
        )

    @AppLogger.get_instance(
        name = 'PatientService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def get_patient_by_id(self, patient_id: int, session: Optional[Session] = None) -> PatientDTO:
        """
        Возвращает пациента по его идентификатору.

        Args:
            patient_id (int): Идентификатор пациента.
            session (Optional[Session]): Сессия БД. Если не указана, то будет создана новая сессия.

        Returns:
            PatientDTO: DTO пациента.

        Raises:
            PatientNotFoundError: Если пациент с указанным идентификатором не найден в базе данных.
        """

        self.logger.debug(f"Запрос пациента по id={patient_id}")

        return self.get_by_id(patient_id, session=session)

    @AppLogger.get_instance(
        name = 'PatientService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def delete_patient(self, patient_id: int, session: Optional[Session] = None) -> None:
        """
        Удаляет пациента и все связанные приёмы (каскадно). Удаляет неиспользуемые заметки.

        Параметры:
            patient_id (int): ID пациента.
            session (Optional[Session]): Внешняя сессия.

        Исключения:
            PatientNotFoundError: Если пациент не найден.
        """

        # Проверяем, что AppointmentService передан
        if self._appointment_service is None:
            raise RuntimeError("AppointmentService не передан")

        self.logger.debug(f"Удаление пациента id={patient_id}")
        
        with self._session_scope(session) as sess:
            # Получаем пациента со связанными приёмами (чтобы собрать ID заметок)
            # patient = session.get(Patient, patient_id)
            patient = sess.query(
                Patient
            ).options(
                selectinload(Patient.appointments)
            ).filter(
                Patient.id == patient_id
            ).first()

            if patient is None:
                raise PatientNotFoundError(patient_id)

            # # Проверяем, что AppointmentService передан
            # if self._appointment_service is None:
            #     raise RuntimeError("AppointmentService не передан в PatientService")
        
            # # Собираем ID заметок, привязанных к приёмам этого пациента
            # note_ids = [app.note_id for app in patient.appointments if app.note_id]

            # if patient.description_id:
            #     note_ids.append(patient.description_id)

            # if patient.comment_id:
            #     note_ids.append(patient.comment_id)

            # Собираем ID заметок
            # note_ids = set()
            # # Заметки из приёмов
            # for app in patient.appointments:
            #     for mapping in self._get_note_field_mappings():
            #         note_id = getattr(app, mapping['orm_id_field'])
            #         if note_id:
            #             note_ids.add(note_id)
            # from app.dependencies import get_appointment_service  # импорт внутри метода так как циклы
            # appointment_service = get_appointment_service()
            # Удаляем все приёмы пациента через AppointmentService (каскадное удаление фото и заметок)
            # for appointment in patient.appointments[:]:  # копия списка, т.к. он будет меняться
            #     try:
            #         self._appointment_service.delete_appointment(appointment.id, session=sess)
            #     except Exception as e:
            #         self.logger.exception(f"Ошибка удаления приёма {appointment.id}: {e}")
            #         raise


            # # Собираем ID заметок самого пациента (поля-заметки, помеченные is_note)
            # note_ids = set()
            # for mapping in self._get_note_field_mappings():
            #     note_id = getattr(patient, mapping['orm_id_field'])
            #     if note_id:
            #         note_ids.add(note_id)

            # # Удаляем пациента — каскадно удалятся все его приёмы и фото
            # sess.delete(patient)
            # sess.flush() # принудительно выполняем удаление, чтобы обновить состояние БД

            # Удаляем все приёмы через сервис
            for app in patient.appointments[:]:
                try:
                    self._appointment_service.delete_appointment(app.id, session=sess)
                except Exception as e:
                    self.logger.exception(f"Ошибка удаления приёма {app.id}: {e}")
                    raise e

            # Теперь удаляем самого пациента (базовый метод удалит его заметки)
            self._delete_entity(patient_id, session=sess)


            # Проверяем каждую заметку: остались ли ещё приёмы, ссылающиеся на неё           
            # note_service = NoteService(
            #     self._db, 
            #     logger_name=self.logger.name + ".NoteService"
            # )

            # # Очищаем неиспользуемые заметки
            # for note_id in note_ids:
            #     # note_service.cleanup_unused_note(note_id, sess)
            #     self._note_service.cleanup_unused_note(note_id, sess)

            self.logger.info(f"Удалён пациент id={patient_id}")
   
    @AppLogger.get_instance(
        name = 'PatientService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def get_patients_filtered(
        self, 
        filters: List[Dict[str, Any]], 
        fuzzy_threshold: int = 60,
        session: Optional[Session] = None
    ) -> List[PatientDTO]:
        """
        Возвращает список пациентов с возможностью фильтрации.

        filters - список словарей, каждый из которых содержит информацию о фильтре:
            - column: имя столбца (строка)
            - operator: оператор из FilterOperator
            - value: значение для сравнения (зависит от оператора)
        fuzzy_threshold - порог схожести для нечеткого поиска (0-100)

        Функция работает следующим образом:
        1. Создаем список словарей filters, где каждый словарь содержит информацию о фильтре:
            - column: имя столбца (строка)
            - operator: оператор из FilterOperator
            - value: значение для сравнения (зависит от оператора)
        2. Создаем экземпляр PatientService
        3. Вызываем метод get_patients_filtered у PatientService, передавая туда полученный список фильтров и порог схожести
        4. Выводим список пациентов, если он не пустой
        """

        self.logger.debug(
            f"Запрос пациентов с фильтрацией: "
            f"filters={filters}, "
            f"fuzzy_threshold={fuzzy_threshold}"
        )

        return self.get_filtered(filters, fuzzy_threshold, session=session)
   
   # Для совместимости с DynamicEditPage
    @AppLogger.get_instance(
        name = 'PatientService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def create(
        self, 
        dto: PatientDTO, 
        session: Optional[Session] = None,
    ) -> PatientDTO:
        """
        Универсальный метод создания, вызывающий create_patient.
        Необходим для совместимости с DynamicEditPage.
        :param dto: DTO, содержащий информацию о создаваемом пациенте
        :type dto: PatientDTO
        :return: DTO, содержащий информацию о созданном пациенте
        :rtype: PatientDTO
        """
        return self.create_patient(
            dto,
            session=session,
        )

    @AppLogger.get_instance(
        name = 'PatientService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def update(
        self, 
        dto: PatientDTO, 
        session: Optional[Session] = None, 
    ) -> PatientDTO:
        """
        Универсальный метод обновления, вызывающий update_patient.
        Возвращает обновленный объект PatientDTO.
        """

        return self.update_patient(
            dto,
            session=session,
        )

    def reload_config(self) -> None:
        super().reload_config()

        # from app.dependencies import clear_services_cache # оставить тут, так как циклы
        # # Очищаем кэш, чтобы при следующем вызове get_appointment_service() создался новый экземпляр
        # clear_services_cache()
        from app.dependencies import get_appointment_service # оставить тут, так как циклы
        self._appointment_service = get_appointment_service()
        self.logger.info("PatientService: appointment_service перезагружен")

class NoteService(
    BaseService[
        AppointmentNote, 
        AppointmentNoteDTO, 
        AppointmentNoteRepository,
    ]
):
    """
    Сервис для работы с заметками приёмов.

    Особенности:
        - Используется всеми сервисами через `_apply_note_updates`.
        - Реализует метод `cleanup_unused_note`, который удаляет заметку, если она больше не используется
          ни в одной из зарегистрированных моделей (через `_NOTE_USAGE_MODELS`).
        - Переопределяет `_get_note_service`, возвращая None (у заметок нет своих заметок).

    Примечание:
        Не создавайте заметки напрямую через этот сервис, если они должны быть привязаны к другой сущности.
        Вместо этого используйте методы родительского сервиса (`PatientService`, `AppointmentService`),
        которые автоматически обработают заметки через `_apply_note_updates`.акцию.


    **Важно:** Не вызывайте методы `create`/`update` напрямую для заметок,
    которые должны быть привязаны к другой сущности (пациенту или приёму).
    Вместо этого используйте родительские сервисы (`PatientService`, `AppointmentService`),
    которые автоматически создадут/обновят заметки через `_apply_note_updates`.
    
    Прямое использование `NoteService` допустимо только для:
        - получения списка всех заметок (`get_all`),
        - поиска по тексту (`get_or_create_note`),
        - ручного удаления сирот (обычно не требуется).
    """

    @AppLogger.get_instance(
        name = 'NoteService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def __init__(
        self, 
        db: Database, 
        field_configs: Optional[Dict[str, Dict[str, Any]]] = None,
        logger_name: Optional[str] = None,
    ):
        """
        Инициализирует сервис для работы с заметками приёмов.
        
        :param db: База данных
        :type db: Database
        :param logger_name: Имя для логгера (необязательный)
        :type logger_name: Optional[str]
        """
        if logger_name is None:
            logger_name = self.__class__.__name__

        super().__init__(
            db=db,
            repo_class=AppointmentNoteRepository,
            model_class=AppointmentNote,
            dto_class=AppointmentNoteDTO,
            field_configs=field_configs,
            logger_name=logger_name
        )

    @AppLogger.get_instance(
        name = 'NoteService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def _not_found_exception(self, entity_id: int) -> Exception:
        """
        Возвращает исключение, если заметка с указанным ID не найдена.
        
        :param entity_id: ID заметки
        :return: исключение, если заметка не найдена
        :rtype: Exception
        """
        return AppointmentNoteNotFoundError(entity_id)

    # ----------------------------------------------------------------------
    # Переопределённые методы базового класса (если нужно добавить логику)
    # ----------------------------------------------------------------------

    # @AppLogger.get_instance(
    #     name = 'NoteService',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )  
    # def get_all(self, session: Optional[Session] = None) -> List[AppointmentNoteDTO]:
    #     """
    #     Возвращает список всех заметок.

    #     :param session: сессия для объединения в одну транзакцию
    #     :type session: Optional[Session]
    #     :return: список заметок в виде объектов AppointmentNoteDTO
    #     :rtype: List[AppointmentNoteDTO]
    #     """
    #     self.logger.debug("Запрос всех заметок")

    #     return super().get_all(session=session)

    @AppLogger.get_instance(
        name = 'NoteService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def get_by_id(self, note_id: int, session: Optional[Session] = None) -> AppointmentNoteDTO:
        """
        Возвращает заметку по ID.

        :param note_id: ID заметки
        :type note_id: int
        :param session: Сессия базы данных
        :type session: Optional[Session]
        :return: DTO заметки
        :rtype: AppointmentNoteDTO
        """
        self.logger.debug(f"Запрос заметки id={note_id}")

        return super().get_by_id(note_id, session=session)

    @AppLogger.get_instance(
        name = 'NoteService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def delete(self, note_id: int, session: Optional[Session] = None) -> None:
        """
        Удаляет заметку по ID.
        
        :param note_id: ID заметки
        :type note_id: int
        :param session: сессия для объединения в одну транзакцию
        :type session: Optional[Session]
        """
        self.logger.debug(f"Удаление заметки id={note_id}")

        # super().delete(note_id, session=session)
        self._delete_entity(note_id, session) # чтобы соответствовать единому универсальному подходу

    @AppLogger.get_instance(
        name = 'NoteService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def create(
        self, 
        dto: AppointmentNoteDTO,
        session: Optional[Session] = None,    
    ) -> AppointmentNoteDTO:
        """
        Создает заметку.
        
        :param dto: данные заметки
        :type dto: AppointmentNoteDTO
        :return: созданная заметка
        :rtype: AppointmentNoteDTO
        """
        # return self.create_note(dto.text)
        return self._create_entity(
            dto,
            session=session,
        )
    
    @AppLogger.get_instance(
        name = 'NoteService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def update(
        self, 
        dto: AppointmentNoteDTO,
        session: Optional[Session] = None,
    ) -> AppointmentNoteDTO:
        """
        Обновляет заметку по ID.
        
        :param dto: данные заметки
        :type dto: AppointmentNoteDTO
        :return: обновленная заметка
        :rtype: AppointmentNoteDTO
        """
        # return self.update_note(dto.id, dto.text)
        if dto.id is None:
            raise ValueError("ID заметки не указан")
        
        return self._update_entity(
            dto,
            dto.id, 
            session=session,
        )
    
    # ----------------------------------------------------------------------
    # Специфические методы сервиса
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'NoteService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def get_note(self, note_id: int, session: Optional[Session] = None) -> AppointmentNoteDTO:
        """
        Синоним для get_by_id.
        
        :param note_id: ID заметки
        :type note_id: int
        :param session: сессия для объединения в одну транзакцию
        :type session: Optional[Session]
        :return: заметка с указанным ID
        :rtype: AppointmentNoteDTO
        """
        return self.get_by_id(note_id, session=session)

    @AppLogger.get_instance(
        name = 'NoteService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def create_note(
        self, 
        text: str, 
        session: Optional[Session] = None
    ) -> AppointmentNoteDTO:
        """
        Создаёт новую заметку с указанным текстом.

        :param text: текст заметки
        :type text: str
        :param session: сессия для работы в одной транзакции
        :type session: Optional[Session]
        :return: созданная заметка
        :rtype: AppointmentNoteDTO
        """
        self.logger.debug("Создание заметки")

        # with self._session_scope(session) as sess:
        #     note = self._model_class(text=text)

        #     sess.add(note)
        #     sess.flush()

        #     # dto_out = self._dto_class.from_orm(note)
        #     dto_out = self.get_dto_out(note)

        #     self.logger.info(f"Создана заметка id={dto_out.id}")

        #     return dto_out
        
        # dto = AppointmentNoteDTO(text=text)
        # return self.create(dto, session)
        return self.create(
            AppointmentNoteDTO(text=text), 
            session
        )

    @AppLogger.get_instance(
        name = 'NoteService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )  
    def update_note(
        self, 
        note_id: int, 
        text: str, 
        session: Optional[Session] = None
    ) -> AppointmentNoteDTO:
        """
        Обновляет текст существующей заметки.

        Args:
            note_id: int - ID заметки, которую нужно обновить.
            text: str - новый текст заметки.
            session: Optional[Session] - сессия БД, которая будет использоваться для работы с репозиторием.

        Returns:
            AppointmentNoteDTO: обновленный объект AppointmentNoteDTO.

        Raises:
            AppointmentNoteNotFoundError: если заметка с указанным ID не найдена.
        """

        # Логгируем начало обновления заметки
        self.logger.debug(f"Обновление заметки id={note_id}")
        dto = AppointmentNoteDTO(id=note_id, text=text)
        return self.update(dto, session)
        # # Создаем сессию для работы с репозиторием
        # with self._session_scope(session) as sess:
            
        #     # Получаем репозиторий для работы с заметками
        #     repo = self._get_repo(sess)
            
        #     # Получаем заметку по ID
        #     note = repo.get_by_id(note_id)
            
        #     # Если заметка не найдена, выбрасываем исключение
        #     if note is None:
        #         err_ = AppointmentNoteNotFoundError(note_id)
        #         self.logger.exception(err_.message)
        #         raise err_
            
        #     # Обновляем текст заметки
        #     note.text = text
            
        #     # Получаем обновленный DTO из обновленной заметки
        #     # updated_dto = self._dto_class.from_orm(note)
        #     updated_dto = self.get_dto_out(note)
            
        #     # Логгируем обновленной заметки
        #     self.logger.info(f"Обновлена заметка id={updated_dto.id}")

        #     # Возвращаем обновленный DTO
        #     return updated_dto

    @AppLogger.get_instance(
        name = 'NoteService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def delete_note(self, note_id: int, session: Optional[Session] = None) -> None:
        """
        Удаляет заметку (синоним delete).
        :param note_id: ID заметки
        :type note_id: int
        :param session: сессия для объединения в одну транзакцию
        :type session: Optional[Session]
        """
        
        self.logger.debug(f"Удаляет запись по ID ({note_id})")

        # self.delete(note_id, session=session)
        self.delete(note_id, session)

    @AppLogger.get_instance(
        name = 'NoteService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def get_or_create_note(self, text: str, session: Optional[Session] = None) -> Optional[AppointmentNoteDTO]:
        """
        Возвращает существующую заметку по точному совпадению текста,
        либо создаёт новую, если такой ещё нет.
        Если text пустой или None, возвращает None.
        
        :param text: текст заметки
        :type text: str
        :param session: сессия БД, которая будет использоваться для работы с репозиторием
        :type session: Optional[Session]
        :return: существующая или созданная заметка
        :rtype: Optional[AppointmentNoteDTO]
        """
        if not text:
            return None

        self.logger.debug(f"Поиск или создание заметки: {text[:50]}...")
        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)
            note = repo.get_by_text_exact(text)
            if note:
                self.logger.debug(f"Найдена существующая заметка id={note.id}")
                # return self._dto_class.from_orm(note)
                return self.get_dto_out(note)

            # Создаём новую заметку
            note = self._model_class(text=text)

            sess.add(note)
            sess.flush()

            self.logger.info(f"Создана новая заметка id={note.id}")

            # return self._dto_class.from_orm(note)
            return self.get_dto_out(note)

    @AppLogger.get_instance(
        name = 'NoteService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def create_note_from_file(self, file_path: str, session: Optional[Session] = None) -> AppointmentNoteDTO:
        """
        Создаёт заметку, читая текст из файла.

        :raises FileNotFoundError, IOError: если файл не найден или ошибка чтения
        :param file_path: путь к файлу, из которого нужно прочитать текст для заметки
        :type file_path: str
        :param session: опциональная сессия для работы в одной транзакции
        :type session: Optional[Session]
        :return: созданная заметка
        :rtype: AppointmentNoteDTO
        """
        self.logger.debug(f"Создание заметки из файла: {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()

        except Exception as e:
            self.logger.exception(f"Ошибка чтения файла {file_path}: {e}")
            raise  # пробрасываем дальше

        return self.create_note(text, session=session)      

    @AppLogger.get_instance(
        name = 'NoteService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    ) 
    def cleanup_unused_note(self, note_id: int, session: Optional[Session] = None) -> None:
        if note_id is None:
            return
        from app.dependencies import _NOTE_USAGE_MODELS # так как циклы
        # from sqlalchemy import or_

        with self._session_scope(session) as sess:
            total_usage = 0
            for model_class, fields in _NOTE_USAGE_MODELS:
                conditions = [getattr(model_class, field) == note_id for field in fields]
                if conditions:
                    cnt = sess.query(model_class).filter(or_(*conditions)).count()
                    total_usage += cnt
                    if total_usage > 0:
                        break   # можно прервать, если уже есть использование

            if total_usage == 0:
                note_repo = self._get_repo(sess)
                note = note_repo.get_by_id(note_id)
                if note:
                    sess.delete(note)
                    self.logger.info(f"Заметка {note_id} удалена как неиспользуемая") 

    # def cleanup_unused_note(self, note_id: int, session: Optional[Session] = None) -> None:
    #     """
    #     Удаляет заметку, если на неё больше нет ссылок ни из patients, ни из appointments.
    #     Если заметка используется, ничего не делает.
        
    #     :param note_id: ID заметки, которую нужно проверить на использование
    #     :type note_id: int
    #     :param session: сессия для работы в одной транзакции
    #     :type session: Session
    #     """
        
    #     if note_id is None:
    #         return
        
    #     with self._session_scope(session) as sess:

    #         # Проверяем patients
    #         patient_usage = sess.query(Patient).filter(
    #             (Patient.description_id == note_id) | (Patient.comment_id == note_id)
    #         ).count()

    #         # Проверяем appointments
    #         appointment_usage = sess.query(Appointment).filter(
    #             (Appointment.reason_id == note_id) |
    #             (Appointment.procedure_id == note_id) |
    #             (Appointment.recommendations_id == note_id) |
    #             (Appointment.note_id == note_id) |
    #             (Appointment.cost_procedure_id == note_id)
    #         ).count()

    #         if patient_usage == 0 and appointment_usage == 0:
    #             note_repo = AppointmentNoteRepository(sess)
    #             note = note_repo.get_by_id(note_id)
    #             if note:
    #                 sess.delete(note)
    #                 self.logger.info(f"Заметка {note_id} удалена как неиспользуемая")

    #     # # Проверяем, остались ли приёмы с этой заметкой
    #     # remaining = session.query(Appointment).filter(Appointment.note_id == note_id).count()
    #     # if remaining == 0:
    #     #     note_repo = AppointmentNoteRepository(session)
    #     #     note = note_repo.get_by_id(note_id)
    #     #     if note:
    #     #         note_repo.delete(note)
    #     #         self.logger.info(f"Заметка id={note_id} удалена как неиспользуемая")   

    @AppLogger.get_instance(
        name = 'NoteService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def get_choices(self, session: Optional[Session] = None) -> List[str]:
        """
        Возвращает список текстов всех заметок для автодополнения.
        :param session: сессия для работы в одной транзакции
        :type session: Optional[Session]
        :return: список текстов заметок
        :rtype: List[str]
        """
        notes = self.get_all(session=session)

        return [note.text for note in notes]

    @AppLogger.get_instance(
        name = 'NoteService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def _get_note_service(self) -> Optional['NoteService']:
        return None

    @AppLogger.get_instance(
        name='NoteService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def reload_config(self) -> None:
        """
        Перезагружает конфигурацию сервиса заметок.
        Вызывает базовый метод, который пересоздаёт Database.
        """
        super().reload_config()
        self.logger.info("NoteService: конфигурация перезагружена")

    # спец метод для виртуальных полей  

    @AppLogger.get_instance(
        name='NoteService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def get_unique_note_texts(self, session: Optional[Session] = None) -> List[str]:
        """
        Возвращает все уникальные тексты заметок из таблицы AppointmentNote.

        Примечание: 
            Для виртуальных полей-заметок (reason_text, procedure_text и т.д.)
            этот метод возвращает все существующие тексты, а не только относящиеся
            к конкретному полю. Это допустимо для автодополнения, так как
            пользователь может использовать любой текст, а сервис при сохранении
            либо создаст новую заметку, либо найдёт существующую по точному
            совпадению текста (см. get_or_create_note).
        """
        with self._session_scope(session) as sess:
            # Получаем все уникальные тексты заметок
            distinct_texts = sess.query(self._model_class.text).distinct().all()
            
            return [t[0] for t in distinct_texts if t[0]]

class AppointmentService(
        BaseService[
            Appointment, 
            AppointmentDTO, 
            AppointmentRepository,
        ]
    ):
    """
    Сервис для работы с приёмами.

    Особенности:
        - Имеет несколько полей-заметок (reason_text, procedure_text, ...).
        - Для отображения количества фото используется виртуальное поле `has_photos`,
          которое вычисляется через отдельный запрос (`_add_photo_counts`).
        - Переопределяет `_post_process_items` для добавления атрибута `_photo_count`.
        - Переопределяет `_get_child_service`, чтобы предоставить доступ к `PhotoService`.
        - Заметки обрабатываются автоматически через `BaseService`.

    Дополнительные атрибуты:
        _note_service (NoteService): Сервис для заметок.
        _photo_service (PhotoService): Сервис для фото (для дочерних операций).

    Пример использования дочернего сервиса:
        # Получение фото приёма
        photos = appointment_service.get_children(appointment_id, 'photos')

        # Добавление нового фото
        new_photo = PhotoDTO(file_path='/tmp/photo.jpg', description='Снимок')
        created = appointment_service.add_child(appointment_id, 'photos', new_photo)

        # Удаление фото
        appointment_service.remove_child(photo_id, 'photos')
    """

    @AppLogger.get_instance(
        name = 'AppointmentService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def __init__(
        self,
        db: Database,
        note_service: Optional['NoteService'] = None,  
        photo_service: Optional['PhotoService'] = None,  
        field_configs: Optional[Dict[str, Dict[str, Any]]] = None, 
        logger_name: Optional[str] = None,
    ):
        """
        Инициализирует сервис для работы с приёмами.
        
        :param db: База данных
        :type db: Database
        :param note_service: сервис для работы с заметками приёмов (необязательный)
        :type note_service: Optional['NoteService']
        :param photo_service: сервис для работы с фотографиями приёмов (необязательный)
        :type photo_service: Optional['PhotoService']
        :param logger_name: имя для логгера (необязательный)
        :type logger_name: Optional[str]
        """

        if logger_name is None:
            logger_name = self.__class__.__name__
          
        # Вызов конструктора базового класса с указанием классов модели, DTO и репозитория
  
        super().__init__(
            db=db,
            repo_class      = AppointmentRepository,
            model_class     = Appointment,
            dto_class       = AppointmentDTO,
            field_configs   = field_configs,
            logger_name     = logger_name,
        )

        self._note_service = note_service
        self._photo_service = photo_service

        # Если не передан, создадим по умолчанию (для совместимости)
        if self._note_service is None:
            self._note_service = NoteService(
                db, 
                logger_name=logger_name + ".NoteService"
            )
 
    @AppLogger.get_instance(
        name = 'AppointmentService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    ) 
    def _validate_parents(self, dto: AppointmentDTO, session: Session) -> None:
        patient_repo = PatientRepository(session)
        if not patient_repo.get_by_id(dto.patient_id):
            raise PatientNotFoundError(dto.patient_id)
    
    @AppLogger.get_instance(
        name = 'AppointmentService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    ) 
    def _get_child_service(self, relation_name: str) -> Optional[BaseService]:
        """
        Возвращает сервис для управления дочерними сущностями по имени отношения.

        Переопределите этот метод в наследниках, если сущность имеет связи "один ко многим",
        требующие отдельного сервиса (например, фотографии приёма). Базовый метод
        возвращает None.

        Параметры:
            relation_name (str): Имя отношения (например, 'photos', 'documents').

        Returns:
            Optional[BaseService]: Сервис для работы с дочерними сущностями или None.

        Пример (AppointmentService):
            def _get_child_service(self, relation_name: str) -> Optional[BaseService]:
                if relation_name == 'photos':
                    return self._photo_service
                return super()._get_child_service(relation_name)
        """

        if relation_name == 'photos':
            return self._photo_service
        
        return super()._get_child_service(relation_name)

    @AppLogger.get_instance(
        name = 'AppointmentService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    ) 
    def _get_note_service(self) -> 'NoteService':
        return self._note_service
    
    # ------------------------------------------------------------
    # Вспомогательный метод для работы с заметками через репозиторий
    # ------------------------------------------------------------

    # @AppLogger.get_instance(
    #     name = 'AppointmentService',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )  
    # @staticmethod
    # def _update_note_field(
    #     sess: Session,
    #     note_repo: AppointmentNoteRepository,
    #     old_note_id: Optional[int],
    #     new_text: Optional[str],
    #     create_if_missing: bool = True
    # ) -> Optional[int]:
    #     """
    #     Обновляет или создаёт заметку, возвращает (new_note_id, old_note_id).
    #     old_note_id – переданный старый ID (может быть None).
    #     Возвращает (новый ID, старый ID), чтобы вызывающий код мог потом удалить старую заметку.
    #     """
    #     # Если текст не передан и не требуется создавать – ничего не меняем
    #     if new_text is None and not create_if_missing:
    #         return old_note_id, None

    #     # Если есть старая заметка и текст передан – обновляем её
    #     if old_note_id is not None:
    #         note = note_repo.get_by_id(old_note_id)
    #         if note:
    #             if new_text is not None:
    #                 note.text = new_text

    #             return old_note_id, None   # ID не изменился, старый не нужно удалять

    #     # Создаём новую заметку
    #     new_note = AppointmentNote(text=new_text or "")
    #     note_repo.add(new_note)
    #     sess.flush()
        
    #     return new_note.id, old_note_id   # возвращаем новый ID и старый ID (который может быть None)

    # @AppLogger.get_instance(
    #     name='AppointmentService',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # def _add_photo_counts(self, appointments: List[Appointment], sess) -> None:
    #     """Добавляет каждому приёму временный атрибут _photo_count с количеством фото."""

    #     if not appointments:
    #         return
        
    #     # from sqlalchemy import func
    #     # from app.database.database_shema.clinic import Photo
    #     app_ids = [app.id for app in appointments]

    #     # Запрос количества фото по каждому приёму
    #     counts = sess.query(
    #         Photo.appointment_id,
    #         func.count(Photo.id).label('cnt')
    #     ).filter(
    #         Photo.appointment_id.in_(app_ids)
    #     ).group_by(
    #         Photo.appointment_id
    #     ).all()

    #     count_map = {c[0]: c[1] for c in counts}

    #     for app in appointments:
    #         setattr(app, '_photo_count', count_map.get(app.id, 0))

    @AppLogger.get_instance(
        name='AppointmentService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def reload_config(self) -> None:
        """
        Перезагружает конфигурацию AppointmentService.
        Обновляет Database, а также пересоздаёт сервисы заметок и фото.
        """
        super().reload_config()
        # from app.dependencies import clear_services_cache # оставить тут, так как циклы
        # # Очищаем кэш, чтобы при следующем вызове get_appointment_service() создался новый экземпляр
        # clear_services_cache()
        from app.dependencies import get_note_service, get_photo_service # оставить тут, так как циклы

        self._note_service = get_note_service()
        self._photo_service = get_photo_service()

        # from app.dependencies import get_appointment_service # импорт внутри метода так как циклы
        # self._appointment_service = get_appointment_service()

        self.logger.info("AppointmentService: note_service и photo_service перезагружены")


    @AppLogger.get_instance(
        name = 'AppointmentService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def _not_found_exception(self, entity_id: int) -> Exception:
        """
        Возвращает исключение, если приём не найден.

        :param entity_id: идентификатор приёма
        :type entity_id: int
        :return: исключение AppointmentNotFoundError
        :rtype: Exception
        """
        self.logger.error(f"Приём с идентификатором {entity_id} не найден.")

        return AppointmentNotFoundError(entity_id)

    # @AppLogger.get_instance(
    #     name = 'AppointmentService',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    # def get_dtos( # ф-ю требуется переделать в динамику
    #         self, 
    #         item_s:Union[List[AppointmentDTO], AppointmentDTO]  
    # )-> Union[List[AppointmentDTO], AppointmentDTO] : 
    #     """
    #     Возвращает список DTO из списка объектов или один DTO из объекта.
    #     Если получен список объектов, то для каждого объекта пытается создать DTO.
    #     Если объект не может быть конвертирован в DTO, то выбрасывается исключение.
    #     :param item_s: список объектов или один объект
    #     :type item_s: Union[List[AppointmentDTO], AppointmentDTO]
    #     :return: список DTO или один DTO
    #     :rtype: Union[List[AppointmentDTO], AppointmentDTO]
    #     """

    #     if isinstance(item_s, list):
    #         # Если получен список объектов
    #         dtos = []  # список DTO
    #         for item in item_s:
    #             # для каждого объекта пытаемся создать DTO
    #             dtos.append(self.get_dtos(item))  # рекурсивно добавляем DTO в список
    #         self.logger.debug(f"Получено {len(dtos)} записей")
    #         return dtos
    #     else:
    #         # данные из ТБ
    #         try:
    #             # создаем DTO из объекта
    #             dto = self._dto_class.model_validate(item_s)  
    #         except Exception as e:
    #             # если объект не может быть конвертирован в DTO, то выбрасываем исключение
    #             self.logger.error(f"Ошибка валидации для объекта: {item_s}")
    #             raise e
            
    #         # Заполняем виртуальные поля
            
    #         # данные, которые подтягиваем отдельно
    #         try:
    #             # если объект имеет поле patient, то подгружаем его имя
    #             if item_s.patient:
    #                 dto.patient_name = f"{item_s.patient.last_name} {item_s.patient.first_name}"
    #         except Exception as e:
    #             # если нет поля patient, то выбрасываем исключение
    #             self.logger.error(f"Ошибка валидации для объекта (patient_name): {item_s}")
    #             raise e
            
    #         try:
    #             # если объект имеет поле note, то подгружаем текст заметки
    #             if item_s.note:
    #                 dto.note_text = item_s.note.text
    #         except Exception as e:
    #             # если нет поля note, то выбрасываем исключение
    #             self.logger.error(f"Ошибка валидации для объекта (photos): {item_s}")
    #             raise e
            

    #         # try:
    #         #     if item_s.note
    #         #     dto.has_photos = '📷' if item_s.photos and len(item_s.photos) > 0 else '❌'
    #         # except Exception as e:
    #         #     # если нет поля note, то выбрасываем исключение
    #         #     self.logger.error(f"Ошибка валидации для объекта (note): {item_s}")
    #         #     raise e
            
    #         return dto
    # @AppLogger.get_instance(
    #     name='AppointmentService',
    #     # share_file_with = 'system',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,  # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    # def _get_extra_data(self, item_s):
    #     extra_data = {}
    #     # Определяем количество фото
    #     if hasattr(item_s, 'photos') and item_s.photos is not None:
    #         extra_data['photo_count'] = len(item_s.photos)
    #     elif hasattr(item_s, '_photo_count'):
    #         extra_data['photo_count'] = item_s._photo_count
    #     else:
    #         extra_data['photo_count'] = 0

    #     return extra_data

    # @AppLogger.get_instance(
    #     name='AppointmentService',
    #     # share_file_with = 'system',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,  # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    # def _conwert_photos_in_PhotoDTO(self, photos):
    #     # Преобразование photos в PhotoDTO (если есть и это не DTO)
    #     if photos:
    #         self.logger.debug("Начинаем явное преобразование photos в PhotoDTO")

    #         # from app.dto import PhotoDTO
    #         # dto.photos = [PhotoDTO.model_validate(p) for p in dto.photos]
    #         photos = [  # Если элемент уже PhotoDTO, оставляем как есть; иначе преобразуем
    #             p if isinstance(p, PhotoDTO) else PhotoDTO.model_validate(p)
    #             for p in photos
    #         ]

    #         self.logger.debug(
    #             f"После преобразования: "
    #             f"тип dto.photos = {type(photos)}, "
    #             f"первый элемент = {type(photos[0]) if photos else None}"
    #         )

    #     return photos

    # @AppLogger.get_instance(
    #     name='AppointmentService',
    #     # share_file_with = 'system',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,  # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    # def get_dtos(
    #     self, 
    #     item_s: Union[List[Appointment], Appointment],
    #     # extra_data_for_photos:bool = False,
    # ) -> Union[List[AppointmentDTO], AppointmentDTO]:

    #     if isinstance(item_s, list):
    #         return [ # Для списка вызываем рекурсивно с тем же флагом
    #             self.get_dtos(
    #                 item,
    #                 # extra_data_for_photos=extra_data_for_photos
    #             ) for item in item_s
    #         ]
        
    #     else:
    #         try:
    #             dto = self._dto_class.model_validate(item_s)

    #             self.logger.debug(
    #                 f"item_s: "
    #                 f"type={type(item_s).__name__}, "
    #                 f"id={getattr(item_s, 'id', None)}"
    #             )
                
    #             if dto.photos:
    #                 self.logger.debug(f"  первый элемент: {type(dto.photos[0])}")

    #         except Exception as e:
    #             self.logger.error(f"Ошибка валидации для объекта: {item_s} : {e}")
    #             raise e

    #         # Преобразование photos в PhotoDTO (если есть и это не DTO)
    #         dto.photos = self._conwert_photos_in_PhotoDTO(dto.photos)

    #         # Определяем количество фото
    #         extra_data = self._get_extra_data(item_s)

    #         # Обогащаем DTO вычисленными полями
    #         enriched_dto = enrich_dto_with_computed_fields(
    #             dto, 
    #             model_obj = item_s, 
    #             field_configs = self._field_configs,
    #             extra_data = extra_data,
    #         )

    #         self.logger.debug(
    #             f"После enrich: тип enriched_dto.photos = {type(enriched_dto.photos)}"
    #         )

    #         if enriched_dto.photos:
    #             self.logger.debug(f"  первый элемент: {type(enriched_dto.photos[0])}")

    #         return enriched_dto

    @AppLogger.get_instance(
        name = 'AppointmentService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def create(
        self, 
        dto: AppointmentDTO, 
        session: Optional[Session] = None,
    ) -> AppointmentDTO:
        """
        Создаёт приём из переданных данных.

        Метод create_appointment будет вызван для создания приёма.
        Если поле note_text передано в dto, то оно будет передано в create_appointment.
        Если поле note_text не передано в dto, то оно будет равно None.

        :param dto: DTO с данными (используются patient_id, date, time, note_id)
        :type dto: AppointmentDTO
        :return: созданный приём
        :rtype: AppointmentDTO
        """
        # получаем текст заметки из dto
        note_text = getattr(
            dto, 
            'note_text', 
            None
        )
        
        # вызываем метод create_appointment для создания приёма
        return self.create_appointment(
            dto, 
            note_text=note_text,
            session=session,
        )

    @AppLogger.get_instance(
        name = 'AppointmentService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def update(
        self, 
        dto: AppointmentDTO, 
        session: Optional[Session] = None, 
    ) -> AppointmentDTO:
        """
        Обновляет существующий приём.

        Мы используем метод update_appointment для обновления приёма,
        а параметр note_text мы передаем в него из поля dto,
        если оно указано.
        (Поле note_text может быть передано в dto как виртуальное.)

        :param dto: данные приёма
        :type dto: AppointmentDTO
        :return: обновленный DTO приёма
        :rtype: AppointmentDTO
        :raises AppointmentNotFoundError: если приём с указанным ID не найден
        :raises ValueError: если ID приёма не указан
        """
        
        # получаем текст заметки из поля dto, если он указан
        note_text = getattr(dto, 'note_text', None)

        # вызываем метод update_appointment для обновления приёма
        # и передаем параметр note_text в него
        return self.update_appointment(
            dto, 
            note_text=note_text,
            session=session,
        )

    # ----------------------------------------------------------------------
    # Переопределение методов получения данных с подгрузкой связей
    # ----------------------------------------------------------------------
    # @AppLogger.get_instance(
    #     name = 'AppointmentService',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # ) 
    # def _post_process_items(self, items: List[Appointment], session: Session) -> List[Appointment]:
    #     self._add_photo_counts(items, session)
    #     return items

    # @AppLogger.get_instance(
    #     name = 'AppointmentService',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )  
    # def get_all(self, session: Optional[Session] = None) -> List[AppointmentDTO]:
    #     """
    #     Возвращает все приёмы с подгруженными пациентом и заметкой.

    #     1. Создаем сессию для работы в одной транзакции (если не указана).
    #     2. Получаем репозиторий для работы с приёмами.
    #     3. Вызываем метод get_all_with_relations у репозитория, чтобы получить все приёмы с подгруженными данными.
    #     4. Создаем список DTO из полученных записей.
    #     5. Возвращаем список DTO.
        
    #     :return: список приёмов с подгруженными данными
    #     :rtype: List[AppointmentDTO]
    #     """
    #     # self.logger.debug("get_all (with relations)")

    #     with self._session_scope(session) as sess:
    #         repo = self._get_repo(sess)
    #         relations = self._get_eager_loading_options()
    #         items = repo.get_all_with_relations(# метод репозитория с подгрузкой
    #             relations
    #         )  

    #         self._add_photo_counts(items, sess) # подсчитываем количество фото

    #         dtos = self.get_dtos(
    #             items,
    #             # extra_data_for_photos=True,
    #         )

    #         return dtos
        

    @AppLogger.get_instance(
        name = 'AppointmentService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def get_appointments_by_patient(
        self, 
        patient_id: int, 
        session: Optional[Session] = None
    ) -> List[AppointmentDTO]:
        """
        Возвращает приёмы пациента с подгруженными связями.

        :param patient_id: ID пациента, для которого хотим получить приёмы
        :type patient_id: int
        :param session: сессия для работы в одной транзакции
        :type session: Optional[Session]
        :return: список приёмов пациента с подгруженными связями
        :rtype: List[AppointmentDTO]
        """
        self.logger.debug(
            f"get_appointments_by_patient: "
            f"patient_id={patient_id}"
        )       


        filters = [{'column': 'patient_id', 'operator': 'eq', 'value': patient_id}]
        return self.get_filtered(filters, session=session)

        # # 1. Создаем сессию для работы в одной транзакции (если не указана)
        # with self._session_scope(session) as sess:

        #     # 2. Получаем репозиторий для работы с приёмами
        #     repo = self._get_repo(sess)

        #     # 3. Вызываем метод get_by_patient_with_relations у репозитория, передавая ID пациента
        #     items = repo.get_by_patient_with_relations(
        #         patient_id,
        #         relations=self._get_eager_loading_options()
        #     )
        #     # query = sess.query(Appointment).filter(Appointment.patient_id == patient_id)
        #     # query = query.options(*self._get_joinedload_Appointment())
        #     # items = query.all()
        #     self._add_photo_counts(items, sess)

        #     # 4. Создаем список DTO из полученных записей
        #     # return [self._dto_class.from_orm(item) for item in items]
        #     # dtos = [self._dto_class.from_orm(item) for item in items]
        #     # dtos = [self._dto_class.model_validate(item) for item in items]
            
        #     dtos = self.get_dtos(
        #         items,
        #         # extra_data_for_photos=True,
        #     )
        #     # self.logger.debug(f"Получено {len(dtos)} записей для пациента {patient_id}")
            
        #     return dtos
        
    # @AppLogger.get_instance(
    #     name = 'AppointmentService',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )  
    # def get_page_with_relations(self, offset, limit, filters=None, order_by=None, session=None):
    #     relations = self._get_joinedload_Appointment()
    #     return self.get_page(offset, limit, filters, order_by, session, relations=relations)

    @AppLogger.get_instance(
        name = 'AppointmentService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def get_appointment(
        self, 
        appointment_id: int, 
        session: Optional[Session] = None
    ) -> AppointmentDTO:
        """
        Возвращает один приём по ID с подгруженными связями (пациентом и заметкой).

        Шаги:
        1. Создаем сессию для работы в одной транзакции (если не указана)
        2. Получаем репозиторий (Repository) для работы с приёмами
        3. Вызываем метод _get_item у репозитория, передавая ID приёма
        4. Если приём не найден, то вызываем исключение AppointmentNotFoundError
        5. Создаем DTO из полученной записи
        6. Возвращаем DTO

        :param appointment_id: ID приёма
        :type appointment_id: int
        :param session: сессия для работы в одной транзакции
        :type session: Optional[Session]
        :return: приём с подгруженными связями
        :rtype: AppointmentDTO
        :raises AppointmentNotFoundError: если приём с указанным ID не существует
        """
        self.logger.debug(f"get_appointment: id={appointment_id}")
        # Используем get_by_id, который учитывает eager_load_detail
        return self.get_by_id(appointment_id, session)
        # with self._session_scope(session) as sess:

        #     _, item = self._get_item(
        #         appointment_id, 
        #         AppointmentNotFoundError, 
        #         sess
        #     )
        #     # repo = self._get_repo(sess)
        #     # item = repo.get_by_id_with_relations(
        #     #     appointment_id, 
        #     #     relations=self._get_eager_loading_options()
        #     # )
        #     # if item is None:
        #     #     raise AppointmentNotFoundError(appointment_id)
            
        #     # return self._dto_class.from_orm(item)

        #     # Создаем DTO из полученной записи
        #     return  self.get_dtos(item)
      
    # @AppLogger.get_instance(
    #     name = 'AppointmentService',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )    
    # def _get_joinedload_Appointment(self) -> List:
    #     relations = []
    #     for rel_name in self._get_relations_for_eager_loading():
    #         if hasattr(Appointment, rel_name):
    #             relations.append(joinedload(getattr(Appointment, rel_name)))
    #     return relations
    # def _get_joinedload_Appointment(self) -> List:
    #     relations = []
    #     # Обязательные связи: пациент (всегда нужен)
    #     relations = [joinedload(Appointment.patient)]
        
    #     # Добавляем заметки из field_configs
    #     for mapping in self._get_note_field_mappings():
    #         relation_name = mapping['relation_name']
    #         if hasattr(Appointment, relation_name):
    #             relations.append(joinedload(getattr(Appointment, relation_name)))
        
    #     return relations
    
    # @AppLogger.get_instance(
    #     name = 'AppointmentService',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )  
    # def get_filtered(
    #     self, 
    #     filters: List[Dict[str, Any]], 
    #     fuzzy_threshold: int = 60,
    #     session: Optional[Session] = None,
    # ) -> List[AppointmentDTO]:
    #     """
    #     Возвращает отфильтрованные приёмы с подгруженными связями.
        
    #     :param filters: список фильтров в виде словарей с именами полей и значениями
    #     :type filters: List[Dict[str, Any]]
    #     :param fuzzy_threshold: порог для фильтрации с нечетким соответствием, в секундах
    #     :type fuzzy_threshold: int
    #     :param session: сессия для работы в одной транзакции
    #     :type session: Optional[Session]
    #     :return: список отфильтрованных приёмов в виде объектов AppointmentDTO
    #     :rtype: List[AppointmentDTO]
    #     """

    #     # from ..utils.filtering import apply_filters, apply_post_filters

    #     self.logger.debug(
    #         f"get_filtered (with relations) "
    #         f"filters={filters}"
    #     )

    #     with self._session_scope(session) as sess:
    #         query = sess.query(self._model_class).options(
    #             # joinedload(Appointment.patient),
    #             # joinedload(Appointment.note)

    #             # joinedload(Appointment.patient),
    #             # joinedload(Appointment.reason_note),
    #             # joinedload(Appointment.procedure_note),
    #             # joinedload(Appointment.recommendations_note),
    #             # joinedload(Appointment.note),
    #             # joinedload(Appointment.cost_procedure_note),
    #             # joinedload(Appointment.photos)
    #             *self._get_eager_loading_options()
    #         )

    #         query, post_filters = apply_filters(
    #             query, 
    #             self._model_class, 
    #             filters, 
    #             fuzzy_threshold,
    #         )

    #         items = query.all()

    #         if post_filters:
    #             items = apply_post_filters(
    #                 items, 
    #                 post_filters, 
    #                 self._model_class
    #             )

    #         # return [self._dto_class.from_orm(item) for item in items]
        
    #         self._add_photo_counts(items, sess)

    #         dtos = self.get_dtos(
    #             items, 
    #             # extra_data_for_photos=True, 
    #         )

    #         return dtos

    # ----------------------------------------------------------------------
    # Методы создания, обновления и удаления (без изменений)
    # ----------------------------------------------------------------------


    @AppLogger.get_instance(
        name = 'AppointmentService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def create_appointment(
        self, 
        dto: AppointmentDTO, 
        note_text: Optional[str] = None,
        session: Optional[Session] = None
    ) -> AppointmentDTO:
        """
        Создаёт новый приём.
        
        :param dto: DTO с данными (используются patient_id, date, time, note_id).
        :param note_text: текст заметки. Если передан, заметка будет найдена или создана,
                          и её ID автоматически подставлен (заменяет dto.note_id).
        :param session: опциональная сессия для работы в одной транзакции.
        :raises PatientNotFoundError: если пациент с указанным ID не найден.
        """

        # Проверка существования пациента (можно вынести в отдельный метод)
        with self._session_scope(session) as sess:
            # patient_repo = PatientRepository(sess)
            # if not patient_repo.get_by_id(dto.patient_id):
            #     raise PatientNotFoundError(dto.patient_id)
        # required = {
        #     'patient_id': dto.patient_id,
        #     'date': dto.date,
        #     'date_next': dto.date_next,
        # }

            if note_text is not None: # Это сохранит работоспособность CLI без переписывания его логики. В дальнейшем, если CLI перевести на прямое заполнение DTO, параметр можно будет удалить
                dto.note_text = note_text

            return self._create_entity(
                dto, 
                # required, 
                session = sess
            )

        # self.logger.debug(
        #     f"Создание приёма: {dto}, "
        #     f"note_text={note_text}"
        # )

        # with self._session_scope(session) as sess:
        #     # Проверка существования пациента
        #     patient_repo = PatientRepository(sess)

        #     if not patient_repo.get_by_id(dto.patient_id):
        #         raise PatientNotFoundError(dto.patient_id)

        #     note_repo = AppointmentNoteRepository(sess)

        #     # Создаём заметки для каждого текстового поля, старых ID нет
        #     # reason_id, _ = self._update_note_field(            
        #     #     sess, 
        #     #     note_repo, 
        #     #     None, 
        #     #     dto.reason_text,                  
        #     #     create_if_missing=False
        #     # )
        #     # procedure_id, _ = self._update_note_field(         
        #     #     sess, 
        #     #     note_repo, 
        #     #     None, 
        #     #     dto.procedure_text,               
        #     #     create_if_missing=False
        #     # )
        #     # recommendations_id , _= self._update_note_field(   
        #     #     sess, 
        #     #     note_repo, 
        #     #     None, 
        #     #     dto.recommendations_text,         
        #     #     create_if_missing=False
        #     # )
        #     # note_id, _ = self._update_note_field(              
        #     #     sess, 
        #     #     note_repo, 
        #     #     None, 
        #     #     dto.note_text,   
        #     #     create_if_missing=False
        #     # )
        #     # cost_procedure_id, _ = self._update_note_field(    
        #     #     sess, 
        #     #     note_repo, 
        #     #     None, 
        #     #     dto.cost_procedure_text,          
        #     #     create_if_missing=False
        #     # )

        #     # # # Обработка заметки
        #     # # note_id = dto.note_id
        #     # # if note_text:
        #     # #     # note_service = NoteService( # создаём экземпляр (можно без логгера)
        #     # #     #     self._db,
        #     # #     #     logger_name=self.logger.name + ".NoteService" # (можно без логгера)
        #     # #     #     )  
        #     # #     note_dto = self._note_service.get_or_create_note(note_text, session=sess)
        #     # #     note_id = note_dto.id if note_dto else None

        #     # # Создаем приём
        #     # appointment = self._model_class(
        #     #     patient_id=dto.patient_id,
        #     #     date=dto.date,
        #     #     date_next=dto.date_next,
        #     #     reason_id=reason_id,
        #     #     procedure_id=procedure_id,
        #     #     recommendations_id=recommendations_id,
        #     #     note_id=note_id,
        #     #     cost_procedure_id=cost_procedure_id,
        #     # )

            
        #     # Динамическое создание/обновление заметок
        #     note_ids = self._apply_note_updates(
        #         dto,
        #         sess,
        #         note_repo,
        #         model_obj=None   # None означает режим создания (нет старой модели)
        #     )

        #     # Создаём приём
        #     appointment = self._model_class(
        #         patient_id=dto.patient_id,
        #         date=dto.date,
        #         date_next=dto.date_next,
        #         **note_ids   # распаковываем словарь {reason_id: val, procedure_id: val, ...}
        #     )

        #     repo = self._get_repo(sess)
        #     repo.add(appointment)
        #     sess.flush()  # чтобы получить id
            
        #     # dto_out = self._dto_class.from_orm(appointment)
        #     dto_out = self.get_dto_out(appointment)

        #     self.logger.info(f"Создан приём id={dto_out.id}")

        #     return dto_out

    @AppLogger.get_instance(
        name = 'AppointmentService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def update_appointment(
        self, 
        dto: AppointmentDTO, 
        note_text: Optional[str] = None,
        session: Optional[Session] = None
    ) -> AppointmentDTO:
        """
        Обновляет существующий приём.
        Если передан note_text, заметка будет найдена или создана, и ID старой заметки
        будет заменён на новую. Старая заметка будет удалена, если она больше не используется.

        :param dto: DTO приёма, который нужно обновить
        :param note_text: текст заметки. Если передан, заметка будет найдена или создана,
                          и ID старой заметки будет заменён на новую. Старая заметка будет удалена,
                          если она больше не используется.
        :param session: опциональная сессия для работы в одной транзакции
        :return: обновленный DTO приёма
        :raises AppointmentNotFoundError: если приём с указанным ID не найден
        :raises ValueError: если ID приёма не указан
        """
        
        
        if dto.id is None:
            self.logger.warning("Попытка обновления приёма без id")
            raise ValueError("ID приёма не указан")

        self.logger.debug(f"Обновление приёма id={dto.id}")


        if note_text is not None: # Это сохранит работоспособность CLI без переписывания его логики. В дальнейшем, если CLI перевести на прямое заполнение DTO, параметр можно будет удалить
            dto.note_text = note_text

        return self._update_entity(dto, dto.id, session)

        # with self._session_scope(session) as sess:            
        #     # ВАЖНО: используем get_by_id_with_relations, чтобы подгрузить все связи
        #     repo = self._get_repo(sess)
        #     appointment = repo.get_by_id_with_relations(dto.id)
        #     if appointment is None:
        #         raise AppointmentNotFoundError(dto.id)


        #     # Обновляем простые поля
        #     # appointment.date = dto.date
        #     # appointment.date_next = dto.date_next
        #     self._apply_simple_updates(appointment, dto) # динамическое обновление простых полей

        #     # # Сохраняем старые ID заметок до изменения
        #     # old_reason_id = appointment.reason_id
        #     # old_procedure_id = appointment.procedure_id
        #     # old_recommendations_id = appointment.recommendations_id
        #     # old_note_id = appointment.note_id
        #     # old_cost_procedure_id = appointment.cost_procedure_id


        #     note_repo = AppointmentNoteRepository(sess)

        #     # # Обновляем каждую заметку, получаем (новый ID, старый ID)
        #     # new_reason_id, old_reason = self._update_note_field(
        #     #     sess, 
        #     #     note_repo, 
        #     #     old_reason_id, 
        #     #     dto.reason_text, 
        #     #     create_if_missing=False
        #     # )
        #     # new_procedure_id, old_procedure = self._update_note_field(
        #     #     sess, 
        #     #     note_repo, 
        #     #     old_procedure_id, 
        #     #     dto.procedure_text, 
        #     #     create_if_missing=False
        #     # )
        #     # new_recommendations_id, old_recommendations = self._update_note_field(
        #     #     sess, 
        #     #     note_repo, 
        #     #     old_recommendations_id, 
        #     #     dto.recommendations_text, 
        #     #     create_if_missing=False
        #     # )
        #     # new_note_id, old_note = self._update_note_field(
        #     #     sess, 
        #     #     note_repo, 
        #     #     old_note_id, 
        #     #     dto.note_text, 
        #     #     create_if_missing=False
        #     # )
        #     # new_cost_id, old_cost = self._update_note_field(
        #     #     sess, 
        #     #     note_repo, 
        #     #     old_cost_procedure_id, 
        #     #     dto.cost_procedure_text, 
        #     #     create_if_missing=False
        #     # )

        #     # # Присваиваем новые ID
        #     # appointment.reason_id = new_reason_id
        #     # appointment.procedure_id = new_procedure_id
        #     # appointment.recommendations_id = new_recommendations_id
        #     # appointment.note_id = new_note_id
        #     # appointment.cost_procedure_id = new_cost_id

        #     # # Очистка старых заметок, которые больше не используются
        #     # # Используем сервис заметок (self._note_service), который уже имеет метод cleanup_unused_note
        #     # for old_id in (old_reason, old_procedure, old_recommendations, old_note, old_cost):
        #     #     if old_id is not None and old_id not in (
        #     #         appointment.reason_id, appointment.procedure_id,
        #     #         appointment.recommendations_id, appointment.note_id,
        #     #         appointment.cost_procedure_id
        #     #     ):
        #     #         self._note_service.cleanup_unused_note(old_id, sess)

        #             # Словари для старых и новых ID заметок
        # # old_ids = {}
        # # new_ids = {}

        # # # Получаем маппинги полей-заметок
        # # for mapping in self._get_note_field_mappings():
        # #     orm_field = mapping['orm_id_field']          # например 'reason_id'
        # #     old_id = getattr(appointment, orm_field)     # старый ID из БД
        # #     old_ids[orm_field] = old_id

        # #     text = getattr(dto, mapping['dto_field'], None)   # текст из DTO
        # #     if text is not None:
        # #         new_id, _ = self._update_note_field(
        # #             sess, 
        # #             note_repo, 
        # #             old_id, 
        # #             text, 
        # #             create_if_missing=False
        # #         )
        # #         new_ids[orm_field] = new_id
        # #     else:
        # #         new_ids[orm_field] = old_id

        # new_ids = self._apply_note_updates(dto, sess, note_repo, model_obj=appointment)

        # # Применяем новые ID к объекту приёма
        # for orm_field, new_id in new_ids.items():
        #     setattr(appointment, orm_field, new_id)
        
        # sess.flush()

        # # # Очистка старых заметок, которые больше не используются
        # # for orm_field, old_id in old_ids.items():
        # #     new_id = new_ids.get(orm_field)
        # #     if old_id is not None and old_id != new_id:
        # #         self._note_service.cleanup_unused_note(old_id, sess)

        # # Обновлённый DTO
        # updated_dto = self.get_dto_out(appointment)
        # self.logger.info(f"Обновлён приём id={updated_dto.id}")

        # return updated_dto   



            # old_note_id = app.note_id

            # # Обновляем основные поля
            # app.date = dto.date
            # app.time = dto.time

            # # Обработка заметки
            # if note_text is not None:
            #     # note_service = NoteService(self._db)
            #     note_dto = self._note_service.get_or_create_note(note_text, session=sess)
            #     app.note_id = note_dto.id if note_dto else None

            # elif dto.note_id is not None:
            #     app.note_id = dto.note_id
            # # иначе оставляем текущую заметку

            # # Если заметка изменилась и была старая заметка
            # if old_note_id is not None and old_note_id != app.note_id:
            #     # Проверяем, остались ли другие приёмы, ссылающиеся на старую заметку
            #     #  self._cleanup_unused_note(old_note_id, sess)
            #     self._note_service.cleanup_unused_note(old_note_id, sess)

            # # updated_dto = self._dto_class.from_orm(app)
            # updated_dto = self.get_dto_out(app)
            # self.logger.info(f"Обновлён приём id={updated_dto.id}")

            # return updated_dto   

    @AppLogger.get_instance(
        name = 'AppointmentService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def delete_appointment(
        self, 
        appointment_id: int, 
        session: Optional[Session] = None
    ) -> None:
        """
        Удаляет приём и, если заметка больше не используется, удаляет её.
        
        Шаги:
        1. Получаем приём из базы данных с подгруженными связями.
        2. Если приём не найден, выбрасываем исключение.
        3. Если приём имеет фото, удаляем их.
        4. Если приём имел заметку, и она больше не используется, удаляем ее.
        5. Удаляем сам приём.
        """
        with self._session_scope(session) as sess:
            _, appointment = self._get_item(
                appointment_id, 
                AppointmentNotFoundError, 
                sess
            )
            # repo = self._get_repo(sess)
            # appointment = repo.get_by_id_with_relations(
            #     appointment_id,
            #     relations=self._get_eager_loading_options()
            # )

            # if appointment is None:
            #     raise AppointmentNotFoundError(appointment_id)

            # Удаляем фото, если есть сервис
            if self._photo_service is not None:
                for photo in appointment.photos:
                    self._photo_service.delete_photo(photo.id, session=sess)

            # else:
            #     self.logger.warning("PhotoService not provided, photos will not be deleted from disk")      
            
            # # # Если приём имел заметку, и она больше не используется, удаляем ее
            # # note_id = appointment.note_id

            # # # Сохраняем все ID заметок до удаления приёма
            # # note_ids = []
            # # for note_id in (
            # #     appointment.reason_id, appointment.procedure_id,
            # #     appointment.recommendations_id, appointment.note_id,
            # #     appointment.cost_procedure_id
            # # ):
            # #     if note_id is not None:
            # #         note_ids.append(note_id)

            # # --- ДИНАМИЧЕСКИЙ СБОР ID ЗАМЕТОК ---
            # note_ids = []
            # for mapping in self._get_note_field_mappings():
            #     note_id = getattr(appointment, mapping['orm_id_field'])
            #     if note_id is not None:
            #         note_ids.append(note_id)
            # # --- КОНЕЦ ДИНАМИЧЕСКОГО СБОРА ---

            
            # # Удаляем приём
            # repo.delete(appointment)
            # sess.flush()

            # # Очищаем неиспользуемые заметки
            # for nid in note_ids:
            #     self._note_service.cleanup_unused_note(nid, sess)

            # Теперь удаляем приём (базовый метод)
            self._delete_entity(appointment_id, sess)

    @AppLogger.get_instance(
        name = 'AppointmentService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )           
    def delete(
        self, 
        entity_id: int, 
        session: Optional[Session] = None
    ) -> None:
        """
        Удаляет приём вместе с фото и заметкой.

        :param entity_id: ID приёма
        :type entity_id: int
        :param session: сессия для работы в одной транзакции
        :type session: Optional[Session]
        :return: None
        :raises AppointmentNotFoundError: если приём с указанным ID не существует
        """
        self.delete_appointment(entity_id, session=session)
        
    @AppLogger.get_instance(
        name = 'AppointmentService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def get_appointments_by_patient_page(
        self, 
        patient_id: int,  # ID пациента, для которого хотим получить страницу приёмов
        offset: int,  # смещение страницы (количество записей, которые нужно пропустить)
        limit: int,  # размер страницы (количество записей, которые нужно вернуть)
        filters: Optional[List[Dict[str, Any]]] = None,  # фильтры SQL (например: [{'column': 'date', 'operator': '>=', 'value': datetime.date(2022, 1, 1)}])
        order_by: Optional[List] = None,  # сортировка SQL (например: ['date', 'time'])
        session: Optional[Session] = None  # сессия для работы в одной транзакции
    ) -> Tuple[List[AppointmentDTO], int]:
        """
        Возвращает страницу приёмов пациента с подгруженными связями.

        Шаги:

        1. Создаем сессию для работы в одной транзакции (если не указана)
        2. Получаем репозиторий (Repository) для работы с приёмами
        3. Вызываем метод get_page_by_patient у репозитория, передавая ID пациента, смещение, размер страницы, фильтры и сортировку
        4. Вызываем метод count_by_patient у репозитория, передавая ID пациента и фильтры, чтобы получить общее количество приёмов
        5. Создаем список DTO из полученных записей
        6. Возвращаем список DTO и общее количество приёмов
        """
        self.logger.debug(
            f"Запрос страницы приёмов пациента {patient_id}: "
            f"offset={offset}, "
            f"limit={limit}"
        )

        ## Формируем фильтр по patient_id
        base_filter = {
            'column': 'patient_id', 
            'operator': 'eq', 
            'value': patient_id
        }
        if filters:
            all_filters = [base_filter] + filters
        else:
            all_filters = [base_filter]

        # Подгружаем все необходимые связи
        relations = self._get_eager_loading_options()

        # Вызываем базовый метод get_page
        return self.get_page(
            offset=offset,
            limit=limit,
            filters=all_filters,
            order_by=order_by,
            session=session,
            relations=relations,
        )

        # # Создаем сессию для работы в одной транзакции (если не указана)
        # with self._session_scope(session) as sess:
        #     # получаем репозиторий
        #     repo = self._get_repo(sess)
        #     relations = self._get_eager_loading_options()

        #     # получаем страницу приёмов для указанного пациента
        #     items = repo.get_page_by_patient(
        #         patient_id, 
        #         offset, 
        #         limit, 
        #         filters=filters, 
        #         order_by=order_by,
        #         relations=relations,          # передаём динамические joinedload
        #     )
            
        #     # получаем общее количество приёмов для указанного пациента
        #     total = repo.count_by_patient(patient_id, filters=filters)
            
        #     # создаем список DTO из полученных записей
        #     # dtos = [self._dto_class.from_orm(item) for item in items]
        #     dtos = self.get_dtos(items)
            
        #     # возвращаем список DTO и общее количество приёмов
        #     return dtos, total

class PhotoService(
    BaseService[
        Photo, 
        PhotoDTO, 
        PhotoRepository
    ]
):
    """
    Сервис для работы с фотографиями приёмов.

    Особенности:
        - Управляет файлами на диске (копирование, удаление).
        - Реализует интерфейс для дочернего сервиса: `get_by_parent` (синоним `get_photos_for_appointment`)
          и `add_to_parent` (синоним `add_photo_to_appointment`).
        - Путь к хранилищу фото можно менять через конфигурацию (`PHOTOS_STORAGE_PATH`).
        - При удалении фото сначала удаляется файл, затем запись в БД (через `_delete_entity`).

    Дополнительные методы:
        - `get_photos_for_appointment(appointment_id, session)`
        - `add_photo_to_appointment(appointment_id, source_file_path, description, session)`
        - `update_photo_description(photo_id, description, session)`
        - `update_photos_for_appointment(appointment_id, pending_photos, deleted_photo_ids, session)`

    Примечание:
        Не используйте `create` напрямую для фото – используйте `add_photo_to_appointment`.
    """

    # Классовый атрибут для хранения пути к папке с фото (общий для всех экземпляров)
    _class_storage_path: Optional[str] = None

    @property
    def _storage_path(self) -> str:
        """Возвращает общий путь к хранилищу фото."""
        if self.__class__._class_storage_path is None:
            # Первое обращение – загружаем из конфига
            # from app.config.config_manager.manager import AppConfigManager
            self.__class__._class_storage_path = AppConfigManager.get_instance().get(
                'PHOTOS_STORAGE_PATH', os.path.join('.', 'photos')
            )

        return self.__class__._class_storage_path

    @_storage_path.setter
    def _storage_path(self, value: str) -> None:
        """Устанавливает общий путь для всех экземпляров."""
        self.__class__._class_storage_path = value
        if value:
            os.makedirs(value, exist_ok=True)

    @AppLogger.get_instance(
        name = 'PhotoService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(   
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def __init__(
        self, 
        db: Database, 
        photos_storage_path: str,  
        field_configs: Optional[Dict[str, Dict[str, Any]]] = None,
        logger_name: 
        Optional[str] = None
    ):
        """
        Инициализирует сервис для работы с фотографиями приёмов.
        
        :param db: объект Database для работы с БД
        :type db: Database
        :param photos_storage_path: путь к директории для хранения фотографий
        :type photos_storage_path: str
        :param logger_name: имя лога для сервиса
        :type logger_name: Optional[str]
        """

        # Если имя лога не указано, то используем имя класса
        if logger_name is None:
            logger_name = self.__class__.__name__

        # Инициализируем базовый класс
        super().__init__(
            db=db,  # объект Database для работы с БД
            repo_class=PhotoRepository,  # класс репозитория для работы с фотографиями
            model_class=Photo,  # класс модели для работы с фотографиями
            dto_class=PhotoDTO,  # класс DTO для работы с фотографиями
            field_configs=field_configs, # словарь конфигурации полей для сервиса (необязательный)
            logger_name=logger_name  # имя лога для сервиса
        )

        self.logger = AppLogger.get_instance(
            name = 'gui.PhotoService',
            # share_file_with = 'user',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'user',
        )

        # Устанавливаем путь к директории для хранения фотографий
        self._storage_path = photos_storage_path

        # Создаем директорию для хранения фотографий, если она не существует
        self._ensure_storage_exists()

    @AppLogger.get_instance(
        name = 'PhotoService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(  
        level=AppLogger._parse_log_level('DEBUG')
    ) 
    def get_by_parent(self, parent_id: int, session=None):
        """Алиас для get_photos_for_appointment."""
        return self.get_photos_for_appointment(parent_id, session)

    @AppLogger.get_instance(
        name = 'PhotoService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(  
        level=AppLogger._parse_log_level('DEBUG')
    ) 
    def add_to_parent(self, parent_id: int, child_dto: PhotoDTO, session=None):
        """Алиас для add_photo_to_appointment, принимает DTO."""
        # child_dto должен содержать file_path и description
        return self.add_photo_to_appointment(parent_id, child_dto.file_path, child_dto.description, session)

    @AppLogger.get_instance(
        name = 'PhotoService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(  
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def update_photo_description(
        self, 
        photo_id: int, 
        description: str, 
        session: Optional[Session] = None
    ) -> None:
        """Обновляет описание существующего фото."""
        # dto = PhotoDTO(id=photo_id, description=description)
        # self._update_entity(dto, photo_id, session)
        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)
            photo = repo.get_by_id(photo_id)

            if photo is None:
                err_ = PhotoNotFoundError(photo_id)
                self.logger.exception(err_.message)

                raise err_
            
            photo.description = description
            
    @AppLogger.get_instance(
        name = 'PhotoService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(    
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def get_unique_values(self, column_name: str, session: Optional[Session] = None) -> List[Any]:
        """
        Возвращает список уникальных значений для указанного столбца.
        
        :param column_name: имя столбца для получения уникальных значений
        :type column_name: str
        :param session: сессия для работы в рамках внешней транзакции
        :type session: Optional[Session]
        :return: список уникальных значений для указанного столбца
        :rtype: List[Any]
        """
        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)

            return repo.get_unique_values(column_name)

    @AppLogger.get_instance(
        name = 'PhotoService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time( 
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def _not_found_exception(self, entity_id: int) -> Exception:
        """
        Возвращает исключение, если фото с указанным ID не найдено.

        :param entity_id: ID фото
        :return: исключение, если фото не найдено
        :rtype: Exception
        """
        err_ = PhotoNotFoundError(entity_id)

        self.logger.exception(err_.message)

        # raise err_
        return err_

    # ----------------------------------------------------------------------
    # Специфические методы сервиса
    # ----------------------------------------------------------------------
 
    # def add_photo_to_appointment(self, appointment_id: int, source_file_path: str,
    #                               description: str = "", session: Optional[Session] = None) -> PhotoDTO:
    #     """
    #     Добавляет фото к приёму: копирует файл в хранилище и создаёт запись в БД.
    #     """
    #     self.logger.debug(f"Добавление фото к приёму id={appointment_id}, файл={source_file_path}, описание='{description}'")
    #     with self._session_scope(session) as sess:
    #         # Проверяем существование приёма
    #         app_repo = AppointmentRepository(sess)
    #         app = app_repo.get_by_id(appointment_id)
    #         if app is None:
    #             raise AppointmentNotFoundError(appointment_id)

    #         # Копируем файл (операция вне БД)
    #         rel_path = self._copy_file_to_storage(source_file_path, appointment_id)

    #         # Создаём запись в БД
    #         photo = self._model_class(
    #             appointment_id=appointment_id,
    #             file_path=rel_path,
    #             description=description
    #         )
    #         sess.add(photo)
    #         sess.flush()  # получаем id
    #         dto_out = self._dto_class.from_orm(photo)
    #         self.logger.info(f"Добавлено фото id={dto_out.id} к приёму {appointment_id}")
    #         return dto_out

    # ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'}

    # def _is_allowed_file(filename: str) -> bool:
    #     ext = os.path.splitext(filename)[1].lower()
    #     return ext in ALLOWED_EXTENSIONS


    @AppLogger.get_instance(
        name = 'PhotoService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(        
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def add_photo_to_appointment(
            self, 
            appointment_id: int, 
            source_file_path: str,
            description: str = "", 
            session: Optional[Session] = None,
    )-> PhotoDTO:
        """
        Добавляет фотографию к указанному приёму.

        Процесс:
            1. Проверяет существование исходного файла.
            2. Создаёт запись в БД с временным путём 'pending' (чтобы получить ID фото).
            3. Копирует файл в хранилище, формируя имя на основе appointment_id и photo.id.
            4. Обновляет путь в записи на реальный относительный путь.
            5. Если на любом этапе (кроме проверки) возникает ошибка, транзакция откатывается,
            и запись не сохраняется.

        Параметры:
            appointment_id: ID приёма, к которому добавляется фото.
            source_file_path: путь к исходному файлу изображения на диске.
            description: описание фотографии (необязательно).
            session: опциональная сессия SQLAlchemy для работы в рамках внешней транзакции.

        Возвращает:
            PhotoDTO созданной фотографии.

        Исключения:
            AppointmentNotFoundError: если приём с указанным ID не существует.
            PhotoFileError: если исходный файл не найден, не удаётся его скопировать
                            или возникает другая ошибка ввода-вывода.
        """
        self.logger.debug(
            f"Добавление фото к приёму "
            f"id={appointment_id}, "
            f"файл={source_file_path}, "
            f"описание='{description}'"
        )
        
        # 1. Проверка существования и типа файла
        if not os.path.isfile(source_file_path):
            raise PhotoFileError(source_file_path, "проверка", "файл не существует")

        # if not self._is_allowed_file(source_file_path):
        #     raise PhotoFileError(source_file_path, "проверка", "неподдерживаемый формат файла")

        # # 2. Проверка свободного места и прав (опционально)
        # file_size = os.path.getsize(source_file_path)

        with self._session_scope(session) as sess:
            # Проверяем существование приёма
            app_repo = AppointmentRepository(sess)
            app = app_repo.get_by_id(appointment_id)
            if app is None:
                err_ = AppointmentNotFoundError(appointment_id)
                self.logger.exception(err_.message)

                raise err_
                # raise AppointmentNotFoundError(appointment_id)

            # 1. Создаём запись с временным путём (помечаем как ожидающую)
            photo = self._model_class(
                appointment_id=appointment_id,
                file_path='pending',  # временная метка
                description=description
            )

            sess.add(photo)
            sess.flush()  # получаем ID фото, нужен для имени файла

            # 2. Копируем файл в хранилище
            try:
                # Генерируем целевой путь на основе appointment_id и photo.id
                target_path = self._generate_target_path(source_file_path, appointment_id, photo.id)
                # Создаём папку назначения, если её нет
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                shutil.copy2(source_file_path, target_path)

                self.logger.debug(
                    f"Файл скопирован: "
                    f"{source_file_path} -> {target_path}"
                )
                
            except Exception as e:
                # Если копирование не удалось — удаляем созданную запись
                # sess.delete(photo) # ненужен, так как дальше должен быть rollback
                # sess.commit()  # фиксируем удаление (чтобы не оставлять pending-запись)
                self.logger.exception(f"Ошибка копирования файла {source_file_path}: {e}")

                raise PhotoFileError(source_file_path, "копирование", str(e))

            # 3. Обновляем путь в записи на реальный относительный путь
            photo.file_path = os.path.relpath(target_path, self._storage_path)
            # при выходе из контекста произойдёт commit, сохраняющий изменения

            # dto_out = self._dto_class.from_orm(photo)
            dto_out = self.get_dto_out(photo)

            self.logger.info(
                f"Добавлено фото "
                f"id={dto_out.id} "
                f"к приёму {appointment_id}"
            )

            return dto_out
        
    # def get_photos_for_appointment(self, appointment_id: int, session: Optional[Session] = None) -> List[PhotoDTO]:
    #     """
    #     Возвращает список фотографий для указанного приёма.
    #     """
    #     self.logger.debug(f"Запрос фото для приёма id={appointment_id}")
    #     with self._session_scope(session) as sess:
    #         repo = self._get_repo(sess)
    #         photos = repo.get_by_appointment(appointment_id)
    #         # return [self._dto_class.from_orm(p) for p in photos]
    #         dto_out = [self._dto_class.from_orm(p) for p in photos]
    #         self.logger.info(f"Запрос фото для приёма id={appointment_id}. Получено {len(dto_out)} записей")
    #         return dto_out

    @AppLogger.get_instance(
        name = 'PhotoService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def get_photos_for_appointment(
        self, 
        appointment_id: int, 
        session: Optional[Session] = None
    ) -> List[PhotoDTO]:
        """
        Возвращает список фотографий для указанного приёма.

        1. Создаём сессию SQLAlchemy (если не указана, то создаем новую).
        2. Получаем репозиторий фотографий.
        3. Получаем список фотографий для указанного приёма.
        4. Создаём список DTO для фотографий.
        5. Если файл фотографии не существует на диске или имеет статус 'pending', то выводим предупреждение.
        6. Возвращаем список DTO для фотографий.
        """
        self.logger.debug(f"Запрос фото для приёма id={appointment_id}")

        # 1. Создаём сессию SQLAlchemy (если не указана, то создаем новую)
        with self._session_scope(session) as sess:
            # 2. Получаем репозиторий фотографий
            repo = self._get_repo(sess)
            
            # 3. Получаем список фотографий для указанного приёма
            photos = repo.get_by_appointment(appointment_id)
            
            # 4. Создаём список DTO для фотографий
            dtos = []
            for p in photos:
                full_path = os.path.join(self._storage_path, p.file_path)

                # 5. Если файл фотографии не существует на диске или имеет статус 'pending', то выводим предупреждение
                if p.file_path == 'pending':
                    self.logger.warning(f"Фото id={p.id} имеет статус 'pending' (файл не загружен)")

                elif not os.path.exists(full_path):
                    self.logger.warning(f"Файл фото id={p.id} отсутствует на диске: {full_path}")
                    
                # 6. Создаём DTO для фотографии и добавляем в список
                # dtos.append(self._dto_class.from_orm(p))
                dtos.append(self.get_dto_out(p))
            
            # 7. Возвращаем список DTO для фотографий
            self.logger.info(
                f"Запрос фото для приёма "
                f"id={appointment_id}. "
                f"Получено {len(dtos)} записей"
            )

            return dtos

    @AppLogger.get_instance(
        name = 'PhotoService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def delete_photo(
        self, 
        photo_id: int, 
        session: Optional[Session] = None
    ) -> None:
        """
        Удаляет фотографию: физический файл + запись в БД + связанные заметки (если есть).

        **Алгоритм:**
            1. Загружает запись `Photo` по `photo_id`.
            2. Определяет полный путь к файлу (`storage_path + относительный путь`).
            3. Удаляет физический файл через `self._del_file` (с поддержкой отложенного удаления).
            4. Удаляет запись из БД и очищает заметки (через `self._delete_entity`).

        **Важное предупреждение (для разработчиков!):**
            - **НИ В КОЕМ СЛУЧАЕ НЕ ЗАМЕНЯЙТЕ ТЕКУЩУЮ РЕАЛИЗАЦИЮ НА ВЫЗОВ `self.delete(photo_id, session)`!**
            - Причина: базовый метод `BaseService.delete` **уже содержит логику удаления файлов** для полей
            с `widget_type='image_thumbnail'` (к которым относится `file_path`). Если вызвать `self.delete` здесь,
            файл будет удалён **дважды**: один раз в `self._del_file` (см. код ниже) и ещё раз внутри `self.delete`.
            Это приведёт к ошибке при попытке удалить уже несуществующий файл.
            - Текущая реализация корректна: файл удаляется **один раз**, затем запись удаляется отдельно.
            - **Не переносите логику удаления файлов в `_delete_entity`** – это нарушит работу всех других сервисов,
            которые полагаются на то, что `_delete_entity` не трогает дисковые файлы.

        **Параметры:**
            photo_id (int): ID фотографии в БД.
            session (Optional[Session]): Опциональная сессия SQLAlchemy для работы в рамках внешней транзакции.
                Если не передана, создаётся новая сессия.

        **Возвращает:**
            None

        **Исключения:**
            PhotoNotFoundError: Если фото с указанным `photo_id` не существует.
            PhotoFileError: Если не удалось удалить физический файл (при немедленном удалении).
                При отложенном удалении ошибка не выбрасывается, а логируется в `after_commit`.

        **Пример использования:**
            >>> photo_service = get_photo_service()
            >>> try:
            ...     photo_service.delete_photo(123)
            ...     print("Фото удалено")
            ... except PhotoNotFoundError:
            ...     print("Фото не найдено")
            ... except PhotoFileError as e:
            ...     print(f"Ошибка удаления файла: {e}")

        **Примечания:**
            - Физический файл удаляется **до** удаления записи из БД. Это предотвращает ситуацию,
            когда запись удалена, а файл остался (из-за ошибки удаления файла транзакция откатится).
            - Благодаря использованию `_del_file`, при наличии активной сессии с поддержкой отложенного удаления,
            файл будет удалён только после успешного коммита, что сохраняет атомарность.
            - Если файл уже отсутствует на диске, метод всё равно удалит запись из БД (файл не мешает).
        """
        self.logger.debug(f"Удаление фото id={photo_id}")

        # 1. Создаём сессию SQLAlchemy (если не указана, то создаем новую)
        with self._session_scope(session) as sess:

            repo = self._get_repo(sess)
            photo = repo.get_by_id(photo_id)

            if photo is None:
                raise PhotoNotFoundError(photo_id)

            # ВНИМАНИЕ! НЕ ЗАМЕНЯТЬ СЛЕДУЮЩИЙ БЛОК НА ВЫЗОВ self.delete()!
            # Причина: self.delete() (базовый метод) уже содержит удаление файла для полей с фото
            # и вызов _delete_entity. Если вызвать self.delete() здесь, файл будет удалён дважды
            # (один раз здесь, другой внутри self.delete), что вызовет ошибку.
            # Текущая реализация удаляет файл один раз (через _del_file), а затем запись и заметки
            # через _delete_entity (который не трогает файл). Это корректно и атомарно.

            
            file_path = os.path.join(self._storage_path, photo.file_path)
            # Удаляем физический файл (или добавляем в отложенное удаление)
            err_text = self._del_file(
                file_path, 
                session = sess,
                if_delete_parent_dir = True,
            )
            if err_text is not None:
                raise PhotoFileError(file_path, "удаление", str(err_text))

            # if os.path.exists(file_path):
            #     if (sess is not None) and hasattr(sess, '_pending_deletions'):
            #         sess._pending_deletions.append(file_path)
            #         self.logger.debug(f"Добавлен файл в отложенное удаление: {file_path}")
            #     else:
            #         # Fallback – удаляем немедленно, но с предупреждением
            #         self.logger.warning("Сессия не поддерживает отложенное удаление, удаляю немедленно")
            #
            #         try:
            #             os.remove(file_path)
            #         except OSError as e:
            #             raise PhotoFileError(file_path, "удаление", str(e))
            # # Удаляем запись через базовый метод
            # self._delete_entity(photo_id, sess)

            # # удаляем запись
            # repo.delete(photo)

            # После удаления файла вызываем базовый метод для удаления записи
            # Важно: передаём ту же сессию, чтобы операция была атомарной
            self._delete_entity(photo_id, session=sess) # для повышения согласованности, упрощения будущие изменения и следует принципу единой ответственности в иерархии сервисов
 
            # # 2. Получаем репозиторий фотографий
            # repo = self._get_repo(sess)
            
            # # 3. Получаем фотографию по ID
            # photo = repo.get_by_id(photo_id)
            # if photo is None:
            #     err_ = PhotoNotFoundError(photo_id)
            #     self.logger.exception(err_.message)

            #     raise err_

            # # 4. Запоминаем путь к файлу до удаления записи
            # file_path_to_delete = os.path.join(self._storage_path, photo.file_path)

            # # 5. Пытаемся удалить файл
            # try:
            #     if os.path.exists(file_path_to_delete):
            #         os.remove(file_path_to_delete)
            #         self.logger.debug(f"Удалён файл {file_path_to_delete}")

            #         # попытка уделения папки для хранения фото от удалённого приёма
            #         # Проверяем, не стала ли родительская папка пустой
            #         parent_dir = os.path.dirname(file_path_to_delete)
            #         if os.path.exists(parent_dir) and not os.listdir(parent_dir):
            #             try:
            #                 os.rmdir(parent_dir)
            #                 self.logger.debug(f"Удалена пустая папка {parent_dir}")

            #             except OSError as e:
            #                 self.logger.warning(f"Не удалось удалить папку {parent_dir}: {e}")
                            
            # except Exception as e:
            #     self.logger.exception(f"Не удалось удалить файл {file_path_to_delete}: {e}")
            #     raise PhotoFileError(file_path_to_delete, "удаление", str(e))

            # # 6. Если файл успешно удалён (или не существовал), удаляем запись
            # repo.delete(photo)  # Удаляем запись
            # self.logger.info(f"Удалена запись фото id={photo_id}")

    # ----------------------------------------------------------------------
    # Вспомогательные методы (не требуют сессии)
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'PhotoService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(   
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def _generate_target_path(
        self, 
        source_path: str, 
        appointment_id: int, 
        photo_id: int
    ) -> str:
        """
        Генерирует полный путь для сохранения файла на основе appointment_id и photo_id.

        Формат: <storage>/app_<appointment_id>/<photo_id>_<name(base_name)>_<unique_id>_<ext(base_name)>

        <storage> - путь к папке для хранения файлов
        app_<appointment_id> - папка для хранения файлов приёма с указанным ID
        <photo_id>_<name(base_name)>_<unique_id>_<ext(base_name)> - имя файла

        <name(base_name)> - имя файла без расширения (например, "image")
        <unique_id> - уникальный идентификатор (например, "12345678")
        <ext(base_name)> - расширение файла (например, ".jpg")

        1. Получаем имя файла и его расширение
        2. Генерируем уникальный идентификатор
        3. Создаем имя файла для хранения
        4. Создаем полный путь к файлу
        """
        # 1. Получаем имя файла и его расширение
        base_name = os.path.basename(source_path)
        name, ext = os.path.splitext(base_name)

        # 2. Генерируем уникальный идентификатор
        unique_id = uuid.uuid4().hex[:8]  # первые 8 символов UUID

        # 3. Создаем имя файла для хранения
        filename = f"{photo_id}_{name}_{unique_id}{ext}"

        # 4. Создаем полный путь к файлу
        app_folder = os.path.join(self._storage_path, f"app_{appointment_id}")

        return os.path.join(app_folder, filename)

    @AppLogger.get_instance(
        name = 'PhotoService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(      
        level=AppLogger._parse_log_level('DEBUG')
    )  
    def _ensure_storage_exists(self):
        """Создаёт папку для фото, если её нет."""
        os.makedirs(self._storage_path, exist_ok=True)

    @AppLogger.get_instance(
        name='PhotoService',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def update_photos_for_appointment(
        self,
        appointment_id: int,
        pending_photos: List[Tuple[str, str]],  # (file_path, description)
        deleted_photo_ids: List[int],
        session: Optional[Session] = None  # опциональная сессия для работы в одной транзакции
    ) -> None:
        """
        Обновляет фото для указанного приёма:
        - удаляет фото из списка deleted_photo_ids
        - добавляет новые фото из списка pending_photos

        :param appointment_id: ID приёма
        :param pending_photos: список кортежей (file_path, description) для добавления
        :param deleted_photo_ids: список ID фото для удаления
        :param session: опциональная сессия для работы в одной транзакции
        """
        # Создаем сессию для работы в одной транзакции, если она не была передана
        with self._session_scope(session) as sess:

            # Удаляем фото из списка deleted_photo_ids
            for photo_id in deleted_photo_ids:
                self.delete_photo(photo_id, session=sess)

            # Добавляем новые фото из списка pending_photos
            for file_path, description in pending_photos:
                self.add_photo_to_appointment(
                    appointment_id, file_path, description, session=sess
                )
    
    # внутри класса PhotoService, после метода __init__ или в любом месте

    @AppLogger.get_instance(
        name='PhotoService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def reload_config(self) -> None:
        """Перезагружает путь к хранилищу фото и пересоздаёт Database."""
        # from app.config.config_manager.manager import AppConfigManager

        super().reload_config()

        # from app.dependencies import get_appointment_service # оставить тут, так как циклы
        # self._appointment_service = get_appointment_service()

        config = AppConfigManager.get_instance()

        new_path = config.get('PHOTOS_STORAGE_PATH', os.path.join('.', 'photos'))
        self._storage_path = new_path  # обновляем путь к хранилищу фото

        self._ensure_storage_exists()  # создаём директорию для хранения,

        self.logger.info(f"Путь к фото обновлён: {self._storage_path}")

    @AppLogger.get_instance(
        name='PhotoService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _get_note_service(self) -> Optional['NoteService']:
        return None
    


