# interfaces/gui/gui_window/drafts_qt.py

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

Диалоги сохранения: ``ask_save_target`` (всё / текущее), ``make_confirmations`` (новые
родители, удаляемые ветки), ``ask_on_close``.

Пример:
    >>> bridge = DraftsQtBridge(store)
    >>> bridge.row_status_changed.connect(table.update_row_badge)
    >>> bridge.has_changes_changed.connect(save_button.setEnabled)
"""

from typing import TYPE_CHECKING, Callable, Iterable, Optional, Tuple

from PySide6.QtCore import QObject, Signal

from app.utils.drafts import DraftEvent, DraftStore, NodeKey

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from app.utils.drafts import SavePlan, TreeSchema


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

    def detach(self) -> None:
        """
        Отписывается от хранилища (при закрытии окна).

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


# ---------------------------------------------------------------------------
# Диалоги сохранения (требования 5–8, app/draft/IMPLEMENTATION.md §2)
# ---------------------------------------------------------------------------

def describe_nodes(schema: 'TreeSchema', nodes: Iterable[NodeKey], limit: int = 15) -> str:
    """
    Список узлов для сообщения: «Приём №12», «Фото (новое)» …; длинный список
    обрезается с припиской «и ещё N».

    Args:
        schema: Схема (названия типов).
        nodes: Ключи узлов.
        limit: Сколько показать.

    Returns:
        Многострочный текст.

    Пример:
        >>> describe_nodes(schema, [('appointment', 12), ('photo', -1)])
        '• Приём №12\n• Фото (новая запись)'
    """
    lines = []
    nodes = list(nodes)
    for entity, entity_id in nodes[:limit]:
        title = schema.get(entity).title if entity in schema else entity
        is_temp = isinstance(entity_id, int) and entity_id < 0
        lines.append(f"• {title} (новая запись)" if is_temp else f"• {title} №{entity_id}")
    if len(nodes) > limit:
        lines.append(f"… и ещё {len(nodes) - limit}")
    return "\n".join(lines)


def ask_save_target(parent: Optional['QWidget'], has_current: bool = True) -> Optional[str]:
    """
    Вопрос «Сохранить всё или текущее?» (требование 5).

    Args:
        parent: Родительское окно.
        has_current: Есть ли «текущее» (выбрана строка/фрейм); нет — только «всё».

    Returns:
        ``'all'``, ``'current'`` или ``None`` (отмена).

    Пример:
        >>> ask_save_target(window)
        'current'
    """
    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle("Сохранение")
    box.setText("Что сохранить?")
    all_btn = box.addButton("Всё", QMessageBox.AcceptRole)
    current_btn = box.addButton("Текущее", QMessageBox.AcceptRole) if has_current else None
    box.addButton("Отмена", QMessageBox.RejectRole)
    box.exec()
    clicked = box.clickedButton()
    if clicked is all_btn:
        return 'all'
    if current_btn is not None and clicked is current_btn:
        return 'current'
    return None


def make_confirmations(
    parent: Optional['QWidget'], schema: 'TreeSchema',
) -> Tuple[Callable[['SavePlan'], bool], Callable[['SavePlan'], bool]]:
    """
    Пара вопросов для ``save_with_confirmation``: новые родители вне объёма
    (требование 6) и удаляемые ветки (требование 7).

    Args:
        parent: Родительское окно.
        schema: Схема (названия типов).

    Returns:
        ``(confirm_new_ancestors, confirm_deletes)``.

    Пример:
        >>> ask_new, ask_del = make_confirmations(window, drafts.schema)
        >>> drafts.save(targets, scope, ask_new, ask_del)
    """
    from PySide6.QtWidgets import QMessageBox

    def confirm_new_ancestors(plan: 'SavePlan') -> bool:
        """
        «Родители ещё не сохранены — сохранить начиная с них?»

        Args:
            plan: План (``missing_new_ancestors``).

        Returns:
            Согласие.

        Пример:
            >>> confirm_new_ancestors(plan)
            True
        """
        answer = QMessageBox.question(
            parent, "Новые родительские записи",
            "Сохраняемые записи ссылаются на записи, которых ещё нет в базе:\n\n"
            f"{describe_nodes(schema, plan.missing_new_ancestors)}\n\n"
            "Сохранить их тоже (начиная с родителей)?",
        )
        return answer == QMessageBox.Yes

    def confirm_deletes(plan: 'SavePlan') -> bool:
        """
        «Будут удалены ветки целиком — продолжить?»

        Args:
            plan: План (``deleted_branches``, ``dropped``).

        Returns:
            Согласие.

        Пример:
            >>> confirm_deletes(plan)
            False
        """
        extra = ""
        lost = [d.key for d in plan.dropped if d.key not in plan.deleted_branches]
        if lost:
            extra = ("\n\nНесохранённые изменения внутри этих веток будут потеряны:\n"
                     f"{describe_nodes(schema, lost)}")
        answer = QMessageBox.warning(
            parent, "Удаление",
            "Будут удалены записи ВМЕСТЕ со всеми вложенными (приёмы, фото …):\n\n"
            f"{describe_nodes(schema, plan.deleted_branches)}{extra}\n\nПродолжить?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        return answer == QMessageBox.Yes

    return confirm_new_ancestors, confirm_deletes


def ask_on_close(parent: Optional['QWidget']) -> str:
    """
    Вопрос при закрытии с несохранёнными изменениями (требование 8).

    Args:
        parent: Родительское окно.

    Returns:
        ``'save'``, ``'discard'`` или ``'cancel'``.

    Пример:
        >>> ask_on_close(window)
        'cancel'
    """
    from PySide6.QtWidgets import QMessageBox

    answer = QMessageBox.question(
        parent, "Несохранённые изменения",
        "Есть несохранённые изменения. Сохранить перед выходом?",
        QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save,
    )
    if answer == QMessageBox.Save:
        return 'save'
    if answer == QMessageBox.Discard:
        return 'discard'
    return 'cancel'
