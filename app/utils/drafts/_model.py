# app/utils/drafts/_model.py

"""
Базовые типы пакета черновиков: ключ узла, черновик, событие, исключения.

Пакет не зависит ни от Qt, ни от БД, ни от кода приложения — только стандартная
библиотека (переносимость, см. IMPLEMENTATION.md §1).

Пример:
    >>> from app.utils.drafts import Draft, NodeKey
    >>> node: NodeKey = ('appointment', 12)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Hashable, Mapping, Optional, Tuple

# Узел дерева: (тип сущности, id). id — любой хешируемый (int из БД, отрицательный
# временный id новой строки, UUID …).
NodeKey = Tuple[str, Hashable]


class _Missing:
    """
    Маркер «аргумент не передан» (отличается от ``None`` — «родителя нет»).

    Пример:
        >>> MISSING is MISSING
        True
    """

    _instance: Optional['_Missing'] = None

    def __new__(cls) -> '_Missing':
        """
        Единственный экземпляр.

        Returns:
            Маркер.

        Пример:
            >>> _Missing() is _Missing()
            True
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        """
        Строковое представление.

        Returns:
            ``'MISSING'``.

        Пример:
            >>> repr(MISSING)
            'MISSING'
        """
        return 'MISSING'

    def __bool__(self) -> bool:
        """
        Маркер ложен в логическом контексте.

        Returns:
            ``False``.

        Пример:
            >>> bool(MISSING)
            False
        """
        return False


MISSING: Any = _Missing()


@dataclass(frozen=True)
class Draft:
    """
    Черновик одного узла — неизменяемый снимок (наружу отдаются только копии).

    Состояния:
        * новая запись (``is_new``): ``data`` — все поля записи;
        * существующая запись: ``data`` — только изменённые поля, ``original`` —
          их исходные значения (если были переданы);
        * ``deleted`` — помечена на удаление (и новая, и существующая); ``data``
          сохраняется — снятие пометки возвращает изменения.

    Attributes:
        entity: Тип сущности (имя из ``TreeSchema``).
        id: Id записи (у новой — временный).
        parent_id: Id родителя (тип родителя — из схемы) или ``None``.
        is_new: Записи ещё нет в хранилище (БД).
        deleted: Помечена на удаление.
        data: Поля (см. выше).
        original: Исходные значения изменённых полей.
        order: Порядковый номер создания черновика (стабильный порядок сохранения).

    Пример:
        >>> d = Draft('photo', -1, parent_id=12, is_new=True, data={'path': 'a.jpg'})
        >>> d.key, d.has_own_changes
        (('photo', -1), True)
    """

    entity: str
    id: Hashable
    parent_id: Optional[Hashable] = None
    is_new: bool = False
    deleted: bool = False
    data: Mapping[str, Any] = field(default_factory=dict)
    original: Mapping[str, Any] = field(default_factory=dict)
    order: int = 0

    @property
    def key(self) -> NodeKey:
        """
        Ключ узла ``(entity, id)``.

        Returns:
            Ключ.

        Пример:
            >>> Draft('photo', 3).key
            ('photo', 3)
        """
        return (self.entity, self.id)

    @property
    def has_own_changes(self) -> bool:
        """
        Есть ли что сохранять по самому узлу (новый, удалён или изменены поля).

        Returns:
            ``True``, если черновик не пустой.

        Пример:
            >>> Draft('photo', 3).has_own_changes
            False
        """
        return self.is_new or self.deleted or bool(self.data)


@dataclass(frozen=True)
class DraftEvent:
    """
    Событие хранилища черновиков.

    Attributes:
        kind: Что произошло: ``'created'``, ``'modified'``, ``'deleted'``,
            ``'undeleted'``, ``'discarded'``, ``'reparented'``, ``'remapped'``,
            ``'saved'``, ``'cleared'``.
        node: Узел, которого касается событие (у ``'cleared'`` — ``None``).
        affected: Узлы, чьё состояние «есть изменения у себя/в ветке» могло
            поменяться: сам узел и все его предки (у ``'reparented'`` — и старые
            предки). Интерфейс обновляет по ним значки строк.
        old_id: Для ``'remapped'`` — прежний (временный) id.

    Пример:
        >>> DraftEvent('modified', ('photo', 3), (('photo', 3), ('appointment', 12)))
        DraftEvent(kind='modified', node=('photo', 3), affected=(('photo', 3), ('appointment', 12)), old_id=None)
    """

    kind: str
    node: Optional[NodeKey]
    affected: Tuple[NodeKey, ...] = ()
    old_id: Optional[Hashable] = None


class DraftError(Exception):
    """
    Базовое исключение пакета черновиков.

    Пример:
        >>> issubclass(PlanError, DraftError)
        True
    """


class SchemaError(DraftError):
    """
    Ошибка описания дерева (неизвестный тип, цикл, нет поля внешнего ключа).

    Пример:
        >>> raise SchemaError('неизвестный тип: x')
        Traceback (most recent call last):
        SchemaError: неизвестный тип: x
    """


class PlanError(DraftError):
    """
    План сохранения нельзя выполнить (нужны подтверждения, план устарел, политика
    удаления запретила).

    Пример:
        >>> raise PlanError('план устарел')
        Traceback (most recent call last):
        PlanError: план устарел
    """


class StalePlanError(PlanError):
    """
    Черновики изменились после построения плана (например, пока был открыт диалог
    подтверждения) — план нужно построить заново.

    Пример:
        >>> issubclass(StalePlanError, PlanError)
        True
    """
