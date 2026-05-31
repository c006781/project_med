# interfaces/gui/gui_window/controllers/action_manager.py
"""
Модуль централизованного управления действиями (ActionManager) для всего приложения.

Предназначен для:
    - Регистрации глобальных действий (QAction) по уникальным именам.
    - Привязки действий к кнопкам, пунктам меню, горячим клавишам.
    - Управления состоянием действий (включено/выключено, выбрано/не выбрано).
    - Упрощения обмена действиями между разными страницами и виджетами.

Основной сценарий использования:
    1. В MainWindow создаётся экземпляр ActionManager.
    2. Регистрируются глобальные действия (например, 'edit_mode', 'save_all_changes').
    3. Страницы получают ссылку на action_manager через main_window.
    4. Страницы могут привязывать свои кнопки к действиям или регистрировать свои действия
       (временные, для конкретной страницы).

Пример:
    >>> # В MainWindow
    >>> self.action_manager = ActionManager(self)
    >>> self.action_manager.register_action(
    ...     name='edit_mode',
    ...     text='Режим редактирования',
    ...     checkable=True,
    ...     callback=self.toggle_edit_mode
    ... )
    >>> self.action_manager.register_action(
    ...     name='save_all',
    ...     text='Сохранить',
    ...     shortcut=QKeySequence.Save,
    ...     callback=self.save_all
    ... )
    >>>
    >>> # В странице
    >>> self.main_window.action_manager.connect_button('edit_mode', self.edit_mode_btn)
    >>> self.main_window.action_manager.connect_button('save_all', self.save_btn)
"""

from typing import (
    Dict, List,
    Optional, Callable
)
import weakref

from app.utils.logger.logger import AppLogger

from PySide6.QtWidgets import QAction, QWidget
from PySide6.QtGui import QKeySequence, QIcon
from PySide6.QtCore import QObject, Signal



