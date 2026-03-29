# -*- coding: utf-8 -*-
"""
Миксин для подключения всех сигналов между страницами и главным окном.
"""

from app.utils.logger.logger import AppLogger


class ConnectionsMixin:
    """
    Миксин, содержащий методы для связывания сигналов страниц с действиями.
    """

    @AppLogger.get_instance(
        name='ConnectionsMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _connect_signals(self):
        """
        Подключает основные сигналы главного окна:
            - кнопка "Назад"
            - кнопка "Настройки"
            - выбор действия в комбобоксе
            - сигналы менеджера страниц (навигация, вход на страницу)
        """
        # Кнопка возврата на предыдущую страницу
        self.back_btn.clicked.connect(self._on_back_clicked)

        # Кнопка открытия страницы настроек
        self.settings_btn.clicked.connect(self._on_settings_clicked)

        # Выбор действия из выпадающего списка (скачать, сохранить, отправить)
        self.action_combo.currentIndexChanged.connect(self._on_action_selected)

        # Сигналы от менеджера страниц
        self.page_manager.navigation_changed.connect(self._on_navigation_changed)
        self.page_manager.page_entered.connect(self._on_page_entered)

    @AppLogger.get_instance(
        name='ConnectionsMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _connect_page_signals(self):
        """
        Связывает сигналы всех страниц (списков и редактирования) с методами-обработчиками.
        """
        self._connect_patient()
        self._connect_appointment()
        self._connect_note()
        self._connect_photo()

    @AppLogger.get_instance(
        name='ConnectionsMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _connect_patient(self):
        """
        Подключает сигналы страницы списка пациентов:
            - add_requested → переход на страницу создания пациента
            - edit_requested → переход на страницу редактирования с переданным DTO
            - delete_requested → вызов обработчика удаления
            - action_requested → переход к списку приёмов выбранного пациента
        """
        # Добавление нового пациента
        self.patient_list_page.add_requested.connect(
            lambda: self.page_manager.switch_to('patient_edit', extra_data=None)
        )
        # Редактирование существующего пациента
        self.patient_list_page.edit_requested.connect(
            lambda dto: self.page_manager.switch_to(
                'patient_edit',
                extra_data={'id': dto.id}
            )
        )
        # Удаление пациента
        self.patient_list_page.delete_requested.connect(self._on_patient_delete)
        # Дополнительное действие: показать приёмы пациента
        self.patient_list_page.action_requested.connect(self._on_patient_appointments_requested)

    @AppLogger.get_instance(
        name='ConnectionsMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _connect_appointment(self):
        """
        Подключает сигналы страницы списка приёмов:
            - add_requested → переход на страницу создания приёма (с patient_id, если есть)
            - edit_requested → переход на страницу редактирования
            - delete_requested → вызов обработчика удаления
        """
        # Добавление нового приёма (если в extra_data есть patient_id, он будет передан)
        self.appointment_list_page.add_requested.connect(
            lambda: self.page_manager.switch_to(
                'appointment_edit',
                extra_data={
                    'patient_id': self.appointment_list_page.current_extra.get('patient_id')
                    if self.appointment_list_page.current_extra else None
                }
            )
        )
        # Редактирование приёма
        self.appointment_list_page.edit_requested.connect(
            lambda dto: self.page_manager.switch_to(
                'appointment_edit',
                extra_data={'id': dto.id}
            )
        )
        # Удаление приёма
        self.appointment_list_page.delete_requested.connect(self._on_appointment_delete)

    @AppLogger.get_instance(
        name='ConnectionsMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _connect_note(self):
        """
        Подключает сигналы страницы списка заметок:
            - add_requested → переход на страницу создания заметки
            - edit_requested → переход на страницу редактирования
            - delete_requested → вызов обработчика удаления
        """
        self.note_list_page.add_requested.connect(
            lambda: self.page_manager.switch_to('note_edit', extra_data=None)
        )
        self.note_list_page.edit_requested.connect(
            lambda dto: self.page_manager.switch_to(
                'note_edit',
                extra_data={'id': dto.id}
            )
        )
        self.note_list_page.delete_requested.connect(self._on_note_delete)

    @AppLogger.get_instance(
        name='ConnectionsMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _connect_photo(self):
        """
        Подключает сигналы страницы списка фотографий:
            - add_requested → переход на страницу создания фото
            - edit_requested → переход на страницу редактирования
            - delete_requested → вызов обработчика удаления
        """
        self.photo_list_page.add_requested.connect(
            lambda: self.page_manager.switch_to('photo_edit', extra_data=None)
        )
        self.photo_list_page.edit_requested.connect(
            lambda dto: self.page_manager.switch_to(
                'photo_edit',
                extra_data={'id': dto.id}
            )
        )
        self.photo_list_page.delete_requested.connect(self._on_photo_delete)