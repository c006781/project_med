# app/utils/dataset/links.py

"""
Связь «главная → подчинённая» (аналог ``MasterSource``/``MasterFields`` RAD Studio).

Сменилась текущая строка главного набора — подчинённый перечитывается с условием
«поле связи = ключ главной строки», а новые подчинённые строки получают это значение
сами. Главной строки нет (пусто, закрыт, новая без ключа) — подчинённый пуст, и
добавлять в него нельзя.

Поле связи можно не указывать: если у подчинённого набора ровно одно поле со ссылкой
на главную таблицу (``FieldDef.references == имя главного набора``), оно найдётся само.
Цепочки (пациенты → приёмы → фото) — две связи; смена пациента опустошает/перечитывает
приёмы, а смена текущего приёма — фото.

Только стандартная библиотека.

Пример:
    >>> link = MasterDetailLink(DataSource(patients), appointments)   # поле — из описания
    >>> link.fields
    {'patient_id': 'id'}
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Union

from .dataset import DataSet
from .events import DataEvent, EventKind
from .source import DataSource

# События главного набора, после которых нужно сверить связь
_SYNC_EVENTS = frozenset({
    EventKind.OPENED, EventKind.CLOSED, EventKind.REFRESHED, EventKind.CURRENT_CHANGED,
    EventKind.STATE_CHANGED, EventKind.ROW_CHANGED, EventKind.ROWS_REMOVED,
})


class LinkError(ValueError):
    """
    Поле связи не удалось определить.

    Пример:
        >>> raise LinkError('укажите поля связи')
        Traceback (most recent call last):
        LinkError: укажите поля связи
    """


class MasterDetailLink:
    """
    Связь главного набора (через ``DataSource``) с подчинённым.

    Attributes:
        master: Источник главного набора.
        detail: Подчинённый набор.
        fields: «поле подчинённого → поле главного».

    Пример:
        >>> MasterDetailLink(DataSource(patients), appointments, {'patient_id': 'id'}).fields
        {'patient_id': 'id'}
    """

    def __init__(self, master: Union[DataSource, DataSet], detail: DataSet,
                 fields: Optional[Mapping[str, str]] = None) -> None:
        """
        Args:
            master: Источник главного набора (или сам набор — источник создастся).
            detail: Подчинённый набор.
            fields: «поле подчинённого → поле главного»; по умолчанию — поле подчинённого,
                ссылающееся на главную таблицу (``references``), → ключ главного.

        Raises:
            LinkError: Поле связи не найдено или их несколько.

        Пример:
            >>> MasterDetailLink(patients, appointments)
            <MasterDetailLink patient_id→id>
        """
        self.master = master if isinstance(master, DataSource) else DataSource(master)
        self.detail = detail
        self.fields: Dict[str, str] = dict(fields) if fields else self._guess_fields()
        self._last: Optional[Dict[str, Any]] = {}      # {} — ещё не сверяли
        self.master.subscribe(self._on_master)
        detail.subscribe(self._on_detail)
        self.sync()

    def __repr__(self) -> str:
        """
        Кратко: поля связи.

        Returns:
            Строка.

        Пример:
            >>> link
            <MasterDetailLink patient_id→id>
        """
        pairs = ', '.join(f"{d}→{m}" for d, m in self.fields.items())
        return f"<MasterDetailLink {pairs}>"

    def _guess_fields(self) -> Dict[str, str]:
        """
        Поле связи по описанию полей подчинённого.

        Returns:
            «поле подчинённого → ключ главного».

        Raises:
            LinkError: Нет имени главного набора, нет поля-ссылки или их несколько.

        Пример:
            >>> link._guess_fields()
            {'patient_id': 'id'}
        """
        master = self.master.dataset
        if master is None or not master.name:
            raise LinkError("у главного набора нет имени (name) — укажите поля связи явно")
        candidates = self.detail.fields.referencing(master.name)
        if len(candidates) != 1:
            found = ', '.join(f.name for f in candidates) or 'нет'
            raise LinkError(f"поле связи с «{master.name}» не определить однозначно "
                            f"(найдено: {found}) — укажите поля связи явно")
        return {candidates[0].name: master.key_field}

    def _master_values(self) -> Optional[Dict[str, Any]]:
        """
        Значения связи из текущей главной строки.

        Returns:
            «поле подчинённого → значение» или ``None`` (главной строки нет / без ключа).

        Пример:
            >>> link._master_values()
            {'patient_id': 5}
        """
        master = self.master.dataset
        if master is None or not master.active or master.current_index < 0:
            return None
        values = {}
        for detail_field, master_field in self.fields.items():
            try:
                value = master.value(master_field)
            except IndexError:            # страховка: строки нет — как «нет главной строки»
                return None
            if value is None:
                return None
            values[detail_field] = value
        return values

    def sync(self) -> None:
        """
        Сверяет подчинённый набор с текущей главной строкой (изменилось — перечитывает).

        Returns:
            None

        Пример:
            >>> link.sync()
        """
        values = self._master_values()
        if values == self._last:
            return
        self._last = values
        self.detail.set_master(values)

    def _on_master(self, event: DataEvent) -> None:
        """
        Событие главного набора → сверка связи.

        Args:
            event: Событие.

        Returns:
            None

        Пример:
            >>> link._on_master(DataEvent(EventKind.CURRENT_CHANGED, patients))
        """
        if event.kind in _SYNC_EVENTS:
            before = self._last
            self.sync()
            # D4 (2026-10-18): главный перечитан, а главная строка та же — связь ничего не
            # меняла, и подчинённые оставались прежними (пользователь ждёт обновления всего
            # дерева). Теперь при перечитывании главного перечитывается и подчинённый.
            if (event.kind is EventKind.REFRESHED and self._last == before and self._last is not None
                    and self.detail.active and not self.detail.state.editing):
                self.detail.refresh()

    def _on_detail(self, event: DataEvent) -> None:
        """
        Подчинённые строки изменились (сохранили, удалили) — у текущей главной строки
        пересчитываются итоги, зависящие от подчинённого набора (число фото у приёма).

        Только когда подчинённый не в правке: во время ввода итог не меняется (строка
        ещё не сохранена), а пересчёт на каждое нажатие клавиши был бы лишним.

        Args:
            event: Событие подчинённого набора.

        Returns:
            None

        Пример:
            >>> link._on_detail(DataEvent(EventKind.ROW_CHANGED, photos, index=0))
        """
        if event.kind not in (EventKind.ROW_CHANGED, EventKind.ROWS_REMOVED):
            return
        if self.detail.state.editing:
            return
        if (event.kind is EventKind.ROW_CHANGED and event.fields
                and all(self.detail.computed_by_program(f) for f in event.fields)):
            # V5 (2026-10-18): сменилось только посчитанное программой (отметка, итог
            # подчинённого) — итоги главного считаются по хранимым полям и от этого не
            # меняются; раньше — лишний запрос к БД на каждый щелчок по галочке
            return
        master = self.master.dataset
        if master is None or not master.active or master.current_index < 0:
            return
        names = [f.name for f in master.fields.aggregates() if f.aggregate.depends_on(self.detail)]
        if names:
            master.recalc([master.current_key], names)

    def unlink(self) -> None:
        """
        Разрывает связь: подписка снимается, условия связи убираются.

        Returns:
            None

        Пример:
            >>> link.unlink()
        """
        self.master.unsubscribe(self._on_master)
        self.detail.unsubscribe(self._on_detail)
        self._last = {}
        self.detail.set_master({})
