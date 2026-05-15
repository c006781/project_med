# interfaces/gui/gui_window/widgets/table_column.py


from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type

from interfaces.gui.gui_window.widgets.delegate.type_delegate import ButtonDelegate


class ColumnType(Enum):
    """Тип столбца: обычный (из БД) или системный (чекбокс, кнопка и т.д.)."""
    DATA = 1       # столбец данных (связан с полем DTO)
    SYSTEM = 2     # системный столбец (не связан с БД, например, чекбокс)


class TableColumn:
    """
    Класс, описывающий столбец таблицы (как для пользовательских, так и для системных столбцов).

    Инкапсулирует все метаданные столбца и предоставляет методы для управления
    порядком, видимостью и другими свойствами. Столбцы хранятся в модели в виде списка,
    порядок в списке соответствует порядку отображения в таблице.

    Класс не зависит от Qt напрямую, только хранит данные о самом столбце как обьекте.

    Атрибуты:
        system_name (str): Уникальное системное имя столбца (используется для идентификации).
        title (str): Заголовок, отображаемый пользователю.
        column_type (ColumnType): Тип столбца (DATA или SYSTEM).
        field_name (Optional[str]): Имя поля в DTO (для DATA-столбцов). Для SYSTEM – None.
        data_type (Optional[Type]): Тип данных Python (int, str, date и т.д.) – для валидации/преобразования.
        editable (bool): Можно ли редактировать ячейки этого столбца (только для DATA).
        visible (bool): Видим ли столбец в данный момент.
        order (int): Порядковый номер (индекс в списке). При изменении order у одного столбца,
                     другие должны пересчитать свои order.
        width (Optional[int]): Предпочтительная ширина столбца (в пикселях). None – автоматически.
        delegate_class (Optional[Type]): Класс делегата Qt для редактирования/отображения
                                         (например, CompleterStringDelegate).
        delegate_args (Dict[str, Any]): Аргументы для создания делегата.
        input_mask (Optional[str]): Маска ввода (для QLineEdit).
        choices (Optional[List[str]]): Список значений для выпадающего списка (если есть).
        autocomplete (bool): Включать ли автодополнение (для строковых полей).
        choices_provider (Optional[Callable[[], List[str]]]): Функция, возвращающая список вариантов
                                                              для автодополнения.
        compute (Optional[Dict]): Настройка вычисления виртуального поля (используется в сервисе,
                                  не в модели). Может быть None.
        is_note (Optional[str]): Для виртуальных полей-заметок – имя ID-поля.
        source_attr (Optional[str]): Имя атрибута в ORM для подгрузки связанных данных.
    """

    def __init__(
        self,
        system_name: str,
        title: str,
        column_type: ColumnType = ColumnType.DATA,
        field_name: Optional[str] = None,
        data_type: Optional[Type] = None,
        editable: bool = True,
        visible: bool = True,
        order: int = 0,
        width: Optional[int] = None,
        delegate_class: Optional[Type] = None,
        delegate_args: Optional[Dict[str, Any]] = None,
        input_mask: Optional[str] = None,
        choices: Optional[List[str]] = None,
        autocomplete: bool = False,
        choices_provider: Optional[Callable[[], List[str]]] = None,
        compute: Optional[Dict] = None,
        is_note: Optional[str] = None,
        source_attr: Optional[str] = None,
    ):
        self.system_name = system_name
        self.title = title
        self.column_type = column_type
        self.field_name = field_name
        self.data_type = data_type
        self.editable = editable
        self.visible = visible
        self.order = order
        self.width = width
        self.delegate_class = delegate_class
        self.delegate_args = delegate_args or {}
        self.input_mask = input_mask
        self.choices = choices
        self.autocomplete = autocomplete
        self.choices_provider = choices_provider
        self.compute = compute
        self.is_note = is_note
        self.source_attr = source_attr

        # Валидация
        if column_type == ColumnType.DATA and not field_name:
            raise ValueError("DATA-столбец должен иметь field_name")
        
        if column_type == ColumnType.SYSTEM and field_name:
            raise ValueError("SYSTEM-столбец не должен иметь field_name")

    # ----------------------------------------------------------------------
    # Методы управления (работают со списком колонок модели)
    # ----------------------------------------------------------------------

    @staticmethod
    def reorder_columns(columns: List['TableColumn'], new_order_map: Dict[str, int]) -> None:
        """
        Переупорядочивает список колонок в соответствии с картой {system_name: new_order}.
        После вызова у каждого столбца обновляется атрибут order.

        Args:
            columns: Список столбцов (будет изменён на месте).
            new_order_map: Словарь, где ключ – system_name, значение – новый порядковый номер.
                           Номера должны быть уникальными и покрывать все столбцы.
        """
        # Сортировка по новому порядку
        columns.sort(key=lambda col: new_order_map.get(col.system_name, col.order))
        # Обновляем order у каждого столбца в соответствии с новыми индексами
        for idx, col in enumerate(columns):
            col.order = idx

    def set_visible(self, columns: List['TableColumn'], visible: bool) -> None:
        """
        Изменяет видимость этого столбца.
        (Сам метод не перестраивает модель – модель должна вызвать _update_column_mapping)
        """
        self.visible = visible

    def set_order(self, columns: List['TableColumn'], new_order: int) -> None:
        """
        Изменяет порядок этого столбца, сдвигая остальные.
        """
        if new_order == self.order:
            return
        # Удаляем текущий столбец из списка
        columns.remove(self)
        # Вставляем на новую позицию
        columns.insert(new_order, self)
        # Обновляем order у всех столбцов
        for idx, col in enumerate(columns):
            col.order = idx

    # ----------------------------------------------------------------------
    # Создание предопределённых системных столбцов
    # ----------------------------------------------------------------------

    @classmethod
    def create_checkbox_column(cls, order: int = 0) -> 'TableColumn':
        """
        Создаёт системный столбец для чекбоксов.
        """
        return cls(
            system_name='__checkbox__',
            title='',
            column_type=ColumnType.SYSTEM,
            field_name=None,
            visible=False,           # по умолчанию скрыт
            order=order,
            editable=False,
        )

    @classmethod
    def create_button_column(
        cls,
        system_name: str,
        title: str = "",
        button_text: str = "...",
        order: int = 0,
    ) -> 'TableColumn':
        """
        Создаёт системный столбец с кнопкой (для действий).
        """
        # from interfaces.gui.gui_window.widgets.delegate.type_delegate import ButtonDelegate
        return cls(
            system_name=system_name,
            title=title,
            column_type=ColumnType.SYSTEM,
            field_name=None,
            visible=True,
            order=order,
            editable=False,
            delegate_class=ButtonDelegate,
            delegate_args={'button_text': button_text},
        )

    # ----------------------------------------------------------------------
    # Преобразование из словаря (для обратной совместимости)
    # ----------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Dict[str, Any], system_name: str = None) -> 'TableColumn':
        """
        Создаёт TableColumn из словаря, который ранее использовался в DynamicTableModel.
        """
        name = system_name or data.get('name', '')
        return cls(
            system_name=name,
            title=data.get('title', name.replace('_', ' ').title()),
            column_type=ColumnType.DATA,
            field_name=name,
            data_type=data.get('type', str),
            editable=data.get('editable', True),
            visible=True,
            order=data.get('order', 0),
            delegate_class=None,   # будет установлен позднее
            delegate_args={},
        )

