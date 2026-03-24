# interfaces/gui/gui_window/pages/dynamic_edit_page.py
# -*- coding: utf-8 -*-

from app.utils.logger.logger import AppLogger

from app.dependencies import get_patient_service , get_note_service # добавить в импорты

from interfaces.gui.gui_window.pages.base_page import BasePage
from interfaces.gui.gui_window.widgets.dynamic_edit_form import DynamicEditForm, CompleterEdit

from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox#, QLineEdit, QSpinBox
from PySide6.QtCore import Slot

class DynamicEditPage(BasePage):
    """
    Универсальная страница редактирования.
    Поддерживает автоматическую подстановку patient_id при создании приёма.
    """

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicEditPage.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
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
    ):
        """
        Инициализирует страницу редактирования.
        
        :param service: сервис, используемый для редактирования записи
        :param dto_class: класс DTO, используемый для создания записи
        :param page_title: заголовок страницы
        :param exclude_fields: список полей, исключаемых из формы (полное исключение из обработки
        # :param field_choices: словарь, где ключ - название поля, а значение - список значений для выбора
        # :param field_rename: словарь, где ключ - название поля, а значение - новое название поля
        :param parent: родительский виджет
        """
        super().__init__(parent)

        # логгер страницы
        self.logger = AppLogger.get_instance(
            name = f"gui.{self.__class__.__name__}",
            enable_file_logging = 'user',
            use_name_in_filename = 'user',
        )


        self.patient_svc = None  # сервис для работы с пациентами (например, для создания приёма)
        
        # сохраняем параметры инициализации страницы
        self.service = service
        self.dto_class = dto_class
        self.page_title = page_title
        self.exclude_fields = exclude_fields or ['id']
        # self.field_choices = field_choices or {}
        # self.field_rename = field_rename or {}
        self.field_configs = field_configs or {}

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

        # # настройка интерфейса страницы
        self._setup_ui()

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicEditPage._setup_ui",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _apply_readonly(self):
        # """Применяет readOnly для полей, у которых editable=False."""
        """
        Применяет readOnly для полей, у которых editable=False.
        
        Этот метод необходим для ограничения редактирования полей, которые не должны быть изменены пользователем.
        """
        for field_name, widget in self.form.widgets.items():
            config = self.field_configs.get(field_name, {})
            if not config.get('editable', True):
                if hasattr(widget, 'setReadOnly'):
                    widget.setReadOnly(True)

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _compute_virtual_fields(self, extra_data=None):
        """
        Вычисляет виртуальные поля формы с помощью функций, заданных в конфигурации.
        
        :param extra_data: дополнительные данные, которые могут быть использованы в функциях вычисления
        :type extra_data: Optional[Dict[str, Any]]
        """
        for field_name, config in self.field_configs.items():
            compute = config.get('compute')
            if not compute:
                continue
            func = compute.get('func')
            if not callable(func):
                self.logger.warning(f"Поле {field_name}: 'func' не является callable")
                continue

            # Собираем позиционные аргументы из полей формы и extra_data
            args = []
            for arg_name in compute.get('args', []):
                if arg_name in self.form.widgets:
                    val = self.form._get_widget_value(self.form.widgets[arg_name])
                    args.append(val)
                elif extra_data and arg_name in extra_data:
                    args.append(extra_data[arg_name])
                else:
                    args.append(None)

            kwargs = compute.get('kwargs', {})

            try:
                value = func(*args, **kwargs)
                if field_name in self.form.widgets:
                    self.form._set_widget_value(self.form.widgets[field_name], value)
            except Exception as e:
                self.logger.exception(f"Ошибка вычисления поля {field_name}: {e}")
                if field_name in self.form.widgets:
                    self.form._set_widget_value(self.form.widgets[field_name], "Ошибка")  


    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicEditPage._connect_button_signals",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicEditPage._on_edit_button_clicked",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def on_enter(self, extra_data=None):
        """
        Вызывается при переходе на страницу.
        extra_data может содержать 'id' и 'patient_id'.

        Если передан 'id' – загружаем существующую запись.
        Если передан 'patient_id' и нет 'id' – создаём новый приём для этого пациента.

        :param extra_data: словарь с дополнительными данными
        :type extra_data: dict
        """
        # загружаем id, если он передан
        # current_id - это ID записи, которую мы хотим отредактировать

        self.current_id = extra_data.get('id') if extra_data else None

        # загружаем patient_id, если он передан
        # current_patient_id - это ID пациента, для которого мы хотим создать новый приём
        # self.current_patient_id = extra_data.get('patient_id') if extra_data else None
        
        # для возврата (если страница вызвана как диалог)
        self._return_to_page_id = extra_data.get('return_to_page') if extra_data else None
        self._return_field = extra_data.get('return_field') if extra_data else None

        # # Предзаполнение текста, если передан (для страницы заметок)
        # if extra_data and 'text' in extra_data:
        #     if 'text' in self.form.widgets:
        #         self.form._set_widget_value(self.form.widgets['text'], extra_data['text'])


        # current_appointment_id - это то же, что current_id
        # current_appointment_id - это ID приёма, который мы хотим отредактировать
        # self.current_appointment_id = self.current_id

        # если передан id, загружаем существующую запись
        if self.current_id is not None:
            # загружаем данные из БД
            self._load_entity(self.current_id)

            # включаем кнопку удаления
            self.delete_btn.setEnabled(True)

        else:
            # если не передан id, чистим форму
            self.form.clear()

            # если не передан id, отключаем кнопку удаления
            self.delete_btn.setEnabled(False)

            # --- ДОПОЛНЕНИЕ: подстановка patient_name при создании нового приёма ---
            # если patient_id передан, загружаем patient_name
            # patient_name - это поле в форме, которое отображает имя пациента
        
        # Заполняем из extra_data (после загрузки DTO или после очистки)
        self._init_from_extra(extra_data)

        # Применяем readOnly (для всех полей, включая существующие)
        self._apply_readonly()

        # Вычисляем виртуальные поля (например, patient_name)
        self._compute_virtual_fields(extra_data)


        #     if ( 
        #         self.current_patient_id is not None and 
        #         # hasattr(self.dto_class, 'patient_name') and 
        #         'patient_name' in self.dto_class.model_fields and 
        #         'patient_name' in self.form.widgets
        #     ):
        #         if self.patient_svc is None:
        #             self.patient_svc = get_patient_service()
        #         try:
        #             patient = self.patient_svc.get_patient_by_id(self.current_patient_id)
        #             self.form.widgets['patient_name'].setText(f"{patient.last_name} {patient.first_name}")
        #         except Exception as e:
        #             self.logger.exception("Ошибка загрузки пациента")
        #             self.form.widgets['patient_name'].setText("Пациент не найден")

        # # --- Применение readOnly на основе field_configs ---
        # for field_name, widget in self.form.widgets.items():
        #     config = self.field_configs.get(field_name, {})
        #     if not config.get('editable', True):
        #         if hasattr(widget, 'setReadOnly'):
        #             widget.setReadOnly(True)

                # # получаем поле patient_name из модели DTO
                # field_info = self.dto_class.model_fields.get('patient_name')

                # if field_info:
                #     # получаем метаданные поля
                #     metadata = field_info.metadata or {}

                #     # если поле patient_name не помечено как virtual, то 
                #     # продолжаем
                #     if not metadata.get('virtual', False):
                #         self.logger.warning("Поле patient_name не помечено как virtual")
                #         # можно продолжить, но лучше не полагаться на него

                #     # Ленивая инициализация сервиса пациентов
                #     if self.patient_svc is None:
                #         self.patient_svc = get_patient_service()

                #     try:
                #         # получаем данные пациента из БД
                #         patient = self.patient_svc.get_patient_by_id(self.current_patient_id)

                #         # подставляем patient_name в форму
                #         self.form.widgets['patient_name'].setText(f"{patient.last_name} {patient.first_name}")

                #         # Принудительное применение readOnly на основе метаданных
                #         for field_name, widget in self.form.widgets.items():
                #             field = self.dto_class.model_fields.get(field_name)
                #             # ее = field.metadata
                #             if field and not field.metadata.get('editable', True):
                #                 if hasattr(widget, 'setReadOnly'):
                #                     widget.setReadOnly(True)
                #     except Exception as e:
                #         self.logger.exception("Ошибка загрузки пациента")
                #         self.form.widgets['patient_name'].setText("Пациент не найден")

        # Загружаем данные для полей с автодополнением
        self._load_completer_data()
        # Подключаем сигналы кнопок
        self._connect_button_signals()

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicEditPage._load_entity",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
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
            self.logger.exception("Ошибка загрузки записи")
            # Возвращаемся на предыдущую страницу
            self._go_back()

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicEditPage._save",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _save(self):
        """
        Сохраняет данные из формы в БД.

        Если создается новый приём, и был передан patient_id, подставляем его.
        Если приём существует, то обновляем его.
        Если приём успешно создан или обновлен, то выводим информационное сообщение и возвращаемся к списку приёмов.
        """
        
        # Получаем данные из формы
        data = self.form.get_data()

        # # Если создаётся новый приём и был передан patient_id, подставляем его
        # if self.current_id is None and self.current_patient_id is not None:
        #     # Если в данных формы нет patient_id (скрытое поле) – добавим
        #     if 'patient_id' not in data or data['patient_id'] is None:
        #         # добавляем patient_id в данные формы
        #         data['patient_id'] = self.current_patient_id

        try:
            # Создаем DTO на основе полученных данных
            dto = self.dto_class(**data)

            # Если приём не существует, то создаем его
            if self.current_id is None:
                created = self.service.create(dto)
                # выводим информационное сообщение
                QMessageBox.information(self, "Успех", f"Запись создана с ID {created.id}")

                saved_dto = created

                # логгируем создания записи
                self.logger.info(f"Создана запись ID={created.id}")
            # Если приём существует, то обновляем его
            else:
                # обновляем id в DTO
                dto.id = self.current_id
                # обновляем приём
                updated = self.service.update(dto)
                # выводим информационное сообщение
                QMessageBox.information(self, "Успех", f"Запись ID {updated.id} обновлена")

                saved_dto = updated

                # логгируем обновления записи
                self.logger.info(f"Обновлена запись ID={updated.id}")


            if self.page_manager and self._return_to_page_id:
                # получаем страницу, на которую мы хотим перейти
                target_page = self.page_manager._pages.get(self._return_to_page_id)
                
                # если страница существует и имеет метод set_field_value
                if target_page and hasattr(target_page, 'set_field_value'):
                    # для заметок передаём текст, для других полей – нужное значение
                    # Здесь предполагаем, что возвращаемое значение – это текст сохранённой сущности
                    # (для AppointmentNote это text, для других можно адаптировать)
                    value = getattr(saved_dto, 'text', None) or str(saved_dto)
                    target_page.set_field_value(self._return_field, value)
                # возвращаемся на исходную страницу
                self.page_manager.switch_to(self._return_to_page_id) # Возвращаемся на исходную страницу
            else:
                # Обычный возврат: помечаем список на обновление
                if self.page_manager and hasattr(self, 'list_page_id'):
                    list_page = self.page_manager._pages.get(self.list_page_id)
                    if list_page and hasattr(list_page, 'set_needs_refresh'):
                        list_page.set_needs_refresh(True)
                        
                # возвращаемся к списку приёмов
                self._go_back()


        except Exception as e:
            # выводим ошибку
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить: {e}")
            # логгируем ошибку
            self.logger.exception("Ошибка сохранения")


    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicEditPage.set_field_value",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def set_field_value(self, field_name: str, value):
        """
        Устанавливает значение в указанное поле формы.

        :param field_name: имя поля формы, в которое нужно установить значение
        :type field_name: str
        :param value: значение, которое нужно установить в поле формы
        :type value: Any
        """
        if field_name in self.form.widgets:
            self.form._set_widget_value(self.form.widgets[field_name], value)

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicEditPage._delete",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
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
                self.logger.exception("Ошибка удаления")

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicEditPage._cancel",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _cancel(self):
        """
        Отмена редактирования записи.

        Метод отменяет редактирование записи и возвращает на предыдущую страницу.
        Он не делает никаких изменений в базе данных.
        """
        self._go_back()

    @AppLogger.get_instance(
        name = 'DynamicEditPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicEditPage._go_back",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
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

