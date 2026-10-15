# app/utils/qt_meta.py

"""
Метакласс для абстрактных классов-наследников ``QObject`` (``ABC`` + ``QObject``).

Нейтральное место (2026-10-16): раньше определялся в
``interfaces/gui/gui_window/controllers/list_controller.py``, и слой приложения
(``app/draft/editable_component.py``) импортировал его из слоя интерфейса. Теперь оба
импортируют ОДИН объект отсюда — классы с обоими базовыми не получают конфликт метаклассов.

Пример:
    >>> from abc import ABC, abstractmethod
    >>> class IThing(QObject, ABC, metaclass=QABCMeta):
    ...     @abstractmethod
    ...     def run(self) -> None: ...
"""

from abc import ABCMeta

from PySide6.QtCore import QObject


class QABCMeta(type(QObject), ABCMeta):
    """
    Метакласс, объединяющий метакласс QObject и ABCMeta.

    Пример:
        >>> class Base(QObject, metaclass=QABCMeta): ...
    """
