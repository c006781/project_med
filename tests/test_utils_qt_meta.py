# tests/test_utils_qt_meta.py

"""
Тесты app.utils.qt_meta (2026-10-25, заход М5; до этого тестов не было).

``QABCMeta`` — метакласс для классов ``QObject`` + ``ABC``. Qt без экрана
(``QT_QPA_PLATFORM=offscreen``); ``QObject`` и сигналы приложения Qt не требуют.
"""

from abc import ABC, abstractmethod

import pytest
from PySide6.QtCore import QObject, Signal

from app.utils.qt_meta import QABCMeta


def test_without_meta_conflict() -> None:
    """Без QABCMeta QObject + ABC — конфликт метаклассов (ради этого модуль и есть)."""
    with pytest.raises(TypeError):
        class Broken(QObject, ABC):  # noqa: F841 — класс нужен только для проверки
            """Должен упасть при создании класса."""


def test_qm1_abstract_not_enforced() -> None:
    """
    QM1: абстрактность не проверяется — экземпляр с нереализованным методом создаётся.

    ``ABCMeta.__new__`` не вызывается (класс создаёт ``Shiboken.ObjectType``), поэтому
    ``__abstractmethods__`` не вычисляется. Тест закрепляет текущее поведение: включение
    проверки сломает страницы окна без ``refresh_data`` (IMPLEMENTATION.md, QM1) — если
    проверку включат, тест нужно заменить на ``pytest.raises(TypeError)``.
    """

    class IThing(QObject, ABC, metaclass=QABCMeta):
        """Интерфейс с абстрактным методом."""

        @abstractmethod
        def run(self) -> None:
            """Абстрактный метод."""

    thing = IThing()
    assert isinstance(thing, QObject)
    assert not getattr(IThing, '__abstractmethods__', frozenset())


def test_concrete_subclass_works_with_signal() -> None:
    """Реализация создаётся, остаётся QObject, сигнал работает."""

    class IThing(QObject, ABC, metaclass=QABCMeta):
        """Интерфейс с сигналом и абстрактным методом."""
        done = Signal(int)

        @abstractmethod
        def run(self) -> None:
            """Абстрактный метод."""

    class Thing(IThing):
        """Реализация."""

        def run(self) -> None:
            """Испускает сигнал."""
            self.done.emit(7)

    thing = Thing()
    got = []
    thing.done.connect(got.append)
    thing.run()
    assert isinstance(thing, QObject) and isinstance(thing, IThing)
    assert got == [7]


def test_same_metaclass_for_both_layers() -> None:
    """Классы обоих слоёв (app/draft и окно) получают один объект метакласса — без конфликта."""
    from app.draft.editable_component import QABCMeta as from_app
    from interfaces.gui.gui_window.controllers.list_controller import QABCMeta as from_gui

    assert from_app is QABCMeta and from_gui is QABCMeta
