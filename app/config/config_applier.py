# app/config/config_applier.py
"""
Централизованное применение настроек приложения.

Этот модуль предоставляет класс :class:`ConfigApplier`, который отвечает за
применение изменений конфигурации после их сохранения в `AppConfigManager`.
Каждый блок настроек (БД, фото, синхронизация, логирование, бекапы)
обрабатывается отдельным методом, который проверяет, изменились ли
соответствующие параметры, и выполняет только необходимые действия.

Основное назначение:
    - Избегать лишних перезагрузок (например, не пересоздавать БД, если путь не изменился).
    - Централизовать логику применения настроек для повторного использования в GUI, CLI и других интерфейсах.
    - Упростить добавление новых блоков настроек в будущем.

Пример использования в GUI:
    old_config = config_manager.get_all().copy()
    # ... сохранить новые значения в config_manager ...
    config_manager.save()
    new_config = config_manager.get_all()
    changed_blocks = ConfigApplier.get_changed_blocks(old_config, new_config)
    applier = ConfigApplier()
    if 'database' in changed_blocks:
        applier.apply_database(new_config)
    if 'photos' in changed_blocks:
        applier.apply_photos_storage(new_config)
    # ... и т.д.

Пример использования в CLI:
    applier = ConfigApplier()
    applier.apply_full_config(config_manager.get_all())
"""

# import os
from typing import (
    Dict, Any, Set,
    # Optional
)

from app.utils.logger.logger import AppLogger

from app.config.config_manager.manager import AppConfigManager
# from app.database import Database
# from app.services import PhotoService, SyncService
from app.dependencies import (
    _SERVICE_PROVIDERS,
    get_sync_service,
    # get_db,
    get_patient_service,
    get_appointment_service, get_note_service, get_photo_service
)


