# interfaces/gui/gui_window/pages/dynamic_edit_page.py

# import os

# from app.config.config_manager.manager import get_config_env

import datetime
from typing import Any

from app.utils.logger.logger import AppLogger

from app.dependencies import (
    # get_patient_service , 
    get_note_service , 
    get_photo_service ,
)
from app.utils.virtual_fields import compute_virtual_fields, enrich_dto_with_computed_fields

from interfaces.gui.gui_window.utils.gui_helpers import apply_readonly_to_widgets
from interfaces.gui.gui_window.pages.base_page import BasePage
from interfaces.gui.gui_window.widgets.dynamic_edit_form import DynamicEditForm, CompleterEdit
from interfaces.gui.gui_window.widgets.photo_uploader_widget import PhotoUploaderWidget

from pydantic import BaseModel

from PySide6.QtWidgets import (
    QApplication,
    QVBoxLayout, 
    QHBoxLayout, 
    QPushButton, 
    QMessageBox,
    # QMenu, 
    # QLineEdit, 
    # QSpinBox,
)
from PySide6.QtCore import (
    Qt,
    Signal, 
    Slot, 
    # QAction
)


class DynamicEditPage(BasePage):
    """
    Универсальная страница редактирования записи.

    Автоматически создаёт форму на основе DTO и `field_configs`, поддерживает:
        - Загрузку существующей записи по ID.
        - Создание новой записи.
        - Обработку виртуальных полей (вычисляемых функций).
        - Автодополнение для строковых полей (CompleterEdit).
        - Работу с фотографиями (через PhotoUploaderWidget).

    Сигналы:
        data_saved (Signal(object)): Испускается при сохранении, если `save_directly=False`
            (возвращает DTO без сохранения в БД).

    Параметры инициализации:
        service: Сервис для работы с сущностью (должен реализовывать `create`, `update`, `delete`,
            `get_by_id`, `_session_scope` и т.д.).
        dto_class (Type[BaseModel]): Класс DTO.
        page_title (str): Заголовок страницы.
        exclude_fields (Optional[List[str]]): Список полей, которые не должны отображаться в форме.
        field_configs (Optional[Dict[str, Dict]]): Конфигурация полей.
        related_services (Optional[Dict[str, Any]]): Словарь сервисов для загрузки связанных объектов
            (например, {'patient': patient_service}).
        save_directly (bool): Если True, данные сохраняются в БД сразу; если False – возвращается
            DTO через сигнал `data_saved` (используется для вложенных окон).
        parent (Optional[QWidget]): Родительский виджет.

    Пример страницы редактирования пациента:
        >>> edit_page = DynamicEditPage(
        ...     service=get_patient_service(),
        ...     dto_class=PatientDTO,
        ...     page_title="Редактирование пациента",
        ...     exclude_fields=['id'],
        ...     field_configs=PATIENT_CONFIG,
        ...     save_directly=True,
        ... )
        >>> edit_page.list_page_id = 'patient_list'  # для возврата после сохранения
        >>> # При переходе передаём extra_data={'id': patient_id}
    """

    data_saved = Signal(object)   # испускается при сохранении, если save_directly=False

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self,
        service,  # сервис, используемый для редактирования записи
        dto_class,  # класс DTO, используемый для создания записи
        page_title="Редактирование",  # заголовок страницы
        exclude_fields=None,  # список полей, исключаемых из формы (полное исключение из обработки)
        # field_choices=None,  # словарь, где ключ - название поля, а значение - список значений для выбора
        # field_rename=None,  # словарь, где ключ - название поля, а значение - новое название поля
        parent=None,  # родительский виджет
        field_configs=None,  # внешняя конфигурация
        related_services=None,
        save_directly: bool = True,   # если True, сохраняет в БД; если False, возвращает DTO через сигнал
        readonly: bool = False,  # режим "только просмотр"
        hide_action_buttons: bool = False, # скрывать кнопки действий
    ):
        """
        Инициализирует страницу редактирования.
        
        :param service: сервис, используемый для редактирования записи
        :param dto_class: класс DTO, используемый для создания записи
        :param page_title: заголовок страницы
        :param exclude_fields: список полей, исключаемых из формы (полное исключение из обработки
        :param parent: родительский виджет
        """

        super().__init__(parent)

        # логгер
        self.logger = AppLogger.get_instance(
            name = f"gui.{self.__class__.__name__}",
            # share_file_with = 'user',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'user',
        )

        # self.patient_svc = None  # сервис для работы с пациентами (например, для создания приёма)
        
        # сохраняем параметры инициализации страницы
        self.service = service
        self.dto_class = dto_class
        self.page_title = page_title
        self.exclude_fields = exclude_fields or ['id']
        # self.field_choices = field_choices or {}
        # self.field_rename = field_rename or {}
        self.field_configs = field_configs or {}
        self.related_services = related_services or {}
        self.save_directly = save_directly
        self.readonly = readonly 
        self.hide_action_buttons = hide_action_buttons

        self._extra_data = None

        self._computed_extra_data = None # дополнительные данные, вычисленные из виртуальных полей

        self._loading = False # Блокировка сигналов при загрузке

        # ID редактируемой записи
        self.current_id = None

        # ID пациента при создании приёма
        # self.current_patient_id = None
        # ID приёма (дублирует current_id)
        # self.current_appointment_id = None

        # Для возврата из выбранной страницы
        self._return_to_page_id = None
        self._return_field = None

        self.form = DynamicEditForm(
            dto_class=self.dto_class,
            field_configs=self.field_configs,
            exclude_fields=self.exclude_fields,
        )

        self.photo_service = get_photo_service()
        # self.pending_photos = None   # будет установлен из формы

        # # настройка интерфейса страницы
        self._setup_ui()

        if self.readonly:
            self._set_readonly_mode(True)
            
        if self.hide_action_buttons:
            self._set_action_buttons_visible(False)    

    @AppLogger.get_instance(
        name='DynamicEditPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _fill_default_values(self):
        """
        Заполняет виджеты формы значениями по умолчанию для полей,
        помеченных как required=True.
        """
        self.logger.debug("=== _fill_default_values START ===")

        for field_name, widget in self.form.widgets.items():
            config = self.field_configs.get(field_name, {})
            required = config.get('required', False)

            self.logger.debug(f"Поле {field_name}: required={required}, виджет={type(widget).__name__}")

            if not required:
                continue

            # Определяем тип поля из DTO
            field_info = self.dto_class.model_fields.get(field_name)
            if not field_info:
                continue

            field_type = self._get_real_type(field_info.annotation)
            default_value = self._get_default_value_for_field(field_name, field_type)

            self.logger.debug(f"  -> значение по умолчанию: {default_value}")

            if default_value is not None:
                self.form._set_widget_value(widget, default_value)
                self.logger.debug(f"Установлено значение по умолчанию для поля {field_name}: {default_value}")
                widget.update()   # принудительная перерисовка

        self.logger.debug("=== _fill_default_values END ===")

    @AppLogger.get_instance(
        name='DynamicEditPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _get_real_type(self, field_type):
        """Извлекает реальный тип из Optional/Union."""
        from typing import get_origin, get_args, Union
        origin = get_origin(field_type)
        if origin is Union:
            args = get_args(field_type)
            for arg in args:
                if arg is not type(None):
                    return arg
        return field_type

    @AppLogger.get_instance(
        name='DynamicEditPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _get_default_value_for_field(self, field_name: str, field_type) -> Any:
        """
        Возвращает значение по умолчанию для поля на основе его типа и конфигурации.
        Используется при создании новой записи.

        Args:
            field_name (str): Имя поля.
            field_type (type): Тип поля (из DTO).

        Returns:
            Any: Значение по умолчанию или None, если поле необязательное.
        """
        config = self.field_configs.get(field_name, {})
        if config.get('required', False):
            if field_type == datetime.date:
                return datetime.date.today()
            elif field_type == datetime.time:
                return datetime.time(0, 0)
            elif field_type == str:
                return ""
            elif field_type == int:
                return 0
            elif field_type == bool:
                return False
        # Для необязательных полей возвращаем None
        return None

    @AppLogger.get_instance(
        name='DynamicEditPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _set_action_buttons_visible(self, visible: bool):
        """Показывает или скрывает кнопки сохранения, отмены и удаления."""
        self.save_btn.setVisible(visible)
        self.cancel_btn.setVisible(visible)
        self.delete_btn.setVisible(visible)

    @AppLogger.get_instance(
        name='DynamicEditPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _set_readonly_mode(self, readonly: bool):
        """Устанавливает режим только для чтения для всех виджетов формы."""
        for widget in self.form.widgets.values():

            if hasattr(widget, 'setReadOnly'):
                widget.setReadOnly(readonly)

            elif hasattr(widget, 'setEnabled'):
                widget.setEnabled(not readonly)

        # Дополнительно отключаем кнопки сохранения/удаления
        self.save_btn.setEnabled(not readonly)
        self.delete_btn.setEnabled(not readonly)

        # Кнопка отмены может остаться активной

    @AppLogger.get_instance(
        name='DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _load_autocomplete_data(self):
        """
        Загружает уникальные значения для полей с autocomplete=True
        и устанавливает QCompleter в соответствующие виджеты.
        """
        for field_name, widget in self.form.widgets.items():
            if not isinstance(widget, CompleterEdit):
                continue
            config = self.field_configs.get(field_name, {})
            if not config.get('autocomplete', False):
                continue
            # Имя столбца в БД – либо source_column, либо field_name
            column_name = config.get('source_column', field_name)
            try:
                values = self.service.get_unique_values(column_name)
            except Exception as e:
                self.logger.exception(f"Ошибка получения уникальных значений для {field_name}: {e}")
                continue
            if values:
                from PySide6.QtWidgets import QCompleter
                completer = QCompleter(values)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
                widget.setCompleter(completer)


    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _load_related_objects(self, extra_data):
        """
        Загружает связанные объекты (например, пациента) по ID из extra_data
        и добавляет их в extra_data для использования в виртуальных полях.
        """
        if not extra_data:
            return

        for field_name, config in self.field_configs.items():
            source_attr = config.get('source_attr')
            if not source_attr:
                continue

            # Если объект уже есть в extra_data, пропускаем
            if source_attr in extra_data:
                continue

            # Ищем ключ вида source_attr + '_id'
            id_key = f"{source_attr}_id"
            if id_key in extra_data and extra_data[id_key] is not None:
                service = self.related_services.get(source_attr)
                if service:
                    try:
                        obj = service.get_by_id(extra_data[id_key])
                        if obj:
                            extra_data[source_attr] = obj
                            self.logger.debug(f"Загружен {source_attr} с id={extra_data[id_key]}")
                    except Exception as e:
                        self.logger.exception(f"Ошибка загрузки {source_attr} по id {extra_data[id_key]}: {e}")

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _setup_ui(self):
        """
        Устанавливает интерфейс страницы редактирования.

        Создаёт форму редактирования на основе класса DynamicEditForm.
        Форма создается с использованием виджетов, соответствующих типам полей DTO.
        Создаёт кнопки "Сохранить", "Отмена" и "Удалить" и добавляет их в нижнюю часть интерфейса.
        """
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.form)   # добавляем существующую форму

        # # Создаем форму редактирования
        # self.form = DynamicEditForm(
        #     dto_class=self.dto_class,  # класс DTO, используемый для создания записи
        #     exclude_fields=self.exclude_fields,  # список полей, исключаемых из формы
        #     field_choices=self.field_choices,  # словарь, где ключ - название поля, а значение - список значений для выбора
        #     field_rename=self.field_rename  # словарь, где ключ - название поля, а значение - новое название поля
        # )
        # main_layout.addWidget(self.form)

        # Создаем кнопки "Сохранить", "Отмена" и "Удалить"
        btn_layout = QHBoxLayout()

        self.save_btn = QPushButton("Сохранить")
        self.save_btn.clicked.connect(self._save)  # при нажатии на кнопку вызывается метод _save
        btn_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self._cancel)  # при нажатии на кнопку вызывается метод _cancel
        btn_layout.addWidget(self.cancel_btn)

        self.delete_btn = QPushButton("Удалить")
        self.delete_btn.clicked.connect(self._delete)  # при нажатии на кнопку вызывается метод _delete
        self.delete_btn.setEnabled(False)  # кнопка "Удалить" по умолчанию отключена (для нового приёма)
        btn_layout.addWidget(self.delete_btn)

        # добавляем растяжку в нижнюю часть интерфейса
        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _apply_readonly(self):
        """
        Применяет readOnly для полей, у которых editable=False.
        
        Этот метод необходим для ограничения редактирования полей, которые не должны быть изменены пользователем.
        """
        apply_readonly_to_widgets(
            self.form.widgets, 
            self.field_configs
        )

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    # def _compute_virtual_fields(self, extra_data=None):
    #     """
    #     Вычисляет виртуальные поля формы с помощью функций, заданных в конфигурации.
        
    #     :param extra_data: дополнительные данные, которые могут быть использованы в функциях вычисления
    #     :type extra_data: Optional[Dict[str, Any]]
    #     """
    #     for field_name, config in self.field_configs.items():
    #         compute = config.get('compute')
    #         if not compute:
    #             continue
    #         func = compute.get('func')
    #         if not callable(func):
    #             self.logger.warning(f"Поле {field_name}: 'func' не является callable")
    #             continue

    #         # Собираем позиционные аргументы из полей формы и extra_data
    #         args = []
    #         for arg_name in compute.get('args', []):
    #             if arg_name in self.form.widgets:
    #                 val = self.form._get_widget_value(self.form.widgets[arg_name])
    #                 args.append(val)
    #             elif extra_data and arg_name in extra_data:
    #                 args.append(extra_data[arg_name])
    #             else:
    #                 args.append(None)

    #         kwargs = compute.get('kwargs', {})

    #         try:
    #             value = func(*args, **kwargs)
    #             if field_name in self.form.widgets:
    #                 self.form._set_widget_value(self.form.widgets[field_name], value)
    #         except Exception as e:
    #             self.logger.exception(f"Ошибка вычисления поля {field_name}: {e}")
    #             if field_name in self.form.widgets:
    #                 self.form._set_widget_value(self.form.widgets[field_name], "Ошибка")  
    def _compute_virtual_fields(
        self, 
        extra_data=None
    ):
        """
        Вычисляет виртуальные поля формы с помощью функций, заданных в конфигурации.
        
        :param extra_data: дополнительные данные, которые могут быть использованы в функциях вычисления
        :type extra_data: Optional[Dict[str, Any]]
        """

        # Проверяем, есть ли виртуальные поля
        has_virtual = any(config.get('compute') for config in self.field_configs.values())

        # self.logger.debug(f"has_virtual: {has_virtual}")
        self.logger.debug(f"not has_virtual: {not has_virtual}")

        if not has_virtual:
            return

        # Объединяем сохранённые данные с переданными
        combined = (self._computed_extra_data or {}).copy()

        # self.logger.debug(f"combined: {combined} result: {combined is not None}")
        # self.logger.debug(f"combined is not None: {combined is not None}")
        self.logger.debug(f'if extra_data : {not(extra_data is None)}')
        if extra_data:
            combined.update(extra_data)

        # self.logger.debug(f"combined: {combined}")

        # Собираем текущие данные из формы
        data = self.form.get_data()

        # Вычисляем виртуальные поля
        computed = compute_virtual_fields(
            data, 
            self.field_configs, 
            # extra_data,
            combined,
        )

        # self.logger.debug(f"computed: {computed} combined: {combined} data: {data} self.field_configs: {self.field_configs}")
        self.logger.debug(f"combined: {combined} self.field_configs: {self.field_configs}")

        # Устанавливаем вычисленные значения в виджеты
        for field_name, value in computed.items():

            self.logger.debug(
                f"field_name: {field_name} value: {value} result: {field_name in self.form.widgets and value is not None}"
            )
            if field_name in self.form.widgets and value is not None:

                # Сравниваем с текущим значением, чтобы избежать лишних сигналов
                current = self.form._get_widget_value(self.form.widgets[field_name])
                self.logger.debug(
                    # f"current: {current} value: {value} result: {current != value}"
                    f"current: {current} value: {value} result: {current != value}"
                )
                if current != value:
                    self.form._set_widget_value(self.form.widgets[field_name], value)

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _get_choices(self, provider_name):
        """
        Возвращает список строк для поля с автодополнением.

        :param provider_name: имя провайдера, из которого загружается список строк
        :return: список строк для поля с автодополнением
        """
        if provider_name == 'note_service.get_choices':
            service = get_note_service()
            # Предполагаем, что у сервиса есть метод get_choices, возвращающий список строк
            return service.get_choices()
        # Можно расширить для других сервисов
        return []

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _load_completer_data(self):
        """
        Загружает данные для полей с автодополнением.
        
        Обходит все поля формы и если поле является CompleterEdit, то загружает список строк от провайдера,
        указанного в метаданных поля. Если у поля нет метаданных с именем choices_provider, то пропускает это поле.
        """
        for field_name, widget in self.form.widgets.items():
            if not isinstance(widget, CompleterEdit):
                continue

            # field = self.dto_class.model_fields.get(field_name)
            # if not field:
            #     continue

            # metadata = field.metadata or {}
            metadata = self.field_configs.get(field_name, {})
            provider_name = metadata.get('choices_provider') 
            if not provider_name: 
                continue

            # Получаем список строк от провайдера
            items = self._get_choices(provider_name)
            if items:
                self.form.set_completer_data(field_name, items)       

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _connect_button_signals(self):
        """
        Подключает сигналы кнопок поля с автодополнением к методу _on_edit_button_clicked.
        
        Метод обрабатывает нажатие кнопки в поле с автодополнением и вызывает метод _on_edit_button_clicked с именем поля.
        """
        for field_name, widget in self.form.widgets.items():
            if isinstance(widget, CompleterEdit) and widget.btn:
                widget.button_clicked.connect(lambda fn=field_name: self._on_edit_button_clicked(fn))

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _on_edit_button_clicked(self, field_name):
        """
        Обработка нажатия кнопки '...' для поля с автодополнением.

        Если поле - note_text, то переходим на страницу заметок, передавая текст для предзаполнения.
        """
        if field_name == 'note_text':
            widget = self.form.widgets.get(field_name)

            if not widget:
                return
            
            current_text = widget.text()

            if self.page_manager:
                # Переходим на страницу заметок, передавая текст для предзаполнения
                self.page_manager.switch_to(
                    'note_edit',
                    extra_data={
                        'text': current_text,
                        'return_to_page': self.page_manager.current_page_id, 
                        'return_field': field_name,
                    }
                )
    
    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _init_from_extra(self, extra_data):
        # """Заполняет поля формы значениями из extra_data согласно конфигурации."""
        """
        Инициализирует поля формы значениями из extra_data согласно конфигурации.
        
        Если extra_data не задан, то метод ничего не делает.
        Иначе, метод обходит все поля формы и ищет соответствующую конфигурацию.
        Если конфигурация поля содержит ключ 'init_from_extra', то метод
        пытается установить значение поля из extra_data.
        Если значение ключа 'init_from_extra' - строка, то метод пытается
        найти значение в extra_data по этому ключу и установить его в поле.
        Если значение ключа 'init_from_extra' - True, то метод пытается найти
        значение в extra_data с именем поля и установить его в поле.
        """

        if not extra_data:
            return
        
        for field_name, widget in self.form.widgets.items():
            config = self.field_configs.get(field_name, {})
            init_key = config.get('init_from_extra')
            
            if init_key is None:
                continue

            if isinstance(init_key, str):
                if init_key in extra_data:
                    self.form._set_widget_value(widget, extra_data[init_key])
            
            elif init_key is True:
                if field_name in extra_data:
                    self.form._set_widget_value(widget, extra_data[field_name])
            
            # можно добавить другие варианты (например, callable)



    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _load_existing_entity(
        self, 
        entity_id
    ):
        """
        Загружает существующую запись по ID и сопутствующие данные (например, фото).
        Очищаем форму перед загрузкой (чтобы сбросить pending_photos).
        Устанавливает кнопку удаления в активное состояние.
        """
        # self.logger.debug(f"self._loading: {self._loading}")
        # self._loading = True
        # try:
        # Очищаем форму перед загрузкой (чтобы сбросить pending_photos)

        self.form._loading = True
        try:
            self.form.clear()
        finally:
            self.form._loading = False
        
        self._computed_extra_data = None

        self.logger.debug(f"entity_id: {entity_id} self._computed_extra_data: {self._computed_extra_data}")

        # 1. Собираем список связей из field_configs (source_attr)
        relations = []
        for config in self.field_configs.values():
            source_attr = config.get('source_attr')

            self.logger.debug(
                f"config {config} source_attr: {source_attr} result: {source_attr and source_attr not in relations}"
            )
            if source_attr and source_attr not in relations:
                relations.append(source_attr)

        self.logger.debug(f"relations: {relations} entity_id: {entity_id}")

        # 2. Загружаем ORM-объект с подгруженными связями
        with self.service._session_scope() as session:
            repo = self.service._get_repo(session)
            model_obj = repo.get_with_relations(entity_id, relations)

            self.logger.debug(f"repo: {repo} model_obj: {model_obj}")

            if model_obj is None:
                self.logger.debug(f"model_obj is None")
                raise self.service._not_found_exception(entity_id)

            # 3. Создаём DTO и обогащаем его (extra_data заполняется автоматически)
            try:
                dto = self.service._dto_class.model_validate(model_obj)
                self.logger.debug(f"В _load_existing_entity: dto.photos тип = {type(dto)}")

                if hasattr(dto, 'photos'):
                    self.logger.debug(f"В _load_existing_entity: dto.photos тип = {type(dto.photos)}")
                else:
                    self.logger.debug("В _load_existing_entity: dto не имеет поля photos")

                # if dto.photos:
                #     self.logger.debug(f"  первый элемент: {type(dto.photos[0])}")

            except Exception as e:
                self.logger.exception(f" service._dto_class.model_validate(model_obj) - e: {e}")
                raise e
        
            extra_data = {}
            
            self.logger.debug(
                f"model_obj: {model_obj} dto: {dto} extra_data: {extra_data} self.field_configs: {self.field_configs}"
            )
            dto = enrich_dto_with_computed_fields(
                dto, 
                model_obj, 
                self.field_configs, 
                extra_data
            )

            # 4. Сохраняем extra_data для будущих вычислений
            self._computed_extra_data = extra_data

            self.logger.debug(f"dto: {dto} extra_data: {extra_data} self._computed_extra_data: {self._computed_extra_data}")
            
            # 5. Загружаем DTO в форму
            self.form._loading = True   # <-- блокируем сигналы
            try:
                self.form.load_data(dto)
            finally:
                self.form._loading = False   # <-- снимаем блокировку

        # Принудительное обновление формы
        self.form.update()
        self.form.repaint() # принудительная перерисовка после загрузки 
        QApplication.processEvents()

        # self._load_entity(entity_id) # загружает DTO и вызывает form.load_data

        # photos = self.photo_service.get_photos_for_appointment(entity_id) # загружаем существующие фото
        # # преобразуем в список (photo_id, full_path, description)
        # if 'photos' in self.form.widgets:
        #     self.form.set_photos_data(photos) # передаём список PhotoDTO

        # 6. Включаем кнопку удаления
        self.delete_btn.setEnabled(True) # включаем кнопку удаления
        # finally:
        #     self._loading = False

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _prepare_new_entity(self):
        """
        Подготавливает форму для создания новой записи:
        очищает форму, отключает кнопку удаления.
        """
        self.form._loading = True
        try:
            self.form.clear()
                   
            self._fill_default_values()  # Устанавливаем значения по умолчанию для обязательных полей
        finally:
            self.form._loading = False

        self._computed_extra_data = None # сбрасываем extra_data
        
        self.delete_btn.setEnabled(False)
        # здесь можно добавить другую логику для нового объекта, если нужно

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _after_load_or_clear(self, extra_data=None):
        """
        Выполняет общие действия после загрузки существующей записи или очистки формы:
        - заполнение из extra_data
        - применение readOnly
        - вычисление виртуальных полей
        - загрузка данных для автодополнения
        - подключение сигналов кнопок
        """ 

        self.logger.debug(f"extra_data: {extra_data}")

        # Заполняем из extra_data (после загрузки DTO или после очистки)
        self._init_from_extra(extra_data)

        # Загружаем связанные объекты (пациента, заметку) для виртуальных полей
        self._load_related_objects(extra_data)

        # Применяем readOnly (для всех полей, включая существующие)
        self._apply_readonly()

        # Вычисляем виртуальные поля (например, patient_name)
        # self._compute_virtual_fields(extra_data)
        # self.form._loading = True
        # try:
        #     self._compute_virtual_fields(extra_data)
        # finally:
        #     self.form._loading = False

        # Вычисляем виртуальные поля только для новой записи
        if self._computed_extra_data is None:
            self.form._loading = True
            try:
                self._compute_virtual_fields(extra_data)
            finally:
                self.form._loading = False

        # Загружаем данные для полей с автодополнением
        self._load_completer_data()
        self._load_autocomplete_data() 

        # Подключаем сигналы кнопок
        self._connect_button_signals()

        # Обновление после загрузки
        self.update()


    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def on_enter(self, extra_data=None):
        """
        Вызывается при переходе на страницу.

        Параметры:
            extra_data (dict, optional): Может содержать:
                - 'id': ID редактируемой записи (для загрузки).
                - Любые другие ключи, указанные в `field_configs` как `init_from_extra`.
                - 'return_to_page' и 'return_field' для возврата значения после сохранения.

        Если `id` не передан, форма очищается для создания новой записи.
        """
        
        # загружаем id, если он передан
        self.current_id = extra_data.get('id') if extra_data else None

        # для возврата (если страница вызвана как диалог)
        try:
            self._return_to_page_id = extra_data.get('return_to_page') if extra_data else None
        except Exception as e:
            self.logger.exception(f"Ошибка в методе on_enter: {e}")
            raise e

        try:
            self._return_field = extra_data.get('return_field') if extra_data else None
        except Exception as e:
            self.logger.exception(f"Ошибка в методе on_enter: {e}")
            raise e

        self.logger.debug(
            f"self.current_id is not None: {self.current_id is not None}"
        )

        if self.current_id is not None:
            self._load_existing_entity(self.current_id)
        else:
            self._prepare_new_entity()

        self._extra_data = extra_data   # сохраняем переданные данные        

        self._after_load_or_clear(extra_data)  

        # После загрузки данных применяем readonly
        if self.readonly:
            self._set_readonly_mode(True)

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _load_entity(self, entity_id):
        """
        Загружает запись по ID.
        
        :param entity_id: ID записи, которую мы хотим получить
        :type entity_id: int
        
        :raises: исключение, если запись не найдена
        :return: None
        """
        try:
            # Получаем запись по ID
            dto = self.service.get_by_id(entity_id)
            
            # Если запись найдена, загружаем данные в форму
            self.form.load_data(dto)
            self.logger.debug(f"Загружена запись id={entity_id}")
        except Exception as e:
            # Если запись не найдена, выводим сообщение об ошибке
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить данные: {e}")
            self.logger.exception(f"Ошибка загрузки записи: {e}")
            # Возвращаемся на предыдущую страницу
            self._go_back()


    # ------------------------------------------------------------
    # Вспомогательные методы для сохранения
    # ------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _collect_form_data(self) -> dict:
        """
        Собирает данные из формы и возвращает словарь для создания DTO.
        Возвращает словарь, содержащий значения из всех виджетов формы.
        :return: словарь с значениями из виджетов формы
        :rtype: dict
        """
        return self.form.get_data()

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _create_or_update_entity(self, dto):
        """
        Создаёт или обновляет сущность в зависимости от self.current_id.
        Если self.current_id is None, создает новую запись.
        Если self.current_id не None, обновляет существующую запись.
        Возвращает кортеж (saved_dto, appointment_id).
        saved_dto - обновленный (или созданный) DTO.
        appointment_id - ID созданной или обновленной записи.
        """
        if self.current_id is None:
            # Создание
            created = self.service.create(dto)
            saved_dto = created
            appointment_id = created.id
            QMessageBox.information(self, "Успех", f"Запись создана с ID {created.id}")
            self.logger.info(f"Создана запись ID={created.id}")
        else:
            # Обновление
            dto.id = self.current_id
            updated = self.service.update(dto)
            saved_dto = updated
            appointment_id = self.current_id
            QMessageBox.information(self, "Успех", f"Запись ID {updated.id} обновлена")
            self.logger.info(f"Обновлена запись ID={updated.id}")
        return saved_dto, appointment_id

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    # def _handle_photos(self, appointment_id: int):
    #     """
    #     Удаляет помеченные фото и добавляет новые.
        
    #     :param appointment_id: ID приема
    #     :type appointment_id: int
    #     """
    #     # Если виджета 'photos' не существует, то ничего не делаем
    #     if 'photos' not in self.form.widgets:
    #         return
        
    #     # Получаем виджет 'photos'
    #     widget = self.form.widgets['photos']

    #      # Если виджет 'photos' не является PhotoUploaderWidget, то ничего не делаем
    #     if not isinstance(widget, PhotoUploaderWidget):
    #         return
        
    #     # Удаляем помеченные фото
    #     deleted_photo_ids = widget.get_deleted_photo_ids()
    #     for photo_id in deleted_photo_ids:
    #         self.photo_service.delete_photo(photo_id)
    #         # Логируем удаление фото
    #         self.logger.info(f"Удалено фото с ID={photo_id}")

    #     # Добавляем новые фото
    #     for file_path, description in widget.get_pending_photos():
    #         photo_dto = self.photo_service.add_photo_to_appointment(
    #             appointment_id, 
    #             file_path, 
    #             description
    #         )
    #         # Логируем добавление нового фото
    #         self.logger.info(f"Добавлено новое фото с ID={photo_dto.id}")  
    def _handle_photos(self, appointment_id: int):
        # Перебираем все виджеты формы
        """
        Удаляет помеченные фото и добавляет новые.

        :param appointment_id: ID приема
        :type appointment_id: int
        """
        for widget in self.form.widgets.values():
            if isinstance(widget, PhotoUploaderWidget):
                # Обрабатываем новый, удалённые и обновлённые описания
                pending = widget.get_pending_photos() # список (путь к фото, описание)
                deleted = widget.get_deleted_photo_ids() # список ID на удаление
                self.photo_service.update_photos_for_appointment( # обновляем фото
                    appointment_id, 
                    pending, 
                    deleted
                )

                # Обновляем описания существующих фото
                for photo in widget.get_existing_photos():
                    if photo.id in deleted:  # если фото помечено на удаление, пропускаем
                        continue

                    self.photo_service.update_photo_description(photo.id, photo.description)

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _after_save_navigation(self, saved_dto: BaseModel) -> None:
        """
        Выполняет навигацию после сохранения данных из формы.

        Если self._return_to_page_id задан, то возвращает на страницу с этим ID,
        передавая saved_dto в качестве значения для поля self._return_field.
        Если self._return_to_page_id не задан, то возвращает на список и помечает
        его на обновление.

        Args:
            saved_dto (BaseModel): Сохранённый DTO (с заполненным id).

        """

        if not self.page_manager:
            return
        
        # Если есть целевая страница для возврата (например, из заметок)
        # Если self._return_to_page_id задан, то возвращает на страницу с этим ID,
        # передавая saved_dto в качестве значения для поля self._return_field
        if self._return_to_page_id:
            # Получаем страницу, на которую мы хотим перейти
            target_page = self.page_manager._pages.get(self._return_to_page_id)
            if target_page and hasattr(target_page, 'set_field_value'):
                # Возвращаемое значение: для заметок – текст, для других – строка DTO
                value = getattr(saved_dto, 'text', None) or str(saved_dto)
                # Устанавливаем значение saved_dto в поле self._return_field на target_page
                target_page.set_field_value(self._return_field, value)
            # Переходим на target_page
            self.page_manager.switch_to(self._return_to_page_id)
            return
        # else:
        #     # Обычный возврат: помечаем список на обновление
        #     if hasattr(self, 'list_page_id') and self.list_page_id:

        #         # Помечаем страницу списка на обновление (чтобы данные перезагрузились)
        #         list_page = self.page_manager._pages.get(self.list_page_id)
        #         if list_page and hasattr(list_page, 'set_needs_refresh'):
        #             # Устанавливаем флаг needs_refresh на True, чтобы список обновился
        #             list_page.set_needs_refresh(True)

        #         # Переходим на список и передаём ID созданной/обновлённой записи для выделения
        #         self.page_manager.switch_to(
        #             self.list_page_id,
        #             extra_data={'select_id': saved_dto.id},
        #             add_to_history=False ,
        #         )
        #         # self._go_back() # Возвращаемся на предыдущую страницу
        #     else:
        #         # Запасной вариант: просто вернуться назад
                
        #         self._go_back() # Возвращаемся на предыдущую страницу

        # Обычный случай: возврат на предыдущую страницу (список)
        #    Найти страницу списка (если известен её ID)
        # list_page = None
        # Помечаем список на обновление (если известен ID)
        if hasattr(self, 'list_page_id') and self.list_page_id:
            list_page = self.page_manager._pages.get(self.list_page_id)
            if list_page and hasattr(list_page, 'set_needs_refresh'):
                list_page.set_needs_refresh(True)

        # #    Пометить страницу списка на обновление
        # if list_page and hasattr(list_page, 'set_needs_refresh'):
        #     list_page.set_needs_refresh(True)
        #     self.logger.debug(f"Страница списка {self.list_page_id} помечена на обновление")

        #    Вернуться на предыдущую страницу (история сохранит контекст)
        self._go_back()



    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _build_dto_from_form_data(self) -> BaseModel:
        """
        Собирает данные из формы и создаёт DTO.
        :return: экземпляр DTO, соответствующий self.dto_class
        """
        data = self._collect_form_data()

        # # Если поле patient_id скрыто, берём его из extra_data (self._computed_extra_data или self.current_extra
        # if 'patient_id' not in data and self._extra_data and 'patient_id' in self._extra_data:
        #     data['patient_id'] = self._extra_data['patient_id']

        # Специальная обработка для поля patient_id (если оно есть в DTO и скрыто в форме)
        if hasattr(self.dto_class, 'model_fields') and 'patient_id' in self.dto_class.model_fields:
            if 'patient_id' not in data and self._extra_data and 'patient_id' in self._extra_data:
                data['patient_id'] = self._extra_data['patient_id' ]
        
        self.logger.debug(f"data: {data}")

        return self.dto_class(**data)
    
    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _save(self):
        # """Сохраняет данные из формы в БД."""
        """
        Сохраняет данные из формы в БД в зависимости от режима save_directly.

        1. Собирает данные из формы
        2. Создает или обновляет запись
        3. Обрабатывает фотографии
        4. Навигация

        Если возникла ошибка, выводит сообщение об ошибке
        """
        
        try:
            # 1. Создать DTO из данных формы
            dto = self._build_dto_from_form_data()

            self.logger.debug(f"if self.save_directly: {self.save_directly}")
            if self.save_directly:
                # Сохраняем или обновляем в БД
                saved_dto, appointment_id = self._create_or_update_entity(dto)
                # Обработать фотографии
                self._handle_photos(appointment_id)
                # Навигация
                self._after_save_navigation(saved_dto)
            else:
                # Режим без сохранения в БД: возвращаем DTO через сигнал и закрываем форму
                self.data_saved.emit(dto)
                self._go_back()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить: {e}")
            self.logger.exception(f"Ошибка сохранения: {e}")

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_field_value(self, field_name: str, value):
        """
        Устанавливает значение в указанное поле формы (используется при возврате из дочерних окон).

        Параметры:
            field_name (str): Имя поля.
            value (Any): Новое значение.
        """
        
        if field_name in self.form.widgets:
            self.form._set_widget_value(self.form.widgets[field_name], value)

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _delete(self):
        """
        Удаляет текущую запись.

        1. Проверяем, существует ли запись.
        2. Если запись существует, то выводим предупреждение о необходимости подтверждения.
        3. Если пользователь подтвердил удаление, то удаляем запись.
        4. Если запись успешно удалена, то выводим информационное сообщение и обновляем список записей.
        """
        if not self.current_id:
            return
        reply = QMessageBox.question(
            self, "Подтверждение",
            "Удалить эту запись?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.service.delete(self.current_id)
                QMessageBox.information(self, "Успех", "Запись удалена")
                self.logger.info(f"Удалена запись ID={self.current_id}")

                if self.page_manager and hasattr(self, 'list_page_id'):
                    list_page = self.page_manager._pages.get(self.list_page_id)
                    if list_page and hasattr(list_page, 'set_needs_refresh'):
                        list_page.set_needs_refresh(True)

                self._go_back()
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
                self.logger.exception(f"Ошибка удаления: {e}")

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _cancel(self):
        """
        Отмена редактирования записи.
        Помечает страницу списка на обновление и возвращается на предыдущую страницу.
        """
        # Помечаем страницу списка на обновление, если известна
        if self.page_manager and hasattr(self, 'list_page_id'):
            list_page = self.page_manager._pages.get(self.list_page_id)
            if list_page and hasattr(list_page, 'set_needs_refresh'):
                list_page.set_needs_refresh(True)
        self._go_back()

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _go_back(self):
        """
        Возврат на предыдущую страницу.
        
        Это метод вызывается, когда пользователь хочет отказаться от редактирования записи.
        Он не делает никаких изменений в базе данных.
        
        Если page_manager существует, то вызываем у него метод go_back.
        Это приводит к возврату на предыдущую страницу.
        """
        if self.page_manager:
            # вызываем у page_manager метод go_back
            # это приводит к возврату на предыдущую страницу
            self.page_manager.go_back()
    
    
