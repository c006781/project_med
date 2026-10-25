# app/utils/drafts_qt/bridge.py

"""
Мост между хранилищем черновиков (``app.utils.drafts.DraftStore``, без Qt) и окнами Qt.

Хранилище сообщает о событиях обычными функциями; этот объект превращает их в сигналы
Qt, на которые подписываются таблицы (значки строк), кнопка «Сохранить» и фреймы.

Сигналы:
    * ``row_status_changed(entity, id, status)`` — для КАЖДОГО затронутого узла (узел и
      его предки): таблица перерисовывает значок строки (``'own'``/``'child'``/``'both'``/
      ``None``);
    * ``row_remapped(entity, old_id, new_id)`` — новая запись сохранена: таблица меняет
      временный id строки на настоящий;
    * ``has_changes_changed(bool)`` — появились/исчезли несохранённые изменения вообще
      (кнопка «Сохранить», вопрос при закрытии);
    * ``draft_event(object)`` — исходное ``DraftEvent`` (для особых случаев).

Диалоги сохранения — ``dialogs.py`` рядом. (До 2026-10-16 мост и диалоги лежали в
``interfaces/gui/gui_window/drafts_qt.py`` — в них нет ничего от приложения.)

Пример:
    >>> bridge = DraftsQtBridge(store)
    >>> bridge.row_status_changed.connect(table.update_row_badge)
    >>> bridge.has_changes_changed.connect(save_button.setEnabled)
"""

import functools
from typing import Optional

from PySide6.QtCore import QObject, Signal

try:
    from ..drafts import DraftEvent, DraftStore
except ImportError:  # pragma: no cover
    from drafts import DraftEvent, DraftStore
# from ..drafts import DraftEvent, DraftStore, NodeKey
# ↑ до 2026-10-25 (DR8): неиспользуемый NodeKey (замечание pyflakes); так же в запасном импорте


class DraftsQtBridge(QObject):
    """
    Сигналы Qt по событиям ``DraftStore``.

    Пример:
        >>> bridge = DraftsQtBridge(store, parent=main_window)
    """

    row_status_changed = Signal(str, object, object)   # entity, id, status | None
    row_remapped = Signal(str, object, object)         # entity, old_id, new_id
    has_changes_changed = Signal(bool)
    draft_event = Signal(object)                       # DraftEvent

    def __init__(self, store: DraftStore, parent: Optional[QObject] = None) -> None:
        """
        Подписывается на хранилище.

        Args:
            store: Хранилище черновиков.
            parent: Родительский QObject.

        Пример:
            >>> DraftsQtBridge(store)
        """
        super().__init__(parent)
        self.store = store
        self._had_changes = not store.is_empty
        store.subscribe(self._on_event)
        # DR6 (2026-10-25): мост уничтожен без detach() — отписка сама (иначе хранилище
        # держит подписку и пишет в журнал ошибку на каждое событие)
        self.destroyed.connect(
            functools.partial(
                store.unsubscribe,  # отписать от этого хранилища
                self._on_event,     # обработчик этого моста
            )
        )

    def detach(self) -> None:
        """
        Отписывается от хранилища (при закрытии окна; при уничтожении моста — само, DR6;
        повторный вызов ничего не делает).

        Returns:
            None

        Пример:
            >>> bridge.detach()
        """
        self.store.unsubscribe(self._on_event)

    def _on_event(self, event: DraftEvent) -> None:
        """
        Событие хранилища → сигналы.

        Args:
            event: Событие.

        Returns:
            None

        Пример:
            >>> bridge._on_event(DraftEvent('modified', ('photo', 3), (('photo', 3),)))
        """
        self.draft_event.emit(event)
        if event.kind == 'remapped' and event.node is not None:
            self.row_remapped.emit(event.node[0], event.old_id, event.node[1])
        for entity, entity_id in event.affected:
            self.row_status_changed.emit(entity, entity_id, self.store.status(entity, entity_id))
        has_changes = not self.store.is_empty
        if has_changes != self._had_changes:
            self._had_changes = has_changes
            self.has_changes_changed.emit(has_changes)
