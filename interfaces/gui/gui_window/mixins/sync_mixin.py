# -*- coding: utf-8 -*-
"""
Миксин для синхронизации базы данных с Яндекс.Диском.
Содержит методы запуска скачивания/загрузки, обновления прогресса и обработки завершения.
"""

from app.utils.logger.logger import AppLogger
from app.config.config_manager.manager import AppConfigManager
from app.network import DownloadThread, UploadThread
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QMessageBox


class SyncMixin:
    """
    Миксин, реализующий асинхронную загрузку и выгрузку БД с Яндекс.Диска.
    Использует отдельные потоки (QThread) для неблокирующей работы.
    """

    @AppLogger.get_instance(
        name='SyncMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(int)
    def _on_action_selected(self, index):
        """
        Обработчик выбора действия в комбобоксе.
            index 0 → скачать БД
            index 1 → сохранить изменения (пока заглушка)
            index 2 → отправить БД на сервер
        """
        if index == 0:
            self._start_download()
        elif index == 1:
            self._save_changes()
        elif index == 2:
            self._start_upload()
        # Сбрасываем выбранный индекс, чтобы можно было повторно выбрать то же действие
        self.action_combo.setCurrentIndex(-1)

    @AppLogger.get_instance(
        name='SyncMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _start_download(self):
        """
        Запускает поток скачивания файла БД с Яндекс.Диска.
        Перед запуском проверяет наличие токена.
        """
        config = AppConfigManager.get_instance()
        token = config.get('YANDEX_TOKEN')
        remote = config.get('database_remote_path')
        local = config.get('database_local_path')

        if not token:
            QMessageBox.warning(self, "Ошибка", "Не задан токен Яндекс.Диска.")
            return

        # Создаём и настраиваем поток загрузки
        self.download_thread = DownloadThread(token, remote, local)
        self.download_thread.progress.connect(self._update_progress)
        self.download_thread.finished.connect(self._on_download_finished)
        self.download_thread.error.connect(self._on_download_error)

        # Показываем прогресс-бар (бесконечный режим до получения размера)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        self.download_thread.start()
        self.logger.info("Запущен поток скачивания БД")

    @AppLogger.get_instance(
        name='SyncMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _start_upload(self):
        """
        Запускает поток загрузки локального файла БД на Яндекс.Диск.
        """
        config = AppConfigManager.get_instance()
        token = config.get('YANDEX_TOKEN')
        remote = config.get('database_remote_path')
        local = config.get('database_local_path')

        if not token:
            QMessageBox.warning(self, "Ошибка", "Не задан токен Яндекс.Диска.")
            return

        self.upload_thread = UploadThread(token, local, remote)
        self.upload_thread.progress.connect(self._update_progress)
        self.upload_thread.finished.connect(self._on_upload_finished)
        self.upload_thread.error.connect(self._on_upload_error)

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        self.upload_thread.start()
        self.logger.info("Запущен поток загрузки БД")

    @AppLogger.get_instance(
        name='SyncMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(int, int)
    def _update_progress(self, current, total):
        """
        Обновляет прогресс-бар в соответствии с текущим и общим размером.
        Если total == 0, переводим бар в режим "безлимитного" прогресса.
        """
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        else:
            self.progress_bar.setRange(0, 0)   # бесконечная анимация

    @AppLogger.get_instance(
        name='SyncMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(int)
    def _on_download_finished(self, code):
        """
        Обработчик завершения скачивания.
        Скрывает прогресс-бар и выводит сообщение об успехе или ошибке.
        """
        self.progress_bar.setVisible(False)
        if code == 0:
            QMessageBox.information(self, "Успех", "База данных успешно скачана.")
            # После скачивания можно обновить текущие страницы, если нужно
        else:
            QMessageBox.critical(self, "Ошибка", f"Скачивание завершилось с кодом {code}")

    @AppLogger.get_instance(
        name='SyncMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(str)
    def _on_download_error(self, message):
        """
        Обработчик ошибки в потоке скачивания.
        """
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Ошибка", message)

    @AppLogger.get_instance(
        name='SyncMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(int)
    def _on_upload_finished(self, code):
        """
        Обработчик завершения загрузки на диск.
        """
        self.progress_bar.setVisible(False)
        if code == 0:
            QMessageBox.information(self, "Успех", "База данных успешно загружена.")
        else:
            QMessageBox.critical(self, "Ошибка", f"Загрузка завершилась с кодом {code}")

    @AppLogger.get_instance(
        name='SyncMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(str)
    def _on_upload_error(self, message):
        """
        Обработчик ошибки в потоке загрузки.
        """
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Ошибка", message)

    @AppLogger.get_instance(
        name='SyncMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _save_changes(self):
        """
        Заглушка для сохранения изменений в локальной БД.
        В текущей версии не реализовано.
        """
        self.logger.info("Сохранение изменений (заглушка)")
        QMessageBox.information(self, "Информация", "Функция сохранения изменений пока не реализована.")

    # Вспомогательные методы управления прогресс-баром (могут вызываться извне)
    def show_progress(self, visible=True):
        """Показать или скрыть прогресс-бар."""
        self.progress_bar.setVisible(visible)

    def set_progress_range(self, minimum, maximum):
        """Установить диапазон значений прогресс-бара."""
        self.progress_bar.setRange(minimum, maximum)

    def set_progress_value(self, value):
        """Установить текущее значение прогресса."""
        self.progress_bar.setValue(value)