class ActionManager(QObject):
    """
    Централизованное хранилище действий (QAction) для всего приложения.

    Позволяет регистрировать действия по уникальному имени, получать их,
    привязывать к виджетам (кнопкам, пунктам меню) и управлять состоянием.

    **Поддержка множественной привязки:**
        Одно действие может быть привязано к нескольким кнопкам или пунктам меню.
        При изменении состояния действия (enabled, checked, текст, иконка) все
        связанные виджеты обновляются автоматически. При активации любого из них
        вызывается один и тот же callback.

        Для привязки нескольких кнопок достаточно вызвать `connect_button()`
        для каждой кнопки с одним и тем же именем действия.

    Сигналы:
        action_changed (str, bool): испускается при изменении состояния checkable действия.
            Передаёт имя действия и новое состояние checked.

    Атрибуты:
        _actions (Dict[str, QAction]): Словарь {имя: QAction}.
        logger (AppLogger): Логгер.

    Пример:
        >>> am = ActionManager(parent)
        >>> am.register_action('save', 'Сохранить', shortcut=QKeySequence.Save, callback=on_save)
        >>> am.connect_button('save', my_button)
        >>> am.set_action_enabled('save', False)
    """

    action_changed = Signal(str, bool)  # имя действия, checked


    # ------------------------------------------------------------------
    # Ленивая инициализация атрибутов (без __init__)
    # ------------------------------------------------------------------

    @property
    def logger(self) -> AppLogger:
        try:
            return self._logger
        except AttributeError as e:
            self._logger = AppLogger.get_instance(
                name='gui.ActionManager',
                enable_file_logging = 'user',
                use_name_in_filename = False, # 'system'
            )

        return self._logger

    @logger.setter
    def logger(self, value):
        self._logger = value


    @AppLogger.get_instance(
        name='ActionManager',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def __init__(self, parent: Optional[QObject] = None):
        """
        Инициализирует ActionManager.

        Args:
            parent (Optional[QObject]): Родительский объект (обычно MainWindow).
        """

        super().__init__(parent)

        self._actions: Dict[str, QAction] = {}
        self._action_widgets: Dict[str, List[weakref.ref]] = {}


    # ----------------------------------------------------------------------
    # Регистрация действий
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='ActionManager',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def register_action(
        self,
        name: str,
        text: str,
        checkable: bool = False,
        shortcut: Optional[QKeySequence] = None,
        icon: Optional[QIcon] = None,
        callback: Optional[Callable[[bool], None]] = None,
        parent: Optional[QObject] = None,
        temporary: bool = False
    ) -> QAction:
        """
        Создаёт и регистрирует новое действие.

        **Поддержка множественной привязки:**
            Зарегистрированное действие можно привязать к нескольким кнопкам через
            `connect_button()`. Все кнопки будут синхронизированы и будут управлять
            одним и тем же действием.

        **Поведение при перезаписи:**
            Если действие с указанным `name` уже существует, оно будет перезаписано
            (старое действие не удаляется автоматически). Это может привести к утечке
            памяти, если на старое действие были привязаны кнопки. Рекомендуется
            регистрировать действия с уникальными именами и избегать перезаписи,
            либо вручную вызывать `unregister_action` перед повторной регистрацией.

        Args:
            name (str): Уникальное имя действия (например, 'edit_mode', 'save_all').
            text (str): Текст действия (отображается в меню/кнопке).
            checkable (bool): Может ли действие быть в двух состояниях (вкл/выкл).
            shortcut (Optional[QKeySequence]): Горячая клавиша.
            icon (Optional[QIcon]): Иконка.
            callback (Optional[Callable[[bool], None]]): Функция, вызываемая при активации.
                Для checkable действий получает bool is_checked.
            parent (Optional[QObject]): Родительский QObject для действия.
                Если не указан, используется сам ActionManager.
                Для временных действий рекомендуется передавать виджет страницы.
            temporary (bool): Если True и передан parent, то при уничтожении parent
                действие автоматически удаляется из реестра.

        Returns:
            QAction: Созданное действие.

        Пример:
            >>> # Регистрация действия
            >>> am.register_action('save', 'Сохранить', callback=on_save)
            >>>
            >>> # Множественная привязка к двум кнопкам
            >>> am.connect_button('save', button1)
            >>> am.connect_button('save', button2)
        """

        if name in self._actions:
            self.logger.warning(f"Действие '{name}' уже зарегистрировано, перезаписываю")

        action_parent = parent if parent is not None else self
        action = QAction(text, action_parent)

        if checkable:
            action.setCheckable(True)

        if shortcut:
            action.setShortcut(shortcut)

        if icon:
            action.setIcon(icon)
        
        if callback:
            if checkable:
                action.toggled.connect(callback)
            else:
                action.triggered.connect(callback)

            # Сигнал action_changed всегда подключаем (даже без callback)
            action.toggled.connect(lambda checked: self.action_changed.emit(name, checked))

        self._actions[name] = action

        # Автоматическая очистка временного действия при уничтожении родителя
        if temporary and parent:
            # Используем замыкание с захватом имени, чтобы не хранить лишние ссылки
            parent.destroyed.connect(lambda: self.unregister_action(name))
            self.logger.debug(f"Зарегистрировано временное действие '{name}' (удалится при разрушении {parent})")
        else:
            self.logger.debug(f"Зарегистрировано действие '{name}'")

        return action

    @AppLogger.get_instance(
        name='ActionManager',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def register_temporary_action(
        self,
        name: str,
        text: str,
        parent: QObject,
        checkable: bool = False,
        shortcut: Optional[QKeySequence] = None,
        icon: Optional[QIcon] = None,
        callback: Optional[Callable[[bool], None]] = None
    ) -> QAction:
        """
        Удобный метод для регистрации временного действия (с temporary=True и parent).

        Args:
            name (str): Уникальное имя действия.
            text (str): Текст действия.
            parent (QObject): Родительский виджет (обычно страница).
            checkable (bool): Может ли действие быть в двух состояниях.
            shortcut (Optional[QKeySequence]): Горячая клавиша.
            icon (Optional[QIcon]): Иконка.
            callback (Optional[Callable[[bool], None]]): Функция-обработчик.

        Returns:
            QAction: Созданное действие.
        """

        return self.register_action(
            name=name,
            text=text,
            checkable=checkable,
            shortcut=shortcut,
            icon=icon,
            callback=callback,
            parent=parent,
            temporary=True
        )

    @AppLogger.get_instance(
        name='ActionManager',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def unregister_action(self, name: str) -> None:
        """
        Удаляет действие из реестра (но не удаляет сам QAction).

        Args:
            name (str): Имя действия.
        """

        # if name in self._actions:
            # del self._actions[name]
            # self.logger.debug(f"Действие '{name}' удалено из реестра")

        if name in self._actions:
            # Отвязываем действие от всех кнопок, которые на него ссылаются
            if name in self._action_widgets:
                for widget_ref in self._action_widgets[name]:
                    widget = widget_ref()
                    if widget is not None and hasattr(widget, 'defaultAction'):
                        
                        # Убираем действие у кнопки, чтобы она не ссылалась на удаляемый объект
                        widget.setDefaultAction(None)

                # Удаляем запись о связях
                self._action_widgets.pop(name, None)

        # Удаляем само действие
        if name in self._actions:
            action = self._actions.pop(name, None)
            if action:
                action.deleteLater()
                self.logger.debug(f"Действие '{name}' удалено из реестра и уничтожено")

    # ----------------------------------------------------------------------
    # Получение действий
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='ActionManager',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def get_action(self, name: str) -> Optional[QAction]:
        """
        Возвращает зарегистрированное действие по имени.

        Args:
            name (str): Имя действия.

        Returns:
            Optional[QAction]: Действие или None, если не найдено.
        """

        return self._actions.get(name)

    # ----------------------------------------------------------------------
    # Управление состоянием действий
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='ActionManager',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def set_action_enabled(self, name: str, enabled: bool) -> None:
        """
        Включает или отключает действие.

        Args:
            name (str): Имя действия.
            enabled (bool): True – включить, False – отключить.
        """

        action = self.get_action(name)
        if action:
            action.setEnabled(enabled)

    @AppLogger.get_instance(
        name='ActionManager',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def set_action_checked(self, name: str, checked: bool) -> None:
        """
        Устанавливает состояние checkable действия.

        Args:
            name (str): Имя действия.
            checked (bool): True – установить, False – снять.
        """

        action = self.get_action(name)
        if action and action.isCheckable():
            action.setChecked(checked)

    @AppLogger.get_instance(
        name='ActionManager',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def is_action_checked(self, name: str) -> bool:
        """
        Возвращает состояние checkable действия.

        Args:
            name (str): Имя действия.

        Returns:
            bool: True – действие выбрано, False – не выбрано или действие не checkable.
        """

        action = self.get_action(name)
        return action.isChecked() if action and action.isCheckable() else False

    @AppLogger.get_instance(
        name='ActionManager',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def trigger_action(self, name: str) -> None:
        """
        Программно активирует действие (испускает сигнал triggered или toggled).

        Args:
            name (str): Имя действия.
        """

        action = self.get_action(name)
        if action:
            action.trigger()

    # ----------------------------------------------------------------------
    # Привязка к UI
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='ActionManager',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def connect_button(self, name: str, button: QWidget) -> None:
        """
        Связывает кнопку (или другой виджет, имеющий setDefaultAction) с действием.

        **Множественная привязка:**
            Можно вызывать этот метод несколько раз с одним и тем же именем действия
            и разными кнопками. Все кнопки будут синхронизированы и будут управлять
            одним и тем же действием.

        Args:
            name (str): Имя действия.
            button (QWidget): Кнопка (QPushButton, QToolButton и т.д.), которая
                поддерживает метод setDefaultAction.

        Примечание:
            После связывания кнопка автоматически отображает текст, иконку,
            горячую клавишу и состояние действия. Также кнопка переключает
            состояние checkable действия при нажатии.

        Пример:
            >>> am.connect_button('save', save_button)
            >>> am.connect_button('save', toolbar_save_button)
            >>> # обе кнопки теперь управляют действием 'save'
        """
        
        action = self.get_action(name)
        if action and hasattr(button, 'setDefaultAction'):
            button.setDefaultAction(action)
            # Сохраняем слабую ссылку на кнопку для последующей отвязки
            if name not in self._action_widgets:
                self._action_widgets[name] = []
            self._action_widgets[name].append(weakref.ref(button))
        else:
            self.logger.warning(f"Не удалось привязать действие '{name}' к кнопке {button}")

    # @AppLogger.get_instance(
    #     name='ActionManager',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # def connect_menu_item(self, name: str, menu_item) -> None: # Если в будущем понадобится привязывать действия к пунктам меню, следует создавать пункты с нужным действием сразу, а не менять их постфактум.
    #     """
    #     Связывает пункт меню (QAction) с действием (меняет действие пункта).

    #     Args:
    #         name (str): Имя действия.
    #         menu_item (QAction): Пункт меню, который должен быть связан с действием.
    #             Фактически заменяет действие пункта меню на зарегистрированное.
    #     """
    #     action = self.get_action(name)
    #     if action and hasattr(menu_item, 'setAction'):
    #         menu_item.setAction(action)
    #     else:
    #         self.logger.warning(f"Не удалось привязать действие '{name}' к пункту меню")