# -*- coding: utf-8 -*-
"""
Миксин для навигации между страницами и обновления хлебных крошек.
"""

from app.utils.logger.logger import AppLogger
from PySide6.QtCore import Slot


class NavigationMixin:
    """
    Миксин, отвечающий за обработку навигационных действий:
        - кнопка "Назад"
        - кнопка "Настройки"
        - переход к списку приёмов пациента
        - обновление хлебных крошек и состояния кнопки "Назад"
    """

    @AppLogger.get_instance(
        name='NavigationMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _on_back_clicked(self):
        """Возврат на предыдущую страницу через PageManager."""
        self.page_manager.go_back()

    @AppLogger.get_instance(
        name='NavigationMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _on_settings_clicked(self):
        """Переход на страницу настроек."""
        self.page_manager.switch_to('settings')

    @AppLogger.get_instance(
        name='NavigationMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_patient_appointments_requested(self, patient_dto):
        """
        Переход к списку приёмов выбранного пациента.
        Передаётся patient_id в extra_data для фильтрации списка.
        """
        self.page_manager.switch_to(
            'appointment_list',
            extra_data={'patient_id': patient_dto.id}
        )

    @AppLogger.get_instance(
        name='NavigationMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(list, str)
    def _on_navigation_changed(self, history, current_page_id):
        """
        Обновляет хлебные крошки и состояние кнопки "Назад" при изменении навигации.
        """
        # Собираем заголовки страниц из истории
        titles = [title for _, title in history]
        # Добавляем заголовок текущей страницы
        if current_page_id:
            current_title = self.page_manager._get_page_title(current_page_id)
            titles.append(current_title)

        # Формируем строку с разделителем " > "
        crumbs = " > ".join(titles) if titles else "Главная"
        self.breadcrumbs_label.setText(crumbs)

        # Кнопка "Назад" активна, только если есть история
        self.back_btn.setEnabled(len(history) > 0)

    @AppLogger.get_instance(
        name='NavigationMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(str, object)
    def _on_page_entered(self, page_id, extra_data):
        """
        Вызывается при входе на страницу. Передаёт extra_data в метод on_enter страницы.
        """
        page = self.page_manager._pages.get(page_id)
        if page and hasattr(page, 'on_enter'):
            try:
                page.on_enter(extra_data)
            except Exception as e:
                self.logger.exception(f"Ошибка в on_enter страницы {page_id}: {e}")
                raise e