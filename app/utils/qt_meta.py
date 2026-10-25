# app/utils/qt_meta.py

"""
Метакласс для абстрактных классов-наследников ``QObject`` (``ABC`` + ``QObject``).

Нейтральное место (2026-10-16): раньше определялся в
``interfaces/gui/gui_window/controllers/list_controller.py``, и слой приложения
(``app/draft/editable_component.py``) импортировал его из слоя интерфейса. Теперь оба
импортируют ОДИН объект отсюда — классы с обоими базовыми не получают конфликт метаклассов.

Без него ``class X(QObject, ABC)`` падает ``TypeError: metaclass conflict`` (у ``QObject``
свой метакласс ``Shiboken.ObjectType``, у ``ABC`` — ``ABCMeta``); сигналы ``Signal``
объявляются как обычно.

**Ограничение (QM1, 2026-10-25): абстрактность НЕ проверяется.** Класс создаётся через
``Shiboken.ObjectType.__new__``, ``ABCMeta.__new__`` не вызывается — ``__abstractmethods__``
не вычисляется, и экземпляр класса с нереализованным ``@abstractmethod`` создаётся без
ошибки (вызов такого метода выполнит тело заглушки). ``@abstractmethod`` здесь — только
пометка для читателя. Включать проверку нельзя без правки окна: у ``PatientListPage``,
``PaginatedAppointmentListPage``, ``PaginatedPhotoListPage`` (и ``PaginatedListPage``)
не реализован абстрактный ``refresh_data`` (IMPLEMENTATION.md, QM1).

Пример:
    >>> from abc import ABC, abstractmethod
    >>> class IThing(QObject, ABC, metaclass=QABCMeta):
    ...     @abstractmethod
    ...     def run(self) -> None: ...
    >>> isinstance(IThing(), QObject)  # создаётся, хотя run не реализован (QM1)
    True
"""

from abc import ABCMeta

from PySide6.QtCore import QObject


class QABCMeta(type(QObject), ABCMeta):
    """
    Метакласс, объединяющий метакласс QObject и ABCMeta.

    Снимает конфликт метаклассов; абстрактные методы не проверяет (см. описание модуля, QM1).

    Пример:
        >>> class Base(QObject, metaclass=QABCMeta):
        ...     @abstractmethod
        ...     def load(self) -> None: ...
        >>> class Impl(Base):
        ...     def load(self) -> None: ...
        >>> isinstance(Impl(), QObject)
        True
    """
