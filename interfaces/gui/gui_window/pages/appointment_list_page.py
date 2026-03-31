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

from interfaces.gui.gui_window.pages.dynamic_detail_list_page import DynamicDetailListPage
from interfaces.gui.gui_window.widgets.photo_uploader_widget import PhotoUploaderWidget

from PySide6.QtWidgets import (
    # QTableView, QPushButton, QHeaderView, QMessageBox,
    # QLineEdit, 
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, 
    QSplitter, QTextEdit, 
    QListWidget, QListWidgetItem, 
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

from PySide6.QtGui import QPixmap, QIcon


class AppointmentListPage(DynamicDetailListPage):
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
        # description="AppointmentListPage.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
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

        # Создаём виджеты правой панели (после того как detail_layout создан в родительском _setup_ui)
        self._setup_detail_panel()

        self.photo_service = get_photo_service()
        self.patient_service = get_patient_service()
        
        # self.current_appointment_id = None  # хранит id выбранного приёма для отображения 
        # self.current_patient_info = None # хранит DTO пациента для отображения сверху

        # Флаг, указывающий, что в правой панели есть несохранённые изменения (фото/заметка)
        self._right_panel_modified = False

        # Блокируем сигналы при загрузке данных в правую панель
        self._loading_right_panel = False

        # # Создаём виджеты правой панели (будет вызвано в _setup_detail_panel)
        # self.note_text_edit = None
        # self.photo_widget = None

        # self._setup_detail_panel()

    # @AppLogger.get_instance(
    #     name = 'AppointmentListPage',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    # def _load_photos(self, appointment_id):
    #     """
    #     Загружает фото для приёма и отображает их в списке.

    #     :param appointment_id: ID приёма
    #     :raises Exception: если произошла ошибка загрузки
    #     """
    #     self.photo_list.clear()
    #     try:
    #         photos = self.photo_service.get_photos_for_appointment(appointment_id)
    #         for photo in photos:
    #             # TODO: загружать реальный QPixmap из файла
    #             pixmap = QPixmap()  # заглушка
    #             if not pixmap.isNull():
    #                 icon = QIcon(pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    #             else:
    #                 icon = QIcon()
    #             item = QListWidgetItem(icon, photo.description or "")
    #             item.setData(Qt.UserRole, photo.id)
    #             self.photo_list.addItem(item)
    #     except Exception as e:
    #         self.logger.exception(f"Ошибка загрузки фото: {e}")

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def showEvent(self, event):
        """Переопределяем showEvent для установки размеров вертикального сплиттера после отображения окна."""
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
        if hasattr(self, 'vertical_splitter'):
            total_height = self.height()
            # Устанавливаем панели высоту, остальное — горизонтальному сплиттеру
            panel_height = self._patient_info_frame_setMinimumHeight
            # Если общая высота меньше panel_height + минимальная высота для второй части (например, 100),
            # можно скорректировать, чтобы не было отрицательных значений.
            min_remaining = 80

            if total_height < panel_height + min_remaining:
                panel_height = max(panel_height, total_height - min_remaining)
            self.vertical_splitter.setSizes([panel_height, total_height - panel_height])
            self.logger.debug(f"_fix_splitter_sizes: set panel height to {panel_height}, "
                            f"total height {total_height}, sizes: {self.vertical_splitter.sizes()}")


            # Принудительно обновляем геометрию всех затронутых виджетов
            self.vertical_splitter.updateGeometry()
            self.patient_info_frame.updateGeometry()
            self.table_view.updateGeometry()
            self.table_view.viewport().update()
            self.table_view.scheduleDelayedItemsLayout()  # пересчёт строк таблицы

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
    # Переопределение построения интерфейса
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_ui(self):
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

        # Создаём панель информации о пациенте
        self._setup_patient_info_panel()

        # Добавляем панель информации в вертикальный сплиттер
        self.vertical_splitter.addWidget(self.patient_info_frame)

        # Добавляем горизонтальный сплиттер
        self.vertical_splitter.addWidget(horizontal_splitter)

        # Настраиваем пропорции: панель информации не растягивается, горизонтальный сплиттер растягивается
        self.vertical_splitter.setStretchFactor(0, 0)
        self.vertical_splitter.setStretchFactor(1, 1)

        # Добавляем вертикальный сплиттер в main_layout
        self.main_layout.addWidget(self.vertical_splitter)

        # Устанавливаем стили для обоих сплиттеров
        self._apply_splitter_style(self.vertical_splitter)
        self._apply_splitter_style(horizontal_splitter)

        # Устанавливаем начальные размеры (панель информации – 100px, остальное – остаток)
        # Точное значение будет установлено в showEvent, когда окно станет видимым
        self.vertical_splitter.setSizes([100, self.height() - 100])

        # Если self.height() ещё 0, установим фиксированные размеры
        self.logger.debug(f"self.height() : {self.height()}")
        if self.height() == 0:
            self.vertical_splitter.setSizes([200, 600])

        self.logger.debug(f"Vertical splitter sizes after setup: {self.vertical_splitter.sizes()}")

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_patient_info_panel(self):
        """
        Создаёт панель с информацией о пациенте на основе PATIENT_CONFIG:
        - QFrame с QScrollArea, внутри которого вертикальный layout с QLabel для каждой строки.
        - Позволяет прокручивать содержимое, если оно не помещается.
        - Высота панели изменяется с помощью разделителя вертикального сплиттера.

        Для каждого поля, не помеченного как hidden и не исключённого, создаётся QLabel.
        """
        
        self.patient_info_frame = QFrame()
        self.patient_info_frame.setFrameShape(QFrame.Shape.StyledPanel)        
        self.patient_info_frame.setMinimumHeight(self._patient_info_frame_setMinimumHeight)   # минимальная высота для удобства
        # self.patient_info_frame.setVisible(False)

        # Временный цвет для отладки
        self.patient_info_frame.setStyleSheet("background-color: lightblue;")

        layout = QHBoxLayout(self.patient_info_frame)
        layout.setContentsMargins(5, 5, 5, 5)

        # Область прокрутки
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)    
        scroll.setMinimumHeight(10)  # добавили минимальную высоту для scroll
        layout.addWidget(scroll)

        # Виджет-контейнер для содержимого
        content_widget = QWidget()
        scroll.setWidget(content_widget)

        # # Вертикальный layout для содержимого
        # self.info_layout = QVBoxLayout(content_widget)
        # self.info_layout.setSpacing(5)


        # Используем QGridLayout для сетки с двумя колонками
        grid = QGridLayout(content_widget)
        grid.setSpacing(5)

        # Словарь для хранения виджетов значений по имени поля
        self.info_value_widgets = {}
        row = 0

        # Перебираем поля из конфигурации пациента
        # Можно отсортировать по порядку, если нужно
        for field_name, config in PATIENT_CONFIG.items():
            # Пропускаем скрытые поля и id
            self.logger.debug(
                f"row: {row}, if config.get('hidden', False) or field_name == 'id': {config.get('hidden', False) or field_name == 'id'}"
            )
            if config.get('hidden', False) or field_name == 'id':
                continue

            # Заголовок из конфигурации
            title = config.get('title', field_name.replace('_', ' ').title())

            # # Создаём горизонтальный layout для заголовка и значения
            # h_layout = QHBoxLayout()
            # h_layout.setSpacing(10)

            label_title = QLabel(f"{title}:")
            label_title.setStyleSheet("font-weight: bold;")
            
            # Выравниваем по верхнему краю, чтобы при многострочном тексте заголовок был на одной линии с первой строкой
            label_title.setAlignment(Qt.AlignTop)

            # Значение поля (правая колонка)
            label_value = QLabel()
            label_value.setWordWrap(True)
            
            # Разрешаем растягиваться по горизонтали
            label_value.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            # label_value.setText(f"строка {row}")

            # Добавляем в сетку
            grid.addWidget(label_title, row, 0, alignment=Qt.AlignTop)
            grid.addWidget(label_value, row, 1, alignment=Qt.AlignTop)

            # Вторая колонка (значения) должна занимать всё доступное горизонтальное пространство
            # Устанавливаем растяжение колонки значений
            grid.setColumnStretch(1, 1)

            # h_layout.addWidget(label_title)
            # h_layout.addWidget(label_value)
            # h_layout.addStretch()

            # self.info_layout.addLayout(h_layout)

            # Сохраняем виджет значения для последующего обновления
            self.info_value_widgets[field_name] = label_value

            row += 1

        # Добавляем растягивающуюся строку в конце, чтобы содержимое не прижималось к верху
        grid.setRowStretch(row, 1)


        # # Растяжка, чтобы содержимое не прижималось к верху
        # self.info_layout.addStretch()

        # По умолчанию панель скрыта, пока нет выбранного пациента
        self.patient_info_frame.setVisible(False)

        # Подключаем сигнал изменения пациента к обновлению панели
        self.current_patient_changed.connect(self._update_patient_info)



        # self.patient_info_label = QLabel()
        # self.patient_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # self.patient_info_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        # layout.addWidget(self.patient_info_label)

        # # Можно добавить дополнительные поля, например, дату рождения, телефон
        # # Но для простоты пока только ФИО
        # layout.addStretch()

        # # Подключаем сигнал изменения текущего пациента для обновления панели
        # self.current_patient_changed.connect(self._update_patient_info)

    # @AppLogger.get_instance(
    #     name='AppointmentListPage',
    #     enable_file_logging='system',
    #     use_name_in_filename='system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    def _debug_widget_hierarchy(self, widget, level=0):
        """Рекурсивно выводит информацию о виджете и его детях."""
        indent = "  " * level
        self.logger.debug(f"{indent}Widget: {widget.__class__.__name__} "
                          f"visible={widget.isVisible()} size={widget.size()} "
                          f"pos={widget.pos()} geometry={widget.geometry()}")
        if hasattr(widget, 'layout'):
            layout = widget.layout()
            if layout:
                self.logger.debug(f"{indent}  Layout: {layout.__class__.__name__} count={layout.count()}")
                for i in range(layout.count()):
                    item = layout.itemAt(i)
                    if item.widget():
                        self._debug_widget_hierarchy(item.widget(), level+1)
                    elif item.layout():
                        self._debug_widget_hierarchy(item.layout(), level+1)
    
    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _update_patient_info(self, patient_dto):
        # """
        # Обновляет панель информации о пациенте.
        # :param patient_dto: DTO пациента (PatientDTO) или None, если пациент не выбран.
        # """
        # if patient_dto:
        #     full_name = f"{patient_dto.last_name} {patient_dto.first_name}"

        #     # Можно добавить дату рождения
        #     birth_str = patient_dto.birth_date.isoformat() if patient_dto.birth_date else ""
        #     info_text = f"Пациент: {full_name}"
        #     if birth_str:
        #         info_text += f" | Дата рождения: {birth_str}"
        #     self.patient_info_label.setText(info_text)
        #     self.patient_info_frame.setVisible(True)
        # else:
        #     self.patient_info_frame.setVisible(False)
    
        """
        Обновляет содержимое панели информации о пациенте на основе DTO и конфигурации.
        """

        self.logger.debug(f"_update_patient_info called, patient_dto: {patient_dto is not None}")
        if patient_dto:
            # Получаем данные в виде словаря
            data = patient_dto.model_dump(exclude_none=True)

            # Для каждого поля, для которого есть виджет, форматируем значение
            for field_name, label in self.info_value_widgets.items():
                self.logger.debug(f'field_name: {field_name}, label: {label}')

                value = data.get(field_name)
                self.logger.debug(f'if value is None: {value is None}')

                if value is None:
                    label.setText("—")

                else:
                    self.logger.debug(f'value: {type(value)}')

                    # Форматирование в зависимости от типа
                    if isinstance(value, datetime.date):
                        label.setText(value.isoformat())
                    elif isinstance(value, datetime.time):
                        label.setText(value.strftime("%H:%M"))
                    else:
                        label.setText(str(value))

            self.patient_info_frame.setVisible(True)
            # self.logger.debug('self.patient_info_frame.setVisible(True)')

            # Принудительное обновление геометрии
            self.patient_info_frame.update()
            self.patient_info_frame.repaint()
            # Обновляем вертикальный сплиттер
            self.vertical_splitter.update()

