# interfaces/gui/gui_window/pages/appointment_list_page.py

"""
Страница со списком приёмов.
Левая часть - таблица приёмов, правая - детали выбранного приёма (заметка и фото).
При клике на строку в таблице справа показывается информация.
В режиме редактирования (edit_mode) правые виджеты становятся доступными для изменения.
Сохранение изменений происходит только по кнопке "Сохранить изменения".

Верхняя панель информации о пациенте:
- отображает ФИО, дату рождения, телефон, email на отдельных строках
- имеет вертикальную прокрутку
- её высоту можно изменять с помощью разделителя (QSplitter)
"""

from functools import wraps
import os
import datetime

from app.config.config_manager.manager import get_config_env
from app.dto.field_configs import PATIENT_CONFIG
from app.utils.logger.logger import AppLogger

from app.dependencies import (
    # get_appointment_service, 
    get_patient_service,
    get_photo_service
)

from interfaces.gui.gui_window.pages.dynamic_list_page import DynamicListPage
from interfaces.gui.gui_window.widgets.photo_uploader_widget import PhotoUploaderWidget

from PySide6.QtWidgets import (
    # QTableView, QPushButton, QHeaderView, 
    # QLineEdit, 
    # QAbstractItemView, 
    QFrame, QGridLayout, 
    # QHBoxLayout,
    QLabel, QMessageBox, QScrollArea, QSizePolicy, 
    QSplitter, QTextEdit, 
    # QListWidget, QListWidgetItem, 
    QVBoxLayout, QWidget
)

from PySide6.QtCore import (
    QTimer,
    Qt, 
    # QAbstractTableModel, 
    # QModelIndex, 
    # Slot, 
    # QSortFilterProxyModel, 
    QSize,
    Signal
)

# from PySide6.QtGui import QPixmap, QIcon