class ConfigApplier:
    """
    Класс для применения изменений конфигурации по блокам.

    Каждый метод-применитель (apply_xxx) принимает словарь с новыми настройками
    (обычно тот же, что вернул `AppConfigManager.get_all()` после сохранения)
    и применяет изменения, если соответствующие параметры действительно изменились.

    Все методы возвращают `bool` – `True`, если были выполнены какие-либо действия
    (например, перезагрузка БД), и `False`, если ничего не изменилось.

    Атрибуты:
        manager (AppConfigManager): Экземпляр менеджера конфигурации.
        logger (AppLogger): Логгер для записи событий.
    """

    @AppLogger.get_instance(
        name = 'ConfigApplier',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self):
        """
        Инициализирует объект ConfigApplier.

        Получает текущий экземпляр `AppConfigManager` и создаёт логгер с именем
        'config_applier'. Логгер будет использовать системные настройки логирования.

        Returns:
            None
        """

        self.manager = AppConfigManager.get_instance()

        self.logger = AppLogger.get_instance('config_applier')

    @staticmethod
    @AppLogger.get_instance(
        name = 'ConfigApplier',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def get_changed_blocks(
        old_config: Dict[str, Any],
        new_config: Dict[str, Any],
    ) -> Set[str]:
        """
        Определяет, какие блоки настроек изменились между двумя конфигурациями.

        Блоки определяются по набору ключей (см. внутренний словарь `blocks`).
        Если хотя бы один ключ из блока отличается в `new_config` по сравнению с
        `old_config`, весь блок считается изменённым.

        Параметры:
            old_config (Dict[str, Any]): Предыдущая конфигурация (словарь).
            new_config (Dict[str, Any]): Новая конфигурация (словарь).

        Returns:
            Set[str]: Множество строк – названий блоков, которые изменились.
                      Возможные значения: 'database', 'photos', 'sync',
                      'logging_system', 'logging_user', 'logging_common', 'backup'.

        Пример:
            >>> old = {'database_local_path': './clinic.db', 'PHOTOS_STORAGE_PATH': './photos'}
            >>> new = {'database_local_path': './clinic_new.db', 'PHOTOS_STORAGE_PATH': './photos'}
            >>> ConfigApplier.get_changed_blocks(old, new)
            {'database'}
        """

        blocks = {
            'database': [
                'database_local_path', 'database_remote_path',
            ],
            'photos': [
                'PHOTOS_STORAGE_PATH',
            ],
            'sync': [
                'YANDEX_TOKEN',
                'database_remote_path', 'database_local_path',
            ],
            'logging_system': [
                'system_enabled', 'system_console_enabled',
                'system_file_enabled', 'system_LEVEL',
            ],
            'logging_user': [
                'user_enabled', 'user_console_enabled',
                'user_file_enabled', 'user_LEVEL',
            ],
            'logging_common': [
                'LOG_DIR', 'LOG_LEVEL',
                'LOG_MAX_BYTES', 'LOG_BACKUP_COUNT',
                'use_timestamp', 'show_call_depth',
            ],
            'backup': [
                'BACKUP_PATH', 'BACKUP_COUNT',
            ],
        }

        changed = set()

        for block, keys in blocks.items():
            for key in keys:
                if old_config.get(key) != new_config.get(key):
                    changed.add(block)
                    break

        return changed

    # ----------------------------------------------------------------------
    # Применение отдельных блоков
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'ConfigApplier',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def apply_database(self, new_config: Dict[str, Any]) -> bool:
        """Применяет настройки БД (путь к файлу). Возвращает True, если БД была пересоздана."""
        """
        Применяет настройки, связанные с путём к файлу базы данных.

        Если путь `database_local_path` изменился, перезагружает все сервисы,
        зависящие от БД (PatientService, AppointmentService, NoteService, PhotoService).
        Сервисы вызывают `reload_config()`, который закрывает старый `Database`
        и создаёт новый с обновлённым путём.

        Параметры:
            new_config (Dict[str, Any]): Словарь с новыми настройками (должен содержать ключ 'database_local_path').

        Returns:
            bool: `True`, если путь изменился и БД была перезагружена;
                  `False`, если путь не изменился (или отсутствует).

        Примечание:
            Сервисы также подписаны на изменения конфигурации через
            `AppConfigManager.add_change_listener`, поэтому этот метод может
            вызывать `reload_config()` дважды. Однако это не ломает логику,
            а лишь добавляет небольшой оверхед.
        """

        old_path = self.manager.get('database_local_path')
        new_path = new_config.get('database_local_path')

        if new_path is None or new_path == old_path:
            return False

        self.logger.info(f"Изменение пути к БД: {old_path} -> {new_path}")

        # Обновляем менеджер (это уже сделано до вызова)

        # # Перезагружаем сервисы, использующие БД
        # # from app.dependencies import get_db, get_patient_service, get_appointment_service, get_note_service, get_photo_service
        # # Закрываем старую БД и создаём новую
        # следующее - ненужно, так как в reload_config - есть
        # db = get_db()
        # db.close()

        # Новая БД будет создана при следующем get_db()
        

        # Сбрасываем кэш синглтон-сервисов, чтобы при следующем вызове get_* создались новые экземпляры
        from app.dependencies import clear_services_cache # оставить тут, так как циклы
        clear_services_cache()

        # Перезагружаем все сервисы, зависящие от БД
        # for i in [
        #     get_patient_service,
        #     get_appointment_service,
        #     get_note_service,
        #     get_photo_service,
        # ]:
        for i in _SERVICE_PROVIDERS:
            i().reload_config()

        return True

    @AppLogger.get_instance(
        name = 'ConfigApplier',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def apply_photos_storage(
        self,
        new_config: Dict[str, Any]
    ) -> bool:
        """
        Применяет новый путь к хранилищу фотографий.

        Обновляет путь в `PhotoService` (через свойство `_storage_path`)
        и создаёт новую директорию, если она не существует.
        Сами виджеты фотографий (`PhotoUploaderWidget`) обновляют пути отдельно
        через `MainWindow.on_settings_changed` (по сигналу).

        Параметры:
            new_config (Dict[str, Any]): Словарь с новыми настройками (должен содержать
                                        ключ 'PHOTOS_STORAGE_PATH').

        Returns:
            bool: `True`, если путь изменился и хранилище обновлено;
                  `False`, если путь не изменился (или отсутствует).
        """

        old_path = self.manager.get('PHOTOS_STORAGE_PATH')
        new_path = new_config.get('PHOTOS_STORAGE_PATH')

        if new_path is None or new_path == old_path:
            return False

        self.logger.info(f"Изменение пути к фото: {old_path} -> {new_path}")

        # Обновляем путь в сервисе и виджетах
        photo_service = get_photo_service()

        photo_service._storage_path = new_path
        photo_service._ensure_storage_exists()

        # Сигнал для виджетов будет отправлен из MainWindow отдельно

        return True
    def _thec_update_key_config(
        self,
        new_config: Dict[str, Any],
        key: str,
    ) -> tuple[bool, Any]:
        """
        Вспомогательный метод для проверки изменения значения по ключу.

        Сравнивает значение ключа в `new_config` с текущим значением в менеджере.
        Если изменилось, возвращает `(True, новое_значение)`, иначе `(False, None)`.

        Параметры:
            new_config (Dict[str, Any]): Словарь с новыми настройками.
            key (str): Имя ключа для проверки.

        Returns:
            tuple[bool, Any]: (изменилось, новое_значение). Если не изменилось, новое_значение равно `None`.
        """

        changed = False
        rezult = None

        old_token = self.manager.get(key)
        new_token = new_config.get(key)

        if new_token is not None and new_token != old_token:
            rezult = new_token
            changed = True

        return changed, rezult

    @AppLogger.get_instance(
        name = 'ConfigApplier',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def apply_sync(self, new_config: Dict[str, Any]) -> bool:
        """
        Применяет настройки синхронизации с Яндекс.Диском.

        Проверяет изменения в ключах 'YANDEX_TOKEN', 'database_remote_path'
        и 'database_local_path'. При изменении обновляет соответствующие атрибуты
        в глобальном экземпляре `SyncService`.

        Параметры:
            new_config (Dict[str, Any]): Словарь с новыми настройками.

        Returns:
            bool: `True`, если хотя бы один параметр синхронизации изменился;
                  `False` в противном случае.
        """

        changed = False
        sync_service = get_sync_service()

        # Токен
        rez, changed_ = self._thec_update_key_config(
            new_config, 'YANDEX_TOKEN'
        )
        if changed_:
            sync_service.token = rez
            changed = changed_

        # Удалённый путь БД
        rez, changed_ = self._thec_update_key_config(
            new_config, 'database_remote_path'
        )
        if changed_:
            sync_service.remote_path = rez
            changed = changed_

        # Локальный путь БД
        rez, changed_ = self._thec_update_key_config(
            new_config, 'database_local_path'
        )
        if changed_:
            sync_service.local_path = rez
            changed = changed_

        if changed:
            self.logger.info("Настройки синхронизации обновлены")

        return changed

    @AppLogger.get_instance(
        name = 'ConfigApplier',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def apply_logging(
        self,
        new_config: Dict[str, Any]
    ) -> bool:
        """
        Применяет все настройки логирования (системный, пользовательский, общие).

        Сравнивает ключи, перечисленные в `logging_keys`, между текущей
        конфигурацией (`self.manager.get_all()`) и `new_config`. Если хотя бы один
        из них изменился, перезагружает все логгеры через
        `AppLogger.reload_all_from_app_config()`.

        Параметры:
            new_config (Dict[str, Any]): Словарь с новыми настройками.

        Returns:
            bool: `True`, если настройки логирования изменились и логгеры перезагружены;
                  `False` в противном случае.
        """

        # Получаем текущую полную конфигурацию логгеров (загружаем свежую из менеджера)
        current_full = self.manager.get_all()

        # Определяем, изменился ли хотя бы один параметр логирования
        logging_keys = [
            'system_enabled', 'system_console_enabled', 'system_file_enabled', 'system_LEVEL',
            'user_enabled', 'user_console_enabled', 'user_file_enabled', 'user_LEVEL',
            'LOG_DIR', 'LOG_LEVEL', 'LOG_MAX_BYTES', 'LOG_BACKUP_COUNT', 'use_timestamp',
            'show_call_depth'
        ]

        changed = any(
            new_config.get(k) != current_full.get(k)
            for k in logging_keys
            if k in new_config
        )
        if changed:
            self.logger.info("Применение новых настроек логирования")
            # Перезагружаем все логгеры через AppLogger
            AppLogger.reload_all_from_app_config()

        return changed

    @AppLogger.get_instance(
        name = 'ConfigApplier',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def apply_backup(
        self,
        new_config: Dict[str, Any]
    ) -> bool:
        """
        Применяет настройки бекапов (путь и количество).

        На данный момент только логирует изменённые параметры.
        В будущем здесь можно добавить реальную логику (например, очистку старых бекапов).

        Параметры:
            new_config (Dict[str, Any]): Словарь с новыми настройками (ключи
                                        'BACKUP_PATH' и 'BACKUP_COUNT').

        Returns:
            bool: `True`, если хотя бы один параметр бекапов изменился;
                  `False` в противном случае.
        """

        old_path = self.manager.get('BACKUP_PATH')
        new_path = new_config.get('BACKUP_PATH')

        old_count = self.manager.get('BACKUP_COUNT')
        new_count = new_config.get('BACKUP_COUNT')

        if new_path != old_path or new_count != old_count:
            self.logger.info(f"Обновлены настройки бекапов: путь={new_path}, кол-во={new_count}")
            # Здесь можно добавить вызов метода для применения (например, очистка старых бекапов)
            return True

        return False

    # ----------------------------------------------------------------------
    # Главный метод применения полного конфига (для CLI/веб)
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'ConfigApplier',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def apply_full_config(self, new_config: Dict[str, Any]) -> None:
        """
        Применяет все настройки из словаря, вызывая все методы `apply_xxx`.

        Этот метод полезен для CLI или веб-приложений, когда нет необходимости
        различать изменившиеся блоки (или когда конфигурация полностью перезаписывается).

        Каждый метод-применитель сам проверяет, изменились ли его параметры,
        и выполняет действия только при необходимости.

        (Вызывается после того, как новые значения уже сохранены в менеджере)

        Параметры:
            new_config (Dict[str, Any]): Словарь с новыми настройками (полная конфигурация).

        Returns:
            None

        Пример:
            manager = AppConfigManager.get_instance()
            manager.save()  # предполагаем, что новые значения уже установлены
            applier = ConfigApplier()
            applier.apply_full_config(manager.get_all())
        """

        # Определяем, какие блоки изменились по сравнению с менеджером до сохранения?
        # Для этого нужен старый конфиг. Проще: сохранить старый конфиг перед вызовом,
        # но в данном методе мы будем полагаться на то, что изменения уже в менеджере,
        # а вызывающий код знает, что изменилось. Поэтому здесь просто применяем всё
        # подряд, но методы проверяют изменения сами.

        self.apply_logging(new_config)
        self.apply_database(new_config)
        self.apply_photos_storage(new_config)
        self.apply_sync(new_config)
        self.apply_backup(new_config)