#             self.logger.debug(
#                 f"""
                



# """
#             )

#             self.logger.debug(
#                 f"Patient info frame visible: {self.patient_info_frame.isVisible()}, size: {self.patient_info_frame.size()}"
#             )
#             0==0

#             self.logger.debug("=== Debugging patient info panel hierarchy ===")
#             self._debug_widget_hierarchy(self.patient_info_frame)
#             self.logger.debug(f"vertical_splitter sizes: {self.vertical_splitter.sizes()}")
#             self.logger.debug(f"vertical_splitter geometry: {self.vertical_splitter.geometry()}")
#             self.logger.debug(f"patient_info_frame geometry after setVisible: {self.patient_info_frame.geometry()}")

#             0==0
        else:
            # Очищаем все поля
            for label in self.info_value_widgets.values():
                label.setText("—")

            self.patient_info_frame.setVisible(False)

    # ----------------------------------------------------------------------
    # Методы, отвечающие за правую панель (заметка и фото)
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_detail_panel(self):
        """
        Создает виджету правой панели.

        Создает виджету с заметкой и фотографиями приема.
        """

        # Создаем виджету с заметкой
        self.note_text_edit = QTextEdit()      
        self.note_text_edit.setReadOnly(True) # Установка режима "только для чтения"
        self.note_text_edit.textChanged.connect(self._on_note_text_changed)

        # Добавляем виджету с заметкой в верхнюю часть detail_layout
        self.detail_layout.addWidget(QLabel("Заметка:"))
        self.detail_layout.addWidget(self.note_text_edit)


        # # Создаем виджету со списком фотографий
        # self.photo_list = QListWidget()

        # # Установка размера иконок фотографий
        # self.photo_list.setIconSize(QSize(100, 100))

        self.photo_widget = PhotoUploaderWidget()
        config = get_config_env()
        storage_path = config.get(
            'PHOTOS_STORAGE_PATH', 
            os.path.join(
                '.', 
                'photos'
            ),
        )
        self.logger.debug(f'storage_path: {storage_path}')
        self.photo_widget.set_storage_path(storage_path)
        self.photo_widget.set_readonly(True) # изначально только просмотр
        self.photo_widget.photosChanged.connect(self._on_photos_changed)

        # Добавляем виджету со списком фотографий в верхнюю часть detail_layout
        self.detail_layout.addWidget(QLabel("Фотографии:"))
        self.detail_layout.addWidget(self.photo_widget)

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_note_text_changed(self):
        """
        Обработчик изменения текста заметки в правой панели.
        Обновляет DTO текущей строки и помечает строку как изменённую (если режим редактирования).
        """
        if self._loading_right_panel:
            return

        if not self.edit_mode:
            return

        if not self.selected_dto:
            return

        new_text = self.note_text_edit.toPlainText()
        # Если текст не изменился, ничего не делаем
        if getattr(self.selected_dto, 'note_text', None) == new_text:
            return

        # Обновляем dto
        self.selected_dto.note_text = new_text
        # Помечаем строку как изменённую
        self._mark_current_row_modified()
        self.logger.debug(f"Заметка изменена для приёма ID={self.selected_dto.id}")

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_photos_changed(self): # обьединить с _on_note_text_changed
        """
        Обработчик изменения списка фотографий (добавление/удаление/изменение описания).
        Помечает текущую строку как изменённую.
        """
        if self._loading_right_panel:
            return

        if not self.edit_mode:
            return

        if not self.selected_dto:
            return

        # Помечаем строку как изменённую
        self._mark_current_row_modified()
        self.logger.debug(f"Фото изменены для приёма ID={self.selected_dto.id}")
    
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
            self._update_row_color(source_row)   # обновляем цвет строки
            self._update_save_button_state()    # активируем кнопку сохранения

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_edit_mode_toggled(self, checked: bool):
        """
        Переопределяем метод для включения/отключения редактирования виджетов правой панели.
        """
        # Вызываем родительский метод для управления кнопками и флагом edit_mode
        super()._on_edit_mode_toggled(checked)

        # Настраиваем виджеты правой панели в зависимости от режима
        if self.edit_mode:
            # Включаем редактирование заметки
            self.note_text_edit.setReadOnly(False)
            # Включаем редактирование фото
            self.photo_widget.set_readonly(False)
        else:
            # Запрещаем редактирование
            self.note_text_edit.setReadOnly(True)
            self.photo_widget.set_readonly(True)

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _save_changes(self):
        """
        Переопределяем метод сохранения изменений.
        Сначала вызываем родительский метод, который сохранит все изменения строк (включая заметки),
        а затем обрабатываем изменения фотографий для текущей строки.
        """
        # Сохраняем все изменения строк (заметки, даты, время и т.д.)
        super()._save_changes()

        # После сохранения строк обрабатываем фотографии для текущего приёма,
        # если он был изменён (имеет pending_photos или удалённые фото).
        if self.selected_dto and self.selected_dto.id:
            pending = self.photo_widget.get_pending_photos()
            deleted = self.photo_widget.get_deleted_photo_ids()
            # Также нужно обработать изменения описаний существующих фото
            # Для этого мы можем использовать тот же метод update_photos_for_appointment,
            # который сам обработает всё (он удаляет, добавляет и обновляет описания).
            if pending or deleted:
                try:
                    self.photo_service.update_photos_for_appointment(
                        self.selected_dto.id,
                        pending,
                        deleted
                    )
                    self.logger.info(f"Обновлены фото для приёма ID={self.selected_dto.id}")
                    # После сохранения фото обновляем данные в правой панели
                    self._refresh_photos()
                except Exception as e:
                    self.logger.exception(f"Ошибка сохранения фото: {e}")
                    # Можно показать сообщение пользователю, но parent может быть не доступен.
                    # Ограничимся логом.
            else:
                self.logger.debug("Нет изменений фото для сохранения")
        else:
            self.logger.debug("Нет выбранного приёма для сохранения фото")

    @AppLogger.get_instance(
        name='AppointmentListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _refresh_photos(self):
        """
        Обновляет список фотографий в правой панели, перезагружая их из БД.
        """
        if not self.selected_dto:
            return
        try:
            photos = self.photo_service.get_photos_for_appointment(self.selected_dto.id)
            self._loading_right_panel = True
            try:
                self.photo_widget.set_existing_photos(photos)
            finally:
                self._loading_right_panel = False
        except Exception as e:
            self.logger.exception(f"Ошибка перезагрузки фото: {e}")

    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def update_details(self, dto):
        """
        Обновляет правую панель данными выбранного приёма.
        Вызывается автоматически при выборе строки в таблице.

        :param dto: данные приёма
        :type dto: AppointmentDTO
        """

        # self.logger.debug(f"dto {dto}")
        self.logger.debug(f"update_details получил dto типа {type(dto)}")
        if not dto:
            return
        
        self.current_appointment_id = dto.id


        # Блокируем сигналы правой панели, чтобы не триггерить _on_note_text_changed и _on_photos_changed при загрузке
        self._loading_right_panel = True
        try:
            # Загружаем текст заметки
            self.note_text_edit.setText(dto.note_text or "")

            # Загружаем фото

            self.logger.debug(f"Проверка photos: hasattr={hasattr(dto, 'photos')}, is not None={dto.photos is not None}")
            if hasattr(dto, 'photos') and dto.photos is not None:
                self.logger.debug(f"dto.photos тип = {type(dto.photos)}")
                self.photo_widget.set_existing_photos(dto.photos)
            else:
                self.photo_widget.set_existing_photos([])
        except Exception as e:
            self.logger.exception(f"Ошибка загрузки данных приёма: {e}")
        finally:
            self._loading_right_panel = False
        
        # Обновляем панель информации о пациенте
        # Для этого нужно получить данные пациента по patient_id из dto
        try:
            if dto.patient_id:
                patient_dto = self.patient_service.get_patient_by_id(dto.patient_id)
                self.current_patient_changed.emit(patient_dto)
            else:
                self.current_patient_changed.emit(None)
        except Exception as e:
            self.logger.exception(f"Ошибка загрузки пациента: {e}")
            self.current_patient_changed.emit(None)


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
