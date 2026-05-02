# app/config/config_applier.py

"""
Централизованное применение настроек.
Может использоваться GUI, CLI, веб-приложением.
"""

import os
from typing import (
    Dict, Any, Set,
    # Optional
)

from app.utils.logger.logger import AppLogger

from app.config.config_manager.manager import AppConfigManager
# from app.database import Database
# from app.services import PhotoService, SyncService
from app.dependencies import (
    get_sync_service, get_db, get_patient_service,
    get_appointment_service, get_note_service, get_photo_service
)


class ConfigApplier:
    """
    Класс, отвечающий за применение изменений конфигурации.
    Каждый метод принимает словарь новых настроек и применяет их,
    если соответствующий блок изменился.
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
    def get_changed_blocks(old_config: Dict[str, Any], new_config: Dict[str, Any]) -> Set[str]:
        """
        Определяет, какие блоки настроек изменились.
        Блоки определяются по префиксам ключей.
        """
        blocks = {
            'database': ['database_local_path', 'database_remote_path'],
            'photos': ['PHOTOS_STORAGE_PATH'],
            'sync': ['YANDEX_TOKEN', 'database_remote_path', 'database_local_path'],
            'logging_system': [
                'system_enabled', 'system_console_enabled',
                'system_file_enabled', 'system_LEVEL'
            ],
            'logging_user': [
                'user_enabled', 'user_console_enabled',
                'user_file_enabled', 'user_LEVEL'
            ],
            'logging_common': [
                'LOG_DIR', 'LOG_LEVEL',
                'LOG_MAX_BYTES', 'LOG_BACKUP_COUNT',
                'use_timestamp', 'show_call_depth'
            ],
            'backup': ['BACKUP_PATH', 'BACKUP_COUNT'],
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
        # Перезагружаем все сервисы, зависящие от БД
        for i in [
            get_patient_service,
            get_appointment_service,
            get_note_service,
            get_photo_service,
        ]:
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
    def apply_photos_storage(self, new_config: Dict[str, Any]) -> bool:
        """Применяет новый путь к хранилищу фото."""
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
        new_config,
        key,
    ):
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
        """Применяет настройки синхронизации (токен, удалённый путь)."""
        changed = False
        sync_service = get_sync_service()

        rez, changed_ = self._thec_update_key_config(
            new_config, 'YANDEX_TOKEN'
        )
        if changed_:
            sync_service.token = rez
            changed = changed_

        rez, changed_ = self._thec_update_key_config(
            new_config, 'database_remote_path'
        )
        if changed_:
            sync_service.remote_path = rez
            changed = changed_

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
    def apply_logging(self, new_config: Dict[str, Any]) -> bool:
        """Применяет все настройки логирования (системный, пользовательский, общие)."""

        # Получаем текущую полную конфигурацию логгеров (загружаем свежую из менеджера)
        current_full = self.manager.get_all()

        # Определяем, изменился ли хотя бы один параметр логирования
        logging_keys = [
            'system_enabled', 'system_console_enabled', 'system_file_enabled', 'system_LEVEL',
            'user_enabled', 'user_console_enabled', 'user_file_enabled', 'user_LEVEL',
            'LOG_DIR', 'LOG_LEVEL', 'LOG_MAX_BYTES', 'LOG_BACKUP_COUNT', 'use_timestamp', 'show_call_depth'
        ]

        changed = any(new_config.get(k) != current_full.get(k) for k in logging_keys if k in new_config)
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
    def apply_backup(self, new_config: Dict[str, Any]) -> bool:
        """Применяет настройки бекапов (пока только сохраняет, логика бекапов может быть добавлена позже)."""
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
        Применяет все настройки из словаря (аналог on_settings_changed).
        Вызывается после того, как новые значения уже сохранены в менеджере.
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
