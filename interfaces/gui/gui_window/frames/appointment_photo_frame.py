# interfaces/gui/gui_window/frames/appointment_photo_frame.py
"""
Страница для работы с приёмами и их фотографиями.
Содержит две таблицы: слева – приёмы, справа – фото выбранного приёма.
Использует общий реестр черновиков для согласованного сохранения.
"""

from app.utils.logger.logger import AppLogger

from app.dependencies import get_patient_service

from app.dto.dto_all import PatientDTO
from app.dto.field_configs import PATIENT_CONFIG

from app.draft.draft_registry import DraftRegistry

from interfaces.gui.gui_window.pages.base_page import BasePage

from interfaces.gui.gui_window.pages.dynamic_edit_page import DynamicEditPage
from interfaces.gui.gui_window.pages.paginated_appointment_list_page import PaginatedAppointmentListPage
from interfaces.gui.gui_window.pages.paginated_photo_list_page import PaginatedPhotoListPage

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, 
    QMessageBox, QPushButton, 
    QVBoxLayout, QSplitter, 
    QWidget, 
)
from PySide6.QtCore import (
    Qt, 
)

class AppointmentPhotoFrame(BasePage):
    """
    Страница, объединяющая список приёмов и список фото выбранного приёма.

    Особенности:
        - При выборе строки в таблице приёмов справа отображаются фото этого приёма.
        - Обе таблицы используют общий DraftRegistry для согласованного сохранения черновиков.
        - Встроенные кнопки таблиц отключены (show_controls=[]), все действия выносятся
          на уровень этой страницы (например, через ActionManager).

    Атрибуты:
        _draft_registry (DraftRegistry): Общий реестр черновиков.
        appointment_page (PaginatedAppointmentListPage): Таблица приёмов.
        photo_page (PaginatedPhotoListPage): Таблица фото.
    """

    @AppLogger.get_instance(
        name='AppointmentPhotoFrame',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def __init__(
        self, 
        parent=None, 
        shared_registry = None
    ):
        """
        Инициализирует страницу.

        Args:
            parent: Родительский виджет (обычно MainWindow).
            shared_registry: Опциональный общий реестр черновиков.
                Если не передан, создаётся локальный реестр.
        """

        super().__init__(parent)

        self.page_title = "Приёмы и фото"

        self._draft_registry = shared_registry or DraftRegistry(self)  # общий реестр для обеих таблиц

        self._current_patient_id = None 

        # Создаём таблицы, отключая их собственные кнопки (show_controls=[])
        self.appointment_page = PaginatedAppointmentListPage(
            parent=self,
            shared_registry=self._draft_registry,
            show_controls=[],   # кнопки будут на уровне этой страницы
            exclude_columns=['patient_name'],   # скрываем столбец с ФИО пациента
        )
        self.photo_page = PaginatedPhotoListPage(
            parent=self,
            shared_registry=self._draft_registry,
            show_controls=[],   # кнопки будут на уровне этой страницы
        )

        # Создаём пустую панель инструментов (будет заполнена в set_main_window)
        self.toolbar_widget = QWidget()
        self.toolbar_widget.setVisible(False)
        self.toolbar_widget.setMaximumHeight(40)          # фиксированная высота панели
        self.toolbar_layout = QHBoxLayout(self.toolbar_widget)
        self.toolbar_layout.setContentsMargins(5, 5, 5, 5)
        self.toolbar_layout.setSpacing(10)                # расстояние между кнопками

        # Размещение: панель сверху, сплиттер под ней
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.toolbar_widget)

        splitter = QSplitter(
            Qt.Vertical # вертикальная ориентация     
        )
        splitter.addWidget(self.appointment_page)
        splitter.addWidget(self.photo_page)
        splitter.setSizes([300, 500])

        main_layout.addWidget(splitter)

        # Подключаем сигнал выбора строки в таблице приёмов
        self.appointment_page.table_view.selectionModel().selectionChanged.connect(
            self._on_appointment_selected
        )


        # Подключаем сигналы изменения выделения для обновления состояния кнопки удаления
        self.appointment_page.table_view.selectionModel().selectionChanged.connect(
            self._update_buttons_state
        )

        self.photo_page.table_view.selectionModel().selectionChanged.connect(
            self._update_buttons_state
        )

        # self.photo_page.action_requested.connect( #  оно не нужно, потому что делегат сам откроет диалог
        #     self._on_photo_action_requested
        # )

        self._actions_setup = False

    # @AppLogger.get_instance(
    #     name='AppointmentPhotoFrame',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    # def _on_photo_action_requested(self, dto):
    #     """Обработчик двойного клика по строке фото – открывает редактирование."""
    #     if not self.photo_page.edit_mode:
    #         self._request_edit_mode(True)
    #     row = self.photo_page._find_row_by_id(dto.id)  # можно использовать find_row_by_id (сделать публичным)
    #     if row is not None:
    #         self.photo_page.edit_photo_in_row(row)

    @AppLogger.get_instance(
        name='AppointmentPhotoFrame',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def find_row_by_id(self, entity_id: int) -> int:
        """Возвращает индекс строки в source_model по ID сущности или -1."""
        return self._find_row_by_id(entity_id)    

    @AppLogger.get_instance(
        name='AppointmentPhotoFrame',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_main_window(self, main_window):
        super().set_main_window(main_window)
        if not getattr(self, '_actions_setup', False):
            self._setup_actions()
            self._setup_toolbar()
            self.toolbar_widget.setVisible(True)
            self._actions_setup = True

    @AppLogger.get_instance(
        name='AppointmentPhotoFrame',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_appointment_selected(self, selected, deselected):
        """
        Обработчик выбора строки в таблице приёмов.
        Обновляет таблицу фото, показывая фото выбранного приёма.
        """

        # Получаем выбранный DTO приёма
        dto = self.appointment_page.get_current_selected_dto()
        if dto:
            # Устанавливаем контекстный параметр для таблицы фото
            self.photo_page._context_params = {'appointment_id': dto.id}
            # Перезагружаем фото с фильтром по appointment_id
            self.photo_page.reload_with_filters({
                'column': 'appointment_id',
                'operator': 'eq',
                'value': dto.id
            })
        else:
            # Очищаем таблицу фото и сбрасываем контекст
            self.photo_page.source_model.clear()
            self.photo_page._context_params = {}

    @AppLogger.get_instance(
        name='AppointmentPhotoPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def on_enter(self, extra_data=None):
        """
        Вызывается при переходе на страницу.

        Args:
            extra_data (dict, optional): Может содержать 'patient_id' для фильтрации приёмов.
        """
        # Сохраняем ID пациента из параметров перехода
        self._current_patient_id = extra_data.get('patient_id') if extra_data else None


        if extra_data and 'patient_id' in extra_data:
            # Показываем только приёмы выбранного пациента
            self.appointment_page.reload_with_filters({
                'column': 'patient_id',
                'operator': 'eq',
                'value': extra_data['patient_id']
            })
             # Передаём patient_id в контекст таблицы приёмов,
            # чтобы новые приёмы создавались с этим ID
            self.appointment_page._context_params['patient_id'] = self._current_patient_id
        else:
            # Показываем все приёмы
            self.appointment_page.reload_with_filters(None)
            self.appointment_page._context_params = {}

        # Очищаем таблицу фото (будет заполнена при выборе приёма)
        self.photo_page.source_model.clear()
        self.photo_page._context_params = {}

    @AppLogger.get_instance(
        name='AppointmentPhotoPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def on_leave(self):
        """
        Вызывается при уходе со страницы.
        Сохраняет состояние (фильтры, прокрутку) через вызов on_leave дочерних страниц.
        """
        self.appointment_page.on_leave()
        self.photo_page.on_leave()

    @AppLogger.get_instance(
        name='AppointmentPhotoFrame',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _setup_actions(self):
        """Регистрирует действия в ActionManager главного окна."""
        am = self.main_window.action_manager

        # Режим редактирования (переключатель)
        am.register_action(
            'edit_mode', 'Режим редактирования',
            checkable=True, callback=self._toggle_edit_mode,
            parent=self, temporary=True
        )
        # Добавить приём
        am.register_action(
            'add_appointment', 'Добавить приём',
            callback=self._add_appointment,
            parent=self, temporary=True
        )
        # Добавить фото
        am.register_action(
            'add_photo', 'Добавить фото',
            callback=self._add_photo,
            parent=self, temporary=True
        )
        # Удалить выбранное
        am.register_action(
            'delete_selected', 'Удалить',
            callback=self._delete_selected,
            parent=self, temporary=True
        )
        # Сохранить все изменения
        am.register_action(
            'save_all', 'Сохранить',
            callback=self._save_all,
            parent=self, temporary=True
        )

        # Кнопка информации о пациенте
        am.register_action(
            'patient_info', 'Информация о пациенте',
            callback=self._show_patient_info,
            parent=self, temporary=True
        )

    @AppLogger.get_instance(
        name='AppointmentPhotoFrame',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _setup_toolbar(self):
        """Создаёт виджет с кнопками, привязанными к действиям."""
        am = self.main_window.action_manager

        # Очищаем layout от старых кнопок (на случай повторного вызова)
        while self.toolbar_layout.count():
            item = self.toolbar_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Создаём кнопки и связываем с действиями
        self.edit_mode_btn = QPushButton()
        am.connect_button('edit_mode', self.edit_mode_btn)
        self.edit_mode_btn.setText("Режим редактирования") 

        self.add_appointment_btn = QPushButton()
        am.connect_button('add_appointment', self.add_appointment_btn)
        self.add_appointment_btn.setText("Добавить приём")

        self.add_photo_btn = QPushButton()
        am.connect_button('add_photo', self.add_photo_btn)
        self.add_photo_btn.setText("Добавить фото")

        self.delete_btn = QPushButton()
        am.connect_button('delete_selected', self.delete_btn)
        self.delete_btn.setText("Удалить")

        self.save_btn = QPushButton()
        am.connect_button('save_all', self.save_btn)
        self.save_btn.setText("Сохранить")

        self.patient_info_btn = QPushButton()
        am.connect_button('patient_info', self.patient_info_btn)
        self.patient_info_btn.setText("Информация о пациенте")

        self.toolbar_layout.addWidget(self.edit_mode_btn)
        self.toolbar_layout.addWidget(self.add_appointment_btn)
        self.toolbar_layout.addWidget(self.add_photo_btn)
        self.toolbar_layout.addWidget(self.delete_btn)
        self.toolbar_layout.addWidget(self.save_btn)

        self.toolbar_layout.addWidget(self.patient_info_btn)

        self.toolbar_layout.addStretch()

        self._update_buttons_state() 

    @AppLogger.get_instance(
        name='AppointmentPhotoFrame',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _show_patient_info(self):
        """Отображает информацию о пациенте, связанном с выбранным приёмом."""

        patient_id = None

        # Приоритет: сохранённый ID пациента (из перехода)
        if self._current_patient_id:
            patient_id = self._current_patient_id
        else:
            # Иначе пытаемся получить из выбранного приёма
            appointment_dto = self.appointment_page.get_current_selected_dto()
            if appointment_dto:
                patient_id = appointment_dto.patient_id


        # appointment_dto = self.appointment_page.get_current_selected_dto()
        # if not appointment_dto:
        #     QMessageBox.warning(self, "Нет приёма", "Сначала выберите приём.")
        #     return

        # patient_id = appointment_dto.patient_id
        if not patient_id:
            
            QMessageBox.warning(
                self, "Нет пациента",
                "Не указан пациент. Сначала выберите приём или перейдите со страницы пациента."
            )

            return

        # from app.dependencies import get_patient_service
        # from interfaces.gui.gui_window.pages.dynamic_edit_page import DynamicEditPage
        # from app.dto.dto_all import PatientDTO
        # from app.dto.field_configs import PATIENT_CONFIG

        try:
            patient_dto = get_patient_service().get_patient_by_id(patient_id)
            dialog = QDialog(self)
            dialog.setWindowTitle(f"Информация о пациенте: {patient_dto.last_name} {patient_dto.first_name}")
            layout = QVBoxLayout(dialog)

            edit_page = DynamicEditPage(
                service=get_patient_service(),
                dto_class=PatientDTO,
                page_title="",
                exclude_fields=['id'],
                field_configs=PATIENT_CONFIG,
                save_directly=False,
                readonly=True,
                hide_action_buttons=True
            )
            edit_page.on_enter(extra_data={'id': patient_id})
            layout.addWidget(edit_page)

            btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
            btn_box.accepted.connect(dialog.accept)
            layout.addWidget(btn_box)

            dialog.resize(600, 500)
            dialog.exec()

        except Exception as e:
            self.logger.exception(f"Ошибка загрузки пациента: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить данные пациента: {e}")


    # ---- Методы действий ----

    @AppLogger.get_instance(
        name='AppointmentPhotoFrame',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _request_edit_mode(self, enable: bool) -> None:
        """
        Переключает режим редактирования через ActionManager (если доступен)
        или напрямую. Это обеспечивает синхронизацию кнопки и состояния страниц.
        
        Args:
            enable: True – включить режим редактирования, False – выключить.
        """
        if hasattr(self, 'main_window') and self.main_window.action_manager:
            self.main_window.action_manager.set_action_checked('edit_mode', enable)
        else:
            # fallback на случай, если ActionManager недоступен
            self._toggle_edit_mode(enable)

    @AppLogger.get_instance(
        name='AppointmentPhotoFrame',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _toggle_edit_mode(self, checked: bool):
        """Переключает режим редактирования для обеих таблиц."""
        # Переключаем режим у страниц
        self.appointment_page.set_edit_mode(checked)
        self.photo_page.set_edit_mode(checked)
        self._update_buttons_state()

    @AppLogger.get_instance(
        name='AppointmentPhotoFrame',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _add_appointment(self):
        """Добавляет новую строку в таблицу приёмов (в режиме редактирования)."""

        # Временно добавляем patient_id в контекст таблицы приёмов, если он известен
        old_context = None
        if self._current_patient_id:
            old_context = self.appointment_page._context_params.copy() if self.appointment_page._context_params else None
            self.appointment_page._context_params['patient_id'] = self._current_patient_id

        if self.appointment_page.edit_mode:
            self.appointment_page._add_inline_row()
        else:
            # Если режим редактирования выключен – включаем и добавляем
            self._request_edit_mode(True)
            self.appointment_page._add_inline_row()

        # Восстанавливаем контекст
        if old_context is not None:
            self.appointment_page._context_params = old_context
        elif self._current_patient_id:
            self.appointment_page._context_params.pop('patient_id', None)    

    @AppLogger.get_instance(
        name='AppointmentPhotoFrame',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _add_photo(self):
        """Добавляет фото к выбранному приёму."""
        # Проверяем, выбран ли приём
        appointment_dto = self.appointment_page.get_current_selected_dto()
        if not appointment_dto:
            QMessageBox.warning(self, "Нет приёма", "Сначала выберите приём в левой таблице.")
            return

        # Открываем диалог выбора файла
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if not file_path:
            return

        # Если режим редактирования выключен – включаем
        if not self.photo_page.edit_mode:
            self._request_edit_mode(True)

        # Находим строку, соответствующую выбранному приёму? Нет – фото добавляется в новую строку
        # Но фото привязано к приёму, поэтому создаём новую строку в таблице фото
        # и сразу устанавливаем appointment_id через контекстные параметры
        # (они уже установлены в _on_appointment_selected)
        self.photo_page.add_photo_to_new_row(file_path)   

    @AppLogger.get_instance(
        name='AppointmentPhotoFrame',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _delete_selected(self):
        """Удаляет выбранные строки в активной таблице."""

        # Определяем, какая таблица имеет фокус
        focus_widget = self.focusWidget()

        # Если режим редактирования выключен, включаем его
        if not (self.appointment_page.edit_mode or self.photo_page.edit_mode):
            self._request_edit_mode(True)

        if focus_widget == self.appointment_page.table_view:
            self.appointment_page._delete_selected_rows()
        elif focus_widget == self.photo_page.table_view:
            self.photo_page._delete_selected_rows()
        else:
            # Если фокус не на таблицах, ничего не делаем
            pass

    @AppLogger.get_instance(
        name='AppointmentPhotoFrame',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _save_all(self):
        """Сохраняет изменения в обеих таблицах."""
        # Сначала сохраняем приёмы (они могут создавать новые ID, нужные для фото)
        success_app = self.appointment_page.save_all_changes()
        success_photo = self.photo_page.save_all_changes()
        if success_app and success_photo:
            QMessageBox.information(self, "Успех", "Все изменения сохранены.")
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось сохранить изменения.")

    @AppLogger.get_instance(
        name='AppointmentPhotoFrame',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _update_buttons_state(self, selected=None, deselected=None):
        """Обновляет состояние кнопок (например, активна ли кнопка удаления)."""
        has_selection = (
            not self.appointment_page.is_selection_empty() or
            not self.photo_page.is_selection_empty()
        )
        
        # Удаление доступно только в режиме редактирования хотя бы одной таблицы
        edit_mode_active = self.appointment_page.edit_mode or self.photo_page.edit_mode
        self.delete_btn.setEnabled(has_selection and edit_mode_active)