def preserve_right_panel_state(func):
    """
    Декоратор для методов, которые обновляют правую панель.
    Блокирует сигналы note_text_edit и photo_widget, устанавливает флаг _loading_right_panel.
    (работает от AppointmentListPage)
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        self._loading_right_panel += 1
        self.note_text_edit.blockSignals(True)
        self.photo_widget.blockSignals(True)
        try:
            result = func(self, *args, **kwargs)
        except Exception as e:
            self.logger.exception(f"Ошибка в {func.__name__}: {e}")
            raise 
        finally:
            self._loading_right_panel -= 1
            if self._loading_right_panel == 0:
                self.note_text_edit.blockSignals(False)
                self.photo_widget.blockSignals(False)

        return result
    
    return wrapper

class DynamicDetailListPage(DynamicListPage):
    """
    Расширение DynamicListPage с правой панелью для отображения деталей выбранной строки.
    """

    @AppLogger.get_instance(
        name='DynamicDetailListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self,
        service,
        loader_func,
        dto_class,
        field_configs,
        *args,
        **kwargs
    ):
        """
        Инициализирует страницу с правой панелью для отображения деталей выбранной строки.
        
        :param service: сервис, используемый для редактирования записи
        :param loader_func: функция, которая возвращает список данных
        :param dto_class: класс DTO, используемый для создания записи
        :param field_configs: конфигурация полей
        :param *args: дополнительные параметры
        :param **kwargs: дополнительные параметры
        """
        super().__init__(service, loader_func, dto_class, field_configs, *args, **kwargs)
        # self.detail_widget = None
        # self.detail_layout = None


    @AppLogger.get_instance(
        name='DynamicDetailListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _clear_layout(self, layout):
        """
        Очищает заданный layout, удаляя все его элементы.
        
        :param layout: макет, который нужно очистить
        :type layout: PySide6.QtWidgets.QLayout
        """
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()

            if widget:
                widget.deleteLater()
                
            elif item.layout():
                self._clear_layout(item.layout())
         
    @AppLogger.get_instance(
        name='DynamicDetailListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )       
    def _setup_ui(self):
        """
        Создаёт интерфейс с разделителем и правой панелью.
        
        Создаёт вертикальную панель с кнопками и поиском, разделитель для таблицы и правой панели,
        таблицу, правую панель и настраивает начальные пропорции для комбобоксов.
        """
        # self.main_layout = QVBoxLayout(self)
        # Очищаем текущий layout (удаляем всё, что добавил родитель)
        self._clear_layout(self.main_layout)
        
        # Верхняя панель (кнопки, поиск)
        self._setup_top_panel()

        # Разделитель: слева таблица, справа детали
        splitter = QSplitter(Qt.Horizontal)
        self.splitter = splitter

        # Создаём таблицу (она будет добавлена в splitter, а не в main_layout)
        self._setup_table()
        splitter.addWidget(self.table_view)

        # Правая панель
        self.detail_widget = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_widget)
        splitter.addWidget(self.detail_widget)

        # Настраиваем начальные пропорции
        splitter.setSizes([400, 600])

        self.main_layout.addWidget(splitter)

        # Делегаты для комбобоксов (если нужны)
        self._setup_delegates()
        
    @AppLogger.get_instance(
        name='DynamicDetailListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_selection_changed(self, selected, deselected):
        """
        Обработка события изменения выбора строки в таблице.
        
        Если строка выбрана, то обновляет правую панель с деталями выбранной строки.
        """
        super()._on_selection_changed(selected, deselected)
        if self.selected_dto:
            self.update_details(self.selected_dto)


class DraftMixin:
    """
    Содержит логику сохранения и восстановления черновиков для приёмов.
    Атрибуты (должны быть определены в классе-наследнике):
        _draft_photos: dict[int, dict]   # черновики фото
        _draft_note_text: dict[int, str] # черновики заметок
        _loading_right_panel: bool       # блокировка сигналов при загрузке
        note_text_edit                   # QTextEdit
        photo_widget                     # PhotoUploaderWidget
        selected_dto                     # текущий выбранный DTO
        logger                           # AppLogger
    """

    @AppLogger.get_instance(
        name='DraftMixin',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _save_current_draft(self) -> None:
        """Сохраняет текущее состояние правой панели в черновики для выбранного приёма."""
        
        if not self.selected_dto:
            return

        aid = self.selected_dto.id   # может быть отрицательным временным ID

        # if aid is None:
        #     # Для новых строк используем ключ None
        #     # Сохраняем состояние заметки для новой строки
        #     self._draft_note_text[None] = self.note_text_edit.toPlainText()
        #     # Сохраняем состояние фото для новой строки
        #     self._draft_photos[None] = self.photo_widget.dump_state()

        #     self.logger.debug(f"Сохранён черновик для нового приёма")
        #     return
        
        # Для существующих

        # Заметка
        self._draft_note_text[aid] = self.note_text_edit.toPlainText()
        # Фото
        self._draft_photos[aid] = self.photo_widget.dump_state()

        self.logger.debug(f"Сохранён черновик для приёма {aid}: pending={self._draft_photos[aid]['pending_photos']}")


    @AppLogger.get_instance(
        name='DraftMixin',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @preserve_right_panel_state
    def _load_draft_for_appointment(self, appointment_id: int, dto) -> None:
        """
        Загружает черновик или свежие данные из БД в правую панель.
        """
        # appointment_id может быть отрицательны

        self.logger.info(
            f"_load_draft_for_appointment для ID={appointment_id}. "
            f"Есть черновик: {appointment_id in self._draft_photos}"
        )

        # if appointment_id is None:
        #     # Новая строка – загружаем черновик, если есть
            
        #     note_text = self._draft_note_text.get(None)
        #     self.note_text_edit.setText(note_text if note_text is not None else "")

        #     # Загружаем состояние фото из черновика
        #     draft_state = self._draft_photos.get(None)
        #     if draft_state:
        #         self.photo_widget.load_state(draft_state)
        #     else:
        #         self.photo_widget.clear()
        #     return

        # заметка
        
        note_text = self._draft_note_text.get(appointment_id)
        if note_text is not None:
            self.note_text_edit.setText(note_text)
            self.logger.debug("Загружена заметка из черновика")
        else:
            self.note_text_edit.setText(dto.note_text or "")

        # фото
        if appointment_id in self._draft_photos:
            self.logger.info("Загружаем СОСТОЯНИЕ ИЗ ЧЕРНОВИКА")
            self.photo_widget.load_state(self._draft_photos[appointment_id])
        else:
            self.logger.info("Черновика нет → загружаем свежие фото из БД через set_existing_photos")
            self.photo_widget.set_existing_photos(dto.photos or [])

        self.logger.info(
            f"_load_draft_for_appointment завершён для {appointment_id}. "
            f"Строк в таблице фото: {self.photo_widget.table.rowCount() if hasattr(self.photo_widget, 'table') else 'N/A'}"
        )


    @AppLogger.get_instance(
        name='DraftMixin',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_draft_changed(self):
        """При любом изменении в правой панели обновляем черновик текущего приёма."""
        if not self.edit_mode:
            return
        # if not self.selected_dto:
        #     return

        if self._loading_right_panel > 0:
            return

        self._save_current_draft()
        self._check_and_clear_modified_if_unchanged()
        self._mark_current_row_modified()
        self._sync_draft_to_model()

    @AppLogger.get_instance(
        name='DraftMixin',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _clear_drafts(self):
        """Полностью очищает все черновики."""
        self._draft_photos.clear()
        self._draft_note_text.clear()
        self.logger.debug("Черновики очищены")


class PatientInfoMixin:
    """
    Создаёт и управляет панелью с данными пациента.
    Атрибуты (должны быть определены в классе-наследнике):
        patient_info_frame: QFrame
        info_value_widgets: dict[str, QLabel]
        current_patient_changed: Signal
        logger: AppLogger
        vertical_splitter: QSplitter (для обновления геометрии)
    """

    @AppLogger.get_instance(
        name='PatientInfoMixin',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_patient_info_panel(self):
        """Создаёт панель с информацией о пациенте на основе PATIENT_CONFIG."""
        self.patient_info_frame = QFrame()
        self.patient_info_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.patient_info_frame.setMinimumHeight(70)   # минимальная высота
        self.patient_info_frame.setVisible(False)

        layout = QGridLayout(self.patient_info_frame)
        layout.setContentsMargins(5, 5, 5, 5)

        # Область прокрутки
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setMinimumHeight(10)
        layout.addWidget(scroll)

        content_widget = QWidget()
        scroll.setWidget(content_widget)

        grid = QGridLayout(content_widget)
        grid.setSpacing(5)

        self.info_value_widgets = {}
        row = 0

        for field_name, config in PATIENT_CONFIG.items():
            if config.get('hidden', False) or field_name == 'id':
                continue

            title = config.get('title', field_name.replace('_', ' ').title())

            label_title = QLabel(f"{title}:")
            label_title.setStyleSheet("font-weight: bold;")
            label_title.setAlignment(Qt.AlignTop)

            label_value = QLabel()
            label_value.setWordWrap(True)
            label_value.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            label_value.setTextInteractionFlags(Qt.TextSelectableByMouse)   # добавить
            # label_value.setTextInteractionFlags(Qt.TextSelectableByMouse)

            grid.addWidget(label_title, row, 0, alignment=Qt.AlignTop)
            grid.addWidget(label_value, row, 1, alignment=Qt.AlignTop)

            self.info_value_widgets[field_name] = label_value
            row += 1

        grid.setColumnStretch(1, 1)
        grid.setRowStretch(row, 1)

        # Подключаем сигнал изменения пациента (сигнал должен быть определён в основном классе)
        self.current_patient_changed.connect(self._update_patient_info)

    @AppLogger.get_instance(
        name='PatientInfoMixin',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _update_patient_info(self, patient_dto):
        """
        Обновляет содержимое панели на основе DTO пациента.
        """
        self.logger.debug(f"_update_patient_info called, patient_dto: {patient_dto is not None}")
        if patient_dto:
            data = patient_dto.model_dump(exclude_none=True)
            for field_name, label in self.info_value_widgets.items():
                value = data.get(field_name)
                if value is None:
                    label.setText("—")
                else:
                    if isinstance(value, datetime.date):
                        label.setText(value.isoformat())
                    elif isinstance(value, datetime.time):
                        label.setText(value.strftime("%H:%M"))
                    else:
                        label.setText(str(value))
            self.patient_info_frame.setVisible(True)
            # Обновляем вертикальный сплиттер
            if hasattr(self, 'vertical_splitter'):
                self.vertical_splitter.update()
        else:
            # Очищаем все поля
            for label in self.info_value_widgets.values():
                label.setText("—")
            self.patient_info_frame.setVisible(False)


class RightPanelMixin:
    """
    Создаёт и управляет правой панелью: заметка и фотографии.
    Атрибуты (должны быть определены в классе-наследнике):
        detail_widget: QWidget
        detail_layout: QVBoxLayout
        note_text_edit: QTextEdit
        photo_widget: PhotoUploaderWidget
        _loading_right_panel: bool
        edit_mode: bool
        selected_dto: Any
        logger: AppLogger
    """

    @AppLogger.get_instance(
        name='RightPanelMixin',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_detail_panel(self):
        """Создаёт виджеты правой панели и подключает сигналы."""
        # Заметка
        self.note_text_edit = QTextEdit()
        self.note_text_edit.setReadOnly(True)  # изначально только просмотр
        self.note_text_edit.textChanged.connect(self._on_draft_changed)

        self.detail_layout.addWidget(QLabel("Заметка:"))
        self.detail_layout.addWidget(self.note_text_edit)

        # Фотографии
        self.photo_widget = PhotoUploaderWidget()
        config = get_config_env()
        storage_path = config.get(
            'PHOTOS_STORAGE_PATH',
            os.path.join('.', 'photos')
        )
        self.logger.debug(f'storage_path: {storage_path}')
        self.photo_widget.set_storage_path(storage_path)
        self.photo_widget.set_readonly(True)
        self.photo_widget.photosChanged.connect(self._on_draft_changed)

        self.detail_layout.addWidget(QLabel("Фотографии:"))
        self.detail_layout.addWidget(self.photo_widget)

        self._loading_right_panel = 0

    @AppLogger.get_instance(
        name='RightPanelMixin',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_note_text_changed(self):
        """
        Обработчик изменения текста заметки (может быть вызван напрямую,
        но мы уже используем _on_draft_changed, поэтому этот метод можно
        оставить как заглушку или вообще убрать.
        """
        pass

    @AppLogger.get_instance(
        name='RightPanelMixin',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_photos_changed(self):
        """
        Обработчик изменения списка фото (используется _on_draft_changed).
        """
        pass

class AppointmentListPage(
    DynamicDetailListPage,
    DraftMixin,
    PatientInfoMixin,
    RightPanelMixin

):
    """
    Страница со списком приёмов с правой панелью (заметка и фото).
    """

    # Сигнал, испускаемый при изменении текущей строки (для обновления панели информации)
    current_patient_changed = Signal(object)

    _patient_info_frame_setMinimumHeight = 70 # высота верхней панели с информацией о пациенте

    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self,
        service,
        loader_func,
        dto_class,
        field_configs,

        # exclude_columns=None,
        *args,
        **kwargs
    ):
        """
        Инициализирует страницу со списком приёмов с правой панелью (заметка и фото).
        """
        
        super().__init__(service, loader_func, dto_class, field_configs, *args, **kwargs)
        
        self.logger = AppLogger.get_instance(
            name = 'gui.AppointmentListPage',
            enable_file_logging = 'user',
            use_name_in_filename = 'user',
        )

        # Словари для хранения черновиков приёмов
        self._draft_photos = {}      # appointment_id -> состояние от photo_widget.dump_state()
        self._draft_note_text = {}   # appointment_id -> str

        # Флаг, указывающий, что в правой панели есть несохранённые изменения (фото/заметка)
        self._right_panel_modified = False
        # Блокируем сигналы при загрузке данных в правую панель
        self._loading_right_panel = 0
        
        # Сервисы
        self.photo_service = get_photo_service()
        self.patient_service = get_patient_service()


        # Создаём правую панель
        # Создаём виджеты правой панели (после того как detail_layout создан в родительском _setup_ui)
        self._setup_detail_panel()

        # # Подключаем сигналы черновиков
        # self.note_text_edit.textChanged.connect(self._on_draft_changed)
        # self.photo_widget.photosChanged.connect(self._on_draft_changed)


        
        
        # self.current_appointment_id = None  # хранит id выбранного приёма для отображения 
        # self.current_patient_info = None # хранит DTO пациента для отображения сверху



        # Явно подключаем кнопку сохранения к нашему методу
        if hasattr(self, 'save_changes_btn'):
            try:
                self.save_changes_btn.clicked.disconnect()  # отключаем ВСЁ
            except TypeError as e:
                self.logger.debug(f"{e}")

                pass  # если не было подключено — нормально

            self.save_changes_btn.clicked.connect(self._save_changes)
            self.logger.debug("Кнопка save_changes_btn подключена к _save_changes в AppointmentListPage")
            self.logger.info("Кнопка 'Сохранить изменения' ПРИНУДИТЕЛЬНО подключена к _save_changes в AppointmentListPage")

        # # Создаём виджеты правой панели (будет вызвано в _setup_detail_panel)
        # self.note_text_edit = None
        # self.photo_widget = None

        # self._setup_detail_panel()


    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _check_and_clear_modified_if_unchanged(self):
        if not self.selected_dto:
            return
        source_row = None
        for row in range(self.source_model.rowCount()):
            dto = self.source_model.get_item_at_row(row)
            if dto and dto.id == self.selected_dto.id:
                source_row = row
                break
        if source_row is None:
            return
        original = self.original_data.get(source_row)
        if original and self.selected_dto.model_dump() == original.model_dump():
            if source_row in self.modified_rows:
                self.modified_rows.discard(source_row)
                self._set_row_color_by_source_row(source_row)
                self._update_save_button_state()

    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _sync_draft_to_model(self):
        """
        Синхронизирует черновики приёма (draft) с моделью (source_model).
        Если выбранная строка (self.selected_dto) не существует в модели, ничего не делает.
        Если в черновике (self._draft_note_text) есть текст для заметки приёма с id, равным id выбранной строки, обновляет поле note_text в DTO из черновика.
        """
        if not self.selected_dto:
            return
        
        # Найти строку в модели
        source_row = None
        for row in range(self.source_model.rowCount()):
            dto = self.source_model.get_item_at_row(row)
            if dto and dto.id == self.selected_dto.id:
                source_row = row
                break

        if source_row is None:
            return
        
        # Обновить поле note_text в DTO из черновика
        note_text = self._draft_note_text.get(self.selected_dto.id)
        if note_text is not None and self.selected_dto.note_text != note_text:
            self.selected_dto.note_text = note_text
            col_idx = self._get_column_index('note_text')
            if col_idx >= 0:
                index = self.source_model.index(source_row, col_idx)
                self.source_model.setData(index, note_text, Qt.EditRole)
        
        # после возможного обновления проверить, не стал ли DTO равным оригиналу
        self._check_and_clear_modified_if_unchanged()

    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _get_column_index(self, field_name: str) -> int:
        """
        Возвращает индекс колонки в таблице, соответствующей полю с именем field_name.
        Если не найдено, возвращает -1.
        """
        for i, col in enumerate(self.columns):
            if col['name'] == field_name:
                return i
        return -1

    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _mark_selected_for_deletion(self):
        """Переопределяем для очистки правой панели, если после удаления строк не осталось."""
        # Сохраняем ID перед удалением (для очистки черновиков)
        temp_id = None
        if self.selected_dto and self.selected_dto.id is not None and self.selected_dto.id < 0:
            temp_id = self.selected_dto.id

        super()._mark_selected_for_deletion()

        # Очищаем черновики для новой строки (если она была)
        if temp_id is not None:
            self._draft_photos.pop(temp_id, None)
            self._draft_note_text.pop(temp_id, None)

        # Если после удаления строк не осталось, очищаем правую панель
        if self.source_model.rowCount() == 0:
            self._clear_right_panel()

    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _load_data(self):
        """Переопределяем для очистки правой панели, если данных нет."""
        super()._load_data()
        # После загрузки, если нет строк, очищаем правую панель
        if self.source_model.rowCount() == 0:
            self._clear_right_panel()

    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _clear_right_panel(self):
        """Очищает правую панель (заметку и фото) и сбрасывает выбранный DTO."""
        self.note_text_edit.clear()
        self.photo_widget.clear()
        self.selected_dto = None
        self.current_patient_changed.emit(None)

    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _save_modified_appointments(self):
        """Сохраняет изменения в существующих приёмах (modified_rows)."""
        for source_row in list(self.modified_rows):
            dto = self.source_model.get_item_at_row(source_row)
            if dto and (dto.id is not None) and (dto.id > 0):
                original = self.original_data.get(source_row)
                if original and dto.model_dump() == original.model_dump():
                    self.modified_rows.discard(source_row)
                    self._set_row_color_by_source_row(source_row)   # добавить
                    self._update_save_button_state()
                    continue
                self._save_single_appointment(dto, source_row)

    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _apply_draft_to_new_dto(self, dto):
        if dto.id is not None and dto.id < 0:
            note_text = self._draft_note_text.get(dto.id)
            if note_text is not None:
                dto.note_text = note_text

    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _save_new_appointments(self):
        """Создаёт новые приёмы (new_rows) и сохраняет их фото."""
        newly_created_id = None
        for row in list(self.new_rows):
            dto = self.source_model.get_item_at_row(row)
            if dto and (dto.id is not None) and (dto.id < 0):
                temp_id = dto.id
                # Заметка из черновика
                note_text = self._draft_note_text.get(temp_id)
                if note_text is not None:
                    dto.note_text = note_text

                # Создаём запись в БД
                created = self.service.create(dto)
                self.source_model.update_row(row, created)
                self.logger.info(f"Создан новый приём ID={created.id}")
                newly_created_id = created.id

                # Обрабатываем фото для новой строки
                draft = self._draft_photos.get(temp_id)
                if draft and created.id is not None:
                    pending = draft.get('pending_photos', [])
                    if pending:
                        self.photo_service.update_photos_for_appointment(
                            created.id, 
                            pending, 
                            []
                        )
                        
                        # Обновление описаний существующих фото (их нет)
                        for photo_dto in draft.get('existing_photos', []):
                            if isinstance(photo_dto, dict) and photo_dto.get('id') in draft.get('modified_photo_ids', []):
                                self.photo_service.update_photo_description(
                                    photo_dto['id'], 
                                    photo_dto.get('description', '')
                                )
                        self.logger.info(f"Добавлено {len(pending)} фото для нового приёма {created.id}")
                elif draft:
                    self.logger.warning(f"Не удалось сохранить фото для нового приёма: created.id = {created.id}")

                # Очищаем черновики для этого временного ID
                self._draft_photos.pop(temp_id, None)
                self._draft_note_text.pop(temp_id, None)

        return newly_created_id

    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _save_deleted_appointments(self):
        """Удаляет помеченные приёмы (если есть такая функциональность)."""
        for row in sorted(self.deleted_rows, reverse=True):
            dto = self.source_model.get_item_at_row(row) 
            if dto:
                if dto.id is not None and dto.id > 0:
                    # Существующий приём – удаляем через сервис
                    self.service.delete_appointment(dto.id)
                    self.logger.info(f"Удалён приём ID={dto.id}")
                else:
                    # Новая строка (временный ID) – просто удаляем из модели
                    self.logger.info(f"Удалена новая строка с временным ID={dto.id}")
                # Удаляем строку из модели
                # self.source_model.remove_row(row)
        self.deleted_rows.clear()
        # pass

    # ----------------------------------------------------------------------
    # Переопределение построения интерфейса
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_ui(self): # - оставить
        """
        Переопределяем метод для создания вертикального сплиттера, включающего панель информации о пациенте и горизонтальный сплиттер (таблица + правая панель).
        """
        # Сначала вызываем родительский метод, который создаст:
        # - main_layout (QVBoxLayout)
        # - верхнюю панель с кнопками и поиском (self.top_panel)
        # - горизонтальный сплиттер self.splitter (таблица + правая панель)

        super()._setup_ui()

        # Сохраняем ссылку на горизонтальный сплиттер (он уже добавлен в main_layout)
        horizontal_splitter = self.splitter

        # Удаляем горизонтальный сплиттер из main_layout (чтобы потом вставить его в вертикальный)
        index = self.main_layout.indexOf(horizontal_splitter)
        self.logger.debug(f"if index != -1 : {index != -1}")
        if index != -1: # если горизонтальный сплиттер есть в main_layout
            self.main_layout.takeAt(index)

        # Создаём вертикальный сплиттер
        self.vertical_splitter = QSplitter(Qt.Vertical)

        # Создаём панель информации о пациенте (миксин)
        self._setup_patient_info_panel()

        # Добавляем панель информации в вертикальный сплиттер -
        self.vertical_splitter.addWidget(self.patient_info_frame) 

        # Добавляем горизонтальный сплиттер
        self.vertical_splitter.addWidget(horizontal_splitter)

        # Настраиваем пропорции: панель информации не растягивается, горизонтальный сплиттер растягивается
        self.vertical_splitter.setStretchFactor(0, 0) # панель не растягивается
        self.vertical_splitter.setStretchFactor(1, 1) # таблица растягивается

        # Добавляем вертикальный сплиттер в main_layout
        self.main_layout.addWidget(self.vertical_splitter)

        # Устанавливаем стили для обоих сплиттеров
        self._apply_splitter_style(self.vertical_splitter)
        self._apply_splitter_style(horizontal_splitter)

        # Устанавливаем начальные размеры (панель информации – 100px, остальное – остаток)
        # Точное значение будет установлено в showEvent, когда окно станет видимым
        self.logger.debug(f"self.height() : {self.height()}")
        self.vertical_splitter.setSizes([100, self.height() - 100])
        self.logger.debug(f"self.height() : {self.height()}")

        # # Если self.height() ещё 0, установим фиксированные размеры
        # if self.height() == 0:
        #     self.vertical_splitter.setSizes([200, 600])

        # # Принудительно показываем и обновляем правую панель
        # if hasattr(self, 'detail_widget'):
        #     self.detail_widget.setVisible(True)
        #     self.detail_widget.updateGeometry()
        #     # Если layout был пересоздан в _setup_detail_panel, убедимся, что он активен
        #     if self.detail_layout:
        #         self.detail_layout.activate()
        # # Обновляем весь вертикальный сплиттер
        # if hasattr(self, 'vertical_splitter'):
        #     self.vertical_splitter.updateGeometry()


        self.logger.debug(f"Vertical splitter sizes after setup: {self.vertical_splitter.sizes()}")


    # ----------------------------------------------------------------------
    # Вспомогательные методы для сплиттеров
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def showEvent(self, event): # - оставить
        """Переопределяем showEvent для установки размеров вертикального сплиттера после отображения окна."""
        if not hasattr(self, 'vertical_splitter'):
            return
        
        super().showEvent(event)
        # Откладываем установку размеров на следующий цикл событий, чтобы гарантировать,
        # что геометрия окна уже определена.
        # from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._fix_splitter_sizes)

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _fix_splitter_sizes(self):
        """Устанавливает начальные размеры вертикального сплиттера, если они ещё не заданы."""

        total_height = self.height()
        # Устанавливаем панели высоту, остальное — горизонтальному сплиттеру
        panel_height = self._patient_info_frame_setMinimumHeight
        # Если общая высота меньше panel_height + минимальная высота для второй части (например, 100),
        # можно скорректировать, чтобы не было отрицательных значений.
        min_remaining = 80

        if total_height < panel_height + min_remaining:
            panel_height = max(panel_height, total_height - min_remaining)

        self.vertical_splitter.setSizes([panel_height, total_height - panel_height])
        self.logger.debug(
            f"_fix_splitter_sizes: set panel height to {panel_height}, "
            f"total height {total_height}, sizes: {self.vertical_splitter.sizes()}"
        )
        
        # Принудительное обновление
        self.vertical_splitter.updateGeometry()
        self.patient_info_frame.updateGeometry()
        self.table_view.updateGeometry()
        self.table_view.viewport().update()
        self.table_view.scheduleDelayedItemsLayout()

        # Для QScrollArea внутри панели обновляем макет
        scroll = self.patient_info_frame.findChild(QScrollArea)
        if scroll:
            scroll.updateGeometry()
            scroll.widget().updateGeometry()
    
    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _apply_splitter_style(self, splitter: QSplitter):
        """
        Применяет единый стиль к сплиттеру, чтобы сделать разделитель видимым.
        :param splitter: QSplitter, который нужно стилизовать
        """
        splitter.setHandleWidth(5)  # увеличиваем толщину для удобства
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #e0e0e0;
            }
            QSplitter::handle:hover {
                background-color: #a0a0a0;
            }
        """)

    # ----------------------------------------------------------------------
    # Обработка выделения строки
    # ----------------------------------------------------------------------
     

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_selection_changed(self, selected, deselected):
        """
        Переопределяем метод для сохранения черновика текущего приёма
        перед переключением на другой.
        """
        # Сохраняем черновик текущего выбранного приёма (если есть)
        if self.selected_dto:
            self.logger.debug(f"Сохранение черновика для приёма {self.selected_dto.id} перед переключением")
            self._save_current_draft()
        # Вызываем родительский метод, который обновит self.selected_dto и вызовет update_details
        super()._on_selection_changed(selected, deselected)


    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _mark_current_row_modified(self): 
        """
        Помечает текущую строку (self.selected_dto) как изменённую в модели.
        Если строка уже в modified_rows, ничего не делает.
        """
        if not self.selected_dto:
            return

        # Находим индекс строки в модели
        proxy_index = self.table_view.currentIndex()
        if not proxy_index.isValid():
            return

        source_row = self.proxy_model.mapToSource(proxy_index).row()
        if source_row == -1:
            return

        # Если строка ещё не помечена как modified, добавляем
        if source_row not in self.modified_rows:
            self.modified_rows.add(source_row)
            # self._update_row_color(source_row)   # обновляем цвет строки
            self._set_row_color_by_source_row(source_row)   # обновляем цвет строки
            self._update_save_button_state()    # активируем кнопку сохранения


    # ----------------------------------------------------------------------
    # Режим редактирования
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_edit_mode_toggled(self, checked: bool):
        """
        Переопределяем метод для:
            - очистки черновиков при отмене
            - настройки readOnly для правой панели
        """
        if not checked and (self.modified_rows or self.deleted_rows or self.new_rows):
            reply = QMessageBox.question(
                self, "Несохранённые изменения",
                "Есть несохранённые изменения. Сохранить перед выходом из режима редактирования?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._save_changes()
                # после сохранения выходим из режима
                super()._on_edit_mode_toggled(checked)
            elif reply == QMessageBox.StandardButton.No:
                # Откат: сбросить черновики и перезагрузить данные
                self._clear_drafts()
                # Перезагружаем данные из БД
                self._load_data()
                
                self.modified_rows.clear()
                self.deleted_rows.clear()
                self.new_rows.clear()
                self._update_save_button_state()
                
                # выходим из режима редактирования
                super()._on_edit_mode_toggled(checked)
            else:
                # Cancel – остаёмся в режиме редактирования
                return
        else:
            # Переключаем режим через родительский метод (устанавливает self.edit_mode и управляет кнопками)
            super()._on_edit_mode_toggled(checked)

        # Настройка правых виджетов в зависимости от режима
        if self.edit_mode:
            self.note_text_edit.setReadOnly(False)
            self.photo_widget.set_readonly(False)
        else:
            self.note_text_edit.setReadOnly(True)
            self.photo_widget.set_readonly(True)
        self.logger.debug(f"Режим редактирования: {'включён' if self.edit_mode else 'выключен'}")


    # ----------------------------------------------------------------------
    # Сохранение изменений
    # ----------------------------------------------------------------------

    # --- Вспомогательные методы для сохранения одного приёма ---
    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _update_appointment_note(self, dto, appointment_id):
        """Обновляет заметку приёма из черновика."""
        note_text = self._draft_note_text.get(appointment_id)
        if note_text is not None:
            dto.note_text = note_text
            self.logger.debug(f"  → Заметка обновлена для {appointment_id}")

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _update_appointment_photos(self, appointment_id, draft):
        """Обрабатывает изменения фото: добавление, удаление, обновление описаний."""
        if not draft:
            return

        pending = draft.get('pending_photos', [])
        deleted = draft.get('deleted_photo_ids', [])

        self.photo_service.update_photos_for_appointment(appointment_id, pending, deleted)

        # Обновление описаний изменённых существующих фото
        for photo_dto in draft.get('existing_photos', []):
            if isinstance(photo_dto, dict) and photo_dto.get('id') in draft.get('modified_photo_ids', []):
                self.photo_service.update_photo_description(
                    photo_dto['id'], photo_dto.get('description', '')
                )
        self.logger.info(f"  → Фото для приёма {appointment_id} успешно сохранены")

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _update_appointment_basic_fields(self, dto):
        """Сохраняет основные поля приёма в БД."""
        if dto.id is not None:
            self.service.update(dto)

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _save_single_appointment(self, dto, source_row):
        """Сохраняет все изменения для одного приёма."""
        appointment_id = dto.id
        self.logger.info(f"Сохраняем приём ID={appointment_id} (строка {source_row})")

        # Заметка
        self._update_appointment_note(dto, appointment_id)
        
        # Фото
        draft = self._draft_photos.get(appointment_id)
        self._update_appointment_photos(appointment_id, draft)

        # Основные поля приёма
        self._update_appointment_basic_fields(dto)
        self.logger.debug(f"  → Основные данные приёма {appointment_id} обновлены")


    # --- Финальные действия после сохранения ---

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _refresh_current_dto(self, appointment_id):
        """Возвращает свежий DTO приёма после перезагрузки данных."""
        for row in range(self.source_model.rowCount()):
            candidate = self.source_model.get_item_at_row(row)
            if candidate and getattr(candidate, 'id', None) == appointment_id:
                return candidate
            
        return None


    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @preserve_right_panel_state # 
    def _update_right_panel_with_fresh_data(self, fresh_dto, fresh_photos):
        """
        Временно обновляет правую панель (заметка и фото) свежими данными.
        Не изменяет выделение строки.
        """
        self.note_text_edit.setText(fresh_dto.note_text or "")
        self.photo_widget.clear()
        self.photo_widget.set_existing_photos(fresh_photos)

        self.selected_dto = fresh_dto

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _finalize_after_save(self, current_appointment_id):
        """Обновляет данные и восстанавливает выделение после сохранения."""
        # Перезагрузка данных
        self._load_data()
        self.source_model.clear_row_colors()

        if current_appointment_id is not None:
            self.logger.debug(f"Восстанавливаем выделение приёма {current_appointment_id}")

            # Получаем свежие данные ДО выделения строки
            fresh_photos = self.photo_service.get_photos_for_appointment(current_appointment_id)
            fresh_dto = self._refresh_current_dto(current_appointment_id)

            if fresh_dto is None:
                self.logger.warning(f"Приём {current_appointment_id} не найден после сохранения")
                return

            self.logger.debug(f"Загружено {len(fresh_photos)} фото для приёма {current_appointment_id}")

            # Блокируем сигналы выделения, чтобы не вызывать update_details
            selection_model = self.table_view.selectionModel()
            if selection_model:
                selection_model.blockSignals(True)

            # Выделяем строку
            self._select_row_by_id(current_appointment_id)

            if selection_model:
                selection_model.blockSignals(False)

            # Обновляем правую панель свежими данными
            self._update_right_panel_with_fresh_data(fresh_dto, fresh_photos) 

            # Обновляем панель информации о пациенте
            try:
                patient_dto = self.patient_service.get_patient_by_id(fresh_dto.patient_id)
                self.current_patient_changed.emit(patient_dto)
            except Exception as e:
                self.logger.exception(f"Ошибка загрузки пациента после сохранения: {e}")
                self.current_patient_changed.emit(None)

    # --- Основной метод сохранения ---

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _save_changes(self):
        """Сохраняет все изменения (заметки, фото, основные поля) в БД."""
        self.logger.info("=== _save_changes ВЫЗВАН В AppointmentListPage ===")

        if not (self.modified_rows or self.deleted_rows or self.new_rows):
            self.logger.debug("Нет изменений для сохранения")
            return

        current_id = None
        if self.selected_dto and getattr(self.selected_dto, 'id', None) is not None:
            current_id = self.selected_dto.id
            self.logger.info(f"Текущий выделенный приём: {current_id}")

        reply = QMessageBox.question(
            self, "Подтверждение сохранения",
            "Сохранить все изменения в БД?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            self.logger.debug("Сохранение отменено пользователем")
            return

        self.table_view.setEnabled(False)
        self.save_changes_btn.setEnabled(False)

        try:
            self.logger.info("=== НАЧАЛО СОХРАНЕНИЯ ИЗМЕНЕНИЙ ===")
            self._save_current_draft()   # сохраняем последние правки перед сохранением


            # 1. Сохраняем новые приёмы
            newly_created_id = self._save_new_appointments()
            self.new_rows.clear()


            # 2. Сохраняем изменённые приёмы
            self._save_modified_appointments()

            # 3. Удаление помеченных приёмов
            self._save_deleted_appointments()

            # # 3. Удаляем (если есть)
            # self._save_deleted_appointments()

            # Очистка черновиков
            self._clear_drafts()

            # Обновляет данные и восстанавливает выделение после сохранения
            self._finalize_after_save(newly_created_id if newly_created_id is not None else current_id)

            QMessageBox.information(self, "Успех", "Изменения успешно сохранены.")

            # Выходим из режима редактирования, если он был включён
            self._exit_edit_mode()

        except Exception as e:
            self.logger.exception(f"Ошибка сохранения: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить изменения:\n{e}")
        finally:
            self.table_view.setEnabled(True)
            self._update_save_button_state()
            self.logger.debug("_save_changes завершён (finally)")
    
    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _force_photo_refresh(self, fresh_photos):
        """Дополнительный принудительный refresh фото-виджета после таймера."""
        if hasattr(self, 'photo_widget'):
            self.photo_widget.clear()
            self.photo_widget.set_existing_photos(fresh_photos)
            self.logger.info("Принудительный _force_photo_refresh выполнен")

    # ----------------------------------------------------------------------
    # Обновление правой панели при выборе строки
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @preserve_right_panel_state
    def update_details(self, dto):
        """
        Обновляет правую панель данными выбранного приёма.
        """
        if not dto:
            self.logger.warning("update_details вызван с dto=None")
            return

        self.logger.info(f"update_details вызван для приёма ID={dto.id}")

        if self.selected_dto and self.selected_dto.id != dto.id:
            self._save_current_draft()

        self.selected_dto = dto
        self.current_appointment_id = dto.id

        self.logger.debug("Вызываем _load_draft_for_appointment")
        self._load_draft_for_appointment(dto.id, dto)
        if self.edit_mode:
            self._sync_draft_to_model()
        # self._sync_draft_to_model()

        # обновление пациента (остаётся как было)
        try:
            if dto.patient_id:
                patient_dto = self.patient_service.get_patient_by_id(dto.patient_id)
                self.current_patient_changed.emit(patient_dto)
            else:
                self.current_patient_changed.emit(None)
        except Exception as e:
            self.logger.exception(f"Ошибка загрузки пациента: {e}")

    # ----------------------------------------------------------------------
    # Вход на страницу
    # ----------------------------------------------------------------------


    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def on_enter(self, extra_data=None):
        """
        При входе на страницу обновляем список приёмов.
        Если передан patient_id, показываем панель с информацией о пациенте.
        """
        # # Сброс черновиков при входе 
        # self._draft_photos.clear()
        # self._draft_note_text.clear()
        # Сбрасываем черновики, если это не возврат после сохранения с select_id
        if not (extra_data and 'select_id' in extra_data):
            self._clear_drafts()

        # Запоминаем patient_id для отображения информации
        patient_id = extra_data.get('patient_id') if extra_data else None
        if patient_id:
            try:
                patient_dto = self.patient_service.get_patient_by_id(patient_id)
                self.current_patient_changed.emit(patient_dto)
            except Exception as e:
                self.logger.exception(f"Ошибка загрузки пациента при входе: {e}")
                self.current_patient_changed.emit(None)
        else:
            self.current_patient_changed.emit(None)

        # Вызываем родительский метод для загрузки данных
        super().on_enter(extra_data)           

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _select_row_by_id(self, entity_id: int):
        """
        Находит строку в таблице, соответствующую DTO с заданным ID и выделяет её.
        """
        for row in range(self.source_model.rowCount()):
            dto = self.source_model.get_item_at_row(row)
            if dto and getattr(dto, 'id', None) == entity_id:
                proxy_index = self.proxy_model.mapFromSource(
                    self.source_model.index(row, 0)
                )
                if proxy_index.isValid():
                    self.table_view.setCurrentIndex(proxy_index)
                    self.table_view.scrollTo(proxy_index)
                break