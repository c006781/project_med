# interfaces/gui/gui_window/pages/dynamic_detail_list_page.py

from interfaces.gui.gui_window.pages.dynamic_list_page import DynamicListPage

from PySide6.QtWidgets import QSplitter, QWidget, QVBoxLayout
from PySide6.QtCore import Qt


class DynamicDetailListPage(DynamicListPage):
    """
    Расширение DynamicListPage с правой панелью для отображения деталей выбранной строки.
    """

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
        
    def _on_selection_changed(self, selected, deselected):
        """
        Обработка события изменения выбора строки в таблице.
        
        Если строка выбрана, то обновляет правую панель с деталями выбранной строки.
        """
        super()._on_selection_changed(selected, deselected)
        if self.selected_dto:
            self.update_details(self.selected_dto)