# app/utils/dataset/actions.py

"""
Массовые действия над отмеченными строками («чеки»: выбор строк для массовой работы).

Механизм, а не набор: действие — объект ``Action`` (подпись, обработчик, доступность,
вопрос-подтверждение, какие параметры спросить); набор действий таблицы — ``ActionSet``.
Добавить своё действие — ``actions.add(Action(...))``: оно само появится в меню экрана
(``dataset_qt.actions_menu``).

Выполнение (``ActionSet.run``):
    * отмеченные строки — по своему полю набора (``mark``, см. ``FieldDef.local``);
    * всё действие — внутри группировки ``batch`` (для черновиков — ``store.batch``: одно
      действие = один шаг отмены);
    * курсор после действия — на прежней записи (если она осталась).

Встроенные: отметить всё / снять / обратить, удалить отмеченные, задать значение поля.

Только стандартная библиотека.

Пример:
    >>> actions = ActionSet(mark_field='mark')
    >>> actions.run('mark_all', ds); actions.run('set_field', ds, field='status', value='готово')
    >>> actions.add(Action('print', 'Печать', lambda ds, keys, params: print(keys)))
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING, Any, Callable, ContextManager, Hashable, Iterator, List, Mapping, Optional,
    Sequence, Tuple,
)

if TYPE_CHECKING:
    from .dataset import DataSet

Handler = Callable[['DataSet', List[Hashable], Mapping[str, Any]], Any]


@dataclass(frozen=True)
class Action:
    """
    Действие над отмеченными строками.

    Attributes:
        name: Имя (уникально в наборе).
        label: Подпись в меню.
        handler: ``(набор, отмеченные ключи, параметры) -> результат``.
        needs_selection: Нужны отмеченные строки (иначе — недоступно).
        params: Какие параметры экран должен спросить перед запуском (``'field_value'`` —
            поле и значение; свои — по договорённости со своим экраном).
        confirm: Вопрос перед запуском (``{count}`` — число отмеченных); ``None`` — без вопроса.
        available: Своё условие доступности ``(набор) -> bool``.
        modifies: Меняет данные (недоступно, если набор менять нельзя).
        group: Группа в меню (разделители между группами).

    Пример:
        >>> Action('delete_marked', 'Удалить отмеченные', handler, confirm='Удалить {count}?').confirm
        'Удалить {count}?'
    """

    name: str
    label: str
    handler: Handler
    needs_selection: bool = True
    params: Tuple[str, ...] = ()
    confirm: Optional[str] = None
    available: Optional[Callable[['DataSet'], bool]] = None
    modifies: bool = False
    group: str = ''


@contextlib.contextmanager
def _no_batch() -> Iterator[None]:
    """
    Группировка «ничего не делать» (по умолчанию, без черновиков).

    Returns:
        Контекст.

    Пример:
        >>> with _no_batch(): pass
    """
    yield


def _for_each(dataset: 'DataSet', keys: Sequence[Hashable], action: Callable[[], None]) -> int:
    """
    Выполняет действие для каждой записи (курсор — на неё), курсор возвращается на прежнюю
    запись, если она осталась.

    Args:
        dataset: Набор.
        keys: Ключи.
        action: Что сделать с текущей записью.

    Returns:
        Сколько записей обработано.

    Пример:
        >>> _for_each(ds, [1, 2], ds.delete)
        2
    """
    start = dataset.current_key
    done = 0
    for key in list(keys):
        if dataset.locate(key):
            action()
            done += 1
    if start is not None:
        dataset.locate(start)
    return done


def mark_all(dataset: 'DataSet', keys: List[Hashable], params: Mapping[str, Any]) -> int:
    """
    Отметить все строки под текущими условиями (не загруженные — догружаются).

    Args:
        dataset: Набор.
        keys: Не используется.
        params: ``mark_field`` — поле отметки.

    Returns:
        Сколько отмечено.

    Пример:
        >>> mark_all(ds, [], {'mark_field': 'mark'})
        20
    """
    name = params['mark_field']
    dataset.fetch_all()
    for i in range(dataset.row_count):
        dataset.set_local(name, True, index=i)
    return dataset.row_count


def unmark_all(dataset: 'DataSet', keys: List[Hashable], params: Mapping[str, Any]) -> int:
    """
    Снять все отметки (и у незагруженных сейчас строк).

    Args:
        dataset: Набор.
        keys: Отмеченные.
        params: ``mark_field``.

    Returns:
        Сколько было отмечено.

    Пример:
        >>> unmark_all(ds, [1, 2], {'mark_field': 'mark'})
        2
    """
    dataset.clear_local(params['mark_field'])
    return len(keys)


def invert_marks(dataset: 'DataSet', keys: List[Hashable], params: Mapping[str, Any]) -> int:
    """
    Обратить отметки загруженных строк (отмеченные — снять, остальные — отметить).

    Args:
        dataset: Набор.
        keys: Не используется.
        params: ``mark_field``.

    Returns:
        Сколько стало отмечено среди загруженных.

    Пример:
        >>> invert_marks(ds, [], {'mark_field': 'mark'})
        18
    """
    name = params['mark_field']
    for i in range(dataset.row_count):
        dataset.set_local(name, not dataset.value(name, i), index=i)
    return sum(1 for i in range(dataset.row_count) if dataset.value(name, i))


def delete_marked(dataset: 'DataSet', keys: List[Hashable], params: Mapping[str, Any]) -> int:
    """
    Удалить отмеченные записи.

    Args:
        dataset: Набор.
        keys: Отмеченные.
        params: Не используются.

    Returns:
        Сколько удалено.

    Пример:
        >>> delete_marked(ds, [3, 7], {})
        2
    """
    dataset.check_browse_mode()
    return _for_each(dataset, keys, dataset.delete)


def set_field(dataset: 'DataSet', keys: List[Hashable], params: Mapping[str, Any]) -> int:
    """
    Задать полю одно значение у всех отмеченных записей.

    Args:
        dataset: Набор.
        keys: Отмеченные.
        params: ``field`` — поле, ``value`` — значение.

    Returns:
        Сколько изменено.

    Raises:
        KeyError: Не задано поле.

    Пример:
        >>> set_field(ds, [3, 7], {'field': 'date_next', 'value': date(2026, 11, 1)})
        2
    """
    name, value = params['field'], params.get('value')
    dataset.check_browse_mode()

    def apply() -> None:
        """
        Значение — в текущую запись, правка сохраняется.

        Returns:
            None

        Пример:
            >>> apply()
        """
        dataset.set_value(name, value)
        dataset.post()

    return _for_each(dataset, keys, apply)


def builtin_actions() -> List[Action]:
    """
    Встроенные действия (по порядку меню).

    Returns:
        Список ``Action``.

    Пример:
        >>> [a.name for a in builtin_actions()]
        ['mark_all', 'unmark_all', 'invert_marks', 'set_field', 'delete_marked']
    """
    return [
        Action('mark_all', 'Отметить все', mark_all, needs_selection=False, group='marks'),
        Action('unmark_all', 'Снять все отметки', unmark_all, group='marks'),
        Action('invert_marks', 'Обратить отметки', invert_marks, needs_selection=False, group='marks'),
        Action('set_field', 'Задать значение поля…', set_field, params=('field_value',),
               modifies=True, group='edit'),
        Action('delete_marked', 'Удалить отмеченные', delete_marked,
               confirm='Удалить отмеченные записи ({count})?', modifies=True, group='edit'),
    ]


@dataclass
class ActionSet:
    """
    Набор действий таблицы.

    Attributes:
        mark_field: Своё поле набора, по которому строки отмечены.
        batch: Группировка всего действия (черновики — ``store.batch``: один шаг отмены).
        actions: Действия по порядку (по умолчанию — встроенные).

    Пример:
        >>> ActionSet().names()
        ['mark_all', 'unmark_all', 'invert_marks', 'set_field', 'delete_marked']
    """

    mark_field: str = 'mark'
    batch: Optional[Callable[[], ContextManager[Any]]] = None
    actions: List[Action] = field(default_factory=builtin_actions)

    def names(self) -> List[str]:
        """
        Имена действий по порядку.

        Returns:
            Список имён.

        Пример:
            >>> actions.names()[0]
            'mark_all'
        """
        return [a.name for a in self.actions]

    def get(self, name: str) -> Action:
        """
        Действие по имени.

        Args:
            name: Имя.

        Returns:
            ``Action``.

        Raises:
            KeyError: Нет такого.

        Пример:
            >>> actions.get('delete_marked').label
            'Удалить отмеченные'
        """
        for action in self.actions:
            if action.name == name:
                return action
        raise KeyError(f"нет действия {name!r}; есть: {', '.join(self.names())}")

    def add(self, action: Action, *, before: Optional[str] = None) -> None:
        """
        Добавляет (или заменяет одноимённое) действие.

        Args:
            action: Действие.
            before: Поставить перед этим действием (по умолчанию — в конец).

        Returns:
            None

        Пример:
            >>> actions.add(Action('print', 'Печать', print_rows))
        """
        self.remove(action.name)
        index = self.names().index(before) if before in self.names() else len(self.actions)
        self.actions.insert(index, action)

    def remove(self, name: str) -> None:
        """
        Убирает действие (нет — ничего).

        Args:
            name: Имя.

        Returns:
            None

        Пример:
            >>> actions.remove('delete_marked')
        """
        self.actions = [a for a in self.actions if a.name != name]

    def selection(self, dataset: 'DataSet') -> List[Hashable]:
        """
        Отмеченные ключи набора.

        Args:
            dataset: Набор.

        Returns:
            Ключи.

        Пример:
            >>> actions.selection(ds)
            [3, 7]
        """
        if self.mark_field not in dataset.fields:
            return []
        return dataset.local_keys(self.mark_field)

    def can_run(self, name: str, dataset: Optional['DataSet']) -> bool:
        """
        Доступно ли действие сейчас.

        Args:
            name: Имя.
            dataset: Набор.

        Returns:
            ``True`` — можно.

        Пример:
            >>> actions.can_run('delete_marked', ds)
            False
        """
        action = self.get(name)
        if dataset is None or not dataset.active:
            return False
        if action.modifies and not dataset.can_modify:
            return False
        if action.needs_selection and not self.selection(dataset):
            return False
        if action.available is not None and not action.available(dataset):
            return False
        return True

    def run(self, name: str, dataset: 'DataSet', **params: Any) -> Any:
        """
        Выполняет действие над отмеченными: в группировке ``batch``, курсор — на месте.

        Args:
            name: Имя.
            dataset: Набор.
            **params: Параметры действия (``field``, ``value``…).

        Returns:
            Результат обработчика.

        Raises:
            PermissionError: Действие сейчас недоступно.

        Пример:
            >>> actions.run('set_field', ds, field='phone', value='')
            2
        """
        if not self.can_run(name, dataset):
            raise PermissionError(f"действие «{self.get(name).label}» сейчас недоступно")
        action = self.get(name)
        keys = self.selection(dataset)
        context = self.batch() if self.batch is not None else _no_batch()
        with context:
            return action.handler(dataset, keys, {'mark_field': self.mark_field, **params})
