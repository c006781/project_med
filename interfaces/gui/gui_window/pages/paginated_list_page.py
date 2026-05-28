# interfaces/gui/gui_window/pages/paginated_list_page.py
"""
Универсальная страница списка с ленивой подгрузкой (пагинацией) и древовидными черновиками.

**Назначение и предпосылки создания:**
    Данная страница пришла на смену `DynamicListPage`, которая загружала все данные сразу
    и использовала `QSortFilterProxyModel` для фильтрации и сортировки. При большом количестве
    записей (десятки тысяч) это приводило к тормозам, высокому потреблению памяти и неэффективной
    фильтрации (которая выполнялась по уже загруженным данным).

    `PaginatedListPage` решает эти проблемы за счёт:
         - **Ленивой подгрузки (виртуальная прокрутка)** – данные загружаются порциями (страницами)
           по мере прокрутки таблицы. Размер страницы и количество «запасных» строк настраиваются.
         - **Фильтрации на стороне сервера** – фильтры, заданные пользователем, преобразуются в SQL
           и применяются в БД, что позволяет получать корректные отфильтрованные страницы.
         - Сортировка на стороне сервера – при отсутствии fuzzy-фильтра выполняется перезагрузка страницы с новым `order_by`.
         - **При активном fuzzy-фильтре сортировка отключается** (пункты меню сортировки в заголовке неактивны) 
         - Хранение фильтров по столбцам – каждый столбец хранит свой словарь условий, что позволяет комбинировать фильтры.
         - Панель активных фильтров (`FilterBar`) отображает чипы для каждого установленного фильтра.
         - Мульти-сортировка – выбор нескольких столбцов и направлений через диалог.
         - Цвет строки привязан к ID сущности (а не к индексу), поэтому не сбрасывается при сортировке.
         - **Единого хранилища черновиков (`DraftRegistry`)** – все несохранённые изменения
           (редактирование полей, удаление, добавление, а также дочерние черновики, например, фото)
           хранятся в плоском реестре, но логически организованы в дерево с помощью префиксов ключей.
         - **Древовидных статусов (`None / 'own' / 'child' / 'both'`)** – каждая сущность (строка)
           имеет статус, который вычисляется на основе собственных изменений и статусов её потомков.
           Статус `'child'` означает, что у сущности нет собственных изменений, но есть изменённые потомки.
           Статус `'both'` – есть и собственные изменения, и изменения у потомков.
           Это позволяет правильно отображать цвет строки (жёлтый) и знать, какие данные нужно сохранить.
         - **Счётчиков потомков** – для оптимизации пересчёта статуса родителя вместо рекурсивного
           обхода всех потомков каждый раз используется счётчик активных черновиков у детей.
           Счётчики синхронизируются через callback, передаваемый дочерним компонентам
           (метод `set_draft_change_notifier`).

**Архитектура и миксины:**
    Класс построен с использованием композиции миксинов, каждый из которых отвечает за отдельную
    функциональность. Все атрибуты миксинов инициализируются лениво через `@property`, что позволяет
    избежать проблем с порядком вызова `__init__` в множественном наследовании.

    - `PaginationMixin`: загрузка страниц данных (виртуальная прокрутка), реакция на скролл и изменение
      размера окна.
    - `SelectionMixin`: управление выделением строк (обычное выделение и чекбоксы), получение выбранных ID.
    - `EditModeMixin`: переключение режима редактирования, сохранение всех изменений, глобальная отмена.
    - `FilterMixin`: интеграция фильтрации через заголовки таблицы и строку поиска.
    - `UIMixin`: построение верхней панели (кнопки, комбобоксы), таблицы, строки фильтров.
    - `ControllerMixin`: реализация интерфейса `IDynamicListController` для внешнего управления.
    - `DraftTreeMixin`: все методы работы с древовидными черновиками, статусами, счётчиками,
      распространением изменений вверх/вниз.

**Ключевые понятия:**
    *Сущность (entity)* – запись в таблице (например, пациент, приём). Идентифицируется типом
    (`self._entity_type`) и ID. Для новых (ещё не сохранённых) строк ID отрицательный.

    *Статус сущности* – хранится в реестре по ключу `__status__:{entity_type}:{entity_id}`.
    Может принимать значения:
        - `None` – нет изменений ни у себя, ни у потомков.
        - `'own'` – есть изменения непосредственно в этой сущности (отредактировано поле,
          добавлена новая строка, помечена на удаление).
        - `'child'` – нет собственных изменений, но хотя бы один потомок имеет статус не `None`.
        - `'both'` – есть и собственные изменения, и изменения у потомков.

    *Черновик* – данные, которые ещё не сохранены в БД. Черновик сущности хранится в реестре
    по ключу `{entity_type}:{entity_id}:` (обычные изменения) или `__new__:{entity_type}:{temp_id}`
    (новая строка), `__deleted__:{entity_type}:{entity_id}` (пометка на удаление).
    Дочерние черновики (например, фото) хранятся по ключу `{entity_type}:{parent_id}:photos`.

    *Счётчик потомков* – хранится в реестре по ключу `__counter__:{entity_type}:{parent_id}`.
    Обновляется при каждом изменении количества активных черновиков у прямых потомков.
    Используется для быстрого пересчёта статуса родителя.

    *Распространение изменений* – при изменении статуса любой сущности автоматически
    пересчитывается статус её родителя (вверх по дереву), и так до корня. Это обеспечивает
    актуальность цвета строк и кнопки «Сохранить». При отмене изменений (например, вызов
    `discard_entity_subtree`) статусы сбрасываются вниз по дереву, а затем родители пересчитываются.

**Методы для работы с родительскими/дочерними сущностями:**

    - _get_parent_id_for_new_row(dto): возвращает ID родителя для НОВОЙ строки (если она является дочерней).
      Переопределяется в наследниках.
    - _get_child_ids(parent_id): возвращает список ID уже сохранённых дочерних записей ТОГО ЖЕ ТИПА.
      Используется для каскадного удаления.
    - _get_children_ids(parent_id): переопределяется в наследниках для разнотипных дочерних сущностей (возвращает set).
    - _get_parent_id(child_id): переопределяется в наследниках (используется DraftTreeMixin).

**Различия между _update_parent_counter и _update_parent_child_counter:**

    - _update_parent_counter (в PaginatedListPage): используется при добавлении новой строки.
      Проверяет, не помечен ли родитель на удаление, и логирует временный ID.
    - _update_parent_child_counter (в DraftTreeMixin): используется при удалении/восстановлении строки.
      Более простой, без проверки на удаление (т.к. родитель уже существует).
    Оба метода в конечном итоге вызывают mark_child_change родителя.

**Порядок сохранения (критически важен!):**
    В `_save_all_changes_impl` шаги выполняются строго в следующем порядке:
        1. Сохранение **новых строк** (ключи `__new__`). При этом дочерние черновики,
           привязанные к временному ID, переносятся на реальный ID родителя.

        2. Применение **дочерних черновиков** (фото, заметки и т.д.) – для всех родителей,
           у которых есть активные дочерние черновики (включая только что созданных).
           Реализовано в `_save_child_changes()`, вызываемом после `_save_new_rows()`

        3. Сохранение **изменённых строк** (статус `'own'` или `'both'`).

        4. Сохранение **удалённых строк** (ключи `__deleted__`).
        
    Такой порядок гарантирует, что дочерние черновики всегда привязаны к реальному ID родителя
    и не теряются.

**Требования к наследникам:**
    - **Обязательно** переопределить `_get_parent_id_for_new_row(dto)` – возвращает ID родителя
      для новой строки (если она является дочерней). Для корневых сущностей (пациенты, приёмы)
      возвращает `None`.
    - **Обязательно** переопределить `_get_child_ids(parent_id)` – возвращает список реальных ID
      уже сохранённых дочерних записей **того же типа** (для каскадного удаления).
      Для разнотипных дочерних связей (приём → фото) этот метод должен возвращать пустой список,
      а каскадное удаление реализуется в сервисе родителя.
    - **Опционально** переопределить `_get_child_service(child_name)` – возвращает сервис,
      необходимый дочернему компоненту для сохранения (например, `PhotoService`).
    - **Опционально** добавить дочерние компоненты (виджеты, реализующие `IEditableComponent`)
      через `add_draft_child`. Такие компоненты **обязаны**:
        * Реализовывать метод `set_draft_change_notifier` и вызывать переданный callback
          при каждом изменении количества своих черновиков (создание/удаление).
        * В методе `apply` удалять свой черновик из реестра (например, через `apply_and_clear`).
        * Испускать сигнал `changed` при любом изменении состояния.
    - **Опционально** переопределить `_get_child_service(child_name)` – возвращает сервис,
      необходимый дочернему компоненту для сохранения (например, `PhotoService`).

**Синхронизация дочерних виджетов после отмены/сохранения:**
        Все дочерние компоненты (например, `PhotoUploaderWidget`), добавленные через
        `add_draft_child`, автоматически подписываются на изменения реестра черновиков.
        При удалении или применении черновика реестр испускает сигнал, и компонент
        самостоятельно перезагружает своё состояние. Благодаря этому не требуется
        вручную вызывать `_load_drafts_for_children()` после операций
        `discard_entity_subtree`, `apply_subtree` и т.п.

**Параметры инициализации (`__init__`):**
    service (BaseService): Сервис для работы с сущностью (должен реализовывать
        `get_page_filtered`, `create`, `update`, `delete`).
    dto_class (Type[BaseModel]): Класс DTO (Pydantic) для сущности.
    field_configs (Dict[str, Dict[str, Any]]): Конфигурация полей.
    page_title (str): Заголовок страницы (отображается в хлебных крошках).
    add_action_text (str): Текст кнопки добавления в обычном режиме.
    action_button_text (Optional[str]): Текст дополнительной кнопки (например, «Приёмы»).
    parent (Optional[QWidget]): Родительский виджет.
    exclude_columns (Optional[List[str]]): Список имён полей, которые не отображать в таблице.
    entity_type (str): Тип сущности (например, "patient", "appointment").
        Используется для построения ключей в реестре черновиков.
    shared_registry (Optional[DraftRegistry]): Если передан, используется общий реестр
        черновиков (для межстраничной работы). Иначе создаётся локальный экземпляр.
    show_controls (Optional[List[str]]): Список строк, определяющих, какие элементы управления
        отображать на верхней панели. Допустимые значения:
        'edit_mode_btn', 'action_combo', 'inline_action_combo', 'save_btn', 'cancel_parent_btn',
        'action_btn', 'search'. Если None или пустой список, элементы не отображаются.

**Атрибуты (важные для наследников):**
    _current_filters (Optional[Union[Dict, List]]): Текущее дерево фильтров (формируется из
        `_column_filters` и `_global_search_text`).
    _current_order_by (Optional[List[str]]): Список полей для сортировки (например, `['-date', 'last_name']`).
    _column_filters (Dict[int, Dict]): Словарь фильтров по столбцам (хранится в `FilterMixin`).
    _global_search_text (str): Текст глобального поиска (хранится в `FilterMixin`).

**Обязательные методы для переопределения в наследниках:**
    - `_get_parent_id_for_new_row(dto)` – возвращает ID родителя для новой строки (если дочерняя).
    - `_get_child_ids(parent_id)` – возвращает список ID дочерних записей того же типа (для каскадного удаления).

**Пример создания страницы списка пациентов:**
    >>> from app.dependencies import get_patient_service
    >>> from app.dto import PatientDTO
    >>> from app.dto.field_configs import PATIENT_CONFIG
    >>> 
    >>> page = PaginatedListPage(
    ...     service=get_patient_service(),
    ...     dto_class=PatientDTO,
    ...     field_configs=PATIENT_CONFIG,
    ...     page_title="Пациенты",
    ...     add_action_text="Добавить пациента",
    ...     entity_type="patient",
    ...     show_controls=['edit_mode_btn', 'action_combo', 'inline_action_combo', 'save_btn', 'search']
    ... )
    >>> 
    >>> # Программное включение режима редактирования
    >>> page.set_edit_mode(True)

**Поддержка фото-столбцов (widget_type='image_thumbnail'):**
    Страница автоматически определяет поля с `widget_type='image_thumbnail'` и назначает
    для них делегат `ImageThumbnailDelegate`. Этот делегат позволяет:
        - отображать миниатюру изображения (асинхронная загрузка, кэширование);
        - при двойном клике или нажатии кнопки «...» открывать диалог `PhotoEditDialog`
            для замены/удаления фото и редактирования описания (если задано `description_field`);
        - работать в режиме «только просмотр» (синхронизируется с `edit_mode`).

    **Временные папки черновиков:**
        Для каждой новой строки (ещё не сохранённой в БД) или для изменяемой существующей
        строки (в режиме редактирования) создаётся уникальная временная папка в системной
        директории (префикс `med_app_draft_`). В эту папку копируются выбранные пользователем
        файлы (фото). При сохранении строки (в `_save_new_row_recursive` или
        `_save_modified_rows_for_ids`) файлы переносятся из временной папки в основное
        хранилище (подпапка `app_{id}`), а пути в DTO заменяются на относительные.
        При отмене изменений (удалении строки, откате черновиков) временная папка
        удаляется вместе с содержимым.

    **Управление временными папками:**
        - `_ensure_temp_dir(entity_id)` – создаёт папку, сохраняет путь в реестре
            по ключу `__temp_dir__:{entity_type}:{entity_id}`.
        - `_get_temp_dir(entity_id)` – возвращает путь из реестра.
        - `_cleanup_temp_dir(entity_id)` – удаляет папку и ключ.
        - `_move_files_from_temp_to_storage(new_id, dto, old_id=None)` – переносит все
            файлы, находящиеся во временной папке (old_id или new_id), в основное хранилище,
            обновляет DTO.
        - Методы `discard_entity_subtree` и `clear_entity_drafts` переопределены для
            автоматической очистки временной папки при отмене изменений.

    **Массовое добавление фото (опционально):**
        Страница предоставляет методы `_has_photo_column()`, `_get_allowed_extensions_for_photo()`,
        `_add_photo_from_file(file_path, photo_field)`. Для интеграции с ActionManager
        зарегистрируйте действие с именем `'multi_photo_add'` и привяжите к нему кнопку.
        Пример регистрации смотрите в разделе «Добавление кнопок через ActionManager».   

**Добавление кнопок через ActionManager (рекомендуемый способ):**
    Для обеспечения гибкости и единообразия управления интерфейсом, страница не создаёт кнопки
    напрямую, а полагается на `ActionManager`, который должен быть доступен через
    `self.main_window.action_manager`. Кнопки верхней панели (например, «Режим редактирования»,
    «Сохранить», «Добавить несколько фото») создаются и привязываются к действиям в методе
    `_setup_actions()`, который следует переопределить в наследнике (например, в `PatientListPage`).

    **Пример добавления кнопки массового добавления фото:**

        def _setup_actions(self):
            # Получаем action_manager из главного окна
            am = self.main_window.action_manager

            # Регистрируем действие (если ещё не зарегистрировано)
            am.register_action(
                name='multi_photo_add',
                text='Добавить несколько фото',
                callback=self._on_multi_photo_clicked,
                parent=self,
                temporary=True
            )

            # Создаём кнопку и привязываем её к действию
            self.multi_photo_btn = QPushButton()
            am.connect_button('multi_photo_add', self.multi_photo_btn)

            # Добавляем кнопку в нужный layout (например, в верхнюю панель)
            self.main_layout.addWidget(self.multi_photo_btn)
            self.multi_photo_btn.setVisible(self.edit_mode)

    **Примечания:**
        - Действие `multi_photo_add` будет автоматически удалено при разрушении страницы
          (благодаря `parent=self` и `temporary=True`).
        - Кнопка наследует текст, иконку, горячую клавишу и состояние enabled/checked от действия.
        - Для переключения видимости кнопки при смене режима редактирования используйте
          `self.multi_photo_btn.setVisible(self.edit_mode)` в `_update_ui_for_edit_mode`.
        - Если действие должно быть доступно из разных страниц, регистрируйте его один раз
          в `MainWindow` с `temporary=False`.    
"""

import datetime

import os
import shutil
import tempfile
from typing import (
    Any, Dict,
    Optional, Set,
    List, Tuple, Type, Union, get_args, get_origin,
)
import uuid

from app.utils.logger import AppLogger

# from app.draft.ihierarchical_editable import IHierarchicalEditableComponent
from app.config.config_manager.manager import AppConfigManager

from app.utils.file_deletions import schedule_deletion, delete_file_safely

from app.dependencies import get_photo_service

from app.draft.draft_registry import DraftRegistry

from interfaces.gui.gui_window.controllers.list_controller import QABCMeta

from interfaces.gui.gui_window.mixins.draft_tree_mixin import DraftTreeMixin
from interfaces.gui.gui_window.mixins.pagination_mixin import PaginationMixin
from interfaces.gui.gui_window.mixins.selection_mixin import SelectionMixin
from interfaces.gui.gui_window.mixins.edit_mode_mixin import EditModeMixin
# from interfaces.gui.gui_window.mixins.data_change_mixin import DataChangeMixin
from interfaces.gui.gui_window.mixins.filter_mixin import FilterMixin
from interfaces.gui.gui_window.mixins.ui_mixin import UIMixin
from interfaces.gui.gui_window.mixins.controller_mixin import ControllerMixin

from interfaces.gui.gui_window.pages.base_page import BasePage

from interfaces.gui.gui_window.widgets.paginated_table_model import PaginatedTableModel
from interfaces.gui.gui_window.widgets.table_column import ColumnType, TableColumn

from interfaces.gui.gui_window.widgets.delegate.image_delegate import ImageThumbnailDelegate
from interfaces.gui.gui_window.widgets.delegate.photo_edit_dialog import PhotoEditDialog

from interfaces.gui.gui_window.widgets.delegate.type_delegate import (
    CompleterStringDelegate,
    DatePickerDelegate,
    StringDelegate,
    TextPopupDelegate,
    TimePickerDelegate,
    BoolDelegate,
    ComboBoxDelegate,
)


from sqlalchemy.orm import Session

from PySide6.QtCore import (
    QSize, QTimer, 
    Qt, Signal, Slot,
)

from PySide6.QtGui import QColor

from PySide6.QtWidgets import (
    QDialog,
    QHeaderView,
    # QHBoxLayout,
    # QPushButton,
    # QMessageBox,
)

class PaginatedListPage(
    BasePage,
    PaginationMixin,
    SelectionMixin,
    EditModeMixin,
    # DataChangeMixin,
    FilterMixin,
    UIMixin,
    ControllerMixin,
    DraftTreeMixin,  
    metaclass=QABCMeta
):
    """
    **Для наследников:**
        - Если у сущности есть дочерние (например, у приёма – фото), необходимо
          переопределить метод `_get_child_ids`, чтобы каскадное удаление
          работало корректно.
        - Метод `_get_child_ids` должен возвращать список ID уже сохранённых
          дочерних записей (из БД). Он используется только для существующих
          сущностей (parent_id > 0). Для новых строк каскадная отмена реализована
          в `_cancel_new_row`.
        - Пример переопределения:
            def _get_child_ids(self, parent_id: int) -> List[int]:
                return [p.id for p in self.photo_service.get_photos_for_appointment(parent_id)]

    **Требования к дочерним компонентам (виджетам, добавляемым через add_draft_child):**
        - Дочерний компонент должен реализовывать интерфейс IEditableComponent
            (методы get_draft_key, load_from_registry, save_to_registry, has_changes,
            apply, discard). Ы методе `apply` удалять свой черновик после сохранения.
        - В методе `apply` компонент **обязан** после успешного сохранения изменений
            в БД **удалить свой черновик** из реестра (например, вызвав
            `registry.apply_and_clear(self.get_draft_key(), applier)` или вручную
            `registry.discard(self.get_draft_key())`). Если этого не сделать,
            черновик останется в реестре и может быть повторно применён при следующем
            сохранении, что приведёт к дублированию данных или ошибкам.
        - Рекомендуется использовать стандартный паттерн:
            def apply(self, registry, parent_id=None, service=None):
                key = self.get_draft_key()
                def applier(data):
                    # логика сохранения с использованием parent_id и service
                    pass
                registry.apply_and_clear(key, applier)

    **Синхронизация счётчиков детей (полностью реализована):**
        Счётчики детей (`__counter__`) обновляются во всех случаях, когда изменяется количество активных черновиков:
            - добавление новой строки (`_add_inline_row`),
            - пометка строки на удаление (`_delete_selected_rows`),
            - отмена новой строки (`_cancel_new_row`),
            - удаление существующей строки (`_delete_entity_and_children`),
            - создание/удаление черновика в дочернем компоненте (через callback `set_draft_change_notifier`).

        Благодаря этому счётчики всегда точны. Статус родителя вычисляется на основе его собственных изменений
        и количества детей с не‑None статусом (`child_count > 0`). Рекурсивная проверка `has_descendant_changes`
        используется только как резервный механизм (например, при ручном редактировании реестра).

        **Механизм уведомлений от дочерних компонентов:**
            - При добавлении дочернего компонента через `add_draft_child` родительская страница передаёт ему
                callback `notifier(parent_id, delta)`.
            - Дочерний компонент (например, `PhotoUploaderWidget`) вызывает этот callback при каждом изменении
                количества своих активных черновиков: +1 при создании, -1 при удалении (отмена или применение).
            - Вызов callback увеличивает или уменьшает счётчик родителя в реестре и запускает пересчёт его статуса.

    **Работа с множественными дочерними компонентами разных типов:**
        - Страница может иметь несколько дочерних компонентов (виджетов), каждый из которых
          реализует IEditableComponent и управляет своим типом сущности.
        - Статус родителя корректно обновляется (сигнал entity_status_changed) благодаря
          рекурсивной проверке has_descendant_changes.
        - При сохранении вызываются apply всех дочерних компонентов.
        - Каскадное удаление родителя для детей разных типов должно быть реализовано
          в сервисе родителя, а не через _get_children_ids (см. AppointmentService).

    Дополнительно:
        При переопределении методов _save_new_rows, _save_modified_rows, _save_deleted_rows
        необходимо сохранять контракт возвращаемых значений (для _save_new_rows – словарь).
    """

    add_requested = Signal()
    edit_requested = Signal(object)
    delete_requested = Signal(object)
    action_requested = Signal(object)

    # ------------------------------------------------------------------
    # Ленивая инициализация атрибутов (без __init__)
    # ------------------------------------------------------------------

    @property
    def logger(self) -> AppLogger:
        try:
            return self._logger
        except AttributeError as e:
            self._logger = AppLogger.get_instance(
                name='gui.PaginatedListPage',
                enable_file_logging = 'user',
                use_name_in_filename = False, # 'system'
            )

        return self._logger

    @logger.setter
    def logger(self, value):
        self._logger = value

    @property
    def edit_mode(self) -> bool:
        try:
            return self._edit_mode
        except AttributeError as e:
            self.logger.debug('edit_mode: инициализация атрибута _edit_mode')
            self._edit_mode: bool = False
        return self._edit_mode

    @edit_mode.setter
    def edit_mode(self, value: bool):
        self.logger.debug(f'edit_mode : {self._edit_mode} -> {value}' )
        self._edit_mode: bool = value

    @property
    def _draft_component_id(self) -> Optional[str]:
        try:
            return self.__draft_component_id
        except AttributeError as e:
            self.__draft_component_id = None  # Установка ключа для текущего компонента (будет установлен позже, при выборе строки)
        return self.__draft_component_id

    @_draft_component_id.setter
    def _draft_component_id(self, value: Optional[str]):
        self.__draft_component_id = value

    @property
    def _next_temp_id(self) -> int:
        try:
            return self.__next_temp_id
        except AttributeError as e:
            self.__next_temp_id = -1
        return self.__next_temp_id

    @_next_temp_id.setter
    def _next_temp_id(self, value: int):
        self.__next_temp_id = value

    @property
    def _current_filters(self):
        try:
            return self.__current_filters
        except AttributeError as e:
            self.__current_filters = None
        return self.__current_filters

    @_current_filters.setter
    def _current_filters(self, value):
        self.__current_filters = value


    @property
    def _current_order_by(self):
        try:
            return self.__current_order_by
        except AttributeError as e:
            self.__current_order_by = None
        return self.__current_order_by

    @_current_order_by.setter
    def _current_order_by(self, value):
        self.__current_order_by = value

    @property
    def original_data(self) -> Dict[int, Any]:
        try:
            return self.AttributeError
        except AttributeError as e:
            self.__original_data = {}
        return self.__original_data

    @original_data.setter
    def original_data(self, value: Dict[int, Any]) -> None:
        self.__original_data = value

    @property
    def _context_params(self) -> Dict:
        try:
            return self.__context_params
        except AttributeError as e:
            self.__context_params = {}
        return self.__context_params

    @_context_params.setter
    def _context_params(self, value: Dict) -> None:
        self.__context_params = value
    
    @property
    def _photo_service(self):
        if not hasattr(self, '__photo_service'):
            # from app.dependencies import get_photo_service
            self.__photo_service = get_photo_service()
        return self.__photo_service


    # @property 
    # def _saving_in_progress(self) -> bool: # убрал, так как наследуется  из EditModeMixin
    #     """
    #     Флаг блокировки повторного входа в методы сохранения (например, при сохранении дочерних
    #     и основных полей одновременно). Используется в `_save_all_changes_impl` и `save_rows_with_children`.

    #     Returns:
    #         True, если сохранение уже выполняется в другом потоке/рекурсивном вызове.
    #     """

    #     if not hasattr(self, '__saving_in_progress'):
    #         self.__saving_in_progress = False # флаг блокировки

    #     return self.__saving_in_progress

    # @_saving_in_progress.setter
    # def _saving_in_progress(self, value: bool):
    #     self.__saving_in_progress = value  # флаг блокировки

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self,
        service,
        dto_class,
        field_configs,
        page_title="Список",
        add_action_text="Добавить",
        action_button_text=None,
        parent=None,
        exclude_columns=None,
        entity_type: str = "",
        shared_registry: Optional[DraftRegistry] = None, 
        show_controls: Optional[List[str]] = None, # 
    ):
        """
        Инициализирует страницу списка с пагинацией, фильтрацией и древовидными черновиками.

        Args:
            service (BaseService): Сервис для работы с сущностью. Должен реализовывать
                методы `get_page_filtered`, `create`, `update`, `delete`.
            dto_class (Type[BaseModel]): Класс DTO (Pydantic) для сущности.
            field_configs (Dict[str, Dict[str, Any]]): Конфигурация полей – описание столбцов,
                виджетов, виртуальных полей, заметок и т.д.
            page_title (str): Заголовок страницы (отображается в хлебных крошках).
                По умолчанию "Список".
            add_action_text (str): Текст кнопки добавления в обычном режиме.
                Используется только если `show_controls` содержит `'action_btn'`.
                По умолчанию "Добавить".
            action_button_text (Optional[str]): Текст дополнительной кнопки действия
                (например, «Приёмы»). Если None, кнопка не создаётся даже при наличии
                `'action_btn'` в `show_controls`. По умолчанию None.
            parent (Optional[QWidget]): Родительский виджет. По умолчанию None.
            exclude_columns (Optional[List[str]]): Список имён полей, которые не должны
                отображаться в таблице (скрываются полностью). По умолчанию None.
            entity_type (str): Тип сущности (например, "patient", "appointment").
                Используется для построения ключей в реестре черновиков.
                По умолчанию "".
            shared_registry (Optional[DraftRegistry]): Если передан, используется общий реестр
                черновиков (для межстраничной работы). Иначе создаётся собственный локальный
                экземпляр `DraftRegistry`. По умолчанию None.
            show_controls (Optional[List[str]]): Список строк, определяющих, какие элементы
                управления отображать на верхней панели. Допустимые значения:
                    - `'edit_mode_btn'`     – кнопка переключения режима редактирования,
                    - `'action_combo'`      – выпадающий список действий в обычном режиме,
                    - `'inline_action_combo'` – выпадающий список inline-действий в режиме
                                                редактирования,
                    - `'save_btn'`          – кнопка сохранения изменений,
                    - `'cancel_parent_btn'` – кнопка отмены правок строки,
                    - `'action_btn'`        – дополнительная кнопка действия
                                            (текст берётся из `action_button_text`),
                    - `'search'`            – поле глобального поиска.
                Если None или пустой список, ни один из этих элементов не отображается.
                Все остальные функции (пагинация, фильтрация, редактирование) остаются
                доступными через соответствующие методы (`set_edit_mode`, `set_global_search`
                и т.д.). По умолчанию None.

        **Последовательность инициализации:**
            1. Сохраняет переданные параметры в атрибуты.
            2. Инициализирует `DataChangeMixin` (создаёт множества modified_ids, deleted_ids, new_rows).
            3. Вызывает `_build_columns()` для построения списка `TableColumn`.
            4. Вызывает `_create_model()` для создания `PaginatedTableModel`.
            5. Вызывает `setup_ui()` (из `UIMixin`) – создаёт верхнюю панель, таблицу, фильтр-бар.
            6. Вызывает `setup_pagination()` (из `PaginationMixin`) – настраивает пагинацию.
            7. Вызывает `setup_filtering()` (из `FilterMixin`) – подключает фильтрацию через заголовки.
            8. Создаёт или принимает `DraftRegistry` и подписывается на его сигнал `draft_changed`.
            9. Подключает сигналы:
                - `draft_modified_changed` → `_on_draft_modified_changed`
                - `entity_status_changed` → `_on_entity_status_changed`
                - `selectionChanged` таблицы → `_on_selection_changed_for_draft`
            10. Загружает первую страницу данных через `reload_with_filters(None)`.

        **Примечания:**
            - Класс наследует несколько миксинов, каждый из которых добавляет свою функциональность:
                `PaginationMixin`, `SelectionMixin`, `EditModeMixin`, `FilterMixin`, `UIMixin`,
                `ControllerMixin`, `DraftTreeMixin`.
            - Атрибуты `edit_mode`, `_draft_component_id`, `_next_temp_id` инициализируются лениво
            через свойства (property), чтобы избежать проблем с порядком вызова `__init__`
            при множественном наследовании.
            - Если `shared_registry` не передан, создаётся локальный реестр, изолированный для этой страницы.
            - После инициализации таблица ещё не содержит данных – они загружаются асинхронно
            при вызове `reload_with_filters(None)`. Первая страница загружается сразу после
            вызова `__init__`, поэтому данные отображаются без дополнительного действия.

        **Пример создания страницы списка пациентов:**
            ```python
            from app.dependencies import get_patient_service
            from app.dto import PatientDTO
            from app.dto.field_configs import PATIENT_CONFIG

            patient_page = PaginatedListPage(
                service=get_patient_service(),
                dto_class=PatientDTO,
                field_configs=PATIENT_CONFIG,
                page_title="Пациенты",
                add_action_text="Добавить пациента",
                entity_type="patient",
                show_controls=['search'],
            )

            # Программное включение режима редактирования
            page.set_edit_mode(True)
        """

        # уточнения:
        #   loader_func – это пережиток старой архитектуры. В новой версии данные загружаются через сервис с пагинацией, поэтому loader_func не нужен и должен быть удалён. Вся логика загрузки данных теперь сосредоточена в PaginationMixin.

        super().__init__(parent)

        self.service = service
        self.dto_class = dto_class
        self.field_configs = field_configs
        self.page_title = page_title
        self.add_action_text = add_action_text
        self.action_button_text = action_button_text
        self.exclude_columns = exclude_columns or []

        self._show_controls = show_controls or []  # Список дополнительных элементов управления
        

        self._entity_type = entity_type


        self._saved_state = {
            'filters': None,
            'column_filters': None,
            'global_search_text': '',
            'order_by': None,
            # 'multi_sort_specs': None,# убрал поскольку _current_order_by уже хранит результат мульти-сортировки (строки order_by), отдельное сохранение multi_sort_specs избыточно и приводит к неиспользуемому ключу.
            'scroll_pos': 0,
            'selected_id': None,
        }

        # self._next_temp_id = -1

        # DataChangeMixin.__init__(self)
        # self.edit_mode = False

        # self._build_columns()
        # # self._create_table()  # создаёт FilterTableView
        # # self._create_model()  # создаёт PaginatedTableModel и устанавливает в таблицу
        # self.setup_ui()                              # UIMixin прочитает self._show_controls
        # self.setup_pagination(service, page_size=50, extra_rows=5)
        # self.setup_filtering(self.filter_bar, self.table_view)

        self._build_columns()

        # # 1. Создаём модель ПЕРЕД вызовом setup_ui
        # self._create_model()  # создаёт self.source_model (PaginatedTableModel)

        # 2. Теперь вызываем setup_ui, который создаст таблицу и настроит её
        self.setup_ui()


        # Настройка высоты строк для корректного отображения миниатюр
        # from PySide6.QtWidgets import QHeaderView
        self.table_view.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        # 3. Пагинация и фильтрация
        self.setup_pagination(service, page_size=50, extra_rows=5)
        self.setup_filtering(self.filter_bar, self.table_view)

        # 4. Реестр черновиков и остальное
        # Инициализация реестра черновиков (глобальный, если передан, иначе локальный)
        if shared_registry is not None: # Если передан shared_registry, используем его (глобальный реестр всего приложения).
            self._draft_registry = shared_registry
            self.logger.debug(f"Используется общий реестр черновиков для страницы {entity_type}")

        else:  # Иначе создаём свой локальный реестр.
            self._draft_registry = DraftRegistry(self) # Инициализация реестра черновиков (глобальный, передаётся из главного окна)
            self.logger.debug(f"Создан локальный реестр черновиков для страницы {entity_type}")
        
        self._draft_registry.draft_changed.connect(self._on_draft_registry_changed)
        # self._draft_component_id = None # Установка ключа для текущего компонента (будет установлен позже, при выборе строки)

        # Создание реестра черновиков для фото и других дочерних виджетов
        self._setup_draft_system()

        # Подключаем сигнал изменения черновиков к перекраске строки
        self.draft_modified_changed.connect(self._on_draft_modified_changed)

        self.entity_status_changed.connect(self._on_entity_status_changed)
        
        # Подключаем сигнал выделения строки (если ещё не подключён)
        selection_model = self.table_view.selectionModel()
        if selection_model:
            selection_model.selectionChanged.connect(self._on_selection_changed_for_draft)

        self.reload_with_filters(None) # Загружаем первую страницу данных (через пагинацию)

    # @AppLogger.get_instance(
    #     name='PaginatedListPage',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time( level=AppLogger._parse_log_level('DEBUG') )
    # def _setup_table(self):
    #     """
    #     Переопределяем метод UIMixin._setup_table, чтобы:
    #     - не создавать новую таблицу (она уже создана в __init__)
    #     - не создавать DynamicTableModel (используем PaginatedTableModel)
    #     - настроить заголовок и фильтрацию для существующей таблицы
    #     """
    #     # Если таблица ещё не создана (например, при наследовании без вызова super().__init__), создаём
    #     if not hasattr(self, 'table_view') or self.table_view is None:
    #         super()._setup_table()
    #         return
    #
    #     # Настройка заголовка таблицы
    #     header = self.table_view.horizontalHeader()
    #     self._setup_header_settings_table(header)
    #     self._setup_header_visible_table(header)
    #
    #     # Устанавливаем функцию получения уникальных значений для заголовка
    #     if hasattr(header, 'set_get_unique_values_func'):
    #         header.set_get_unique_values_func(self.get_unique_values_for_column)
    #
    #     # Подключаем сигналы фильтрации (они будут преобразовываться в серверные фильтры)
    #     if hasattr(header, 'filter_requested'):
    #         header.filter_requested.connect(self.on_filter_requested)
    #         header.filter_clear_requested.connect(self.on_filter_clear)

    # Добавить в класс PaginatedListPage
    def _del_file(self, 
        file_path: Union[str, List[str]], 
        session: Optional[Session] = None, 
        if_delete_parent_dir: bool = False,
        force: bool = False,
    ) -> None:
        """
        Отложенное удаление файла(ов) через schedule_deletion.

        Args:
            file_path: Путь к файлу (str) или список путей (List[str]).
            session: Сессия SQLAlchemy (если передана, удаление откладывается до коммита).
            if_delete_parent_dir: Если True, после удаления файла удалить родительскую папку,
                                если она станет пустой.
            force: Если True и удаляется папка, удалять рекурсивно (даже непустую).
        """
        
        if isinstance(file_path, str):
            schedule_deletion(
                path=file_path, 
                session=session, 
                remove_parent_if_empty=if_delete_parent_dir, 
                force=force,
                logger=self.logger
            )

        # elif isinstance(file_path, List[str]):
        elif isinstance(file_path, list):
            for path in file_path:
                self._del_file(
                    path, 
                    session=session, 
                    if_delete_parent_dir=if_delete_parent_dir,
                    force=force,
                )
        else:
            raise TypeError(f"Invalid type for file_path: {type(file_path)}")
        
    def _is_file_in_temp_dir(self, temp_dir: str, value: str) -> bool:
        """
        Проверяет, существует ли файл с именем value во временной папке.
        Учитывает, что value может быть просто именем файла или относительным путём.

        Args:
            temp_dir (str): Путь к временной папке.
            value (str): Имя файла или относительный путь.

        Returns:
            bool: True, если файл существует во временной папке.
        """
        
        if not temp_dir or not value:
            return False
        
        # Пытаемся соединить временную папку и значение как есть
        candidate = os.path.join(temp_dir, value)
        if os.path.exists(candidate):
            return True
        
        # Если не существует, пробуем извлечь базовое имя файла (последний компонент)
        # на случай, если value содержит лишние разделители (например, "./file.jpg")
        base = os.path.basename(value)
        if base != value:
            candidate2 = os.path.join(temp_dir, base)
            if os.path.exists(candidate2):
                return True
            
        return False

    def discard_entity_subtree(self, entity_id: int) -> None:
        """
        Переопределяет метод из DraftTreeMixin для дополнительной очистки временной папки.
        Удаляет временную папку сущности, затем вызывает родительский метод.

        Args:
            entity_id (int): ID сущности (может быть временным отрицательным).
        """
        self._cleanup_temp_dir(entity_id)
        super().discard_entity_subtree(entity_id)

    def _get_temp_dir(self, entity_id: int) -> Optional[str]:
        """
        Возвращает путь к временной папке для сущности, если она была создана.

        Args:
            entity_id (int): ID сущности (может быть временным отрицательным).

        Returns:
            Optional[str]: Путь к временной папке или None, если папка не создана.
        """

        key = f"__temp_dir__:{self._entity_type}:{entity_id}"
        return self._draft_registry.get(key)

    def _ensure_temp_dir(self, entity_id: int) -> str:
        """
        Создаёт временную папку для сущности, если её нет, и возвращает путь.
        Папка создаётся в системной временной директории с префиксом 'med_app_draft_'.
        Путь сохраняется в реестре по ключу `__temp_dir__:{entity_type}:{entity_id}`.

        ВАЖНО: Папка должна быть удалена вызовом _cleanup_temp_dir после завершения
        работы с черновиком (например, в discard_entity_subtree, clear_entity_drafts
        или при успешном сохранении).

        Args:
            entity_id (int): ID сущности (может быть временным отрицательным).

        Returns:
            str: Абсолютный путь к созданной временной папке.
        """

        key = f"__temp_dir__:{self._entity_type}:{entity_id}"
        temp_dir = self._draft_registry.get(key)
        if not temp_dir:
            base_temp = tempfile.gettempdir()
            folder_name = f"med_app_draft_{self._entity_type}_{entity_id}_{uuid.uuid4().hex[:8]}"
            temp_dir = os.path.join(base_temp, folder_name)
            os.makedirs(temp_dir, exist_ok=True)
            self._draft_registry.set(key, temp_dir)

        return temp_dir

    def _cleanup_temp_dir(self, entity_id: int):
        """
        Удаляет временную папку сущности и соответствующий ключ в реестре черновиков.
        Если папка не существует, ничего не делает.

        Args:
            entity_id (int): ID сущности.
        """

        key = f"__temp_dir__:{self._entity_type}:{entity_id}"
        temp_dir = self._draft_registry.get(key)

        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            
        self._draft_registry.discard(key)

    # @AppLogger.get_instance(
    #     name='PaginatedListPage',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # def _delete_old_files(self, old_files: List[str]) -> None:
    #     """
    #     Удаляет перечисленные файлы из хранилища. Ошибки игнорируются (только лог).
    #     Вызывается после успешного коммита (после service.update).
    #     """
    #     for full_path in old_files:
    #         if os.path.exists(full_path):
    #             try:
    #                 os.remove(full_path)
    #                 self.logger.debug(f"Удалён старый файл: {full_path}")
    #             except OSError as e:
    #                 self.logger.warning(f"Не удалось удалить старый файл {full_path}: {e}")
    #         else:
    #             self.logger.debug(f"Старый файл {full_path} не существует, пропуск")

    # @AppLogger.get_instance(
    #     name='PaginatedListPage',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # def _del_time_file(self, copied_files, entity_id):
    #     # После успешного update удаляем временные файлы
    #     for src in copied_files:
    #         try:
    #             if os.path.exists(src):
    #                 os.remove(src)

    #         except OSError as e:
    #             self.logger.warning(f"Не удалось удалить временный файл {src}: {e}")

    #     # Удаляем временную папку (если она пуста)
    #     temp_dir = self._get_temp_dir(entity_id)

    #     if temp_dir and os.path.exists(temp_dir):
    #         try:
    #             if not os.listdir(temp_dir):
    #                 shutil.rmtree(
    #                     temp_dir, 
    #                     # ignore_errors=True
    #                 )
    #                 self._draft_registry.discard(f"__temp_dir__:{self._entity_type}:{entity_id}")
                    
    #             else:
    #                 self.logger.debug(f"Временная папка {temp_dir} не пуста, оставляем")

    #         except Exception as e:
    #             self.logger.warning(f"Не удалось удалить временную папку {temp_dir}: {e}")

    @AppLogger.get_instance(
        name='PaginatedListPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def clear_entity_drafts(self, entity_id: int) -> None:
        """
        Переопределяет метод из DraftTreeMixin, чтобы перед очисткой черновиков
        удалить временную папку сущности (если она существует).

        Args:
            entity_id (int): ID сущности.
        """
        
        self._cleanup_temp_dir(entity_id)
        super().clear_entity_drafts(entity_id)

    @AppLogger.get_instance(
        name='PaginatedListPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _move_files_from_temp_to_storage(
        self,
        new_id: int,
        dto: Any,
        old_id: Optional[int] = None
    ) -> Tuple[Any, List[str], List[str]]:
        """
        Переносит файлы из временной папки сущности (определяемой по old_id или new_id)
        в основное хранилище в папку `app_{new_id}`. Обновляет пути в DTO на относительные.

        TODO: При замене фото (когда в DTO уже был относительный путь) необходимо
        удалить старый файл в хранилище после успешного сохранения нового.
        Это можно реализовать, возвращая дополнительно список старых путей,
        и удалять их в _save_modified_rows_for_ids после вызова service.update.

        **Алгоритм:**
            1. Определяет временную папку: по old_id, если передан, иначе по new_id.
            2. Если временная папка не существует – возвращает DTO без изменений.
            3. Для каждого поля с `widget_type='image_thumbnail'` проверяет, является ли
               текущее значение DTO именем файла, присутствующим во временной папке.
            4. Копирует файл во `storage_path/app_{new_id}/`, удаляет исходный, заменяет
               путь в DTO на относительный (относительно `storage_path`).
            5. Если хотя бы один файл не удалось скопировать – накапливает ошибки и в конце
               выбрасывает `RuntimeError`, отменяя транзакцию.

        Args:
            new_id (int): Реальный ID сущности после сохранения (целевая папка).
            dto (Any): DTO сущности, содержащий поля с путями к фото.
            old_id (Optional[int]): Временный ID сущности, по которому находим временную папку.
                                    Если не указан, используется new_id (для уже сохранённых строк).

        Returns:
            Any: Обновлённый DTO (те же поля, но с изменёнными путями).

        Raises:
            RuntimeError: Если хотя бы один файл не удалось перенести – транзакция откатывается.

        Примечание:
            Метод вызывается внутри `_save_new_row_recursive` и `_save_modified_rows_for_ids`
            перед сохранением DTO в БД. Если возникает исключение, транзакция откатывается.
        """

        # Определяем, по какому ID искать временную папку
        temp_id = old_id if old_id is not None else new_id
        temp_dir = self._get_temp_dir(temp_id)

        if not temp_dir or not os.path.exists(temp_dir):
            # Временной папки нет – нечего переносить
            return dto, [], []

        storage_path = self._get_photo_storage_path()
        parent_folder = os.path.join(storage_path, f"app_{new_id}")
        os.makedirs(parent_folder, exist_ok=True)

        # any_success = False
        error_messages = []
        copied_dest_paths = []  # ЦЕЛЕВЫЕ файлы в хранилище (для отката при ошибке)
        copied_files = []          # исходные файлы во временной папке (будут удалены после переноса)
        old_files = []   # старые файлы в хранилище (будут удалены после успешного update)

        for field_name, config in self.field_configs.items():
            if config.get('widget_type') != 'image_thumbnail':
                continue
            
            old_value = getattr(dto, field_name, None)   # сохраняем старый путь ДО изменения
            current_value = old_value                    # текущее значение из DTO

            if not current_value or not isinstance(current_value, str):
                continue

            # Проверяем, является ли значение именем файла во временной папке
            if not self._is_file_in_temp_dir(temp_dir, current_value):
                continue
            
            src = os.path.join(temp_dir, current_value)
            dst = os.path.join(parent_folder, current_value)

            try:
                # Копируем, затем удаляем исходный
                
                shutil.copy2(src, dst)
                copied_files.append(src)   # запоминаем исходный путь для последующего удаления
                copied_dest_paths.append(dst)  # запоминаем целевой путь
                # os.remove(src)
                rel_path = os.path.relpath(dst, storage_path)
                setattr(dto, field_name, rel_path)

                # Если старый путь был относительным (не временная папка) – помечаем на удаление
                if old_value is not None and not os.path.isabs(old_value):
                    old_full = os.path.join(storage_path, old_value)
                    if os.path.exists(old_full) and old_full != dst:
                        old_files.append(old_full)

                self.logger.debug(f"файл скопирован {current_value} -> {rel_path} для поля {field_name}")
                # any_success = True

            except Exception as e:
                self.logger.error(f"Ошибка переноса файла {current_value}: {e}")
                # ОТКАТ: удаляем уже скопированные целевые файлы
                for dest in copied_dest_paths:
                    self._del_file(
                        dest,
                        session=None, # намеренно. чтобы немедленно удалить
                        if_delete_parent_dir=False, force=False)
                # Очищаем список, чтобы не пытаться удалить их повторно
                error_messages.append(str(e))
                # Не обновляем DTO, файл остаётся во временной папке

        if error_messages:
            err_text = f"Не удалось перенести файлы из временной папки: {', '.join(error_messages)}"
            self.logger.error(err_text)
            raise RuntimeError(err_text)


        # Удаляем временную папку после успешного переноса
        # self._cleanup_temp_dir(temp_id)
        # if any_success:
        #     # Проверяем, не стала ли родительская папка пустой (если была создана только для этих файлов)
        #     if os.path.exists(parent_folder) and not os.listdir(parent_folder):
        #         try:
        #             os.rmdir(parent_folder)
        #             self.logger.debug(f"Удалена пустая папка {parent_folder}")
        #         except OSError as e:
        #             self.logger.warning(f"Не удалось удалить пустую папку {parent_folder}: {e}")

        return dto, copied_files, old_files

    # def _move_files_from_temp_to_storage(self, entity_id: int, dto: Any) -> Any:
    #     """
    #     Переносит файлы из временной папки сущности в основное хранилище.
    #     Возвращает обновлённый DTO (с заменёнными путями).
    #     """
    #
    #     # Переносим файлы из временной папки в основное хранилище
    #
    #     temp_dir = self._get_temp_dir(entity_id)
    #     if not temp_dir or not os.path.exists(temp_dir):
    #         return dto
    #
    #     storage_path = self._get_photo_storage_path()
    #     parent_folder = os.path.join(storage_path, f"app_{entity_id}")
    #     os.makedirs(parent_folder, exist_ok=True)
    #
    #
    #     any_success = False
    #     # any_failure = False
    #
    #     error_messages = []
    #
    #     for field_name, config in self.field_configs.items():
    #         if config.get('widget_type') != 'image_thumbnail':
    #             continue
    #
    #         current_value = getattr(dto, field_name, None)
    #         if not current_value or not isinstance(current_value, str):
    #             continue
    #
    #         # Проверяем, является ли значение именем файла во временной папке
    #         if not self._is_file_in_temp_dir(temp_dir, current_value):
    #             continue
    #
    #         src = os.path.join(temp_dir, current_value)
    #         dst = os.path.join(parent_folder, current_value)
    #
    #         # try:
    #         #     shutil.move(src, dst)
    #         #     rel_path = os.path.relpath(dst, storage_path)
    #         #     setattr(dto, field_name, rel_path)
    #         #     self.logger.debug(f"Перенесён файл {current_value} -> {rel_path} для поля {field_name}")
    #         # except Exception as e:
    #         #     self.logger.warning(f"Ошибка переноса файла {current_value}: {e}")
    #
    #         try:
    #             # Сначала копируем, затем удаляем исходный
    #             shutil.copy2(src, dst)
    #             os.remove(src)
    #             rel_path = os.path.relpath(dst, storage_path)
    #             setattr(dto, field_name, rel_path)
    #             self.logger.debug(f"Перенесён файл {current_value} -> {rel_path} для поля {field_name}")
    #             any_success = True
    #         except Exception as e:
    #             self.logger.error(f"Ошибка переноса файла {current_value}: {e}")
    #             any_failure = True
    #             error_messages.append(str(e))
    #             # Не обновляем DTO, файл остаётся во временной папке
    #
    #     # Если хотя бы один файл успешно перенесён, обновляем DTO в БД (вызывающий код сделает update)
    #     # Если были ошибки, не удаляем временную папку – оставляем для повторной попытки
    #     if any_failure:
    #         err_text = f"Не удалось перенести файлы из временной папки: {', '.join(error_messages)}"
    #         self.logger.error(err_text)
    #
    #         # # Все файлы перенесены успешно – удаляем временную папку
    #         # self._cleanup_temp_dir(entity_id)  # удаляем временную папку (она не должна оставаться)
    #
    #         raise RuntimeError(err_text)
    #
    #     # Все файлы перенесены успешно – удаляем временную папку
    #     self._cleanup_temp_dir(entity_id)
    #     # Проверяем, не стала ли родительская папка пустой (если были только что перенесённые файлы – она не пуста,
    #     # но если она была создана только для этих файлов и больше ничего нет – удалять не нужно, оставляем)
    #
    #     # После переноса всех файлов проверяем, не стала ли родительская папка пустой
    #     if os.path.exists(parent_folder) and not os.listdir(parent_folder):
    #         try:
    #             os.rmdir(parent_folder)
    #             self.logger.debug(f"Удалена пустая папка {parent_folder}")
    #         except OSError as e:
    #             self.logger.warning(f"Не удалось удалить пустую папку {parent_folder}: {e}")
    #
    #     # Если не было ни одного переноса (any_success == False and any_failure == False) – удаляем временную папку?
    #     # Такое может быть, если _is_file_in_temp_dir не сработало, но папка существует – просто чистим
    #     if not any_success and not any_failure:
    #     # Удаляем временную папку после переноса
    #         self._cleanup_temp_dir(entity_id)
    #
    #     return dto

    def _get_allowed_extensions_for_photo(
        self, 
        field_name: str = None,
        default_extensions: Optional[List[str]] = None
    ) -> List[str]:
        """
        Возвращает список разрешённых расширений для фото.
        Если передан field_name, сначала ищет в конфигурации этого поля ключ 'allowed_extensions'.
        Если не найден или field_name не указан, возвращает список по умолчанию.

        Args:
            field_name (str, optional): Имя поля (столбца) для получения специфичных расширений.
            default_extensions (Optional[List[str]], optional): Пользовательский список расширений
                по умолчанию. Если None, используются стандартные:
                ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'].

        Returns:
            List[str]: Список разрешённых расширений (например, ['.jpg', '.jpeg', '.png']).
        """

        if not default_extensions:
            default_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']
        
        if field_name:
            config = self.field_configs.get(field_name, {})
            extensions = config.get('allowed_extensions')
            if extensions:
                return extensions
        return default_extensions

    # def _setup_top_panel(self): # делаем через ActionManager ...
    #     """Переопределяем метод UIMixin для добавления кнопки массового добавления фото."""
    #     super()._setup_top_panel()
    #     if self._has_photo_column():
    #         self.multi_photo_btn = QPushButton("Добавить несколько фото")
    #         self.multi_photo_btn.clicked.connect(self._on_multi_photo_clicked)
    #         self.multi_photo_btn.setVisible(self.edit_mode)

    #         # Добавляем кнопку в горизонтальный layout верхней панели (предполагаем, что он первый)
    #         for i in range(self.main_layout.count()):
    #             item = self.main_layout.itemAt(i)
    #             if item and isinstance(item.layout(), QHBoxLayout):
    #                 item.layout().addWidget(self.multi_photo_btn)
    #                 break

    def _on_multi_photo_clicked(self):
        """Обработчик кнопки массового добавления фото."""
        if not self.edit_mode:
            return
        
        # Определяем первый столбец с фото (поле file_path)
        photo_field = None
        for col in self.columns:
            config = self.field_configs.get(col.field_name, {})
            if config.get('widget_type') == 'image_thumbnail':
                photo_field = col.field_name
                break

        if not photo_field:
            self.logger.warning("Нет столбца с фото для массового добавления")
            return

        storage_path = self._get_photo_storage_path()

        # Получаем разрешённые расширения для этого поля
        allowed_extensions = self._get_allowed_extensions_for_photo(photo_field)

        dialog = PhotoEditDialog(
            parent=self,
            allowed_extensions=allowed_extensions,
            readonly=False,
            storage_path=storage_path,
            mode='multi'
        )

        if dialog.exec() == QDialog.Accepted:
            file_paths = dialog.get_selected_files()
            for file_path in file_paths:
                self._add_photo_from_file(file_path, photo_field)

    def _add_photo_from_file(
        self, 
        file_path: str,
        photo_field: str
    ) -> None:
        """
        Создаёт новую строку с предзаполненным путём к фото.
        Используется для массового добавления фото (через диалог).

        Копирует исходный файл во временную папку новой строки,
        сохраняет в DTO только имя файла, добавляет строку в модель и помечает как новую.

        Args:
            file_path (str): Абсолютный путь к исходному файлу.
            photo_field (str): Имя поля DTO, содержащего путь к фото.
        """

        try:
            # Создаём временную папку для этой новой строки
            temp_dir = self._ensure_temp_dir(self._next_temp_id)

            # Копируем файл во временную папку
            ext = os.path.splitext(file_path)[1]
            unique_name = f"{uuid.uuid4().hex}{ext}"
            dest_path = os.path.join(temp_dir, unique_name)
            shutil.copy2(file_path, dest_path)

            # В DTO сохраняем только имя файла
            rel_path_in_temp = unique_name

        except Exception as e:
            self.logger.error(f"Не удалось скопировать файл {file_path} во временную папку: {e}")
            return

        defaults = {}
        for col in self.columns:
            if col.column_type == ColumnType.DATA:
                defaults[col.field_name] = None

        # Копируем контекстные параметры
        if hasattr(self, '_context_params'):
            for key, value in self._context_params.items():
                if key in defaults:
                    defaults[key] = value

        # defaults[photo_field] = file_path
        defaults[photo_field] = rel_path_in_temp
        dto = self.dto_class(**defaults)
        # temp_id = self._next_temp_id
        dto.id = self._next_temp_id
        self._next_temp_id -= 1

        # dto.id = temp_id

        #  # создаём временную папку для этой новой строки (черновик)
        # self._ensure_temp_dir(temp_id)

        # Сохраняем в реестр черновиков как новую строку
        self._draft_registry.set(
            f"__new__:{self._entity_type}:{dto.id}", {"dto": dto}
        )
        row = self.source_model.add_row(dto)
        self.mark_own_change(dto.id)
        self._register_new_row_parent_balance(dto, dto.id)
        self._update_row_color(row)
        self._update_save_button_state()

    def _has_photo_column(self) -> bool:
        """
        Проверяет, есть ли в текущей конфигурации столбец с типом виджета 'image_thumbnail'.

        Returns:
            bool: True, если хотя бы один такой столбец существует.
        """

        for field_name, config in self.field_configs.items():
            if config.get('widget_type') == 'image_thumbnail':
                return True
            
        return False

    def _set_edit_mode(self, enable: bool) -> None:
        """
        Устанавливает режим редактирования и синхронизирует состояние кнопки.
        """
        super()._set_edit_mode(enable)
        # Синхронизируем состояние кнопки, если она существует
        if hasattr(self, 'edit_mode_btn') and self.edit_mode_btn:
            self.edit_mode_btn.blockSignals(True)
            self.edit_mode_btn.setChecked(enable)
            self.edit_mode_btn.blockSignals(False)

    @Slot(bool)
    def _on_edit_mode_toggled(self, checked: bool):
        """
        Обработчик переключения режима редактирования (вызывается из кнопки `edit_mode_btn`).

        **Назначение:**
            Включает или выключает режим редактирования таблицы, управляет видимостью элементов
            интерфейса, обновляет состояние чекбокс-столбца и переустанавливает делегаты.

        **Алгоритм (кратко):**
            1. Проверяет, не равен ли `checked` текущему состоянию `self.edit_mode`.
            Если равен – ничего не делает.
            2. **При выключении режима (`checked=False`)**:
            - Проверяет наличие несохранённых изменений через `_has_unsaved_changes()`.
            - Если изменения есть, показывает диалог с предложением сохранить, не сохранять
                или отменить переключение.
            - В зависимости от выбора пользователя:
                * Сохранить – вызывает `save_all_changes()` (через `_save_all_changes_impl`).
                * Не сохранять – откатывает изменения через `_discard_all_changes()`.
                * Отмена – возвращается без переключения режима.
            3. **При включении режима (`checked=True`)**:
            - Если таблица пуста, автоматически добавляет новую строку (`_add_inline_row()`).
            - Устанавливает `self.edit_mode = True`.
            4. Обновляет UI:
            - Вызывает `_update_ui_for_edit_mode(checked)` (показывает/скрывает кнопки,
                комбобоксы, изменяет режим редактирования таблицы).
            - Включает/отключает чекбокс-столбец в модели (`set_checkbox_column_visible`).
            - Переустанавливает делегаты (`_reapply_delegates`).
            - Обновляет `readonly` у `TextPopupDelegate`.
            - Сбрасывает выделение (`clearSelection`).
            - Обновляет состояние кнопки сохранения.
            5. Выходит из метода.

        **Параметры:**
            checked (bool): Новое состояние кнопки (True – режим редактирования включён,
                            False – выключен).

        **Возвращает:**
            None

        **Примечания:**
            - Метод использует `preserve_selection` декоратор (не показан в сигнатуре, но подразумевается
            в коде), который сохраняет и восстанавливает текущую выделенную строку.
            - Переопределение этого метода в `PaginatedListPage` расширяет поведение из `UIMixin`.

        **Пример:**
            >>> # Пользователь нажимает кнопку «Режим редактирования»
            >>> # checked = True -> включается режим, появляется чекбокс-столбец, включается редактирование ячеек
            >>> # При повторном нажатии checked = False -> если есть изменения, предложит сохранить
        """

        self.set_edit_mode(checked)

        # Дополнительно управляем видимостью чекбокс‑столбца (если не делается в toggle_edit_mode)
        if hasattr(self, 'source_model'):
            self.source_model.set_checkbox_column_visible(checked)
    
    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time( level=AppLogger._parse_log_level('DEBUG') )
    def _update_ui_for_edit_mode(self, edit_mode: bool):
        """
        Обновляет элементы пользовательского интерфейса при переключении режима редактирования.

        **Действия:**
            - Скрывает/показывает выпадающие списки действий (action_combo, inline_action_combo).
            - Показывает/скрывает кнопку сохранения (save_changes_btn).
            - Показывает/скрывает кнопку отмены правок строки (cancel_parent_btn).
            - Включает/отключает дополнительную кнопку действия (action_btn).
            - Устанавливает режим редактирования таблицы (DoubleClicked / NoEditTriggers).
            - Обновляет видимость чекбокс-столбца в модели.
            - Переустанавливает делегаты (через _reapply_delegates).
            - Обновляет read-only режим для TextPopupDelegate и ImageThumbnailDelegate.

        Args:
            edit_mode (bool): True – режим редактирования включён, False – выключен.

        Примечания:
            - Этот метод вызывается из `EditModeMixin._set_edit_mode()`.
            - В наследниках (например, в AppointmentListPage) может быть переопределён
            для дополнительной кастомизации, но обязательно должен вызывать super().
        """

        # Вызываем родительский метод (UIMixin), чтобы обновить базовые элементы
        super()._update_ui_for_edit_mode(edit_mode)
        
        # --- Работа с чекбокс-столбцом ---
        if hasattr(self, 'source_model'):
            self.source_model.set_checkbox_column_visible(edit_mode)

        # --- Переустановка делегатов (чтобы обновить read-only для фото и текстов) ---
        self._reapply_delegates()  
        
        # --- Обновление read-only для TextPopupDыelegate (если есть) ---
        for col in range(self.table_view.model().columnCount()):
            delegate = self.table_view.itemDelegateForColumn(col)
            if isinstance(delegate, TextPopupDelegate):
                delegate.set_readonly(not edit_mode)

        # --- Обновление read-only для ImageThumbnailDelegate (фото) ---
        # (делегат фото создаётся в _setup_delegates, но его нужно настроить после переустановки)
        if hasattr(self, 'table_view') and self.table_view:
            for col in range(self.table_view.model().columnCount()):
                delegate = self.table_view.itemDelegateForColumn(col)
                if delegate and hasattr(delegate, 'set_readonly'):
                    # Для ImageThumbnailDelegate и других делегатов с методом set_readonly
                    delegate.set_readonly(not edit_mode)

        # Управление видимостью кнопки массового добавления
        if hasattr(self, 'multi_photo_btn'):
            self.multi_photo_btn.setVisible(edit_mode)

        # --- Дополнительная синхронизация кнопки "Сохранить" ---
        self._update_save_button_state()

        self.logger.debug(f"Режим редактирования: {'включён' if edit_mode else 'выключен'}, UI обновлён")


    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_edit_mode(self, enable: bool) -> None:
        """
        Включает или выключает режим редактирования.

        Args:
            enable: True – включить режим редактирования, False – выключить.
        """
        if hasattr(self, 'toggle_edit_mode'):
            self.toggle_edit_mode(enable)

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_global_search(self, text: str) -> None:
        """
        Устанавливает глобальный текстовый фильтр (вызывается из внешнего виджета поиска).

        Args:
            text: Строка поиска (подстрока, регистронезависимая).
        """
        super().set_global_search(text)

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_multi_sorting(
        self, 
        specs: List[Tuple[int, Qt.SortOrder]]
    ) -> None: 
        """
        Устанавливает многоколоночную сортировку для таблицы.

        **Назначение:**
            Позволяет пользователю отсортировать данные по нескольким столбцам с указанием
            направления сортировки для каждого. Метод вызывается из диалога мульти-сортировки
            (`FilterHeaderView._show_multi_sort_dialog`).

        **Алгоритм:**
            1. Проверяет, есть ли активный fuzzy-фильтр (через `_has_fuzzy_filter`).
            Если есть – сортировка отключается (метод ничего не делает или может показать
            предупреждение). Это связано с тем, что fuzzy-фильтр применяется в памяти
            после загрузки данных, и серверная сортировка при нём не поддерживается.
            2. Если fuzzy-фильтра нет, преобразует спецификации в формат `order_by` для сервиса.
            Каждый элемент `specs` – кортеж `(видимый_индекс_столбца, порядок)`.
            Например, `specs = [(1, Qt.AscendingOrder), (2, Qt.DescendingOrder)]`.
            Преобразование: получает имя поля для каждого видимого индекса через
            `_get_column_name_by_visible_index`, затем формирует строку:
            `"last_name"` для возрастания, `"-date"` для убывания.
            3. Сохраняет полученный список в `self._current_order_by`.
            4. Вызывает `reload_with_order_by(order_by)`, который перезагружает страницу
            с новой сортировкой (сбрасывает пагинацию).

        **Параметры:**
            specs (List[Tuple[int, Qt.SortOrder]]): Список кортежей, где первый элемент –
                видимый индекс столбца (0-based), второй – порядок сортировки
                (`Qt.AscendingOrder` или `Qt.DescendingOrder`).

        **Возвращает:**
            None

        **Исключения:**
            Ничего не выбрасывает (при ошибках логирует и игнорирует).

        **Пример:**
            >>> specs = [(1, Qt.AscendingOrder), (2, Qt.DescendingOrder)]
            >>> # Столбец 1 (например, "last_name") – по возрастанию, столбец 2 (например, "date") – по убыванию
            >>> self.set_multi_sorting(specs)

        **Примечания:**
            - Этот метод переопределяет (или вызывает) метод `set_multi_sorting` из `FilterMixin`.
            - Сортировка выполняется на стороне сервера (через метод `get_page_filtered` сервиса).
            - Если fuzzy-фильтр активен, сортировка игнорируется (пункты меню сортировки
            в заголовке таблицы отключаются, см. `FilterHeaderView`).
        """

        super().set_multi_sorting(specs)  # вызывает метод миксина FilterMixin

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def save_children_only(
        self, 
        parent_id: int, 
        session: Optional[Session] = None
    ) -> bool:
        """
        Сохраняет только дочерние черновики для указанной родительской сущности,
        не затрагивая её основные поля.

        **Алгоритм:**
            1. Проверяет флаг _saving_in_progress (защита от реентерабельности).
            2. Вызывает `_save_child_components_for_parent(parent_id)`.
            3. Пересчитывает статус родителя.
            4. Обновляет цвет строки и состояние кнопки сохранения.

        **Синхронизация UI дочерних компонентов:**
            Дочерние компоненты (например, PhotoUploaderWidget) автоматически подписываются
            на изменения реестра черновиков (через `subscribe_to_registry`). При удалении
            черновика в методе `apply` компонент получает сигнал `draft_changed` и самостоятельно
            вызывает `load_from_registry`, обновляя своё состояние. Поэтому после вызова
            `save_children_only` **не требуется** вручную обновлять дочерние виджеты.
    

        **Пример использования:**
            # В приёме есть изменённые фото, но сам приём не редактировался
            success = page.save_children_only(appointment_id)
            if success:
                print("Фото сохранены, приём не затронут")

        Args:
            parent_id: ID родительской сущности (должен быть > 0).
            session: Опциональная сессия SQLAlchemy для работы в одной транзакции.

        Returns:
            True, если сохранение прошло успешно, False при ошибке.
        """

        self.logger.debug(
            f"self._saving_in_progress  = {self._saving_in_progress} "
        )
        if self._saving_in_progress:
            self.logger.warning("save_children_only уже выполняется, повторный вызов игнорирован")
            return False

        self._saving_in_progress = True
        try:
            # Сохраняем дочерние черновики для родителя
            self._save_child_components_for_parent(parent_id, session=session)

            # После успешного применения дочерних черновиков обновляем статус родителя
            # (родитель мог быть в статусе 'child' или 'both' – пересчитываем)
            self._recompute_parent_status(parent_id)

            # Обновляем цвет строки и состояние кнопки сохранения
            row = self._find_row_by_id(parent_id)
            if row >= 0:
                self._update_row_color(row)

            self._update_save_button_state()

            return True
        
        except Exception as e:
            self.logger.exception(f"Ошибка при сохранении дочерних черновиков для родителя {parent_id}: {e}")
        
        finally:
            self._saving_in_progress = False

        return False

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _clear_page_drafts_prefixes(self) -> None:
        """
        Удаляет все черновики, связанные с текущим типом сущности (страницей) (self._entity_type).         
        """

        # Существующие префиксы...
        temp_dir_prefix = f"__temp_dir__:{self._entity_type}:"

        # Сначала собираем ключи временных папок, чтобы потом удалить папки
        temp_keys = list(self._draft_registry.get_keys_by_prefix(temp_dir_prefix))
        temp_items = []
        for key in temp_keys:
            temp_dir = self._draft_registry.get(key)
            if temp_dir:
                temp_items.append((key, temp_dir))

        # Теперь удаляем все ключи (включая служебные)
        for prefix in [
            f"{self._entity_type}:",
            f"__status__:{self._entity_type}:",
            f"__counter__:{self._entity_type}:",
            f"__deleted__:{self._entity_type}:",
            f"__new__:{self._entity_type}:",
            f"__parent_counter_inc__:{self._entity_type}:",   # Очистка служебных ключей балансировки счётчиков
            temp_dir_prefix,

        ]:
            # Удалить все черновики с этим префиксом (включая дочерние, но они уже удалены рекурсивно)
            self._draft_registry.discard_by_prefix(prefix)  

        # Удаляем физические папки
        for key, temp_dir in temp_items:
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    self.logger.warning(f"Не удалось удалить временную папку {temp_dir}: {e}")

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def discard_page_drafts(self) -> None:
        """
        Удаляет все черновики, связанные с текущим типом сущности (страницей) (self._entity_type).

        **Очищаемые префиксы:**
            - `{entity_type}:` – обычные черновики
            - `__status__:{entity_type}:` – статусы сущностей
            - `__counter__:{entity_type}:` – счётчики детей
            - `__deleted__:{entity_type}:` – пометки на удаление
            - `__new__:{entity_type}:` – новые строки

        Используется при закрытии страницы или при полной очистке изменений для данного типа
        в глобальном реестре (не затрагивая другие типы).

        Примечание: Если используется локальный реестр, вызов эквивалентен `self._draft_registry.clear()`.
        """

        self._clear_page_drafts_prefixes()       

        self._status_cache.clear()
        self.source_model.clear_row_colors()
        self._update_save_button_state()

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def discard_children_only(self, parent_id: int) -> None:
        """
        Отменяет (удаляет) все дочерние черновики для указанной родительской сущности,
        не затрагивая основные поля родителя.

        **Что удаляется:**
            - Все черновики с префиксом `{self._entity_type}:{parent_id}:`
            (исключая системные ключи __status__, __counter__, __deleted__, __new__).

        **После удаления:**
            - Пересчитывается статус родителя (через `_recompute_parent_status`).
            - Обновляется цвет строки и состояние кнопки сохранения.

        **Пример:**
            page.discard_children_only(123)  # удалить только фото для приёма 123

        Args:
            parent_id: ID родительской сущности (может быть временным, но обычно >0).
        """

        # Удаляем все черновики с префиксом "entity_type:parent_id:"
        # (исключая системные ключи __status__, __counter__, __deleted__, __new__)
        prefix = f"{self._entity_type}:{parent_id}:"
        for key in list(self._draft_registry.get_keys_by_prefix(prefix)):
            if not key.startswith(('__status__', '__counter__', '__deleted__', '__new__')):
                self._draft_registry.discard(key)

        # Пересчитываем статус родителя (могут остаться собственные изменения)
        self._recompute_parent_status(parent_id)
        self._update_row_color_by_id(parent_id)
        self._update_save_button_state()

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_parent_id_for_new_row(self, dto: Any) -> Optional[int]:
        """
        Возвращает ID родительской сущности для новой строки.
        Должен быть переопределён в наследниках, если новая строка является дочерней.
        По умолчанию возвращает None (корневая сущность).
        """

        return None

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_child_ids(self, parent_id: int) -> List[int]:
        """
        Возвращает список ID дочерних сущностей для указанного родителя.
        **Должен быть переопределён в наследниках**, если у сущности есть дочерние,
        которые должны удаляться каскадно при удалении родителя.

        Пример переопределения в AppointmentListPage:
            def _get_child_ids(self, parent_id: int) -> List[int]:
                return [p.id for p in self.photo_service.get_photos_for_appointment(parent_id)]

        Args:
            parent_id: ID родительской записи (реальный, из БД, >0).

        Returns:
            Список ID дочерних записей (могут быть пустым). ID должны соответствовать уже сохранённым в БД записям.
        """

        # Базовая реализация возвращает пустой список (нет дочерних).
        # Наследники должны переопределить этот метод, если у них есть дочерние сущности.
        return []

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _delete_children(self, parent_id: int) -> None:
        """
        Рекурсивно помечает на удаление всех потомков указанной сущности.
        Используется внутри `_save_deleted_rows`, чтобы при удалении родителя
        автоматически удалить всех его детей (и внуков).

        **Важно:** Этот метод работает только с уже сохранёнными в БД сущностями
        (parent_id >= 0). Для новых (временных) строк каскадное удаление
        реализовано в `_cancel_new_row`.

        Алгоритм:
            1. Получает список дочерних ID через переопределённый `_get_child_ids`.
            2. Для каждого дочернего ID:
                - Если он ещё не помечен на удаление, создаёт ключ "__deleted__".
                - Увеличивает счётчик родителя (чтобы родитель узнал об удалении потомка).
                - Рекурсивно вызывает `_delete_children` для потомка (удаление внуков).
            3. **Защита от зацикливания:** не обрабатывает уже помеченных детей.

        Args:
            parent_id: ID родительской записи (должен быть >0, т.е. существовать в БД).
        """
        for child_id in self._get_child_ids(parent_id):
            # Если дочерняя уже помечена на удаление – пропускаем
            if not self._draft_registry.has(f"__deleted__:{self._entity_type}:{child_id}"):
                self._draft_registry.set(f"__deleted__:{self._entity_type}:{child_id}", {})
                # Увеличиваем счётчик родителя (для дочерней сущности, не для родителя)
                # Здесь parent_of_child = parent_id, но увеличение счётчика уже сделано?
                # Лучше просто пометить, без дополнительных уведомлений, так как родитель всё равно удаляется.
                # Но для синхронизации счётчиков можно вызвать _update_parent_child_counter(child_id, 1)
                self._update_parent_child_counter(child_id, 1)

            # Рекурсивно удаляем детей детей
            self._delete_children(child_id)

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_row_modified_from_model(self, row: int):
        """
        Обработчик сигнала `row_modified` от модели таблицы (`PaginatedTableModel`).

        **Когда возникает:**
            - При прямом редактировании ячейки в таблице (пользователь изменил значение в поле
            и подтвердил изменение, например, нажатием Enter).

        **Алгоритм:**
            1. Получает DTO для указанной строки через `self.source_model.get_item_at_row(row)`.
            2. Если DTO существует и его ID не `None` и не отрицательный (существующая запись):
            - Проверяет, не помечена ли строка на удаление (наличие ключа `__deleted__`).
                Если помечена – игнорирует изменение (логирует и выходит).
            - Если не помечена, вызывает `self.mark_own_change(dto.id)`, который:
                * Устанавливает статус `'own'` для сущности в реестре.
                * Обновляет кэш и испускает сигнал `entity_status_changed`, что приводит к перекраске строки.
            3. Если DTO не существует или ID временный (отрицательный) – ничего не делает
            (строки с временным ID обрабатываются отдельно при создании).

        **Параметры:**
            row (int): Индекс строки в исходной модели (`source_model`).

        **Возвращает:**
            None

        **Примечания:**
            - Сигнал `row_modified` испускается моделью после успешной установки нового значения
            через `setData`. Не путать с сигналом изменения выделения или другими событиями.
            - Для новых строк (ID < 0) редактирование ячейки также должно помечать строку
            как изменённую, но в текущей реализации новые строки уже имеют статус `'own'`
            с момента создания (в `_add_inline_row`). Поэтому дополнительная пометка не требуется.

        **Пример:**
            >>> # Пользователь дважды кликает по ячейке телефона, вводит новое значение и нажимает Enter
            >>> # Модель вызывает setData, затем испускает row_modified(0)
            >>> # Этот обработчик вызывает mark_own_change(id) -> строка становится жёлтой
        """

        self.logger.debug(f"_on_row_modified_from_model: row={row}")

        dto = self.source_model.get_item_at_row(row)
        if dto and dto.id is not None and dto.id >= 0:
            # Проверяем, не помечена ли строка на удаление
            if self._draft_registry.has(f"__deleted__:{self._entity_type}:{dto.id}"):
                self.logger.debug(f"Редактирование удалённой строки {dto.id} игнорировано")
                return

            self.logger.debug(f"Вызов mark_own_change для id={dto.id}")
            self.mark_own_change(dto.id)
        else:
            self.logger.debug(f"dto={dto}, id={dto.id if dto else None} – пропуск")

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_model_layout_changed(self):
        """
        Перекрашивает все загруженные строки после изменения layout модели.
        Это необходимо для восстановления цветов после локальной сортировки
        (когда PaginatedTableModel.sort сбрасывает цвета).
        """

        for row in range(self.source_model.rowCount()):
            self._update_row_color(row)

    # def _load_data(self): # Удалить метод полностью – он больше не нужен # Если в наследниках он переопределялся, их нужно переписать, используя пагинацию
  
    # ------------------------------------------------------------------
    # Переопределение абстрактных методов DraftTreeMixin
    # ------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_parent_id(self, child_id: int) -> Optional[int]:
        """
        Для текущей страницы (например, список приёмов) у приёма нет родителя.
        Для списка фото нужно было бы вернуть appointment_id, но здесь мы работаем
        с основным списком (например, пациенты или приёмы). Поэтому возвращаем None.
        Если страница будет использоваться как дочерняя, метод переопределяется.
        """
        return None

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_children_ids(self, parent_id: int) -> Set[int]:
        """
        Возвращает множество ID дочерних сущностей, имеющих ТОТ ЖЕ ТИП (self._entity_type).
        Используется для каскадного удаления записей одного типа (например, дерево папок).
        Для разнотипных дочерних связей (например, приём → фото) этот метод НЕ ДОЛЖЕН
        возвращать ID, так как удаление таких детей должно выполняться в сервисе родителя.
        Базовый метод возвращает пустое множество.
        """

        return set()

    # ------------------------------------------------------------------
    # Обработка сигналов реестра
    # ------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_entity_status_changed(
        self, 
        entity_id: int, 
        has_changes: bool
    ):
        """
        Обработчик сигнала `entity_status_changed` из `DraftTreeMixin`.

        **Сигнал возникает:**
            - При изменении статуса любой сущности (с `None` на `'own'`, `'child'`, `'both'` или наоборот).
            - Сигнал испускается внутри `_update_own_change` и `_recompute_parent_status`.

        **Действия:**
            1. Вызывает `_update_row_color_by_id(entity_id)` для перекраски строки,
            соответствующей данной сущности.
            2. Вызывает `_update_save_button_state()` для обновления активности кнопки «Сохранить».

        **Параметры:**
            entity_id (int): ID сущности, статус которой изменился.
            has_changes (bool): True – статус не `None` (есть изменения), False – статус `None`. (ПО ФАКТУ НЕ ИСПОЛЬЗУЕТСЯ)

        **Возвращает:**
            None

        **Примечания:**
            - Статус может быть `'own'`, `'child'`, `'both'` или `None`.
            - Цвет строки определяется в `_get_row_color` на основе статуса (жёлтый для `'own'`/`'child'`/`'both'`, красный для удалённой, зелёный для новой, белый для неизменённой).
            - Этот обработчик гарантирует, что UI всегда отражает актуальное состояние
            черновиков для всех строк, даже для тех, которые не были выбраны.

        **Пример:**
            >>> # После редактирования ячейки строки с ID=1 статус меняется на 'own'
            >>> # Сигнал вызывает _on_entity_status_changed(1, True) -> строка перекрашивается в жёлтый
        """
            
        self._update_row_color_by_id( # Перекрашиваем строку, соответствующую этой сущности
            entity_id = entity_id ,          
        )  

        self._update_save_button_state() # Обновляем состояние кнопки сохранения

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_draft_registry_changed(self, key: str, has_draft: bool):
        """
        Обработчик сигнала `draft_changed` из `DraftRegistry`.

        **Сигнал возникает:**
            - При любом добавлении или удалении черновика в реестре (включая служебные ключи:
            `__status__`, `__counter__`, `__new__`, `__deleted__`).

        **Логика:**
            1. Разбирает ключ на части (разделитель `:`).
            2. Если ключ относится к статусу (`__status__:{entity_type}:{entity_id}`):
            - Извлекает `entity_type` и `entity_id`.
            - Если `entity_type` совпадает с текущим типом сущности страницы,
                обновляет кэш статуса (`_set_cached_status`) и испускает сигнал
                `entity_status_changed(entity_id, status is not None)`, что приводит к перекраске строки.
            3. Если ключ относится к счётчику (`__counter__:{entity_type}:{parent_id}`) –
            игнорируется, так как изменения счётчика уже обработаны в `_update_child_change`.
            4. Для остальных ключей (черновики, новые строки, удалённые) – ничего не делает,
            так как они не требуют немедленного обновления UI.

        **Параметры:**
            key (str): Ключ черновика, который изменился.
            has_draft (bool): True – черновик добавлен, False – удалён.

        **Возвращает:**
            None

        **Примечания:**
            - Основная цель этого обработчика – синхронизировать кэш статусов в миксине
            с реестром и уведомить UI о необходимости перекраски строки.
            - Статусы сущностей (`__status__`) обновляются в реестре через вызовы
            `set_entity_status` (например, в `_update_own_change`), и здесь мы просто отражаем
            эти изменения в локальном кэше.

        **Пример:**
            >>> # После вызова mark_own_change(1) в реестре появится ключ __status__:patient:1
            >>> # Сигнал draft_changed вызовет этот обработчик, который обновит кэш и цвет строки
        """

        parts = key.split(':')
        if len(parts) < 2:
            return
        
        # Определяем entity_id из ключа
        if parts[0] == '__status__':
            # Ключ статуса: __status__:entity_type:entity_id
            entity_type = parts[1]
            if entity_type != self._entity_type:
                return
            
            entity_id = int(parts[2])

            status = self._draft_registry.get_entity_status(entity_type, entity_id)
            self._set_cached_status(entity_id, status)
            self.entity_status_changed.emit(entity_id, status is not None) # Перекрашиваем строку, соответствующую этой сущности
            # Перекрашиваем строку, соответствующую этой сущности # убрал так как есть вызов в entity_status_changed

        elif parts[0] == '__counter__':
            # Изменение счётчика – не требует UI, только пересчёт статуса родителя
            # (уже сделан через _update_child_change)
            pass

        else:
            # Другие ключи – игнорируем (черновики, удалённые, новые)
            pass

    # ------------------------------------------------------------------
    # Обработка изменения черновиков
    # ------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_draft_modified_changed(self, has_draft: bool):
        """
        Обработчик сигнала `draft_modified_changed` из `DraftTreeMixin`.

        **Сигнал возникает:**
            - Когда изменяется флаг `_draft_modified` (наличие изменений в поддереве черновиков,
            начиная с текущего компонента). Например, когда дочерний виджет (фото) добавляет
            или удаляет черновик, или когда меняется статус сущности.

        **Действия:**
            1. Если нет выбранной строки (`self.selected_dto`), ничего не делает.
            2. Вызывает `_update_row_color_by_id(entity_id)` для перекраски строки,
            соответствующей текущей выбранной сущности. Цвет строки зависит от нового статуса.
            3. Вызывает `_update_save_button_state()` для обновления активности кнопки «Сохранить».

        **Параметры:**
            has_draft (bool): True – появились черновики (изменения есть), False – все черновики удалены.

        **Возвращает:**
            None

        **Примечания:**
            - Статус сущности уже обновлён в реестре (через `entity_status_changed`),
            поэтому здесь не требуется дополнительно пересчитывать статус.
            - Этот обработчик обеспечивает синхронизацию UI (цвет строки и кнопка «Сохранить»)
            с изменениями в дочерних компонентах.

        **Пример сценария:**
            >>> # Пользователь добавил фото к выбранному приёму
            >>> # PhotoUploaderWidget испускает photosChanged -> вызывается _save_current_draft
            >>> # Далее DraftTreeMixin обновляет _draft_modified и испускает сигнал
            >>> self._on_draft_modified_changed(True)  # перекрасит строку в жёлтый
        """

        if not self.selected_dto:
            return

        self._update_row_color_by_id(  # Просто перекрашиваем строку; статус уже обновлён через реестр
            entity_id = self.selected_dto.id           
        )  

        self._update_save_button_state() # Обновляем состояние кнопки сохранения
        

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _has_any_changes(self, entity_id: int) -> bool:
        """
        Проверяет, есть ли у сущности какие-либо несохранённые изменения
        (собственные или дочерние).

        **Актуальная реализация (для PaginatedListPage):**
            Использует статус сущности, хранящийся в реестре черновиков.
            Статус вычисляется автоматически при любом изменении (правка ячейки,
            добавление/удаление строки, изменение дочерних компонентов) и
            может принимать значения: None (нет изменений), 'own' (есть собственные),
            'child' (есть изменения у потомков), 'both' (есть и те, и другие).

        **Почему это лучше старой версии:**
            Старая реализация (из DynamicListPage) сравнивала DTO с оригиналом
            и дополнительно проверяла словари черновиков (_draft_photos и т.п.),
            что было неэффективно и не масштабировалось на глубокую вложенность.
            Новая версия опирается на централизованный реестр и древовидные
            статусы, которые обновляются через механизм счётчиков.

        **Параметры:**
            entity_id (int): ID сущности (должен быть >0 для существующих записей,
                            для новых строк всегда возвращает True, так как они
                            ещё не сохранены).

        **Возвращает:**
            bool: True, если есть любые изменения (статус 'own', 'child' или 'both'),
                иначе False.

        **Пример:**
            >>> if self._has_any_changes(123):
            ...     print("Строка или её потомки имеют несохранённые изменения")
            ... else:
            ...     print("Нет изменений")

        **Примечание:**
            Для новых строк (с временным ID < 0) этот метод не следует вызывать,
            так как они всегда считаются изменёнными (они ещё не в БД).
            Используйте `self._draft_registry.has(f"__new__:{self._entity_type}:{temp_id}")`
            для явной проверки.
        """

        status = self._draft_registry.get_entity_status(self._entity_type, entity_id)

        return status in ('own', 'child', 'both')
    
        # """
        # Проверяет, есть ли изменения в строке (основные поля или черновики потомков).
        # """
        # # Проверка основных полей
        # row = self._find_row_by_id(entity_id)
        # if row < 0:
        #     return False
        
        # dto = self.source_model.get_item_at_row(row)
        # original = self.original_data.get(row)
        # if original and dto.model_dump() != original.model_dump():
        #     return True
        
        # # Проверка черновиков потомков через свойство миксина
        # return self.has_descendant_drafts

    # ------------------------------------------------------------------
    # Переопределение методов сохранения (работа с реестром)
    # ------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _update_id_own_in_real_id(
        self,
        temp_id,
        id,
    ):
        """
        Переносит статус `'own'` (наличие собственных изменений) с временного ID на реальный ID.

        **Назначение:**
            Когда создаётся новая строка (временный ID), она сразу помечается как имеющая
            собственные изменения (статус `'own'`). После сохранения строки в БД она получает
            реальный ID. Чтобы сохранить информацию о том, что строка была изменена пользователем,
            необходимо перенести статус `'own'` с временного ID на реальный. Этот метод
            выполняет перенос статуса и очищает запись о временном ID.

        **Алгоритм:**
            1. Получает старый статус для временного ID из кэша (`_get_cached_status(temp_id)`).
            2. Если статус существовал:
            - Сохраняет его для реального ID в кэше и реестре (через `set_entity_status`).
            - Удаляет статус для временного ID из реестра и кэша.
            3. **Не изменяет счётчик родителя** – это делается отдельно в `_save_new_row_recursive`
            через вызов `_balance_parent_counter`.

        **Параметры:**
            temp_id (int): Временный (отрицательный) ID новой строки.
            real_id (int): Реальный (положительный) ID, присвоенный строке после сохранения.

        **Возвращает:**
            None

        **Пример:**
            >>> self._update_id_own_in_real_id(-1, 123)
            # Если у строки с ID=-1 был статус 'own', теперь он будет у ID=123, а запись для -1 удалена.

        **Важно:**
            - Метод **не вызывает** `mark_child_change` для родителя, потому что увеличение
            счётчика родителя уже произошло при создании строки (`_add_inline_row`), а уменьшение
            будет выполнено после сохранения через `_balance_parent_counter`.
            - Цвет строки пересчитывается автоматически через сигнал `entity_status_changed`,
            который испускается при изменении статуса.
        """
        
        # Переносим статус 'own' (если был) с временного ID на реальный
        old_status = self._get_cached_status(temp_id)
        if old_status:
            self._set_cached_status(id, old_status)

            self._draft_registry.set_entity_status(self._entity_type, id, old_status)

            # Удаляем старый статус временного ID из реестра
            self._draft_registry.delete_entity_status(self._entity_type, temp_id)
            self._status_cache.pop(temp_id, None)

            # ВАЖНО: НЕ вызываем mark_child_change для родителя сейчас, потому что родительский счётчик будет обновлён при сохранении самих дочерних черновиков (они вызовут mark_child_change сами).
        
        # Цвет строки не переносится, потому что он вычисляется динамически
        # на основе статуса сущности. При изменении статуса (через entity_status_changed)
        # будет вызвана перекраска с новым цветом.

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _transferring_child_drafts(
        self,
        temp_id,
        id,
    ):
        """
        Переносит все дочерние черновики с префикса, содержащего временный ID, на префикс с реальным ID.

        **Назначение:**
            При создании новой строки (например, нового пациента или приёма) ей присваивается
            временный отрицательный ID. Пользователь может добавить дочерние черновики
            (например, фото к приёму) **до** сохранения родительской строки. В этом случае
            дочерние черновики хранятся в реестре под ключами, содержащими временный ID родителя
            (например, `"appointment:-1:photos"`). После сохранения родитель получает реальный
            положительный ID из БД. Данный метод переносит все дочерние черновики с префикса
            `{entity_type}:{temp_id}:` на новый префикс `{entity_type}:{real_id}:`,
            чтобы они были привязаны к реальному ID родителя.

        **Алгоритм:**
            1. Формирует старый префикс: `f"{self._entity_type}:{temp_id}:"`.
            2. Формирует новый префикс: `f"{self._entity_type}:{real_id}:"`.
            3. Проходит по всем ключам реестра, начинающимся со старого префикса.
            4. Для каждого такого ключа извлекает данные, создаёт новый ключ заменой префикса
            и сохраняет данные под новым ключом.
            5. Удаляет старый ключ.

        **Параметры:**
            temp_id (int): Временный (отрицательный) ID родительской строки.
            real_id (int): Реальный (положительный) ID, присвоенный строке после сохранения в БД.

        **Возвращает:**
            None

        **Пример:**
            >>> # После сохранения новой строки с temp_id=-1 и реальным ID=123
            >>> self._transferring_child_drafts(-1, 123)
            # Все черновики с префиксом "appointment:-1:" будут перенесены на "appointment:123:"

        **Важно:**
            - Метод должен вызываться **после** успешного сохранения родительской строки,
            но **до** рекурсивного сохранения потомков (если они есть).
            - Без этого вызова дочерние черновики будут потеряны, так как останутся привязаны
            к несуществующему временному ID.
        """

        # Переносим ВСЕ дочерние черновики (фото, заметки и т.д.)
        #    с префикса "entity_type:temp_id:" на "entity_type:created.id:"

        old_prefix = f"{self._entity_type}:{temp_id}:"
        new_prefix = f"{self._entity_type}:{id}:"
        for child_key in list(self._draft_registry.get_keys_by_prefix(old_prefix)):
            child_data = self._draft_registry.get(child_key)
            if child_data is not None:
                new_child_key = child_key.replace(old_prefix, new_prefix, 1)
                self._draft_registry.set(new_child_key, child_data)
                self._draft_registry.discard(child_key)
                self.logger.debug(f"Перенесён дочерний черновик {child_key} -> {new_child_key}")

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _update_parent_counter(
        self,
        entity_id: Optional[int],
        delta: int,
        temp_id: Optional[int] = None
    ) -> bool:
        """
        Увеличивает или уменьшает счётчик родителя для сущности.

        **Отличие от _update_parent_child_counter (из DraftTreeMixin):**
            - Этот метод проверяет, не помечен ли родитель на удаление.
            - Если родитель уже помечен на удаление, счётчик не изменяется (и логируется предупреждение).
            - Используется только при создании новой строки (_add_inline_row) и при её отмене (_cancel_new_row).

        **Логика:**
            - Если родитель не указан (entity_id is None) или его ID <= 0 – ничего не делаем, возвращаем False.
            - Если родитель помечен на удаление – ничего не делаем, возвращаем False.
            - Иначе вызываем mark_child_change(entity_id, delta) и возвращаем True.


        Args:
            parent_id: ID родительской сущности (может быть None или отрицательным для новой строки).
            delta: +1 (появление потомка), -1 (исчезновение).
            temp_id: Временный ID новой строки (для логирования).

        Returns:
            True, если счётчик был изменён (родитель существует и не удалён), иначе False.
        """

        # Уменьшаем счётчик родителя
        if (entity_id is not None) and (entity_id > 0):
            # Причина:
            # Родитель с временным ID (parent_id < 0) не должен влиять на счётчик, так как он сам ещё не сохранён.
            # Если родитель уже помечен на удаление, то новая строка не должна ИЗМЕНЯТЬ его счётчик, так как родитель всё равно будет удалён. Это предотвращает дисбаланс счётчиков.

            if not self._draft_registry.has(f"__deleted__:{self._entity_type}:{entity_id}"):
                self.mark_child_change(entity_id, delta)
                return True

            else:
                self.logger.debug(
                    f"Родитель {entity_id} помечен на удаление, счётчик не изменён для "
                    f'новой строки {temp_id}' if temp_id else 'строки'
                )

        return False


    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _recursive_save_new_row(
        self, 
        temp_id: int, 
        created_id: int,
        session: Optional[Session] = None
    ):
        """
        Находит и рекурсивно сохраняет всех прямых потомков новой строки.

        **Алгоритм:**
            1. Перебирает все ключи `__new__:{entity_type}:{child_id}` в реестре.
            2. Для каждого такого ключа проверяет, имеет ли DTO атрибут `parent_id`.
            3. Если `parent_id` == `temp_id` (текущий временный ID родителя), 
               извлекает `child_temp_id` и рекурсивно вызывает
               `_save_new_row_recursive(child_temp_id, created_id, session)`,
               передавая реальный ID уже сохранённого родителя.

        **Важно:**
            - Этот метод вызывается **после** успешного сохранения родительской строки,
              когда родитель уже получил реальный ID (`created_id`).
            - Метод не изменяет счётчики родителей – они уже были обновлены при создании
              новой строки в `_add_inline_row` и будут скорректированы при сохранении
              каждого потомка через `_balance_parent_counter`.

        Args:
            temp_id: Временный отрицательный ID родительской строки (ещё не сохранённой).
            created_id: Реальный ID, присвоенный родительской строке после сохранения в БД.
            session: Опциональная сессия SQLAlchemy для работы в одной транзакции.

        Returns:
            None
        """

        # Находим и рекурсивно сохраняем всех прямых потомков
        for child_key in list(self._draft_registry.get_keys_by_prefix("__new__")):
            child_data = self._draft_registry.get(child_key)
            if child_data and hasattr(child_data["dto"], 'parent_id'):
                child_dto = child_data["dto"]
                if child_dto.parent_id == temp_id:
                    child_temp_id = int(child_key.split(':')[-1])

                    # Защита от зацикливания (если parent_id указывает на самого себя)
                    if child_temp_id == temp_id:
                        self.logger.error(f"Обнаружена циклическая ссылка: parent_id = {child_dto.parent_id} для строки {temp_id}")
                        continue

                    # Рекурсивно сохраняем потомка, передавая реальный ID текущей строки
                    self._save_new_row_recursive(child_temp_id, created_id, session=session)

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _balance_parent_counter(
        self, 
        temp_id: int, 
        created_id: int
    ):
        """
        Уменьшает счётчик родителя новой строки, если при её создании был увеличен счётчик.

        **Когда вызывается:** 
            сразу после успешного сохранения строки в БД (в `_save_new_row_recursive`).

        **Логика:** 
            находит служебный ключ `__parent_counter_inc__:{temp_id}`, извлекает `parent_id`,
            уменьшает счётчик родителя на 1 и удаляет ключ. Если ключа нет – ничего не делает.

        **Примечание:** 
            Параметр `created_id` используется **только для отладки** (записывается в лог)
            и не влияет на логику метода. Он передан для удобства сопоставления строки в сообщениях лога.

        Args:
            temp_id: Временный ID новой строки.
            created_id: Реальный ID, присвоенный строке в БД (используется только для логирования).

        Returns:
            None
        """
        
        # --- Балансировка счётчика родителя ---
        inc_key = f"__parent_counter_inc__:{self._entity_type}:{temp_id}"
        inc_data = self._draft_registry.get(inc_key)

        if inc_data:
            parent_id = inc_data.get("parent_id")
            if parent_id is not None and parent_id > 0:
                self._update_parent_counter(parent_id, -1)
                self.logger.debug(f"Уменьшен счётчик родителя {parent_id} после сохранения строки {created_id}")

            self._draft_registry.discard(inc_key)

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _save_new_row_recursive(
        self, 
        temp_id: int, 
        real_parent_id: Optional[int] = None, 
        session: Optional[Session] = None,
    ) -> Optional[Any]:
        """
        Рекурсивно сохраняет новую строку по её временному ID и всех её прямых потомков.

        **Алгоритм:**
            1. Проверяет существование ключа `__new__:{entity_type}:{temp_id}` в реестре.
            Если ключа нет – возвращает None.
            2. Извлекает DTO из реестра.
            3. Если передан `real_parent_id` и DTO имеет поле `parent_id`, обновляет его на реальный ID
            и перезаписывает DTO в реестре.
            4. Сохраняет строку в БД через `self.service.create(dto, session)`, получая реальный ID.
            5. **Балансирует счётчик родителя:** вызывает `_balance_parent_counter(temp_id, created.id)`.
            Этот метод находит служебный ключ `__parent_counter_inc__:{temp_id}` (созданный при добавлении)
            и, если он есть, уменьшает счётчик родителя на 1, удаляя ключ.
            6. Переносит дочерние черновики (фото, заметки) через `_transferring_child_drafts(temp_id, created.id)`.
            7. Переносит статус `'own'` с временного ID на реальный через `_update_id_own_in_real_id`.
            8. Удаляет ключ `__new__` текущей строки.
            9. Находит все новые строки, у которых в DTO поле `parent_id` равно текущему `temp_id`,
            и рекурсивно вызывает `_save_new_row_recursive` для каждого потомка,
            передавая реальный ID только что сохранённой строки как `real_parent_id`.
            10. Возвращает созданный DTO.

        **Важные замечания:**
            - **Этот метод не обновляет счётчики родителей.** Счётчики родителей увеличиваются
            при создании новой строки в `_add_inline_row` 
            - **Перенос дочерних черновиков** (`_transferring_child_drafts`) происходит **после**
            сохранения текущей строки, но **до** рекурсивного сохранения потомков. Это
            гарантирует, что дочерние черновики (фото, заметки) будут привязаны к реальному
            ID родителя до того, как потомки (другие строки) будут сохранены.
            - **Рекурсия** обрабатывает потомков в глубину: сначала сохраняется родитель,
            затем его первый потомок, затем потомок потомка и т.д. Это гарантирует,
            что все внешние ключи будут корректны при сохранении.

        **Балансировка счётчиков (подробно):**
            - При создании новой строки (в `_add_inline_row`) для существующего родителя
            создаётся служебный ключ `__parent_counter_inc__:{temp_id}` с ID родителя.
            - Здесь, после успешного сохранения, этот ключ находится, и счётчик родителя уменьшается,
            компенсируя предыдущее увеличение.
            - Для новых родителей (временный ID) такой ключ отсутствует, и балансировка не выполняется.
            - Балансировка выполняется **до** переноса дочерних черновиков и **до** рекурсивного сохранения потомков,
            чтобы у родителя уже был правильный счётчик, когда потомки будут сохраняться.

        **Рекурсия и иерархия:**
            - Метод обрабатывает потомков в глубину: сначала родитель, затем его первый потомок,
            затем потомок потомка и т.д.
            - Благодаря передаче `real_parent_id = created.id` все потомки получают правильный
            реальный ID родителя, что гарантирует целостность внешних ключей.
            - Обнаружение циклических ссылок предотвращает бесконечную рекурсию.

        **Важные замечания:**
            - Метод предполагает, что все сервисные вызовы (`create`) принимают опциональный параметр `session`
            и используют его для выполнения операций в рамках одной транзакции.
            - Если в процессе сохранения возникает ошибка, транзакция откатывается вышестоящим кодом
            (в `_save_all_changes_impl_session`), и реестр черновиков остаётся неизменным для этой ветки.
            - Метод **не изменяет** флаг `_saving_in_progress` – это ответственность вызывающего кода.

        **Пример использования (внутри _save_new_rows):**
            >>> created = self._save_new_row_recursive(temp_id=-1, real_parent_id=None)
            >>> if created:
            ...     print(f"Сохранена корневая строка ID={created.id}")

        **Примечания:**
            - Метод **не сохраняет** строки, которые уже были обработаны (ключ удалён).
            - Если в процессе сохранения возникает ошибка, транзакция должна быть откачена
            вышестоящим кодом (метод `_save_all_changes_impl` уже обёрнут в `try-finally`).
            - Метод предполагает, что все DTO новых строк имеют атрибут `parent_id` (если они
            являются дочерними). Для корневых сущностей этот атрибут может отсутствовать.

        
        Args:
            temp_id (int): Временный (отрицательный) ID новой строки.
            real_parent_id (Optional[int]): Реальный ID родителя (если строка является дочерней).
                Если передан, то поле `parent_id` в DTO будет обновлено перед сохранением.
                Если `None`, строка считается корневой (обновление не выполняется).

        Returns:
            Optional[Any]: Созданный DTO (с заполненным реальным ID) или None, если ключ `__new__`
            не найден в реестре.
        """

        key = f"__new__:{self._entity_type}:{temp_id}"
        if not self._draft_registry.has(key):
            return None

        data = self._draft_registry.get(key)
        dto = data["dto"]

        # Если передан реальный ID родителя, обновляем parent_id в DTO
        if real_parent_id is not None and hasattr(dto, 'parent_id'):
            dto.parent_id = real_parent_id
            self._draft_registry.set(key, {"dto": dto})
            self.logger.debug(f"Обновлён parent_id новой строки {temp_id} -> {real_parent_id}")

        # Сохраняем строку в БД
        try:
            created = self.service.create(dto, session=session)
        except Exception as e:
            self.logger.error(f"Ошибка сохранения новой строки {temp_id}: {e}")
            
            # ВАЖНО: не удаляем служебный ключ __parent_counter_inc__ при ошибке!
            # Строка сохраняется в реестре (ключ __new__ остаётся), и счётчик родителя уже увеличен.
            # При повторном успешном сохранении ключ будет использован для балансировки.
            # Удаление ключа здесь привело бы к завышению счётчика родителя.
            # Очистка ключа происходит только при успешном сохранении (в _balance_parent_counter)
            # или при отмене строки (в _cancel_new_row).

            # ВАЖНО: При ошибке сохранения ключ __parent_counter_inc__ не удаляется,
            # потому что строка остаётся в реестре (__new__). При повторной попытке
            # сохранения _balance_parent_counter найдёт ключ и корректно уменьшит счётчик.
            # Если пользователь отменит строку, ключ будет удалён в _cancel_new_row.
            raise

        # Переносим файлы из временной папки в основное хранилище
        # created = self._move_files_from_temp_to_storage(temp_id, created)
        updated_dto, copied_files, old_files  = self._move_files_from_temp_to_storage(
            created.id, 
            created, 
            old_id=temp_id
        )

        # # Проверяем, не осталось ли файлов во временной папке (признак ошибки переноса)
        # temp_dir = self._get_temp_dir(temp_id)
        # if temp_dir and os.path.exists(temp_dir) and os.listdir(temp_dir):
        #     error_msg = f"Не удалось перенести файлы из временной папки {temp_dir}. Сохранение отменено."
        #     self.logger.error(error_msg)
        #     raise RuntimeError(error_msg)

        # # Обработка фото для новой строки (копирование файлов и преобразование в относительный путь)
        # created = self._process_photo_fields_for_new_row(created, created.id, session)

        # # Удаляем временную папку новой строки, так как файлы уже скопированы 
        # self._cleanup_temp_dir(temp_id)


        # Обновляем запись в БД, сохраняя относительные пути
        try:
            updated_dto = self.service.update(updated_dto, session=session)
        except Exception as e:
            
             # При ошибке сохраняем удаляем только что скопированные файлы (откат)
            for src in copied_files:
                delete_file_safely(src, logger = self.logger)
                # if os.path.exists(src):
                #     try:
                #         os.remove(src)
                #         self.logger.debug(f"Удалён скопированный файл при ошибке: {src}")
                #     except OSError as err:
                #         self.logger.warning(f"Не удалось удалить {src}: {err}")
            # Старые файлы не удаляем – они остались как были
            # Временную папку всё равно чистим
            self._cleanup_temp_dir(temp_id)

            raise

        # finally:
        # Если update успешен , удаляем скопированные файлы (они ещё не привязаны к БД)
        #     
        # self._del_time_file(copied_files, temp_id)
        # self._delete_old_files(old_files) 

        for files in [
            copied_files,  # Удаляем временные файлы (скопированные из временной папки) отложенно
            old_files,  # Удаляем старые файлы (заменяемые) отложенно
        ]:
            self._del_file(files, session=session)

        # Принудительно удаляем временную папку, если она осталась
        self._cleanup_temp_dir(temp_id)

        created = updated_dto   # теперь created ссылается на окончательный DTO

        # Найти строку в модели по временному ID и заменить DTO
        row = self._find_row_by_id(temp_id)
        if row >= 0:
            self._source_model_update_row(row, created)
        else:
            self.logger.warning(f"Не найдена строка для временного ID {temp_id} при обновлении модели")
        
        self.logger.debug(f"Сохранена новая строка {temp_id} -> реальный ID {created.id}")

        # Уменьшает счётчик родителя новой строки, если при её создании был увеличен счётчик
        self._balance_parent_counter(temp_id, created.id)

        # Переносим дочерние черновики (фото, заметки) с temp_id на created.id
        self._transferring_child_drafts(temp_id, created.id)

        # Переносим статус 'own' (если был) с временного ID на реальный
        self._update_id_own_in_real_id(temp_id, created.id)

        # Снимаем флаг собственных изменений (строка сохранена, статус пересчитается с учётом детей)
        self.clear_own_change(created.id)

        # Удаляем ключ __new__ текущей строки
        self._draft_registry.discard(key)

        # Находим и рекурсивно сохраняем всех прямых потомков
        self._recursive_save_new_row(temp_id, created.id, session=session)

        return created

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _save_new_rows(self, session: Optional[Session] = None) -> Dict[int, Any]:
        """
        Сохраняет все новые строки, рекурсивно обрабатывая иерархию.

        **Алгоритм:**
            1. Проходит по всем ключам `__new__:{entity_type}:{temp_id}` в реестре.
            2. Для каждого ключа определяет, является ли строка **корневой**:
            - Корневой считается строка, у которой в DTO поле `parent_id` отсутствует (None),
                равно 0 или является положительным числом (уже существующий родитель).
            3. Для каждой корневой строки вызывает `_save_new_row_recursive(temp_id)`,
            которая рекурсивно сохраняет всю ветку (потомков).
            4. Строки, у которых `parent_id` отрицательный (временный ID), считаются потомками
            и будут обработаны рекурсивно при сохранении своего родителя.
            5. Возвращает словарь `{временный_id: созданный_DTO}` для всех успешно сохранённых
            корневых строк (потомки не включаются в этот словарь, но их ID доступны
            через DTO родителей).

        **Важные замечания:**
            - **НЕ актуально (требует проверки):** Ранее в этом методе присутствовала проверка
            на наличие ключа `__deleted__` для временного ID. Согласно текущей логике,
            новая строка при пометке на удаление полностью удаляется (через `_cancel_new_row`),
            а не переводится в состояние `__deleted__`. Поэтому такая проверка **не требуется**.
            Если код устарел, проверка удалена. Если в будущем поведение изменится,
            необходимо пересмотреть этот метод.
            - **Актуальное предупреждение:** Метод **не уменьшает счётчики родителей**
            для сохранённых строк. Это сделано намеренно, потому что:
                - При создании новой строки (в `_add_inline_row`) счётчик родителя был увеличен
                только если родитель был существующим (ID > 0).
                - Если родитель сам был новым (временный ID), то счётчик для него не увеличивался.
                - При сохранении родителя его счётчик (для его собственного родителя) уменьшается
                в `_update_parent_counter` (вызывается в `_save_new_row_recursive`? Нет,
                в `_save_new_row_recursive` нет вызова `_update_parent_counter`, потому что
                этот вызов уже сделан в `_add_inline_row`. Баланс соблюдается.
            Поэтому дополнительных вызовов `_update_parent_counter` в этом методе не требуется.
            - **Актуальное предупреждение:** Метод **не переносит** дочерние черновики компонентов
            для корневых строк, кроме вызова `_transferring_child_drafts` внутри
            `_save_new_row_recursive`. Это корректно.
            - **Актуальное предупреждение:** Если в процессе сохранения возникает ошибка,
            транзакция откатывается вышестоящим методом `_save_all_changes_impl`.
            Реестр черновиков при этом не очищается автоматически – это ответственность
            вызывающего кода.

        Args:
            session: Сессия SQLAlchemy (опционально, для работы в одной транзакции).

        Returns:
            Dict[int, Any]: Словарь, где ключ – временный ID (отрицательный) новой строки,
            значение – созданный DTO (с реальным ID). Включает только корневые строки,
            обработанные в этом вызове. Потомки в словарь не попадают.

        **Пример использования (в _save_all_changes_impl):**
            >>> new_map = self._save_new_rows()
            >>> for temp_id, created in new_map.items():
            ...     print(f"Сохранена новая строка: временный {temp_id} -> реальный {created.id}")

        **Примечания:**
            - Метод полагается на `_save_new_row_recursive`, который рекурсивно обрабатывает
            иерархию. Если в реестре есть циклические ссылки (чего быть не должно),
            это приведёт к бесконечной рекурсии.
            - Метод **не изменяет** флаг `_saving_in_progress` – это задача вызывающего кода.
        """
        saved_map = {}

        # Обрабатываем все корневые новые строки
        for key in list(self._draft_registry.get_keys_by_prefix("__new__")):
            temp_id = int(key.split(':')[-1])
            # Пропускаем, если ключ уже был удалён рекурсивным вызовом
            if not self._draft_registry.has(key):
                continue

            data = self._draft_registry.get(key)
            parent_id = getattr(data["dto"], 'parent_id', None)

            # Корень: parent_id отсутствует (None), равен 0 или положительному числу
            if parent_id is None or parent_id >= 0:
                created = self._save_new_row_recursive(
                    temp_id,
                    real_parent_id=None, 
                    session=session,
                )
                if created:
                    saved_map[temp_id] = created
            # Если parent_id отрицательный (временный), то эта строка будет обработана
            # как потомок при сохранении своего родителя – игнорируем здесь.

        return saved_map

    # def _save_new_rows(self) -> Dict[int, Any]:
    #     """
    #     Сохраняет все новые строки, помеченные как __new__, в БД.

    #     **Важное пояснение о логике «новых» и «удалённых» строк:**
    #         В данной реализации для новой строки (с временным ID < 0) невозможно
    #         одновременное существование ключей `__new__` и `__deleted__`.
    #         Это достигается следующим образом:
    #             1. При добавлении новой строки создаётся только ключ `__new__:{entity_type}:{temp_id}`.
    #             2. Если пользователь помечает эту новую строку на удаление (ещё до сохранения),
    #             вызывается метод `_cancel_new_row(temp_id)`, который:
    #                 - рекурсивно удаляет всех потомков новой строки,
    #                 - удаляет сам ключ `__new__:{entity_type}:{temp_id}`,
    #                 - удаляет строку из модели,
    #                 - и **не создаёт** ключ `__deleted__`.
    #             3. Следовательно, после пометки на удаление строка перестаёт существовать в реестре
    #             и в модели, и метод `_save_new_rows` её просто не увидит.

    #         Поэтому дополнительная проверка на наличие `__deleted__:{entity_type}:{temp_id}`
    #         в этом методе **не требуется** – такая ситуация невозможна по построению.

    #     **Важное примечание о логике переноса черновиков:**
    #         Пользователь может создать новую строку (например, приём) с временным ID,
    #         а затем, до сохранения этой строки, добавить к ней дочерние черновики
    #         (например, фото). В этом случае дочерние черновики хранятся в реестре
    #         под ключами, содержащими временный ID родителя (например, "appointment:-1:photos").

    #         При сохранении родителя в БД он получает реальный ID (например, 123).
    #         Без специальной обработки дочерние черновики остались бы привязанными
    #         к временному ID и не были бы найдены при последующем вызове `_save_child_changes`.

    #         Поэтому данный метод выполняет:
    #             1. Сохранение родительской строки в БД, получение реального ID.
    #             2. Перенос всех дочерних черновиков (по префиксу "entity_type:temp_id:")
    #                на новый префикс с реальным ID.
    #             3. Перенос статуса 'own' с временного ID на реальный.
    #             4. Очистку временных ключей и кэша.

    #     Returns:
    #         Dict[int, Any]: Словарь {временный_id: созданный_DTO} для всех успешно сохранённых строк.
    #     """

    #     # Не удаляйте блок переноса дочерних черновиков! Без него фото, добавленные до сохранения родителя, будут потеряны.
    #     # Не вызывайте mark_child_change после переноса статуса – это нарушит счётчики (родитель получит +1 дважды: один раз от дочернего черновика, второй – здесь).
    #     # Не переносите статус до переноса дочерних черновиков – порядок не важен, но предпочтительнее сначала перенести черновики, чтобы они уже были на новом ключе, когда статус родителя изменится (хотя родительский статус изменится только после clear_own_change).

    #     prefix = f"__new__:{self._entity_type}:"
    #     saved_map = {}

    #     for key in list(self._draft_registry.get_keys_by_prefix(prefix)):
    #         # 1. Извлекаем временный ID и DTO
    #         temp_id = int(key.split(':')[-1])

    #         # Примечание: проверка на __deleted__ не требуется,
    #         # так как новая строка при пометке на удаление полностью удаляется через _cancel_new_row,
    #         # а не переводится в состояние __deleted__.

    #         data = self._draft_registry.get(key)
    #         dto = data["dto"]

    #         # 2. Сохраняем в БД, получаем реальный объект с ID
    #         created = self.service.create(dto)

    #         # 3. Находим строку в модели по временному ID
    #         row = self._find_row_by_id(temp_id)
    #         if row >= 0:
    #             # 4. Обновляем модель (заменяем временный DTO на созданный)
    #             self.source_model.update_row(row, created)

    #             # 5. Переносим ВСЕ дочерние черновики (фото, заметки и т.д.)
    #             #    с префикса "entity_type:temp_id:" на "entity_type:created.id:"
    #             self._transferring_child_drafts(temp_id, created.id)

    #             # 6. Переносим статус 'own' (если был) с временного ID на реальный
    #             self._update_id_own_in_real_id(temp_id, created.id)

    #             # 7. Удаляем ключ __new__ (чтобы не сохранить повторно)
    #             self._draft_registry.discard(key)

    #             # =========================================================
    #             # ВАЖНО: Уменьшаем счётчик родителя, так как новая строка больше не имеет изменений
    #             # (см. детальное объяснение в docstring метода)
    #             # =========================================================
    #             # ВНИМАНИЕ: Не переносите этот вызов внутрь clear_own_change!
    #             # clear_own_change (вызываемая ниже) НЕ должна влиять на счётчик – она только сбрасывает статус 'own' и распространяет изменение статуса вверх, но не меняет счётчик детей. Не добавляйте туда mark_child_change, иначе счётчик будет уменьшен дважды.
    #             # Уменьшаем счётчик родителя, так как новая строка больше не имеет изменений.
    #             parent_id = self._get_parent_id_for_new_row(dto)
    #             self._update_parent_counter(parent_id, -1)  # уменьшаем счётчик

    #             # незабыть обернуть в try-finally: В PaginatedListPage._save_new_rows вы после сохранения новой строки вызываете self._update_parent_counter(parent_id, -1). Но ранее при добавлении новой строки (_add_inline_row) вы вызывали _update_parent_counter(parent_id, 1). Так что баланс соблюдается. Однако есть нюанс: если в процессе сохранения произойдёт ошибка и _update_parent_counter(parent_id, -1) не выполнится, счётчик останется завышенным. Это не страшно, так как реестр черновиков для временного ID будет очищен, но родительский счётчик не уменьшится. В коде это не обрабатывается (нет try-finally вокруг этого вызова). Рекомендуется поместить вызов в блок try-finally или убедиться, что он выполняется всегда

    #             # 8. Снимаем флаг собственных изменений (строка сохранена, статус станет None)
    #             self.clear_own_change(created.id) # сбрасываем статус (не трогает счётчик)
    #             # порядок _update_parent_counter, clear_own_change - выжен для избежания лишнего сигнала. но требуется проверка не ломает ли это логику....

    #             # 9. Запоминаем соответствие для возможного обновления selected_dto
    #             saved_map[temp_id] = created

    #         else:
    #             self.logger.warning(f"Не найдена строка для временного ID {temp_id}")

    #     # После сохранения всех новых строк обновляем состояние кнопки сохранения
    #     if saved_map:
    #         self._update_save_button_state() # Обновляем состояние кнопки сохранения

    #     return saved_map

        # """
        # Сохраняет все новые строки, помеченные как __new__.
        #
        # Returns:
        #     Словарь {временный_id: созданный_DTO} для всех успешно сохранённых строк.
        # """
        #
        # prefix = f"__new__:{self._entity_type}:"
        #
        # saved_map = {}
        #
        # for key in list(self._draft_registry.get_keys_by_prefix(prefix)):
        #     temp_id = int(key.split(':')[-1])
        #     data = self._draft_registry.get(key)
        #     dto = data["dto"]
        #     created = self.service.create(dto)
        #
        #     # Обновляем модель
        #     row = self._find_row_by_id(temp_id)
        #     if row >= 0:
        #         self.source_model.update_row(row, created)
        #
        #         # # Убираем пометку 'new' и сбрасываем собственные изменения
        #         # self._draft_registry.discard(key)
        #
        #         old_status = self._get_cached_status(temp_id) # Получаем старый статус (по временному ID)
        #
        #         if old_status:
        #             # Переносим статус на реальный ID
        #             self._set_cached_status(created.id, old_status)
        #             self._draft_registry.set_entity_status(self._entity_type, created.id, old_status)
        #             self._status_cache.pop(temp_id, None)
        #
        #             # # Уведомляем родителя, что появился потомок с изменениями
        #             # parent_id = self._get_parent_id(created.id)
        #             # if parent_id is not None:
        #             #     self.mark_child_change(parent_id, +1)
        #             # self._update_own_change(created.id, False)
        #
        #         # Удаляем ключ __new__ (чтобы не сохранить повторно)
        #         self._draft_registry.discard(key)
        #
        #         # Снимаем флаг собственных изменений (строка сохранена)
        #         self.clear_own_change(created.id)
        #
        #         saved_map[temp_id] = created
        #
        #     else:
        #         self.logger.warning(f"Не найдена строка для временного ID {temp_id}")
        #
        # if saved_map:
        #     self._update_save_button_state() # Обновляем состояние кнопки сохранения
        #
        # return saved_map

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _filtered_ids_no_deleted(self, entity_ids: List[int]):
        """
        Фильтрует список ID, исключая сущности, помеченные на удаление (__deleted__).

        Args:
            entity_ids: Список ID для фильтрации.

        Returns:
            Кортеж (filtered_ids, skipped_ids), где filtered_ids – множество ID без пометки на удаление,
            skipped_ids – список ID, помеченных на удаление.
        """

        filtered_ids = set()
        skipped_ids = []
        for entity_id in entity_ids:
            # Проверяем наличие ключа удаления
            if self._draft_registry.has(f"__deleted__:{self._entity_type}:{entity_id}"):
                skipped_ids.append(entity_id)
            else:
                filtered_ids.add(entity_id)

        return filtered_ids, skipped_ids
    
    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def save_rows_with_children(self, entity_ids: List[int]) -> bool:
        """
        Сохраняет основные поля и дочерние черновики для указанных ID.
        Строки, помеченные на удаление (__deleted__), автоматически пропускаются.

        **Алгоритм:**
            1. Фильтрует переданные ID, исключая помеченные на удаление.
            2. Сохраняет основные поля строк через `_save_modified_rows_for_ids`.
            3. Применяет дочерние черновики для этих же ID через `_save_child_components_for_parents`.
            4. Перезагружает данные (reload_data).
            5. Очищает реестр для каждого сохранённого ID через `clear_entity_drafts`.

        Примечание:
            Этот метод предназначен для выборочного сохранения (например, из контекстного меню).
            Для сохранения всех изменений используйте стандартную кнопку «Сохранить»,
            которая вызывает _save_all_changes_impl.
        Args:
            entity_ids: Список ID сущностей (должны существовать в БД).

        Returns:
            True, если сохранение прошло успешно, иначе False.
        """

        self.logger.debug(
            f"self._saving_in_progress  = {self._saving_in_progress} "
        )
        # Причина проверки: предотвращаем повторный вход при параллельных вызовах
        if self._saving_in_progress:
            self.logger.warning("Сохранение уже выполняется, повторный вызов игнорирован")
            return False

        self._saving_in_progress = True
        try:
            # Фильтруем ID: оставляем только те, которые не помечены на удаление
            # Причина: строки, помеченные на удаление, не должны сохраняться – они будут удалены
            filtered_ids, skipped_ids = self._filtered_ids_no_deleted(entity_ids)

            # Логируем пропущенные ID (для отладки)
            if skipped_ids:
                self.logger.info(f"Сохранение пропущено для строк, помеченных на удаление: {skipped_ids}")

            if not filtered_ids:
                self.logger.warning("Нет строк для сохранения (все переданные ID помечены на удаление)")
                return True

            # 1. Сохраняем основные поля для указанных ID
            self._save_modified_rows_for_ids(filtered_ids)

            # 2. Сохраняем дочерние черновики для этих же ID
            self._save_child_components_for_parents(filtered_ids)

            # 3. Перезагружаем данные (чтобы модель обновилась)
            self.reload_data()

            # # 4. Очищаем реестр от использованных черновиков
            # self._clear_entity_registry()
            # причина удаления: save_rows_with_children предназначен для выборочного сохранения только переданных сущностей, а _clear_entity_registry() удаляет все черновики для текущего типа, в том числе для других строк (не вошедших в entity_ids). Это нарушает инкапсуляцию и может привести к неожиданной потере несохранённых изменений в других строках. Удаление этой строки предотвращает побочные эффекты.

            # 4. Очищаем реестр от использованных черновиков только для отфильтрованных
            for entity_id in filtered_ids:
                self.clear_entity_drafts(entity_id)

            # # 5. Выходим из режима редактирования (если был включён)
            # self._exit_edit_mode()
            # Причина удаления: изменил несколько строк (например, приём А и приём Б). Затем он выбрал только приём А и вызвал этот метод - Режим редактирования выключится , Несохранённые изменения в приёме Б останутся в реестре, но пользователь больше не сможет их сохранить

            self._update_save_button_state() # Обновляем состояние кнопки сохранения

            return True

        except Exception as e:
            self.logger.exception(f"Ошибка при выборочном сохранении строк: {e}")
            return False

        finally:
            self._saving_in_progress = False

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _save_child_components_for_parents(
        self, 
        parent_ids: Set[int], 
        session: Optional[Session] = None
    ) -> None:
        """
        Применяет черновики всех дочерних компонентов для указанного родителя.

        **Логика работы с счётчиком родителя:**
            - При создании черновика (например, добавлении фото к приёму) счётчик родителя
              увеличивается на +1 (через `mark_child_change(parent_id, +1)`).
            - При успешном применении черновика счётчик должен быть уменьшен на -1.
            - Если дочерний компонент по ошибке не удалил черновик, мы принудительно удаляем
              его сами и всё равно уменьшаем счётчик, чтобы избежать дисбаланса.
              Это не скрывает ошибку – в лог записывается сообщение уровня ERROR,
              привлекающее внимание разработчика.

        **Важно:** Дочерний компонент **НЕ ДОЛЖЕН вызывать mark_child_change внутри apply** –
            это приведёт к двойному учёту. Весь учёт счётчиков выполняет только `PaginatedListPage`.
        
        Args:
            parent_ids: Множество ID родителей (должны быть > 0).
            session: Сессия SQLAlchemy (опционально, для работы в одной транзакции).
        """

        for parent_id in parent_ids:
            if parent_id >= 0:
                self._save_child_components_for_parent(
                    parent_id,
                    session=session
                )

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _save_modified_rows(
        self, 
        session: Optional[Session] = None
    ) -> None:
        """
        Сохраняет изменения существующих строк (только те, у которых есть статус 'own' или 'both').

        Args:
            session: Сессия SQLAlchemy (опционально, для работы в одной транзакции).
        """

        self.logger.debug(f"_save_modified_rows: session is None = {session is None}")
        
        entity_ids = set()

        # Ищем все ключи статусов для данного типа
        for key in self._draft_registry.get_keys_by_prefix(f"__status__:{self._entity_type}:"):
            parts = key.split(':')
            if len(parts) >= 3:
                entity_id = int(parts[2])
                status = self._draft_registry.get_entity_status(self._entity_type, entity_id)
                if status in ('own', 'both'):
                    entity_ids.add(entity_id)

        self._save_modified_rows_for_ids(
            entity_ids=entity_ids,
            session=session, 
        )

        # for entity_id in entity_ids:
        #     row = self._find_row_by_id(entity_id)
        #     if row < 0:
        #         continue
        #
        #     dto = self.source_model.get_item_at_row(row)
        #     if dto is None:
        #         continue
        #
        #     updated = self.service.update(dto)
        #     self.source_model.update_row(row, updated)
        #
        #     # уточнение:
        #     # так как в дальнейшем может потребоваться делать общий буфер на все страници - чистим сейчас
        #     self.clear_entity_drafts(entity_id) # Удаляет черновики для данной сущности
        #
        #     # Снимаем флаг собственных изменений (обновляем статус)
        #     self.clear_own_change(entity_id)  # снимаем флаг 'own'

        # """
        # Сохраняет изменения существующих строк, у которых есть черновики.
        # Использует ключи вида "entity_type:entity_id:*" (не служебные).
        # """
        # prefix = f"{self._entity_type}:"
        # # Собираем уникальные ID сущностей, у которых есть черновики
        # entity_ids = set()
        # for key in self._draft_registry.get_keys_by_prefix(prefix):
        #     # Пропускаем служебные ключи
        #     if key.startswith(('__', f"{self._entity_type}:")):
        #         parts = key.split(':')
        #         if len(parts) >= 2 and parts[0] == self._entity_type:
        #             try:
        #                 entity_id = int(parts[1])
        #                 entity_ids.add(entity_id)
        #             except ValueError:
        #                 pass
        # # Для каждого ID обновляем запись в БД
        # for entity_id in entity_ids:
        #     row = self._find_row_by_id(entity_id)
        #     if row < 0:
        #         continue
        #     dto = self.source_model.get_item_at_row(row)
        #     if dto is None:
        #         continue
        #     updated = self.service.update(dto)
        #     self.source_model.update_row(row, updated)
        #     # Снимаем флаг собственных изменений (черновики остаются? Нет, черновики нужно удалить)
        #     # Решаем: после сохранения все черновики для этой сущности должны быть удалены.
        #     self._draft_registry.discard_entity_subtree(self._entity_type, entity_id)
        #     self._update_own_change(entity_id, False)

    
    # def _save_modified_rows(self):
    #     for entity_id in list(self.modified_ids):
    #         row = self._find_row_by_id(entity_id)
    #         if row < 0:
    #             continue
    #         dto = self.source_model.get_item_at_row(row)
    #         if dto:
    #             updated = self.service.update(dto)
    #             self.source_model.update_row(row, updated)
    #             self.original_data[row] = updated
    #     self.modified_ids.clear()

    # def _clear_draft_registry(self, entity_id: int) -> None:
    #     """
    #     Удаляет черновики для данной сущности.
    #     Примечание: дочерние черновики (например, фото) уже сохранены и удалены
    #     в _save_child_components, поэтому удаление по префиксу безопасно.
    #     """

    #     # # После сохранения сбрасываем статус и черновики
    #     # self._draft_registry.discard_entity_subtree(self._entity_type, entity_id)


    #     # Удаляем все ключи, начинающиеся с "entity_type:entity_id:"
    #     # (включая возможные остаточные дочерние черновики – они уже применены)
    #     temp = f"{self._entity_type}:{entity_id}"
    #     self._draft_registry.discard_by_prefix(f"{temp}:") # Удаляем ТОЛЬКО прямые черновики этой сущности (но не дочерние)

    #     # Удаляем статус и счётчик
    #     self._draft_registry.delete_entity_status(self._entity_type, entity_id)
    #     self._draft_registry.discard(f"__counter__:{temp}")

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _clear_selected_dto_dict(self, dict_entity_id: Dict[int, Any], new_dto = None) -> None:

        if dict_entity_id is None:
            return

        # Если удаляемая строка – текущая выбранная, сбрасываем selected_dto
        if self.selected_dto and self.selected_dto.id in dict_entity_id:
            self.selected_dto = new_dto

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _clear_selected_dto(self, entity_id:int, new_dto = None) -> None:
        """
        Сбрасывает текущий выбранный DTO, если он соответствует указанному ID.

        Используется при удалении строки, чтобы `self.selected_dto` не ссылался на удалённый объект.
        Если передан `new_dto`, то он становится новым `selected_dto` (например, после перезагрузки строки).

        **Пример:**
            >>> # Удаляем строку с ID=123
            >>> self._clear_selected_dto(123)
            >>> # Если selected_dto.id == 123, то selected_dto станет None
            >>> self._clear_selected_dto(123, fresh_dto)
            >>> # Если selected_dto.id == 123, он заменится на fresh_dto

        Args:
            entity_id: ID сущности, для которой проверяется совпадение с selected_dto.
            new_dto: dto, на замену при совпадении с entity_id (может быть None).

        Returns:
            None
        """

        if entity_id is None:
            return

        # Если удаляемая строка – текущая выбранная, сбрасываем selected_dto
        if self.selected_dto and self.selected_dto.id == entity_id:
            self.selected_dto = new_dto
        
        # # Если удаляемая строка – текущая выбранная, сбрасываем selected_dto
        # if self.selected_dto and self.selected_dto.id == entity_id:
        #     self.selected_dto = new_dto


    # def _save_deleted_rows(self) -> None:
    #     """
    #     Удаляет строки, помеченные как __deleted__, и каскадно их потомков.
    #
    #     **Важное примечание о каскадном удалении:**
    #     ----------------------------------------------------------------
    #     В отличие от каскада в БД (ON DELETE CASCADE), этот метод реализует
    #     каскад на уровне приложения. Это необходимо, потому что:
    #         1. Дочерние сущности могут иметь свои черновики, которые нужно очистить.
    #         2. Счётчики родителей должны быть корректно уменьшены.
    #         3. Мы не хотим полагаться на конкретную реализацию БД (SQLite, PostgreSQL и т.д.).
    #
    #     Алгоритм для каждого удаляемого ID:
    #         1. Рекурсивно помечает на удаление всех потомков (через `_delete_children`).
    #         2. Удаляет родителя из БД через сервис.
    #         3. Очищает реестр от всех ключей, связанных с родителем и его потомками.
    #         4. Уменьшает счётчик родителя (если есть).
    #     ----------------------------------------------------------------
    #     """
    #
    #     prefix = f"__deleted__:{self._entity_type}:"
    #
    #     for key in list(self._draft_registry.get_keys_by_prefix(prefix)):
    #         entity_id = int(key.split(':')[-1])
    #
    #         # Каскадно помечаем всех детей (и внуков) на удаление
    #         self._delete_children(entity_id)
    #
    #         # Если удаляемая строка – текущая выбранная, сбрасываем selected_dto
    #         self._clear_selected_dto(entity_id)
    #
    #         # Удаляем из БД (первым делом, чтобы при ошибке не трогать реестр)
    #         self.service.delete(entity_id)
    #
    #         # Удаляем все черновики дочерних сущностей, связанных с этим родителем
    #         # ВАЖНО: удаляем ВСЕ черновики дочерних сущностей, связанные с удаляемым родителем...
    #         self._draft_registry.discard_by_prefix(f"{self._entity_type}:{entity_id}:")
    #
    #         # Удаляем сам ключ __deleted__
    #         self._draft_registry.discard(key)
    #
    #         # Удаляем все черновики, статусы и счётчики для этой сущности
    #         self._draft_registry.delete_entity_status(self._entity_type, entity_id)
    #         self._draft_registry.discard(f"__counter__:{self._entity_type}:{entity_id}")
    #
    #         # Очищаем кэш статусов в миксине
    #         self._status_cache.pop(entity_id, None)
    #
    #         # Уведомляем родителя удаляемой строки (уменьшаем его счётчик)
    #         self._update_parent_child_counter(entity_id, -1) # -1 к счётчику родителя # Уведомляем родителей (если есть) # Наследован из DraftTreeMixin
    #
    #         # # Удаляем из БД
    #         # self.service.delete(entity_id)

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _save_deleted_rows(
        self, 
        session: Optional[Session] = None
    ) -> None:
        """
        Удаляет строки, помеченные как __deleted__, и каскадно всех их потомков из БД.

        **Важное примечание о каскадном удалении:**
        --------------------------------------------------------------------
        В отличие от каскада в БД (ON DELETE CASCADE), этот метод реализует
        каскад на уровне приложения. Это необходимо, потому что:
            1. Дочерние сущности могут иметь свои черновики, которые нужно очистить.
            2. Счётчики родителей должны быть корректно уменьшены.
            3. Мы не хотим полагаться на конкретную реализацию БД (SQLite, PostgreSQL и т.д.).

        Алгоритм для каждого удаляемого ID:
            1. Рекурсивно удаляет всех потомков (вызовом `_delete_entity_and_children`).
            2. Удаляет родителя из БД через сервис.
            3. Очищает реестр от всех ключей, связанных с родителем.
            4. Уменьшает счётчик родителя (если есть).
        --------------------------------------------------------------------
        Args:
            session: Сессия SQLAlchemy (опционально, для работы в одной транзакции).
        """

        self.logger.debug(f"_save_deleted_rows: session is None = {session is None}")

        prefix = f"__deleted__:{self._entity_type}:"
        keys = list(self._draft_registry.get_keys_by_prefix(prefix))
        for key in keys:
            entity_id = int(key.split(':')[-1])
            self._delete_entity_and_children(
                entity_id=entity_id, 
                session=session
            )

            # Удаляем строку из модели
            row = self._find_row_by_id(entity_id)
            if row >= 0:
                self.source_model.remove_row(row)
                self.original_data.pop(row, None)

            # Если удаляемая строка была выбрана – сбрасываем выделение
            self._clear_selected_dto(entity_id)

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _delete_entity_and_children(
        self, 
        entity_id: int, 
        session: Optional[Session] = None,
    ) -> None:
        """
        Рекурсивно удаляет сущность и всех её потомков из БД, а также очищает реестр.

        Алгоритм:
            1. Получает список ID прямых потомков через `_get_child_ids(entity_id)`.
            2. Для каждого потомка:
                - Если он ещё не помечен на удаление в реестре – помечает (создаёт ключ __deleted__)
                  и увеличивает счётчик родителя (чтобы родитель знал об удалении).
                - Рекурсивно вызывает `_delete_entity_and_children` для потомка.
            3. Удаляет саму сущность из БД через сервис.
            4. Очищает все ключи реестра, связанные с этой сущностью:
               - черновики по префиксу "entity_type:entity_id:"
               - ключ __deleted__ (если был)
               - статус (__status__)
               - счётчик детей (__counter__)
            5. Очищает кэш статусов в миксине.
            6. Уведомляет родителя (если есть) об уменьшении счётчика потомков (-1).

        **Важно:** Этот метод предполагает, что `_get_child_ids` переопределён в наследнике
        и возвращает список реальных ID дочерних записей, уже сохранённых в БД.

        Args:
            entity_id: ID сущности (должен быть >= 0, т.е. существовать в БД).
            session: Сессия SQLAlchemy (опционально, для работы в одной транзакции).
        """

        # Рекурсивно удалить всех потомков
        for child_id in self._get_child_ids(entity_id):
            # Если дочерняя ещё не помечена на удаление – помечаем
            temp = f"__deleted__:{self._entity_type}:{child_id}"
            if not self._draft_registry.has(temp):
                self._draft_registry.set(temp, {})
                # # Увеличиваем счётчик родителя дочерней сущности (чтобы её родитель знал)
                # self._update_parent_child_counter(child_id, 1) # причин удаления: Этот счётчик уже был увеличен ранее, когда child_id был помечен на удаление (в _delete_selected_rows или при каскадной пометке).

            # Рекурсивно удаляем ребёнка и его потомков
            self._delete_entity_and_children(
                entity_id=child_id, 
                session=session,
            )
        
        # Очищаем временную папку для удаляемой сущности
        self._cleanup_temp_dir(entity_id)

        # Очистить реестр от ключей, связанных с этой сущностью
        self._clean_entity_registry_by_id("__deleted__", entity_id)

        #    - счётчик детей
        self._draft_registry.discard(f"__counter__:{self._entity_type}:{entity_id}")

        # Удалить саму сущность из БД
        self.service.delete(
            entity_id=entity_id, 
            session=session,
        )

        # Очистить кэш статусов
        self._status_cache.pop(entity_id, None)

        # Удалить цвет для этого ID (строка уже удалена из модели)
        self.source_model.clear_row_color(entity_id)

        # Уменьшить счётчик родителя удаляемой сущности (компенсируем увеличение при пометке к примеру в _delete_selected_rows)
        self._update_parent_child_counter(entity_id, -1)

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _save_child_changes(
        self, 
        new_map,
        session: Optional[Session] = None
    ):
        """
        Применяет (сохраняет) черновики всех дочерних компонентов для всех родительских сущностей, у которых есть активные дочерние черновики.

        **Логика работы:**
            1. Сначала обрабатываются все новые строки (те, что были созданы в текущей сессии редактирования).
               Для каждой такой строки (уже сохранённой в БД, с реальным ID) вызывается
               `_save_child_components_for_parent()`, которая применяет дочерние черновики
               (например, фото) к этому родителю.
            2. Затем собираются ID всех родителей, у которых есть дочерние черновики
               (статус 'child' или 'both'), через метод `_get_parents_with_child_drafts()`.
            3. Чтобы не обрабатывать одного родителя дважды (если он уже был обработан как новая строка),
               используется множество `processed_parents`. В него сразу добавляются ID новых строк.
            4. Для каждого родителя из полученного списка, который ещё не был обработан,
               вызывается `_save_child_components_for_parent()`.
            5. После применения черновиков выполняется **проверка дисбаланса счётчиков**:
               - Если у родителя после обработки остался статус 'child', но при этом в реестре
                 нет ни одного активного дочернего черновика (по префиксу), то это указывает на
                 ошибку в учёте счётчиков. В таком случае счётчик принудительно уменьшается на 1,
                 чтобы синхронизировать состояние.
               - Такая ситуация может возникнуть, если дочерний компонент не удалил свой черновик
                 после применения (нарушение контракта) или если произошла ошибка в логике.

        **Важно:**
            - Дочерние компоненты **обязаны** после успешного применения удалять свой черновик
              из реестра (например, через `registry.apply_and_clear()`).
            - Метод не изменяет основные поля родительских строк – за это отвечает
              `_save_modified_rows` и другие методы.
            - Вызов этого метода происходит внутри `_save_all_changes_impl` **после** сохранения
              новых строк (`_save_new_rows`), но **до** сохранения изменённых и удалённых строк.

        Args:
            new_map (Dict[int, Any]): Словарь, возвращённый методом `_save_new_rows`,
                где ключ – временный ID новой строки, значение – созданный DTO с реальным ID.
                Используется для того, чтобы сразу обработать дочерние черновики для новых родителей
                и не обрабатывать их повторно в основном цикле.
            session: Сессия SQLAlchemy (опционально, для работы в одной транзакции).

        Returns:
            None
        """

        # Сохраняем дочерние черновики для всех новых строк (они уже имеют реальный ID)
        for temp_id, created in new_map.items():
            parent_id = created.id
            self._save_child_components_for_parent(
                parent_id, 
                session=session,
            )
            # processed_parents.add(parent_id)

        # Множество ID уже обработанных новых строк
        processed_parent_ids  = {created.id for created in new_map.values()}

        # Обрабатываем всех родителей, у которых есть дочерние черновики
        # Сохраняем дочерние черновики для всех существующих строк, у которых есть такие черновики
        for parent_id in self._get_parents_with_child_drafts():
            # Исключаем новые строки (они уже обработаны)
            if parent_id in processed_parent_ids:
                continue

            self._save_child_components_for_parent(
                parent_id, 
                session=session,
            )

            # === ЗАЩИТА ОТ ДИСБАЛАНСА СЧЁТЧИКОВ ===
            # Если после обработки статус родителя всё ещё 'child', а активных черновиков нет,
            # принудительно сбрасываем счётчик (уменьшаем на 1).
            # Это предотвращает ситуацию, когда родитель остаётся жёлтым без реальных изменений.
            status = self._draft_registry.get_entity_status(self._entity_type, parent_id)
            if status == 'child':
                # Проверяем, есть ли дочерние черновики по префиксу
                prefix = f"{self._entity_type}:{parent_id}:"
                has_child_drafts = any(
                    not k.startswith(('__status__', '__counter__', '__deleted__', '__new__'))
                    for k in self._draft_registry.get_keys_by_prefix(prefix)
                )
                if not has_child_drafts:
                    self.logger.warning(
                        f"Обнаружен дисбаланс счётчика для родителя {parent_id}: статус 'child', "
                        "но дочерние черновики отсутствуют. Принудительный сброс."
                    )
                    self.mark_child_change(parent_id, -1)

        # Принудительная очистка оставшихся черновиков для всех дочерних префиксов
        # (на случай, если какой-то компонент забыл удалить свой черновик)
        for key in list(self._draft_registry.get_keys_by_prefix(f"{self._entity_type}:")):
            if not key.startswith(('__status__', '__counter__', '__deleted__', '__new__')):
                self.logger.warning(
                    f"Обнаружен неочищенный черновик после сохранения: {key}. "
                    "Это может указывать на ошибку в дочернем компоненте, но черновик не удалён."
                )
                # self._draft_registry.discard(key) # Причина удаления: может стереть легитимные черновики, если какой-то компонент ещё не успел их применить (например, из-за ошибки в порядке вызовов). Лучше только логировать, но не удалять.

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _discard_all_changes(self) -> None:
        """
        Полностью отменяет все несохранённые изменения для текущего типа сущности.

        **Алгоритм:**
            1. Очищает реестр от всех черновиков, статусов, счётчиков, удалённых и новых записей
               для текущего типа (через `_clear_entity_registry`).
            2. Перезагружает данные из БД (первая страница с учётом фильтров).
            3. Сбрасывает цвета строк в таблице.
            4. Очищает черновики дочерних компонентов (если они реализуют `discard`).
            5. Обновляет состояние кнопки сохранения (делает её неактивной).

        **Использование:**
            Вызывается из `cancel_all_changes` (глобальная кнопка «Отменить все изменения»).
            После вызова пользователь может продолжить редактирование – изменения будут создавать новые черновики.

        **Важно:**
            - Этот метод переопределяет абстрактный метод `EditModeMixin._discard_all_changes`.
            - Этот метод **не** вызывает `_exit_edit_mode` – выход из режима редактирования
              должен быть выполнен отдельно (вызов `cancel_all_changes` сам вызовет `_exit_edit_mode`).
            - Реестр очищается только для текущего `self._entity_type`, что безопасно даже
              при глобальном реестре (одном на всё приложение).
            - После выполнения метода пользователь может продолжить редактирование в режиме
              редактирования (если он был включён) – изменения будут создавать новые черновики.

        **Побочные эффекты:**
            - Все черновики для текущего типа сущности удаляются без возможности восстановления.
            - Текущий `selected_dto` остаётся прежним, но его данные перезагружаются из БД.
            - Если страница находится в режиме редактирования, UI остаётся в этом режиме
              (чекбоксы, редактирование), но все данные уже сброшены.

        **Пример использования (внутри класса):**
            >>> # пользователь нажал кнопку «Отменить все»
            >>> self._discard_all_changes()
            >>> self.reload_data()          # уже вызывается внутри
            >>> self._exit_edit_mode()      # вызывается из cancel_all_changes
            >>> self._update_save_button_state()  # кнопка станет неактивной

        **Примечание:**
            Этот метод переопределяет абстрактный метод `EditModeMixin._discard_all_changes`.
            Если в будущем потребуется частичная отмена (например, только для выбранных строк),
            используйте `_cancel_selected_rows_changes`.
        """

        # 1. Очищаем реестр от всех черновиков, статусов, счётчиков для текущего типа
        self._clear_entity_registry()

        # 2. Перезагружаем данные из БД (первая страница)
        self.reload_data()

        # 3. Сбрасываем цвета строк в таблице
        self.source_model.clear_row_colors()

        # 4. Очищаем черновики дочерних компонентов (если есть)
        for child in self._children_components:
            if hasattr(child, 'discard'):
                child.discard(self._draft_registry)

        # 5. Обновляем состояние кнопки сохранения
        self._update_save_button_state()

        self.logger.debug(f"Глобальная отмена изменений для типа {self._entity_type}")

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _save_all_changes_impl_reload_clear_entity_registry(self) -> bool:
        """
        Выполняет сохранение всех изменений в рамках единой транзакции, затем перезагружает данные и очищает реестр.

        **Алгоритм:**
            1. Вызывает `_save_all_changes_impl_session()` для выполнения операций сохранения
            (новые строки, дочерние черновики, изменённые строки, удалённые строки) внутри
            одной сессии БД. При возникновении ошибки транзакция откатывается.
            2. После успешного сохранения вызывает `reload_data()` для перезагрузки данных
            из БД в модель таблицы.
            3. Очищает реестр черновиков от всех служебных ключей (статусы, счётчики, черновики)
            для текущего типа сущности через `_clear_entity_registry()`.

        **Важно:**
            - Этот метод является **вспомогательным** и вызывается внутри `_save_all_changes_impl`.
            - Он не управляет флагом `_saving_in_progress` – это делает вызывающий код.
            - После вызова метода все черновики для текущей страницы удаляются, а данные
            в таблице соответствуют состоянию БД.
        
        **Исключения:**
            Любое исключение, возникшее в `_save_all_changes_impl_session()`, пробрасывается выше.

        **Пример использования (внутри `_save_all_changes_impl`):**
            >>> try:
            ...     self._save_all_changes_impl_reload_clear_entity_registry()
            ...     self._exit_edit_mode()
            ...     return True
            ... except Exception as e:
            ...     self.logger.exception(f"Ошибка: {e}")
            ...     return False

        **Примечания:**
            - Разделение на `_save_all_changes_impl_session` и этот метод позволяет
            вызывать сохранение без перезагрузки данных (например, для дочерних черновиков).
            - Очистка реестра после перезагрузки данных гарантирует, что реестр не содержит
            устаревших ключей, которые могли бы повлиять на следующие операции.
        """

        # Сохраняем всех изменений внутри единой транзакции.
        self._save_all_changes_impl_session()

        # Перезагружаем данные (и выходим из режима редактирования?????)
        self.reload_data() 

        # Очищаем реестр от служебных ключей (черновики, статусы, счётчики, удалённые, новые)
        self._clear_entity_registry()

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _save_all_changes_impl_session(
        self, 
        session: Optional[Session] = None,
    ) -> bool:
        """
        Выполняет основную логику сохранения всех изменений внутри единой транзакции.

        **Назначение:**
            Данный метод инкапсулирует операции сохранения (новые строки, дочерние черновики,
            изменённые строки, удалённые строки) в рамках одной сессии базы данных.
            Это гарантирует, что при возникновении ошибки на любом этапе все изменения
            будут откачены, сохраняя целостность данных.

        **Порядок операций (критически важен):**
            1. Сохраняет новые строки через `_save_new_rows(session)`, получая словарь
            `{временный_id: созданный_DTO}`.
            2. Если текущая выбранная строка (`self.selected_dto`) была новой
            (её временный ID присутствует в `new_map`), обновляет `self.selected_dto`
            на сохранённый DTO с реальным ID. Это необходимо для корректной работы
            последующих операций (например, добавления дочерних черновиков).
            3. Сохраняет дочерние черновики (фото, заметки и т.д.) через
            `_save_child_changes(new_map, session)`. Для новых родителей дочерние
            черновики уже перенесены на реальные ID на шаге 1.
            4. Сохраняет изменения в существующих строках через `_save_modified_rows(session)`.
            5. Удаляет помеченные строки через `_save_deleted_rows(session)`.

        **Гарантии транзакционности:**
            - Все операции выполняются внутри одного контекстного менеджера
            `self._db.session_scope()`. При успешном завершении блока происходит
            автоматический `commit`, при любом исключении – `rollback`.
            - Реестр черновиков (`self._draft_registry`) **не очищается** внутри этого метода.
            Очистка выполняется в вызывающем методе `_save_all_changes_impl` после успешного
            завершения транзакции.

        Args:
            session: Опциональная внешняя сессия SQLAlchemy.    

        **Возвращаемое значение:**
            bool: Всегда `True`, если исключение не возникло. В случае ошибки исключение
            пробрасывается наверх (метод не перехватывает исключения).

        **Исключения:**
            Любое исключение, возникшее при сохранении (ошибка БД, нарушение внешнего ключа,
            ошибка сервиса и т.п.), пробрасывается вызывающему коду. Это позволяет
            вышестоящему методу (`_save_all_changes_impl`) обработать ошибку и показать
            сообщение пользователю.

        **Пример использования (в `_save_all_changes_impl`):**
            >>> def _save_all_changes_impl(self) -> bool:
            ...     if self._saving_in_progress:
            ...         return False
            ...     self._saving_in_progress = True
            ...     try:
            ...         success = self._save_all_changes_impl_session()
            ...         if success:
            ...             self.reload_data()
            ...             self._clear_entity_registry()
            ...             self._exit_edit_mode()
            ...         return success
            ...     except Exception as e:
            ...         self.logger.exception(...)
            ...         return False
            ...     finally:
            ...         self._saving_in_progress = False

        **Примечания:**
            - Метод предполагает, что все сервисные вызовы (`service.create`, `service.update`,
            `service.delete`) принимают опциональный параметр `session` и используют его
            для выполнения операций в рамках переданной сессии.
            - Счётчики родителей и статусы сущностей обновляются автоматически внутри
            вызываемых методов (`_save_new_rows`, `_save_child_changes` и т.д.).
            - Метод **не** перезагружает данные и **не** очищает реестр – это ответственность
            вызывающего кода.
        """

        if session is None:
            with self.service._db.session_scope() as new_session:
                return self._save_all_changes_impl_session(new_session)

        # with self.service._db.session_scope() as session:
                
        # Сохраняем новые строки, получаем словарь {temp_id: created_dto}
        new_map = self._save_new_rows(session=session)

        # # Если текущая выбранная строка была новой – обновляем selected_dto
        # if self.selected_dto and self.selected_dto.id in new_map:
        #     self.selected_dto = new_map[self.selected_dto.id]

        # # # Сохраняем дочерние черновики (например, фото)
        # # self._save_child_components()

        # # # Сохраняем дочерние черновики для всех новых строк (они уже имеют реальный ID)
        # # for temp_id, created in new_map.items():
        # #     self._save_child_components_for_parent(created.id)
        # #
        # # # Сохраняем дочерние черновики для текущей выбранной строки, если она существует и не новая
        # # if self.selected_dto and self.selected_dto.id >= 0:
        # #     self._save_child_components_for_parent(self.selected_dto.id)

        # Если текущая выбранная строка была новой – обновляем selected_dto
        # if self.selected_dto and self.selected_dto.id in new_map:
        #     self.selected_dto = new_map[self.selected_dto.id]
        self._clear_selected_dto_dict(new_map, new_map[self.selected_dto.id])
        
        # Сохраняем дочерние черновики для всех новых строк (они уже имеют реальный ID) и для всех существующих строк, у которых есть такие черновики
        self._save_child_changes(new_map, session=session)
        
        # Сохраняем изменённые строки
        self._save_modified_rows(session=session)
        
        # Сохраняем удалённые строки
        self._save_deleted_rows(session=session)

        return True

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _save_all_changes_impl(self) -> bool:
        """
        Основной метод сохранения всех изменений (вызывается из `EditModeMixin.save_all_changes`).

        **Порядок сохранения (критически важен!):**
            1. Сохраняем новые строки (`_save_new_rows`) – они получают реальные ID из БД.
               При этом дочерние черновики, привязанные к временным ID, переносятся на реальные ID.
            2. Применяем дочерние черновики (`_save_child_changes`) – фото, заметки и т.д.
               Для новых родителей (только что созданных) дочерние черновики уже находятся на
               правильных ключах (благодаря шагу 1).
            3. Сохраняем изменённые существующие строки (`_save_modified_rows`).
            4. Сохраняем удалённые строки (`_save_deleted_rows`).
            5. Перезагружаем данные, очищаем реестр от использованных черновиков и выходим
               из режима редактирования.

        Returns:
            True, если сохранение прошло успешно, иначе False.
        """

        self.logger.debug(
            f"self._saving_in_progress  = {self._saving_in_progress} "
        )
        if self._saving_in_progress: # флаг блокировки
            self.logger.warning("Сохранение уже выполняется, повторный вызов игнорирован")
            return False
        
        self._saving_in_progress = True 

        try:
            # Сохранение изменений внутри единой транзакции, Перезагружаем данные, Очищаем реестр от служебных ключей
            self._save_all_changes_impl_reload_clear_entity_registry()

            # Выходим из режима редактирования (отключаем чекбоксы, блокируем редактирование)
            self._exit_edit_mode()

            self._update_save_button_state() # Обновляем состояние кнопки сохранения (на случай, если _exit_edit_mode не вызывает)

            return True
        
        except Exception as e:
            self.logger.exception(f"Ошибка при сохранении: {e}")
            return False
        
        finally:
            self._saving_in_progress = False

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _source_model_update_row(self, row: int, updated: Any) -> None:
        """
        Обновляет строку в модели таблицы и синхронизирует сохранённую копию исходных данных.

        **Назначение:**
            Данный метод инкапсулирует две операции, которые должны выполняться вместе:
                1. Обновление DTO в `self.source_model` (основной модели таблицы) через
                вызов `self.source_model.update_row(row, updated)`.
                2. Обновление словаря `self.original_data[row]` (копии данных до редактирования)
                на тот же DTO `updated`.

            Это гарантирует, что после сохранения изменений (например, после вызова
            `service.update`) исходная копия данных для строки будет соответствовать
            актуальному состоянию в БД, что предотвращает ложное определение изменений
            при последующих правках.

        **Когда используется:**
            - В `_save_modified_rows_for_ids` после успешного обновления строки в БД,
            перед вызовом `clear_entity_drafts`.
            - В любом другом месте, где необходимо одновременно обновить модель
            и синхронизировать эталонные данные для отслеживания изменений.

        **Почему нельзя просто вызвать `self.source_model.update_row`:**
            Без обновления `self.original_data` при последующем редактировании строки
            сравнение текущего DTO с оригиналом покажет, что данные «изменились»,
            даже если пользователь вернул значения к исходным. Это приведёт к
            ложному появлению жёлтого цвета и ненужному сохранению.

        **Важно:**
            - Метод не вызывает сигналы модели (они испускаются внутри `update_row`).
            - Не проверяет, изменилось ли фактически значение DTO – вызывающий код
            должен быть уверен, что обновление необходимо.

        Args:
            row (int): Индекс строки в модели (0-based).
            updated (Any): Новый DTO (обычно возвращённый сервисом после `update`).

        Returns:
            None

        Example:
            >>> dto = self.service.update(dto, session=session)
            >>> self._source_model_update_row(row, dto)
            >>> # теперь self.original_data[row] == dto
        """

        self.source_model.update_row(row, updated)

        self.original_data[row] = updated

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _save_modified_rows_for_ids(
        self, 
        entity_ids: Set[int], 
        session: Optional[Session] = None
    ) -> None:
        """
        Сохраняет изменения основных полей для указанных ID (статус 'own' или 'both').

        *Алгоритм для каждого ID:**
            1. Пропускает строки, помеченные на удаление (__deleted__).
            2. Находит DTO в модели, вызывает `service.update()`.
            3. Обновляет модель и словарь `original_data` через `_source_model_update_row`.
            4. Вызывает `clear_entity_drafts(entity_id)`, который:
               - удаляет прямые черновики (основные поля) сущности,
               - пересчитывает статус (с учётом дочерних черновиков),
               - при необходимости уменьшает счётчик родителя.

        **Примечание:** 
            Этот метод не удаляет черновики дочерних компонентов – они
            обрабатываются отдельно в `_save_child_components_for_parent`.

        Args:
            entity_ids: Множество ID сущностей, которые нужно обновить в БД.
            session: Сессия SQLAlchemy (опционально, для работы в одной транзакции).

        Returns:
            None
        """

        self.logger.debug(
            f"_save_modified_rows_for_ids: "
            f"{len(entity_ids)} ids, "
            f"session is None = {session is None}"
        )

        for entity_id in entity_ids:
            # Пропускаем строки, помеченные на удаление
            if self._draft_registry.has(f"__deleted__:{self._entity_type}:{entity_id}"):
                self.logger.debug(f"Строка {entity_id} помечена на удаление – пропуск сохранения")
                
                continue

            row = self._find_row_by_id(entity_id)
            if row < 0:
                continue

            dto = self.source_model.get_item_at_row(row)
            if dto is None:
                continue

            # Переносим файлы из временной папки в основное хранилище
            dto, copied_files, old_files  = self._move_files_from_temp_to_storage(entity_id, dto)

            # # Проверяем, не осталось ли файлов во временной папке (признак ошибки переноса)
            # temp_dir = self._get_temp_dir(entity_id)
            # if temp_dir and os.path.exists(temp_dir) and os.listdir(temp_dir):
            #     error_msg = f"Не удалось перенести файлы из временной папки {temp_dir}. Сохранение отменено."
            #     self.logger.error(error_msg)
            #     raise RuntimeError(error_msg)

            # --------------------------------------------------------------
            # Сохраняем обновлённый DTO в БД
            # --------------------------------------------------------------
            temp_err = False
            try:
                updated = self.service.update(
                    dto, 
                    session=session
                )
                # self.source_model.update_row(row, updated)
                # self.original_data[row] = updated

                self._source_model_update_row(row, updated)


                # Обновляем selected_dto, если эта строка была выбрана
                # if self.selected_dto and self.selected_dto.id == entity_id:
                #     self.selected_dto = updated
                self._clear_selected_dto(entity_id, updated)

            except Exception as e:
                # При ошибке удаляем уже скопированные файлы (они в основном хранилище)
                for files in [
                    old_files,
                    copied_files,
                ]:
                    for file in files:
                         delete_file_safely(
                             file,
                             logger=self.logger
                         )
                raise

            for files in [
                copied_files,  # Удаляем временные файлы (скопированные из временной папки) отложенно
                old_files,  # Удаляем старые файлы (заменяемые) отложенно
            ]:
                self._del_file(files, session=session)




            # уточнение:
            # так как в дальнейшем может потребоваться делать общий буфер на все страници - чистим сейчас
            # Что делает clear_entity_drafts (DraftTreeMixin):
            #   Удаляет прямые черновики по префиксу entity_type:entity_id:.
            #   Получает текущий счётчик детей (child_count).
            #   Вычисляет новый статус: _status_from_flags(False, child_count > 0).
            #   Если старый статус был не None, а новый стал None, вызывает _update_parent_child_counter(entity_id, -1) – уменьшает счётчик родителя на 1.
            #   Обновляет статус в реестре и кэше.
            #   Если статус изменился, вызывает _propagate_status_up(entity_id) (пересчитывает статус родителей).
            # (Очищаем черновики сущности – они больше не нужны, данные сохранены в БД)
            self.clear_entity_drafts(entity_id)  # Удаляет черновики для данной сущности

            # ВНИМАНИЕ: Счётчик родителя уже был уменьшен при вызове clear_entity_drafts (он вызывает discard_entity_subtree, который уменьшает счётчик). Поэтому clear_own_change НЕ должна изменять счётчик – она только сбрасывает статус 'own' и пересчитывает статус родителя.

            # # Снимаем флаг собственных изменений (обновляем статус)
            # #   Вычисляет новый статус: _status_from_flags(has_own_change=False, child_count > 0).
            # #   Если статус изменился, обновляет реестр и кэш, испускает сигналы, вызывает _propagate_status_up
            # self.clear_own_change(entity_id)  # снимаем флаг 'own'

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def reload_with_filters(self, filters_tree):
        """Перезагружает данные с новыми фильтрами и обновляет состояние кнопки сохранения."""
    
        super().reload_with_filters(filters_tree)   # вызывает _load_first_page() в миксине
        self._update_save_button_state() # Обновляем состояние кнопки сохранения

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _save_child_components_for_parent(
        self, 
        parent_id: int,
        session: Optional[Session] = None
    ) -> None:
        """
        Применяет черновики всех дочерних компонентов (например, фото) для указанного родителя.

        **Требования к дочерним компонентам:**
            - Должны реализовывать `IEditableComponent`.
            - В методе `apply` **обязаны** после успешного сохранения удалить свой черновик из реестра (например, через `registry.apply_and_clear`). Если этого не сделать, черновик останется и может быть повторно применён при следующем сохранении.
            - **Не должны вызывать `mark_child_change` внутри `apply`** – весь учёт счётчиков выполняет `PaginatedListPage`.

        **Логика работы с счётчиком родителя:**
            - При создании черновика дочерний компонент вызывает callback `notifier(parent_id, +1)`, что приводит к увеличению счётчика родителей.
            - При успешном применении черновика счётчик должен быть уменьшен на -1.
            - Если дочерний компонент по ошибке не удалил черновик, метод принудительно удаляет его и всё равно уменьшает счётчик, записывая предупреждение в лог.

        ЕЩЁ РАЗ!: Дочерний компонент **НЕ ДОЛЖЕН вызывать mark_child_change внутри apply** – это приведёт к двойному учёту. Весь учёт счётчиков выполняет только PaginatedListPage

        **Примечание:** В текущей реализации PaginatedListPage этот метод не используется
                для обработки фото, так как фото являются обычными полями DTO, а не дочерними
                компонентами. Для добавления дочерних компонентов (например, PhotoUploaderWidget)
                необходимо переопределить `_setup_draft_system` в наследнике и вызывать
                `add_draft_child`.

        Args:
            parent_id: ID родительской сущности (должен быть >= 0, то есть существовать в БД).
            session: Сессия SQLAlchemy (опционально, для работы в одной транзакции).
        """

        if parent_id is None or parent_id < 0:
            return

        # Проверка: не удалён ли родитель?
        if self._draft_registry.has(f"__deleted__:{self._entity_type}:{parent_id}"):
            self.logger.warning(f"Попытка сохранить дочерние черновики для удалённого родителя {parent_id}")
            return

        for child in self._children_components:
            if hasattr(child, 'apply'):
                # Сохраняем ключ черновика до вызова (для проверки)
                key = child.get_draft_key() if hasattr(child, 'get_draft_key') else None
                if (key is not None) and self._draft_registry.has(key):
                    try:
                        child.apply(
                            self._draft_registry,
                            parent_id=parent_id,
                            service=self._get_child_service(),
                            session=session
                        )

                    except Exception as e:
                        self.logger.exception(
                            f"Ошибка при применении черновика дочернего компонента {child.__class__.__name__} "
                            f"для родителя {parent_id}: {e}"
                        )
                        raise  # прерываем сохранение, так как данные в неконсистентном состоянии

                    # Проверяем, удалён ли черновик
                    if not self._draft_registry.has(key):  # черновик удалён. причина: Если child.apply не удалит черновик (например, из-за ошибки или если он не использует apply_and_clear), то вы всё равно уменьшите счётчик родителя. Это приведёт к дисбалансу
                        # Нормальный случай: черновик удалён дочерним компонентом:
                        # Черновик был успешно удалён – значит, изменения применены
                        # Уменьшаем счётчик родителя (который был увеличен при создании потомка)
                        # тоесть:
                        # Уменьшаем счётчик родителя независимо от того, удалил ли компонент черновик.
                        # Если черновик не был удалён – мы делаем это принудительно, затем всё равно уменьшаем счётчик
                        self.mark_child_change(parent_id, -1) # Счётчик родителя увеличивается ровно один раз при создании черновика (в _add_inline_row для дочерней строки или при добавлении черновика через add_draft_child). Поэтому после применения он должен быть уменьшен ровно один раз. Уменьшение должно происходить независимо от способа удаления черновика

                    else: # Проверяем, удалён ли черновик (если компонент предоставил ключ)
                        # self.logger.warning(
                        #     f"Дочерний компонент {child.__class__.__name__} не удалил черновик после apply. "
                        #     f"Ключ {key} остался в реестре. Убедитесь, что метод apply вызывает registry.apply_and_clear "
                        #     f"или вручную удаляет черновик."
                        # )

                        # Черновик не был удалён – нарушение контракта.
                        # Принудительно удаляем черновик и уменьшаем счётчик, чтобы восстановить консистентность.
                        self.logger.error(
                            f"Дочерний компонент {child.__class__.__name__} не удалил черновик после apply. "
                            f"Ключ {key} остался в реестре. Выполнено принудительное удаление черновика "
                            f"и уменьшение счётчика родителя {parent_id}."
                        )
                        self._draft_registry.discard(key)
                        self.mark_child_change(parent_id, -1)

                    # # После успешного применения (или принудительного удаления) синхронизируем дочерние виджеты, чтобы UI отобразил актуальное состояние (например, удалённые фото исчезли).
                    # self._load_drafts_for_children()  # УДАЛЕНО – компоненты сами обновятся через подписку    # Дочерний компонент сам перезагрузится через сигнал draft_changed (так как он подписан на реестр)
                    # После успешного применения черновика (и его удаления из реестра)
                    # дочерний компонент получит сигнал draft_changed (так как он подписан)
                    # и сам вызовет load_from_registry для обновления UI.
                    # Явный вызов _load_drafts_for_children() не требуется.
                    # Обратите внимание: мы не обновляем статус родителя вручную, так как mark_child_change уже вызвал пересчёт статуса.

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_parents_with_child_drafts(self) -> Set[int]:
        """
        Возвращает множество ID родительских сущностей, у которых есть дочерние черновики.
        Используется для применения дочерних черновиков при сохранении всех изменений.

        **Почему статус, а не счётчик?**
            Статус родителя ('child' или 'both') надёжно отражает наличие активных дочерних черновиков,
            так как счётчики детей синхронизируются через callback. Использование статуса вместо прямого
            чтения счётчика делает код более устойчивым к возможным ошибкам синхронизации
            (статус пересчитывается при любом изменении дочернего компонента).
        """

        parent_ids = set()
        for key in self._draft_registry.get_keys_by_prefix(f"__status__:{self._entity_type}:"):
            parts = key.split(':')
            if len(parts) >= 3:
                entity_id = int(parts[2])
                status = self._draft_registry.get_entity_status(self._entity_type, entity_id)
                if status in ('child', 'both'):  # есть изменения у потомков
                    parent_ids.add(entity_id)

        return parent_ids

    # def _save_child_components(self):
    #     """
    #     Сохраняет черновики всех дочерних компонентов (например, фото).
    #     Вызывается перед сохранением строк таблицы, чтобы дочерние сущности
    #     успели записаться в БД и получить ID родителя.
    #
    #     Примечание: Если parent_id равен None (например, для новой строки, ещё не сохранённой),
    #     дочерние компоненты не смогут сохраниться – это нормально, так как им нужен реальный ID.
    #     """
    #     # Сохраняем дочерние черновики (например, фото)
    #
    #     parent_id = self.selected_dto.id if self.selected_dto else None
    #     # Если parent_id is None, дочерние черновики не могут быть сохранены,
    #     # так как им не с чем связаться – пропускаем.
    #     if parent_id is None or parent_id < 0:
    #         self.logger.warning(
    #             f"_save_child_components: родительский ID {parent_id} невалиден, "
    #             "дочерние черновики не будут сохранены"
    #         )
    #         return
    #
    #     for child in self._children_components:
    #         if hasattr(child, 'apply'):
    #             child.apply(
    #                 self._draft_registry,
    #                 parent_id=parent_id,
    #                 service=self._get_child_service()
    #             )
    #
    #     # self._update_save_button_state() #  тут неадо, так как работаем только с дочерними, а не с нынешней

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _clear_entity_registry(self):
        """
        Очищает реестр от всех черновиков, статусов, счётчиков, удалённых и новых записей
        для текущего типа сущности (self._entity_type).

        ВНИМАНИЕ: Этот метод удаляет черновики только для текущего типа сущности
        (self._entity_type). Если в будущем реестр станет глобальным (один на всё приложение),
        очистка будет ограничена префиксами данного типа, что безопасно.
        """

        # Очищаем реестр от служебных ключей (черновики, статусы, счётчики, удалённые, новые)

        # уточнение:
        # метод удаляет все черновики из реестра, включая те, которые могут быть нужны для других страниц (если реестр общий). Поскольку у вас реестр создаётся для каждой страницы отдельно, это не страшно. Но если в будущем вы решите сделать реестр глобальным, лучше удалить этот метод или переопределить его в наследниках. Пока можно оставить.
        # Если в будущем нудно делать реестр глобальным (один на всё приложение), тогда очистку нужно будет делать выборочно (по префиксу типа сущности). Но пока оставляйте как есть
        
        self._clear_page_drafts_prefixes()
        
        # Очищаем кэш статусов, чтобы при следующей загрузке страницы не осталось старых данных
        self._status_cache.clear()

    # ------------------------------------------------------------------
    # Вспомогательные методы для цвета строки
    # ------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_row_color(self, dto: Any) -> QColor:
        """Определяет цвет строки на основе статуса сущности."""

        entity_id = dto.id
        
        if entity_id is None or entity_id < 0:
            # Новая строка – зелёный, если есть черновик __new__
            if self._draft_registry.has(f"__new__:{self._entity_type}:{entity_id}"):
                return QColor(200, 255, 200)
            
            return QColor(255, 255, 255)
        
        # Существующая строка
        if self._draft_registry.has(f"__deleted__:{self._entity_type}:{entity_id}"):
            return QColor(255, 200, 200)  # красный
        
        status = self._get_cached_status(entity_id)
        if status in ('own', 'child', 'both'):

            return QColor(255, 255, 180)  # жёлтый
        
        return QColor(255, 255, 255)      # белый

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _source_model_set_row_color(self, row: int, color: QColor):
        dto = self.source_model.get_item_at_row(row)
        if dto:
            self.source_model.set_row_color(dto.id, color)

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _update_row_color(self, row: int):
        """
        Обновляет цвет строки в таблице на основе статуса сущности.

        **Цветовая схема:**
            - Зелёный (`#C8FFC8`): новая строка (временный ID, есть __new__).
            - Красный (`#FFC8C8`): строка помечена на удаление (__deleted__).
            - Жёлтый (`#FFFFB4`): статус 'own', 'child' или 'both' (есть изменения).
            - Белый (`#FFFFFF`): без изменений.

        Args:
            row: Индекс строки в модели.
        """

        dto = self.source_model.get_item_at_row(row)
        if dto is None:
            return
        
        color = self._get_row_color(dto) # этот метод уже использует реестр
        # self.source_model.set_row_color(row, color)
        self._source_model_set_row_color(row, color)

    # ------------------------------------------------------------------
    # Методы для работы с выделением и кнопками
    # ------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _has_unsaved_changes(self) -> bool:
        """Проверяет наличие любых несохранённых изменений в реестре."""
        status_prefix = f"__status__:{self._entity_type}:"
        for key in self._draft_registry.get_keys_by_prefix(status_prefix):
            status_data = self._draft_registry.get(key)
            if status_data and status_data.get('status') is not None:
                self.logger.debug(f"_has_unsaved_changes: найден статус {status_data.get('status')} по ключу {key}")
                return True

        # Есть ли черновики для текущего типа?
        if self._draft_registry.has_prefix(f"{self._entity_type}:"):
            self.logger.debug(f"_has_unsaved_changes: есть черновики с префиксом {self._entity_type}:")
            return True
        
        # Есть ли удалённые?
        if self._draft_registry.has_prefix(f"__deleted__:{self._entity_type}:"):
            self.logger.debug("_has_unsaved_changes: есть удалённые записи")
            return True
        
        # Есть ли новые?
        if self._draft_registry.has_prefix(f"__new__:{self._entity_type}:"):
            self.logger.debug("_has_unsaved_changes: есть новые записи")
            return True
        
        return False

        # # Есть ли черновики для текущего типа?
        # prefix = f"{self._entity_type}:"
        # if any(k.startswith(prefix) for k in self._draft_registry._storage):
        #     return True
        
        # # Есть ли удалённые?
        # if self._draft_registry.has_prefix(f"__deleted__:{self._entity_type}:"):
        #     return True
        
        # # Есть ли новые?
        # if self._draft_registry.has_prefix(f"__new__:{self._entity_type}:"):
        #     return True
        
        # return False

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _update_save_button_state(self):
        """
        Обновляет состояние кнопки сохранения.
        """

        if hasattr(self, 'save_changes_btn') and self.save_changes_btn:
            # self.save_changes_btn.setEnabled(self._has_unsaved_changes())

            has_changes = self._has_unsaved_changes()
            self.logger.debug(f"_update_save_button_state: has_changes={has_changes}")
            self.save_changes_btn.setEnabled(has_changes)

    # ------------------------------------------------------------------
    # Обработка изменения выделения строки
    # ------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_selection_changed_for_draft(self, selected, deselected):
        """
        Обработчик изменения выделения в таблице.
        Обновляет self.selected_dto и перекрашивает новую строку.
        """

        new_dto = self.get_current_selected_dto()
        if new_dto == self.selected_dto:
            return
        
        self.selected_dto = new_dto
        if new_dto:
            row = self._find_row_by_id(new_dto.id)
            if row >= 0:
                self._update_row_color(row)

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _clear_drafts(self):
        """Очищает черновики (заглушка, переопределяется в наследниках)."""
        
        if hasattr(self, '_draft_registry'):
            self._draft_registry.clear()

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_child_service(self, child_name: str = None):
        """Возвращает сервис для дочернего компонента (переопределяется в наследниках)."""

        return None

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_draft_system(self):
        """Создаёт дочерние компоненты, реализующие IEditableComponent."""

        # Пример: фото-виджет (будет создан в AppointmentListPage)
        pass

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def on_leave(self):
        """Сохраняет текущее состояние (фильтры, сортировку, прокрутку)."""
        self._saved_state = {
            'filters': self._current_filters,
            'column_filters': self._column_filters.copy(),
            'global_search_text': self._global_search_text,
            'order_by': self._current_order_by,
            # 'multi_sort_specs': self._current_order_by,  # можно хранить то же, что и order_by # убрал поскольку _current_order_by уже хранит результат мульти-сортировки (строки order_by), отдельное сохранение multi_sort_specs избыточно и приводит к неиспользуемому ключу.
            'scroll_pos': self.table_view.verticalScrollBar().value(),
            'selected_id': self.selected_dto.id if self.selected_dto else None,
        }
        super().on_leave()


        # Очищаем кэш миниатюр, чтобы не накапливать память при переключении страниц
        ImageThumbnailDelegate.clear_cache()

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _restore_scroll_and_selection(self):
        """Восстанавливает позицию прокрутки и выделенную строку."""
        scroll_pos = self._saved_state.get('scroll_pos', 0)
        self.table_view.verticalScrollBar().setValue(scroll_pos)

        selected_id = self._saved_state.get('selected_id')
        if selected_id is not None:
            self.select_by_id(selected_id)

        # Обновляем ключ черновика для выбранной строки
        self._update_draft_key_for_selected() # Без этого дочерние виджеты не будут обновляться после возврата

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def has_active_fuzzy_filter(self) -> bool:
        """Возвращает True, если в текущих фильтрах есть оператор 'fuzzy'."""
        return self._has_fuzzy_filter()

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def on_enter(self, extra_data=None):
        """
        Вызывается при переходе на страницу.

        **Что делает:**
            1. Сохраняет контекстные параметры (все ключи `extra_data`, кроме служебных)
            в `self._context_params` для использования при добавлении новых строк.
            2. Если передан флаг `reset_state=True`, сбрасывает сохранённое состояние фильтров
            и сортировки.
            3. Если сохранённые фильтры (`_saved_state['filters']`) не `None`,
            восстанавливает их и перезагружает данные.
            4. Иначе сбрасывает фильтры и загружает первую страницу без фильтрации.
            5. Через 100 мс восстанавливает прокрутку и выделение строки.

        Args:
            extra_data (dict, optional): Может содержать:
                - 'select_id' (int): ID строки для выделения после загрузки.
                - 'return_to_page' (str): Страница для возврата (используется в дочерних окнах).
                - 'return_field' (str): Поле для установки значения при возврате.
                - 'reset_state' (bool): Сбросить сохранённые фильтры/сортировку.
                - Любые другие ключи сохраняются в `self._context_params`.

        Returns:
            None
        """

        # Если передан специальный флаг "reset_state", сбрасываем сохранённое состояние
        reset = extra_data.get('reset_state', False) if extra_data else False

        self._context_params = {}
        if extra_data:
            for key, value in extra_data.items():
                if key not in ('select_id', 'return_to_page', 'return_field', 'reset_state'):
                    self._context_params[key] = value

        if reset:            
            self._saved_state = {  # значения по умолчанию
                'filters': None,
                'column_filters': None,
                'global_search_text': '',
                'order_by': None,
                # 'multi_sort_specs': None, # убрал поскольку _current_order_by уже хранит результат мульти-сортировки (строки order_by), отдельное сохранение multi_sort_specs избыточно и приводит к неиспользуемому ключу.
                'scroll_pos': 0,
                'selected_id': None,
            }


        # Восстанавливаем фильтры и сортировку из сохранённого состояния
        saved_filters = self._saved_state.get('filters')
        if not reset and (saved_filters is not None):

            self._current_filters = saved_filters

            self._column_filters = self._saved_state.get('column_filters', {}).copy()
            self._global_search_text = self._saved_state.get('global_search_text', "")
            self._current_order_by = self._saved_state.get('order_by')

            # Обновляем панель фильтров (чипы)
            self._refresh_filter_bar()

            # Вызываем super().on_enter перед загрузкой данных, 
            # чтобы BasePage мог выполнить свою логику (если появится в будущем)
            super().on_enter(extra_data)  # вызовет загрузку без фильтров

            # Перезагружаем данные с сохранёнными фильтрами/сортировкой
            self.reload_with_filters(self._current_filters)
        else:
            # Нет сохранённых фильтров – сбрасываем всё
            self._current_filters = None
            self._current_order_by = None
            self._column_filters = {}
            self._global_search_text = ""
            self._refresh_filter_bar()
            super().on_enter(extra_data)
            self.reload_with_filters(None)

        # После загрузки данных восстанавливаем прокрутку и выделение
        QTimer.singleShot(100, self._restore_scroll_and_selection)

    # def on_enter(self, extra_data=None):   
        # """При входе на страницу обновляет ключ черновика для текущей строки."""

        # super().on_enter(extra_data)
        # if self.selected_dto:
        #     self._update_draft_key_for_selected()

    # def _save_all_changes_impl(self) -> bool:
    #     # 1. Сохраняем дочерние черновики (фото и т.д.)
    #     # for child in self._children_components:
    #     #     if hasattr(child, 'apply'):
    #     #         child.apply(
    #     #             self._draft_registry, 
    #     #             parent_id=self.get_current_selected_dto().id, 
    #     #             service=self._get_child_service()
    #     #         )
    #     # self._save_changes()
    #     self._save_child_drafts()
        
    #     # 2. Сохраняем строки таблицы (родительский метод)
    #     return super()._save_all_changes_impl()

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _update_draft_key_for_selected(self):
        """
        Обновляет ключ черновика текущего компонента на основе ID выбранной строки.

        **Что делает:**
            1. Формирует новый ключ вида "{entity_type}:{entity_id}:".
            2. Отписывается от старого ключа (если был).
            3. Устанавливает новый ключ и настраивает дерево черновиков.
            4. Уведомляет всех дочерних компонентов о смене `parent_id` через
            вызов `update_parent_id(parent_id)`, чтобы они могли переподписаться
            на новые ключи (например, "appointment:{new_id}:photos").

        **Почему не вызывается `_load_drafts_for_children()`:**
            При автоматической подписке дочерних компонентов (через `subscribe_to_registry`)
            они самостоятельно получат сигнал `draft_changed` и перезагрузят UI.
            Явный вызов `_load_drafts_for_children()` является устаревшим и должен
            быть удалён при полном переходе на автоматическую подписку.
        """

        if not self.selected_dto:
            return
        
        new_key = f"{self._entity_type}:{self.selected_dto.id}:"
        old_key = self._draft_component_id

        if new_key != old_key:
            if old_key is not None:
                self._draft_registry.unsubscribe(
                    old_key,
                    self._on_registry_changed
                )

            self._draft_component_id = new_key
            self.setup_draft_tree(self._draft_registry, new_key)

            # Уведомляем дочерние компоненты об изменении parent_id
            for child in self._children_components:
                if hasattr(child, 'update_parent_id'):
                    child.update_parent_id(self.selected_dto.id)
                # Если у компонента есть метод подписки, можно вызвать его
                elif hasattr(child, 'subscribe_to_registry'):
                    child.subscribe_to_registry(self._draft_registry)

            # # Перезагружаем данные из реестра в дочерние виджеты
            # self._load_drafts_for_children() ## УДАЛЕНО – компоненты сами обновятся через подписку    # Дочерний компонент сам перезагрузится через сигнал draft_changed (так как он подписан на реестр)

            # Если автоматическая подписка не реализована, здесь требуется вызов
            # self._load_drafts_for_children(). Он закомментирован, так как предполагается,
            # что все дочерние компоненты уже используют subscribe_to_registry.
            # self._load_drafts_for_children()

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _load_drafts_for_children(self):
        """
        Загружает черновики в дочерние компоненты.
        Вызывается при смене выбранной строки (после обновления ключа) и после отмены изменений родителя,
        чтобы синхронизировать UI дочерних виджетов (например, фото) с актуальным состоянием реестра.

        **Примечание:** 
            Метод `_load_drafts_for_children()` устарел и не используется.
            Вместо него дочерние компоненты автоматически синхронизируются через подписку на реестр
            (см. `EditableComponentMixin.subscribe_to_registry`). В будущих версиях этот метод будет удалён.
        """

        for child in self._children_components:
            if hasattr(child, 'load_from_registry'):
                child.load_from_registry(self._draft_registry)

    # def _on_row_modified(self, row: int):
    #     """Обработчик изменения строки – теперь также проверяем дочерние черновики."""
    #     super()._on_row_modified(row)
    #     # Если изменения есть в дочерних – помечаем строку как изменённую
    #     if self._draft_modified:
    #         self._add_to_modified(self.selected_dto.id)

    # def _update_row_color(self, row: int):
    #     """Обновляет цвет строки с учётом дочерних черновиков."""

    #     dto = self.source_model.get_item_at_row(row)
    #     if dto is None:
    #         return
        
    #     if dto.id is None or dto.id < 0:
    #         color = QColor(200, 255, 200) if row in self.new_rows else QColor(255, 255, 255)

    #     else:
    #         if dto.id in self.deleted_ids:
    #             color = QColor(255, 200, 200)

    #         elif dto.id in self.modified_ids or self._draft_modified:
    #             color = QColor(255, 255, 180)

    #         else:
    #             color = QColor(255, 255, 255)

    #     self.source_model.set_row_color(row, color)

    # # def _save_changes(self, if_question: bool = True) -> bool:
    # # def _save_changes(self, if_question: bool = True):
    # def _save_child_drafts(self, if_question: bool = True):
    #     """Сохраняет изменения: сначала дочерние поддеревья, затем основные поля."""
    #     # Сохраняем дочерние черновики
    #     for child in self._children_components:
    #         if hasattr(child, 'apply'):
    #             child.apply(
    #                 self._draft_registry, 
    #                 parent_id=self.selected_dto.id, 
    #                 service=self._get_child_service()
    #             )

    #     # # Затем основные поля
    #     # return super()._save_changes(if_question) # непонятно нужно ли...

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_real_type(self, annotation):




        # from typing import get_origin, get_args, Union
        origin = get_origin(annotation)
        if origin is Union:
            args = get_args(annotation)
            # non_none = [arg for arg in args if arg is not type(None)]
            # if non_none:
            #     return non_none[0]
            
            for arg in args:
                if arg is not type(None):
                    return arg
        return annotation

    def _reapply_delegates(self):
        """
        Переустанавливает все делегаты для столбцов таблицы.

        **Назначение:**
            Вызывается при изменении видимости столбцов (например, после включения/выключения
            чекбокс-столбца), а также при инициализации страницы. Поскольку делегаты привязаны
            к видимым индексам столбцов, а не к системным именам, необходимо переустанавливать
            их каждый раз, когда меняется набор видимых столбцов или их порядок.

        **Алгоритм:**
            Просто вызывает `self._setup_delegates()`, который заново проходит по всем видимым
            столбцам, получает из `TableColumn` сохранённые `delegate_class` и `delegate_args`
            и устанавливает делегаты для соответствующих видимых индексов.

        **Параметры:**
            None

        **Возвращает:**
            None

        **Когда вызывается:**
            - В `_update_ui_for_edit_mode` после изменения видимости чекбокс-столбца.
            - В `__init__` после создания модели (неявно через `setup_ui`).
            - При необходимости в других местах, где меняется состав столбцов
            (например, после изменения настроек видимости столбцов пользователем).

        **Пример:**
            >>> # После включения режима редактирования
            >>> self.source_model.set_checkbox_column_visible(True)
            >>> self._reapply_delegates()  # чекбокс-столбец появился, индексы сдвинулись – делегаты переустанавливаются

        **Примечания:**
            - Метод не удаляет старые делегаты явно, `setItemDelegateForColumn` заменяет их.
            - Для `TextPopupDelegate` дополнительно в `_update_ui_for_edit_mode` вызывается
            `set_readonly`, чтобы синхронизировать режим редактирования.
        """

        self._setup_delegates()

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _build_columns(self):
        """
        Создаёт список объектов TableColumn на основе field_configs и dto_class.

        **Алгоритм:**
            1. Проходит по field_configs.
            2. Пропускает поля из exclude_columns и скрытые (hidden=True).
            3. Создаёт TableColumn для каждого поля, заполняя метаданные.
            4. Сортирует столбцы по атрибуту order.

        Результат сохраняется в self.columns.
        """

        # from interfaces.gui.gui_window.widgets.table_column import TableColumn
        self.columns = []
        for field_name, config in self.field_configs.items():
            if field_name in self.exclude_columns:
                continue

            if config.get('hidden', False):
                continue
            
            # Получаем делегат для этого поля
            delegate_class, delegate_args = self._get_delegate_for_field(field_name, config)

            col = TableColumn(
                system_name=field_name,
                title=config.get('title', field_name.replace('_', ' ').title()),
                field_name=field_name,
                data_type=self._get_real_type(
                    self.dto_class.model_fields[field_name].annotation
                ),
                editable=config.get('editable', False),
                order=config.get('order', 0),
                choices=config.get('choices'),
                autocomplete=config.get('autocomplete', False),
                input_mask=config.get('input_mask'),
                delegate_class=delegate_class,
                delegate_args=delegate_args,
            )
            self.columns.append(col)
        self.columns.sort(key=lambda c: c.order)

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _create_model(self):
        """
        Создаёт экземпляр PaginatedTableModel, устанавливает его в table_view
        и подключает сигнал row_modified к обработчику `_on_row_modified_from_model`.
        """

        # from interfaces.gui.gui_window.widgets.paginated_table_model import PaginatedTableModel
        self.source_model = PaginatedTableModel(self.columns, parent=self)
        self.table_view.setModel(self.source_model)
        
        # self.source_model.row_modified.connect(self._on_row_modified)
        self.source_model.row_modified.connect(self._on_row_modified_from_model)

        self.source_model.layoutChanged.connect(self._on_model_layout_changed)

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _create_table(self):
        """Создаёт таблицу, если она ещё не создана."""

        self.logger.debug(
           f"hasattr(self, 'table_view') = {hasattr(self, 'table_view')} "
           f"hasattr(self, 'table_view') and self.table_view is not None = {hasattr(self, 'table_view') and self.table_view is not None} "
        )

        if hasattr(self, 'table_view') and self.table_view is not None:
            return
        
        super()._create_table()


    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_delegate_for_field(
        self, 
        field_name: str, 
        config: Dict[str, Any]
    ) -> Tuple[Optional[Type], Dict[str, Any]]:
        """
        Определяет класс делегата и его аргументы для поля.
        Возвращает (delegate_class, delegate_args).
        """

        # from interfaces.gui.gui_window.widgets.delegate.type_delegate import (
        #     CompleterStringDelegate, DatePickerDelegate, TimePickerDelegate,
        #     TextPopupDelegate, BoolDelegate, ComboBoxDelegate, StringDelegate
        # )
        # import datetime

        # 1) Выпадающий список
        choices = config.get('choices')
        if choices:
            return ComboBoxDelegate, {'choices': choices}

        # 2) Многострочный текст
        if config.get('widget_type') == 'textarea':
            return TextPopupDelegate, {'readonly': not self.edit_mode}

        # 3) Автодополнение для строк
        real_type = self._get_real_type(self.dto_class.model_fields[field_name].annotation)
        if real_type == str and config.get('autocomplete', False):
            return CompleterStringDelegate, {'column': None}  # column будет передан при установке

        # 4) Дата
        if real_type == datetime.date:
            return DatePickerDelegate, {'config': config}

        # 5) Время
        if real_type == datetime.time:
            return TimePickerDelegate, {'config': config}

        # 6) Булево
        if real_type == bool:
            return BoolDelegate, {}

        # 7) Строка (обычная или с маской)
        if real_type == str:
            # Для строк с маской используем StringDelegate, без маски – тоже StringDelegate
            return StringDelegate, {}

        # 8) Отображение миниатюры изображения
        if config.get('widget_type') == 'image_thumbnail':
            # from interfaces.gui.gui_window.widgets.delegate.image_delegate import ImageThumbnailDelegate
            # from app.config.config_manager.manager import AppConfigManager

            # # Путь к хранилищу фото нужно получить из конфигурации
            storage_path = AppConfigManager.get_instance().get(
                'PHOTOS_STORAGE_PATH', 
                os.path.join('.', 'photos')
            )

            args = {
                'page': self,
                'storage_path': storage_path,
                'target_size': QSize(80, 80),
                'allowed_extensions': self._get_allowed_extensions_for_photo(field_name),
                'description_field': config.get('description_field'),
            }

            return ImageThumbnailDelegate, args

        # 9) Остальные типы – нет делегата (стандартный)
        return None, {}

    # @AppLogger.get_instance(
    #     name='PaginatedListPage',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # def _process_photo_fields_for_new_row(self, dto: Any, new_id: int, session: Session = None) -> Any:
    #     """
    #     Для новой строки (созданной из временного ID) обрабатывает поля с фото:
    #     - если путь абсолютный и родитель теперь имеет реальный ID,
    #     копирует файл в хранилище и обновляет DTO.

    #     (Метод устарел)
    #     """
    #     # if self._photo_service is None:
    #     #     self._photo_service = get_photo_service()

    #     storage_path = self._get_photo_storage_path()

    #     for field_name, config in self.field_configs.items():
    #         if config.get('widget_type') != 'image_thumbnail':
    #             continue

    #         abs_path = getattr(dto, field_name, None)
    #         if not abs_path or not isinstance(abs_path, str):
    #             continue

    #         # Если путь уже относительный – пропускаем
    #         if not os.path.isabs(abs_path):
    #             continue

    #         if not os.path.exists(abs_path):
    #             self.logger.warning(f"Файл {abs_path} не существует, пропускаем")
    #             continue

    #         # Копируем файл в хранилище
    #         parent_folder = os.path.join(storage_path, f"app_{new_id}")
    #         os.makedirs(parent_folder, exist_ok=True)

    #         # import uuid
    #         ext = os.path.splitext(abs_path)[1]
    #         unique_name = f"{uuid.uuid4().hex}{ext}"
    #         dest_path = os.path.join(parent_folder, unique_name)

    #         # import shutil
    #         shutil.copy2(abs_path, dest_path)

    #         rel_path = os.path.relpath(dest_path, storage_path)
    #         setattr(dto, field_name, rel_path)

    #     return dto

    @AppLogger.get_instance(
        name='PaginatedListPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_photo_storage_path(self) -> str:
        """Возвращает путь к хранилищу фотографий из конфигурации."""
        config = AppConfigManager.get_instance()
        return config.get('PHOTOS_STORAGE_PATH', os.path.join('.', 'photos'))

    @AppLogger.get_instance(
        name='PaginatedListPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_delegates(self) -> None:
        """
        Устанавливает делегаты для столбцов таблицы на основе сохранённых в TableColumn.

        **Принцип работы:**
            - В `_build_columns` для каждого столбца (`TableColumn`) определяется
                класс делегата (`delegate_class`) и его аргументы (`delegate_args`)
                с учётом типа поля, конфигурации (`field_configs`) и виджетов.
            - Данный метод проходит по всем **видимым** столбцам модели,
                получает объект `TableColumn` и, если у него задан `delegate_class`,
                создаёт экземпляр делегата с предварительно сохранёнными аргументами
                и устанавливает его для соответствующего столбца в `table_view`.
            - Если `delegate_class` равен `None`, для столбца используется
                стандартный делегат (редактирование по умолчанию).

        **Поддерживаемые делегаты и их настройка:**
            - `ComboBoxDelegate` – для полей с `choices`.
            - `TextPopupDelegate` – для многострочного текста (`widget_type='textarea'`).
            - `CompleterStringDelegate` – для строк с `autocomplete=True`.
            - `DatePickerDelegate` – для полей типа `datetime.date`.
            - `TimePickerDelegate` – для полей типа `datetime.time`.
            - `BoolDelegate` – для полей типа `bool`.
            - `StringDelegate` – для обычных строк (с возможной маской ввода).
            - `ImageThumbnailDelegate` – для полей с `widget_type='image_thumbnail'` (фото).


        **Особые случаи (дополнительная настройка при создании делегата):**
            - Для `CompleterStringDelegate` в аргументы добавляются `column` (видимый индекс)
                и `get_unique_values_func` (функция получения уникальных значений для автодополнения).
            - Для `StringDelegate`, если у столбца задан `input_mask`, создаётся
                словарь `column_masks` (маска для данного столбца), который передаётся
                в делегат. Это позволяет применять маску ввода (например, для телефона).
            - Для `ImageThumbnailDelegate` передаются `storage_path` (путь к хранилищу),
                `target_size` (размер миниатюры), `allowed_extensions` (спок разрешённых
                расширений) и `description_field` (имя поля описания, если есть).

        **Переустановка делегатов:**
            - Метод вызывается в `_update_ui_for_edit_mode` после изменения видимости
                чекбокс-столбца, а также при инициализации страницы.
            - Поскольку делегаты привязаны к видимым индексам, а не к системным именам,
                переустановка необходима, чтобы делегаты оказались на правильных местах
                после добавления/удаления системных столбцов (например, чекбокса).

        **Требования к классу-наследнику:**
            - Должен иметь метод `_get_unique_values_for_column(visible_index) -> List[str]`
                (реализован в `FilterMixin`), который возвращает уникальные значения
                для указанного видимого столбца (используется в `CompleterStringDelegate`).

        **Пример использования (внутри класса):**
            >>> # После изменения модели или видимости столбцов
            >>> self._reapply_delegates()   # вызывает _setup_delegates

        **Примечание:**
            - Метод не удаляет существующие делегаты перед установкой новых,
                а просто перезаписывает их. Это корректно, так как `setItemDelegateForColumn`
                заменяет предыдущий делегат.
            - Для отладки в лог выводятся сообщения о создании каждого делегата.
        """

        # self.logger.debug("=== _setup_delegates START ===")

        # Проходим по всем видимым столбцам таблицы
        for visible_idx in range(self.source_model.columnCount()):
            # Получаем объект TableColumn по видимому индексу
            col = self.source_model.get_column_at_visible_index(visible_idx)
            if col is None or col.column_type != ColumnType.DATA:
                continue

            # Если для столбца не задан класс делегата – используем стандартный
            if col.delegate_class is None:
                self.logger.debug(f"  -> стандартный делегат для {col.field_name}")
                continue

            # Копируем аргументы делегата, чтобы не изменять оригинал в TableColumn
            args = col.delegate_args.copy()

            # --- Дополнительная настройка для конкретных типов делегатов ---
            if col.delegate_class.__name__ == 'CompleterStringDelegate':
                # Для автодополнения передаём видимый индекс столбца и функцию получения уникальных значений
                args['column'] = visible_idx
                args['get_unique_values_func'] = self._get_unique_values_for_column

            elif col.delegate_class == StringDelegate and col.input_mask:
                # Для строк с маской создаём словарь column_masks (маска для этого столбца)
                args['column_masks'] = {visible_idx: col.input_mask}

            # Для DatePickerDelegate и TimePickerDelegate аргументы (config) уже переданы из _get_delegate_for_field

            # --- ДЛЯ ФОТО (новый блок) ---
            elif col.delegate_class.__name__ == 'ImageThumbnailDelegate':

                # Получаем путь к хранилищу из конфигурации
                storage_path = self._get_photo_storage_path()
                args['storage_path'] = storage_path

                # target_size может быть передан из field_configs, иначе значение по умолчанию
                if 'target_size' not in args:
                    args['target_size'] = QSize(80, 80)

                # Дополнительные параметры из field_configs
                config = self.field_configs.get(col.field_name, {})
                if 'allowed_extensions' in config:
                    args['allowed_extensions'] = config['allowed_extensions']

                if 'description_field' in config:
                    args['description_field'] = config['description_field']

                args['page'] = self # <-- передаём страницу

                # Устанавливаем режим readonly в зависимости от edit_mode
                # (сам делегат получит этот параметр при создании)
                # Но readonly нужно будет обновлять при смене режима – см. _update_ui_for_edit_mode

                # Создаём экземпляр делегата
                delegate = col.delegate_class(
                    self.table_view, 
                    **args,
                )

                 # set_registry больше не нужен, но оставляем для обратной совместимости (необязательно)
                # # Устанавливаем реестр и тип сущности для поиска временных папок 
                # if hasattr(delegate, 'set_registry'):
                #     delegate.set_registry(self._draft_registry, self._entity_type)

                # Устанавливаем делегат для видимого столбца
                self.table_view.setItemDelegateForColumn(visible_idx, delegate)

                self.logger.debug(
                    f"  -> {col.delegate_class.__name__} для {col.field_name} "
                    f"(видимый индекс {visible_idx})"
                )
                continue

            # Создаём экземпляр делегата
            delegate = col.delegate_class(self.table_view, **args)

            # Устанавливаем делегат для видимого столбца
            self.table_view.setItemDelegateForColumn(visible_idx, delegate)

            self.logger.debug(
                f"  -> {col.delegate_class.__name__} для {col.field_name} "
                f"(видимый индекс {visible_idx})"
            )

        # self.logger.debug("=== _setup_delegates END ===")

    # @AppLogger.get_instance(
    #     name='PaginatedListPage',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    # def _setup_delegates(self) -> None:
    #     """
      
    #     Устанавливает делегаты для столбцов таблицы на основе field_configs и типа данных.
    #     Адаптировано для PaginatedTableModel.

    #     **Порядок выбора делегата:**
    #         1. Если есть choices – ComboBoxDelegate.
    #         2. Если widget_type == 'textarea' – TextPopupDelegate (с автодополнением).
    #         3. Если autocomplete=True и тип str – CompleterStringDelegate.
    #         4. Для datetime.date – DatePickerDelegate.
    #         5. Для datetime.time – TimePickerDelegate.
    #         6. Для bool – BoolDelegate.
    #         7. Для str с маской ввода – StringDelegate с mask.
    #         8. Иначе – StringDelegate.

    #     Примечание: Прокси-модель не используется, поэтому видимый индекс столбца напрямую
    #     соответствует индексу в модели.
    #     """
        
    #     # from interfaces.gui.gui_window.widgets.delegate.type_delegate import (
    #     #     CompleterStringDelegate,
    #     #     DatePickerDelegate,
    #     #     StringDelegate,
    #     #     TextPopupDelegate,
    #     #     TimePickerDelegate,
    #     #     BoolDelegate,
    #     #     ComboBoxDelegate,
    #     # )
    #     # from interfaces.gui.gui_window.widgets.table_column import ColumnType
    #     # import datetime

    #     self.logger.debug("=== _setup_delegates START ===")
    #     type_delegate_map = {
    #         datetime.date: DatePickerDelegate,
    #         datetime.time: TimePickerDelegate,
    #         bool: BoolDelegate,
    #         # str: StringDelegate, обрабатываем отдельно в конце с учётом маски
    #     }

    #     # Проходим по всем видимым столбцам
    #     for visible_idx in range(self.source_model.columnCount()):

    #         self.logger.debug(
    #             f"visible_idx = {visible_idx}"
    #         )
    #         # Находим объект TableColumn по видимому индексу
    #         col = self.source_model.get_column_at_visible_index(visible_idx)

    #         self.logger.debug(
    #             f"col is None = {col is None} "
    #             f"col.column_type != ColumnType.DATA = {col.column_type != ColumnType.DATA}"
    #         )
    #         if col is None or col.column_type != ColumnType.DATA:
    #             continue

    #         field_name = col.field_name
    #         config = self.field_configs.get(field_name, {})
    #         model_col = visible_idx  # в PaginatedTableModel видимый индекс = индекс в представлении

    #         self.logger.debug(
    #             f"Обработка столбца {field_name}: "
    #             f"data_type={col.data_type}, "
    #             f"editable={col.editable}, "
    #             f"widget_type={config.get('widget_type')}, "
    #             f"autocomplete={config.get('autocomplete')} "
    #         )

    #         # 1) Выпадающий список (choices)
    #         choices = config.get('choices')

    #         self.logger.debug(
    #             f"choices is None = {choices is None}"
    #         )
    #         if choices:
    #             delegate = ComboBoxDelegate(self.table_view, choices)
    #             self.table_view.setItemDelegateForColumn(model_col, delegate)
    #             self.logger.debug(f"  -> ComboBoxDelegate для {field_name}")

    #             self.logger.debug(
    #                 f"Установка делегата для столбца {field_name} "
    #                 f"(data_type={col.data_type}) -> {delegate.__class__.__name__}"
    #             )
    #             continue

    #         # 2) Многострочный текст (textarea)
    #         widget_type = config.get('widget_type')
    #         self.logger.debug(
    #             f"widget_type = {widget_type}"
    #         )
    #         if widget_type == 'textarea':
    #             self.logger.debug(f"Создаём TextPopupDelegate для {field_name}, readonly={not self.edit_mode}")
    #             delegate = TextPopupDelegate(
    #                 self.table_view,
    #                 readonly = not self.edit_mode,
    #                 get_completion_list = lambda col=visible_idx: self._get_unique_values_for_column(col)
    #             )
    #             self.table_view.setItemDelegateForColumn(model_col, delegate)
    #             self.logger.debug(f"  -> TextPopupDelegate для {field_name}")

    #             self.logger.debug(
    #                 f"Установка делегата для столбца {field_name} "
    #                 f"(data_type={col.data_type}) -> {delegate.__class__.__name__}"
    #             )
    #             continue

    #         # 3) Автодополнение для строк
    #         self.logger.debug(
    #             f"col.data_type == str = {col.data_type == str} "
    #             f"config.get('autocomplete', False) = {config.get('autocomplete', False)} "
    #         )
    #         if col.data_type == str and config.get('autocomplete', False):
    #             delegate = CompleterStringDelegate(
    #                 self.table_view,
    #                 get_unique_values_func=self._get_unique_values_for_column,
    #                 column=visible_idx
    #             )
    #             self.table_view.setItemDelegateForColumn(model_col, delegate)
    #             self.logger.debug(f"  -> CompleterStringDelegate для {field_name}")

    #             self.logger.debug(
    #                 f"Установка делегата для столбца {field_name} "
    #                 f"(data_type={col.data_type}) -> {delegate.__class__.__name__}"
    #             )
    #             continue

    #         # 4) Стандартные делегаты по типу
    #         delegate_class = type_delegate_map.get(col.data_type)  # может быть проблема с типизацией!

    #         self.logger.debug(
    #             f"delegate_class is None > {delegate_class is None} "
    #         )
    #         if delegate_class:

    #             self.logger.debug(
    #                 f"delegate_class in (DatePickerDelegate, TimePickerDelegate) = {delegate_class in (DatePickerDelegate, TimePickerDelegate)} "
    #             )
    #             if delegate_class in (DatePickerDelegate, TimePickerDelegate):
    #                 delegate = delegate_class(self.table_view, config=config)

    #             else:
    #                 delegate = delegate_class(self.table_view)

    #             self.table_view.setItemDelegateForColumn(model_col, delegate)
    #             self.logger.debug(f"  -> {delegate_class.__name__} для {field_name}")

    #             self.logger.debug(
    #                 f"Установка делегата для столбца {field_name} "
    #                 f"(data_type={col.data_type}) -> {delegate.__class__.__name__}"
    #             )
    #             continue

    #         # 5) Обычные строки с маской ввода

    #         self.logger.debug(
    #             f"col.data_type == str = {col.data_type == str}"
    #         )
    #         if col.data_type == str:
    #             mask = config.get('input_mask')
    #             column_masks = {model_col: mask} if mask else None
    #             delegate = StringDelegate(
    #                 self.table_view, 
    #                 column_masks=column_masks
    #             )
    #             self.table_view.setItemDelegateForColumn(model_col, delegate)
    #             self.logger.debug(f"  -> StringDelegate с маской {mask} для {field_name}")

    #             self.logger.debug(
    #                 f"Установка делегата для столбца {field_name} "
    #                 f"(data_type={col.data_type}) -> {delegate.__class__.__name__}"
    #             )

    #     self.logger.debug("=== _setup_delegates END ===")

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def reload_data(self) -> None:
        """Перезагружает данные текущей страницы с учётом активных фильтров."""

        self.reload_with_filters(self._current_filters)

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _register_new_row_parent_balance(
        self,
        dto: Any,
        temp_id: int
    ) -> Optional[int]:
        """
        Увеличивает счётчик родителя при создании новой строки и создаёт служебный ключ.

        **Когда вызывается:** из `_add_inline_row` сразу после создания DTO.

        **Логика:** определяет родителя через `_get_parent_id_for_new_row(dto)`,
        увеличивает его счётчик (если родитель существует), и если увеличение произошло,
        создаёт ключ `__parent_counter_inc__:{temp_id}` с ID родителя.

        Returns:
            int: ID родителя (может быть None, если родителя нет).
        """

        # Уведомляем родителя о появлении нового потомка (если есть родитель)
        entity_id = self._get_parent_id_for_new_row(dto)
        was_incremented = self._update_parent_counter(entity_id, 1, temp_id)

        # Если родитель существовал (ID > 0) и счётчик был увеличен,
        # сохраняем факт увеличения для последующего уменьшения при сохранении

        self.logger.debug(
            f"was_incremented = {was_incremented} "
            f"entity_id = {entity_id} "
        )
        if was_incremented and (entity_id is not None) and entity_id > 0:
            # Ключ теперь entity_type для изоляции при глобальном реестре
            self._draft_registry.set(
                f"__parent_counter_inc__:{self._entity_type}:{temp_id}",
                {"parent_id": entity_id}
            )
    
        return entity_id

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _add_inline_row(self):
        """
        Добавляет новую пустую строку в конец таблицы (режим редактирования).

        **Алгоритм:**
            1. Создаёт пустой DTO, заполняя поля значениями по умолчанию:
                - строковые поля → пустая строка
                - целочисленные поля → 0
                - дата → сегодняшняя дата
                - остальные → None
            
            2. Если есть контекстные параметры (`self._context_params`), перезаписывает
                соответствующие поля (например, `patient_id` для дочерних сущностей).
            3. Генерирует временный отрицательный ID (self._next_temp_id).
            4. Сохраняет DTO в реестре черновиков по ключу `__new__:{entity_type}:{temp_id}`.
            5. Добавляет строку в модель таблицы (self.source_model.add_row).
            6. Помечает сущность как имеющую собственные изменения (mark_own_change(temp_id)).
            7. Уведомляет родителя (если есть) о появлении нового потомка:
                - вызывает `_register_new_row_parent_balance(dto, temp_id)`
                - этот метод увеличивает счётчик родителя (через `_update_parent_counter(parent_id, +1)`)
                - если родитель существующий и не удалён, создаёт служебный ключ `__parent_counter_inc__:{temp_id}`
            8. Обновляет цвет строки (зелёный) и состояние кнопки «Сохранить».

        **Балансировка счётчиков:**
            - При добавлении новой строки **с существующим родителем** счётчик родителя увеличивается,
            и создаётся служебный ключ, который будет использован при сохранении для уменьшения счётчика.
            - Для новых родителей (временный ID) счётчик не увеличивается и служебный ключ не создаётся.

        **Примечания:**
            - Временный ID генерируется отрицательным и уникальным для текущей сессии редактирования.
            - Метод не вызывает `save_to_registry` – все данные сохраняются напрямую в реестр.
            - Родитель определяется через переопределяемый метод `_get_parent_id_for_new_row(dto)`.
            - Если родитель помечен на удаление, счётчик не увеличивается (и ключ не создаётся).
            - Контекстные параметры из `_context_params` имеют приоритет
                над значениями по умолчанию и позволяют создавать дочерние строки
                (например, новый приём для уже выбранного пациента).
        """

        defaults = {}
        for col in self.columns:

            if col.column_type != ColumnType.DATA:
                continue

            if col.data_type == str:
                defaults[col.field_name] = ""

            elif col.data_type == int:
                defaults[col.field_name] = 0

            elif col.data_type == datetime.date:
                defaults[col.field_name] = datetime.date.today()

            else:
                defaults[col.field_name] = None

        if hasattr(self, '_context_params'):
            for key, value in self._context_params.items():
                if key in defaults:
                    defaults[key] = value

        dto = self.dto_class(**defaults)

        temp_id = self._next_temp_id
        self._next_temp_id -= 1
        dto.id = temp_id

        # # создаём временную папку для этой новой строки (черновик)
        # self._ensure_temp_dir(temp_id) # (папка будет создана при первом добавлении фото)

        # Сохраняем в реестр как новую строку
        self._draft_registry.set(f"__new__:{self._entity_type}:{temp_id}", {"dto": dto})

        # Добавляем в модель
        row = self.source_model.add_row(dto)

        # Помечаем как имеющую собственные изменения (новая строка)
        self.mark_own_change(temp_id)  # устанавливает статус 'own' для временного ID (без уведомления родителя)

        # # Уведомляем родителя о появлении нового потомка (если есть родитель)
        # # parent_id = self._get_parent_id_for_new_row(dto)
        # # if parent_id is not None:
        # #     self.mark_child_change(parent_id, +1)
        #
        # # Увеличиваем счётчик родителя только если родитель существует (ID > 0) и не помечен на удаление
        #
        # # if parent_id is not None and parent_id > 0:
        # #     # Причина:
        # #     # Родитель с временным ID (parent_id < 0) не должен влиять на счётчик, так как он сам ещё не сохранён.
        # #     # Если родитель уже помечен на удаление, то новая строка не должна увеличивать его счётчик, так как родитель всё равно будет удалён. Это предотвращает дисбаланс счётчиков.
        # #
        # #     if not self._draft_registry.has(f"__deleted__:{self._entity_type}:{parent_id}"):
        # #         self.mark_child_change(parent_id, +1)
        # #     else:
        # #         self.logger.debug(
        # #             f"Родитель {parent_id} помечен на удаление, счётчик не увеличен для новой строки {temp_id}")

        # # Уведомляем родителя о появлении нового потомка (если есть родитель)
        # parent_id = self._get_parent_id_for_new_row(dto)
        # self._update_parent_counter(parent_id, 1, temp_id)

        # # # Уведомляем родителя о появлении нового потомка с изменениями
        # # self._update_parent_child_counter(temp_id, +1)

        # Уведомляем родителя о появлении нового потомка
        self._register_new_row_parent_balance(dto, temp_id)

        # self._update_row_color(row)  # Перекрашиваем строку

        # После возможной сортировки нужно найти актуальную строку по temp_id
        actual_row = self._find_row_by_id(temp_id)

        self.logger.debug(
            f"actual_row = {actual_row} "
        )
        if actual_row >= 0:
            self._update_row_color(actual_row)  # Перекрашиваем строку
        else:
            self._update_row_color(row)  # fallback  # Перекрашиваем строку

        self._update_save_button_state() # Обновляем состояние кнопки сохранения

        # # Создать пустой DTO и добавить
        # defaults = {}
        # for col in self.columns:
        #     if col.column_type != ColumnType.DATA:
        #         continue
        #     if col.data_type == str:
        #         defaults[col.field_name] = ""
        #     elif col.data_type == int:
        #         defaults[col.field_name] = 0
        #     elif col.data_type == datetime.date:
        #         defaults[col.field_name] = datetime.date.today()
        #     else:
        #         defaults[col.field_name] = None
        # # Применяем контекстные параметры
        # if hasattr(self, '_context_params'):
        #     for key, value in self._context_params.items():
        #         if key in defaults:
        #             defaults[key] = value
        # dto = self.dto_class(**defaults)
        # dto.id = self._next_temp_id if hasattr(self, '_next_temp_id') else -1
        # self._next_temp_id = (self._next_temp_id or -1) - 1
        # self._add_new_row(dto)

    # def _update_parent_child_counter(self, entity_id, delta:int): # перенесён в DraftTreeMixin
    #     # Если есть родитель, увеличиваем счётчик его потомков
    #     parent_id = self._get_parent_id(entity_id)
    #     if parent_id is not None:
    #         self.mark_child_change(parent_id, delta)

    # def _update_parent_child_counter(self, entity_id: int, delta: int) -> None: # есть в миксине DraftTreeMixin
    #     """
    #     Уведомляет родителя сущности entity_id об изменении количества активных потомков.
    #     Реализован в DraftTreeMixin.
    #     """

    #     super()._update_parent_child_counter(entity_id, delta)

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _cancel_draft_new_row(self,  entity_id: int):
        """
        Рекурсивно отменяет создание новой строки и всех её потомков (новых строк).

        **Алгоритм:**
            1. Находит все дочерние ключи __new__:{entity_type}:{child_id} с parent_id == entity_id.
            2. Для каждого рекурсивно вызывает `_cancel_new_row(child_id)`.
            3. После удаления всех потомков удаляет саму строку и её ключи.

        **Почему нельзя использовать `discard_by_prefix`:**
            Простое удаление всех ключей по префиксу `{entity_type}:{entity_id}:`
            **не удалит** дочерние **новые строки**, которые имеют собственный ключ
            `__new__:{entity_type}:{child_id}`, потому что они хранятся отдельно.
            Без рекурсивного вызова `_cancel_new_row` эти дочерние строки останутся
            в реестре и будут ссылаться на несуществующий временный ID родителя,
            что при последующем сохранении вызовет ошибки целостности данных.

        **Важно:** 
            Без этого шага дочерние новые строки останутся висеть на мёртвого временного ID родителя.

        Args:
            entity_id: Временный отрицательный ID новой строки.
        
        
        Returns:
            None
        """
        
        prefix_new = f"__new__:{self._entity_type}:"

        for key in list(self._draft_registry.get_keys_by_prefix(prefix_new)):

            self.logger.debug(
                f"key = {key} "
            )

            child_id = int(key.split(':')[-1])

            # Пропускаем самого себя, чтобы избежать бесконечной рекурсии
            self.logger.debug(
                f"child_id = {child_id} "
                f"entity_id = {entity_id} "
            )
            if child_id == entity_id:
                continue

            child_data = self._draft_registry.get(key)
            self.logger.debug(
                f"child_data is None = {child_data is None} "
                f"'dto' in child_data = {'dto' in child_data} "
            )
            if child_data and 'dto' in child_data:
                child_dto = child_data["dto"]
                child_parent_id = self._get_parent_id_for_new_row(child_dto)
                self.logger.debug(
                    f"child_parent_id = {child_parent_id} "
                    f"entity_id = {entity_id} "
                )
                if child_parent_id == entity_id:
                    self._cancel_new_row(child_id)

        # # Рекурсивно отменить всех потомков (по префиксу)
        #
        # # Удаляем все черновики, привязанные к этому временному ID
        # prefix = f"{self._entity_type}:{entity_id}:"
        #
        # for key in list(self._draft_registry.get_keys_by_prefix(prefix)):
        #     # Извлечь ID потомка из ключа (например, из "appointment:-1:photos" или "appointment:-1:...")
        #     parts = key.split(':')
        #     if len(parts) >= 3 and parts[0] == self._entity_type:
        #         child_id = int(parts[1])
        #         if child_id != entity_id and child_id < 0:
        #             if self._draft_registry.has(f"__new__:{self._entity_type}:{child_id}"):
        #                 self._cancel_new_row(child_id)

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _clean_entity_registry_by_id(self, prefix: str, entity_id: int):
        """
        Удаляет из реестра все ключи, связанные с указанной сущностью (новой или удалённой).

        **Что удаляет:**
            1. Все черновики, которые начинаются с префикса "{self._entity_type}:{entity_id}:"
               (например, "appointment:-1:photos", "appointment:-1:notes" и т.д.).
            2. Ключ удаления/новой строки вида "{prefix}:{self._entity_type}:{entity_id}".
                Обычно `prefix` равен :
                - Если `prefix == "__new__"` – удаляет ключ новой строки.
                - Если `prefix == "__deleted__"` – удаляет ключ пометки на удаление.
                (без двоеточия).
            3. Статус сущности (ключ "__status__:{self._entity_type}:{entity_id}").

        **Важно:**
            - Этот метод не удаляет дочерние **новые строки** (имеющие собственный ключ `__new__`).
              Для каскадной отмены новых строк следует использовать `_cancel_new_row`.
            - Метод используется внутри `_cancel_new_row` (очистка после рекурсивного удаления потомков)
              и внутри `_delete_entity_and_children` (очистка после удаления существующей сущности).
            - Если `prefix == "__deleted__"`, служебный ключ балансировки счётчиков
              (`__parent_counter_inc__`) не удаляется, так как он не создаётся для удалённых строк.

        **Пример:**
            >>> # Отмена новой строки с ID = -1
            >>> self._clean_entity_registry_by_id("__new__", -1)
            # Удалит все черновики "appointment:-1:*", ключ "__new__:appointment:-1" и статус.

        Args:
            prefix (str): Префикс служебного ключа. Для новых строк – "__new__",
                          для удалённых строк – "__deleted__". Может быть и другим в зависимости
                          от контекста (например, при использовании в `_delete_entity_and_children`
                          передаётся "__deleted__").

            entity_id (int): Временный (отрицательный) ID новой строки или реальный ID
                             существующей сущности.

        Returns:
            None

        Пример:
            >>> # Отмена новой строки с ID = -1
            >>> self._clean_entity_registry_by_id("__new__", -1)
            # Удалит:
            #   - все ключи вида "appointment:-1:*"
            #   - ключ "__new__:appointment:-1"
            #   - статус "__status__:appointment:-1"
        """

        prefix_temp = f"{self._entity_type}:{entity_id}"

        # Удалить все черновики с этим префиксом (включая дочерние, но они уже удалены рекурсивно)

        self._draft_registry.discard_by_prefix(f"{prefix_temp}:")

        # Удаляем ключ __new__
        self._draft_registry.discard(f"{prefix}:{prefix_temp}")

        # Удаляем статус сущности из реестра (ключ __status__)
        self._draft_registry.delete_entity_status(self._entity_type, entity_id)

        # Удаляем служебный ключ балансировки счётчиков, созданный при добавлении новой строки
        self._draft_registry.discard(f"__parent_counter_inc__:{prefix_temp}")

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _cancel_new_row(self, entity_id: int):
        """
        Полностью отменяет создание новой строки и всех её потомков (новых строк).

        **Универсальный метод, работающий при любой глубине вложенности:**
            1. Рекурсивно находит и отменяет все дочерние новые строки (через `_cancel_draft_new_row`).
            2. Удаляет все черновики, связанные с текущей сущностью (по префиксу).
            3. Удаляет ключ `__new__`, статус и строку из модели.
            4. Уведомляет родителя (если есть) об уменьшении количества потомков.

        **Важно: Почему нельзя заменить на `discard_by_prefix`:**
            Простой вызов `self._draft_registry.discard_by_prefix(f"{self._entity_type}:{entity_id}:")`
            удалит только черновики, но оставит **дочерние новые строки** (имеющие собственные
            ключи `__new__:{entity_type}:{child_id}`) в реестре. Эти дочерние строки будут
            ссылаться на мёртвый временный ID родителя, что приведёт к ошибкам целостности
            при следующем сохранении. Рекурсивный вызов `_cancel_new_row` для каждого потомка
            гарантирует полную очистку всей иерархии.

        ПРАВИЛЬНЫЙ ПОДХОД:
            1. Сначала удалить все "нестрочные" черновики (фото, заметки) по префиксу.
            2. Затем рекурсивно найти и отменить все дочерние НОВЫЕ строки,
               проверяя их DTO на parent_id, указывающий на текущий entity_id.
            3. Только после этого удалить саму строку и её ключи.

            См. реализацию ниже.

        Args:
            entity_id: Временный отрицательный ID новой строки.
        
        Returns:
            None
        """

        # Получаем DTO до удаления, чтобы узнать родителя
        row = self._find_row_by_id(entity_id)
        dto = self.source_model.get_item_at_row(row) if row >= 0 else None
        parent_id = self._get_parent_id_for_new_row(dto) if dto else None

        # # Удаляем все черновики, привязанные к этому временному ID
        # prefix = f"{self._entity_type}:{entity_id}:"



        #  РЕКУРСИВНОЕ УДАЛЕНИЕ ДОЧЕРНИХ НОВЫХ СТРОК (критически важно!)
        #    Без этого шага дочерние строки останутся висеть на мёртвого родителя.
        self._cancel_draft_new_row(entity_id) # отмена новых потомков

        # удаляем временную папку, если она была создана
        self._cleanup_temp_dir(entity_id)

        # Удаляет из реестра все ключи, связанные с указанной временной сущностью (новой строкой).
        self._clean_entity_registry_by_id("__new__", entity_id)

        # Удаляем служебный ключ балансировки, если он остался
        inc_key = f"__parent_counter_inc__:{self._entity_type}:{entity_id}"
        self._draft_registry.discard(inc_key)

        # Если это была выбранная строка – сбрасываем выделение до удаления строки
        self._clear_selected_dto(entity_id)

        # Удаляем строку из модели
        self.logger.debug(
            f"row = {row} "
        )
        if row >= 0:
            self.source_model.remove_row(row)

            # # Удаляем цвет для этого ID (теперь он не нужен)
            # self.source_model.clear_row_color(entity_id) # перенёс в PaginatedTableModel.remove_row

        # Очищаем кэш статусов
        self._status_cache.pop(entity_id, None)

        # Уведомляем родителя, что потомок исчез (если был уведомлён при создании)
        # if parent_id is not None:
        #     # Проверяем, не был ли родитель уже помечен на удаление
        #     if not self._draft_registry.has(f"__deleted__:{self._entity_type}:{parent_id}"):
        #         self.mark_child_change(parent_id, -1)
        self._update_parent_counter(parent_id, -1)

    
    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _delete_selected_rows(self):
        """
        Помечает выбранные строки на удаление или снимает пометку, если строка уже была помечена.

        Для существующих строк (entity_id >= 0):
            - Если строка ещё не помечена – создаётся ключ "__deleted__:entity_type:entity_id",
              увеличивается счётчик родителя на +1, строка перекрашивается в красный цвет.
            - Если строка уже помечена – пометка снимается (ключ удаляется, счётчик родителя
              уменьшается на -1, цвет восстанавливается).

        Для новых строк (entity_id < 0):
            - Они просто отменяются (удаляются из реестра и модели) через _cancel_new_row,
              потому что они ещё не сохранены и не имеют смысла «удаления».

        После обработки всех выбранных строк чекбоксы сбрасываются,
        и обновляется состояние кнопки сохранения.
        """

        ids_to_delete = self.get_selected_entity_ids()

        for entity_id in ids_to_delete:
            self.logger.debug(
                f"entity_id = {entity_id} "
            )
            if entity_id < 0:
                # Новая строка – просто удаляем её (как при отмене)
                self._cancel_new_row(entity_id)

                # # Примечание: внутри _cancel_new_row уже вызывается self._clear_selected_dto(entity_id),
                # # который сбрасывает selected_dto, если он совпадает с удаляемым ID.
                # # Поэтому дополнительный вызов self._clear_selected_dto(entity_id) не требуется.
                
                # # Если это была выбранная строка – сбрасываем выделение (запасной вариант, но метод уже делает это)
                # self._clear_selected_dto(entity_id) # не требуется, так как уже сделано в _cancel_new_row

            else:
                # Существующая строка – помечаем на удаление
                temp = f"__deleted__:{self._entity_type}:{entity_id}"
                tt = self._draft_registry.has(temp)  # проверка если строка уже была помечена на удаление
                self.logger.debug(
                    f"self._draft_registry.has(temp) = {tt} "
                )
                if tt: # проверка если строка уже была помечена на удаление

                    # Строка уже помечена на удаление – снимаем пометку
                    self._unmark_deleted_row(entity_id)

                else:
                    # Помечаем как удалённую
                    self._draft_registry.set(temp, {})

                    # Уведомляем родителя о том, что появился потомок, помеченный на удаление (если что компенсимуем в _delete_entity_and_children)
                    # (это увеличит счётчик детей родителя)
                    self._update_parent_child_counter(entity_id, 1) # +1 к счётчику родителя # Если есть родитель, увеличиваем счётчик его потомков  # Наследован из DraftTreeMixin

                    self._update_row_color_by_id(entity_id)  # Перекрашиваем строку

        self._clear_checkboxes() # Чистим чекбоксы

        self._update_save_button_state() # Обновляем состояние кнопки сохранения

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _update_row_color_by_id(self, entity_id):
        """
        Обновляет цвет строки для сущности по её ID.

        Args:
            entity_id: ID сущности, цвет которой нужно обновить.
        """

        # Перекрашиваем строку, соответствующую этой сущности
        row = self._find_row_by_id(entity_id)
        self.logger.debug(
            f"row = {row} "
        )
        if row >= 0:
            # Просто перекрашиваем строку; статус уже обновлён через реестр
            self._update_row_color(row)

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _unmark_deleted_row(self, entity_id: int) -> None:
        """
        Снимает пометку на удаление с существующей строки.

        Алгоритм:
            1. Проверяет, существует ли ключ __deleted__ для данной сущности.
            2. Если да – удаляет его.
            3. Уменьшает счётчик родителя на -1 (уведомляет родителя, что удалённый потомок «восстановлен»).
            4. Перекрашивает строку в актуальный цвет (без пометки на удаление).

        Args:
            entity_id: ID сущности, с которой нужно снять пометку на удаление.
        """

        deleted_key = f"__deleted__:{self._entity_type}:{entity_id}"
        if not self._draft_registry.has(deleted_key):
            # Пометки не было – ничего не делаем
            return

        self.logger.debug(f"Снятие пометки на удаление: {entity_id}")

        # Удаляем ключ удаления
        self._draft_registry.discard(deleted_key)

        # Уменьшаем счётчик родителя (родитель теряет одного удалённого потомка)
        # Используем -1, так как ранее при пометке мы увеличивали счётчик на +1
        self._update_parent_child_counter(entity_id, -1)

        # Перекрашиваем строку (цвет будет определён по текущему статусу, без удаления)
        self._update_row_color_by_id(entity_id)

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _cancel_selected_rows_changes(self):
        """
        Отменяет изменения для выбранных строк.

        **Для новых строк (id < 0):**
            - Удаляет строку и всех её потомков (рекурсивно) через `_cancel_new_row`.
            - Не уведомляет родителя, так как он никогда не получал уведомления о создании.

        **Для существующих строк (id >= 0):**
            - Если строка помечена на удаление: снимает пометку, а затем **полностью отменяет ВСЕ изменения**
              (основные поля и дочерние черновики), возвращая строку к исходному состоянию.
            - Если строка не помечена на удаление: отменяет все изменения через `discard_entity_subtree`
              и перезагружает DTO из БД.

        **Почему для удалённой строки нужен полный откат, а не только снятие пометки?**
            Пользователь мог сначала отредактировать поля (жёлтый цвет), а затем пометить строку на удаление (красный цвет).
            Нажав «Отменить изменения», он ожидает вернуть строку к состоянию, предшествующему ЛЮБЫМ его действиям,
            то есть убрать и правки, и пометку. Простое снятие пометки оставило бы строку жёлтой, что противоречит интуиции.

        **После отмены:**
            - Нет пометки на удаление.
            - Нет собственных изменений полей.
            - Нет дочерних черновиков.
            - Цвет строки становится белым.

        **Связь с другими методами:**
            - `_unmark_deleted_row`: снимает пометку на удаление, уменьшает счётчик родителя.
            - `discard_entity_subtree`: удаляет все черновики, статусы и счётчики для сущности и её потомков.
            - После отмены кнопка «Сохранить» деактивируется, если нет других изменений.

        **Пример сценария:**
            1. Пользователь редактирует поле строки A → строка становится жёлтой.
            2. Затем помечает строку A на удаление → строка становится красной.
            3. Нажимает «Отменить изменения» для строки A.
            4. Результат: строка A возвращается к исходному белому цвету, пометка удаления снята,
               все правки отменены.

        **Примечание:** Для новых строк (id < 0) полный откат означает их удаление, так как они ещё не сохранены в БД.
        """

        ids_to_cancel = self.get_selected_entity_ids()
        for entity_id in ids_to_cancel:
            self.logger.debug(
                f"entity_id = {entity_id} "
            )
            row = self._find_row_by_id(entity_id)
            self.logger.debug(
                f"row = {row} "
            )
            if row < 0:
                continue

            dto = self.source_model.get_item_at_row(row)
            self.logger.debug(
                f"dto is None = {dto is None} "
            )
            if dto and dto.id is not None and dto.id < 0:
                self._cancel_new_row(entity_id)

                # Родитель НЕ уведомляется, потому что он никогда не получал уведомления
                # о существовании этой новой строки (см. _add_inline_row).

                # # Примечание: внутри _cancel_new_row уже вызывается self._clear_selected_dto(entity_id),
                # # который сбрасывает selected_dto, если он совпадает с удаляемым ID.
                # # Поэтому дополнительный вызов self._clear_selected_dto(entity_id) не требуется.
                
                # # Если это была выбранная строка – сбрасываем выделение (запасной вариант, но метод уже делает это)
                # self._clear_selected_dto(entity_id) # не требуется, так как уже сделано в _cancel_new_row

            else:
                # причины закоментирования следующего блока: При отмене изменений удалённой строки не нужно отдельно снимать пометку __deleted__, так как discard_entity_subtree уже удалит этот ключ и корректно уменьшит счётчик родителя. Это предотвращает двойное уменьшение счётчика.
                # # Если строка была помечена на удаление – снимаем пометку
                # if self._draft_registry.has(f"__deleted__:{self._entity_type}:{entity_id}"):  
                #     self.logger.debug(f"Снятие пометки на удаление для строки {entity_id}")
                #     self._unmark_deleted_row(entity_id)

                for key in list(self._draft_registry.get_keys_by_prefix("__new__")):
                    data = self._draft_registry.get(key)
                    if data and hasattr(data["dto"], 'parent_id') and data["dto"].parent_id == entity_id:
                        child_temp_id = int(key.split(':')[-1])
                        self._cancel_new_row(child_temp_id)   # рекурсивно удалит и внуков
                    
                # # Существующая – отменяем всё поддерево (уже удалит ключ __deleted__ и корректно уменьшит счётчик родителя)
                # # Существующая строка (id > 0) – отменяем все изменения в поддереве.
                # # discard_entity_subtree удаляет все черновики и статусы для entity_id и её потомков,
                # # а также уменьшает счётчик родителя (если был). При этом:
                # #   - В реестре рассылается сигнал draft_changed для каждого удалённого ключа.
                # #   - Дочерние компоненты (например, PhotoUploaderWidget), подписанные на реестр,
                # #     автоматически получают уведомление и перезагружают своё состояние через
                # #     load_from_registry. Поэтому явно вызывать _load_drafts_for_children() НЕ НУЖНО.
                # self.discard_entity_subtree(entity_id)  # метод из DraftTreeMixin

                # Определяем, были ли у строки собственные изменения
                status = self._draft_registry.get_entity_status(self._entity_type, entity_id)
                self.logger.debug(
                    f"status  = {status} "
                )
                if status in ('own', 'both'):
                    # Были собственные изменения – отменяем всё поддерево (уменьшит счётчик дедушки)
                    self.discard_entity_subtree(entity_id)
                else:
                    # Не было собственных изменений – удаляем только черновики, не трогая счётчик дедушки
                    self.clear_entity_drafts(entity_id)

                    # # Также удаляем временную папку, если она была создана
                    # self._cleanup_temp_dir(entity_id)  # убираем , так как clear_entity_drafts уже удаляет временную папку

                    # Также удаляем статус (clear_entity_drafts это уже делает)
                    # self._draft_registry.delete_entity_status(self._entity_type, entity_id)


                # Перезагружаем DTO из БД
                fresh = self.service.get_by_id(
                    entity_id, 
                    # session=session # сессия не требуется, т.к. это чтение
                )
                
                # self.source_model.update_row(row, fresh)
                # self.original_data[row] = fresh

                self._source_model_update_row(row, fresh)

                self._clear_selected_dto(entity_id, fresh)

                # НЕ вызываем _load_drafts_for_children() – дочерние виджеты уже синхронизированы через сигналы реестра (см. механизм подписки в EditableComponentMixin)

                # Перезагружаем дочерние виджеты (например, фото), чтобы они отобразили актуальное состояние
                # причины дабавления: После отмены изменений родительской строки необходимо синхронизировать дочерние виджеты, так как их черновики были удалены, а UI мог остаться старым.
                # self._load_drafts_for_children() # УДАЛЕНО – компоненты сами обновятся через подписку    # Дочерний компонент сам перезагрузится через сигнал draft_changed (так как он подписан на реестр)

                # Статус обновится автоматически через сигналы, цвет тоже
                self._update_row_color(row) # Перекрашиваем строку

        self._clear_checkboxes() # Чистим чекбоксы

        self._update_save_button_state() # Обновляем состояние кнопки сохранения
    
    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def cancel_parent_changes_only(self) -> None:
        """
        Отменяет только собственные изменения (основные поля) текущей выбранной строки,
        не затрагивая дочерние черновики (например, фотографии, заметки).

        **Когда используется:**
            - Пользователь отредактировал основные поля строки (статус 'own' или 'both'),
            а также внёс изменения в дочерние сущности (статус 'child' или 'both').
            - Он хочет отменить правки в основных полях, но оставить дочерние черновики нетронутыми.
            - Применяется только к существующим строкам (id > 0). Для новых строк (id < 0)
            этот метод не имеет смысла – используйте обычную отмену.

        **Алгоритм:**
            1. Проверяет, что выбранная строка существует и имеет положительный ID.
            2. Вызывает `clear_entity_drafts(entity_id)`, который:
            - удаляет собственные черновики (по префиксу `entity_type:entity_id:`);
            - **не трогает** черновики дочерних сущностей (префикс `entity_type:entity_id:` с дополнительными компонентами, например `photos`);
            - удаляет статус `'own'`, но оставляет `'child'`, если дочерние черновики есть.
            3. Обновляет цвет строки (перекрашивает в соответствии с новым статусом).
            4. Обновляет состояние кнопки сохранения (активна, если есть дочерние черновики).
            5. Логирует действие.

        **Исключения:**
            - Ничего не делает, если нет выбранной строки или её ID <= 0.

        **Пример:**
            >>> # пользователь выбрал строку с изменениями в основных полях и дочерних
            >>> page.cancel_parent_changes_only()
            >>> # основные поля возвращены к состоянию из БД, дочерние черновики остались
            >>> # строка перекрашивается в жёлтый (если есть дети) или белый (если нет)

        **Примечания:**
            - После вызова этого метода статус сущности пересчитывается автоматически
            (через `clear_entity_drafts`, который вызывает `_propagate_status_up`).
            - Если дочерние черновики отсутствуют, строка станет белой, и кнопка сохранения
            деактивируется (если других изменений нет).
            - Для новых строк (временный ID) этот метод не работает – используйте
            `cancel_selected_rows_changes` или `_cancel_new_row`.
            - Наследники (например, `AppointmentListPage`) могут переопределить этот метод,
            добавив обновление правой панели, если необходимо.
        """
        self.logger.debug(
            f"not self.selected_dto  = {not self.selected_dto} "
        )
        if not self.selected_dto:
            self.logger.debug("cancel_parent_changes_only: нет выбранной строки")
            return

        entity_id = self.selected_dto.id
        self.logger.debug(
            f"entity_id  = {entity_id} "
        )
        if entity_id is None or entity_id < 0:
            self.logger.debug(f"cancel_parent_changes_only: строка с id={entity_id} не является существующей, пропуск")
            return

        self.logger.info(f"Отмена собственных изменений для строки id={entity_id} (дочерние черновики остаются)")

        # Удаляем только собственные черновики (основные поля)
        self.clear_entity_drafts(entity_id)

        # Обновляем цвет строки (если строка есть в таблице)
        row = self._find_row_by_id(entity_id)
        self.logger.debug(
            f"row  = {row} "
        )
        if row >= 0:
            self._update_row_color(row)

        # Обновляем состояние кнопки сохранения (может остаться активной, если есть дочерние)
        self._update_save_button_state()

    @AppLogger.get_instance(
        name='PaginatedListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def save_changes_for_entity(self, entity_type: str) -> bool:
        """
        Сохраняет изменения ТОЛЬКО для указанного типа сущности,
        не затрагивая черновики других типов.
        
        Полезно, когда используется общий реестр черновиков между разными страницами.
        
        Args:
            entity_type: Тип сущности (например, 'patient', 'appointment')
            
        Returns:
            True при успешном сохранении, иначе False
        """

        self.logger.debug(
            f"self._saving_in_progress  = {self._saving_in_progress} "
        )
        if self._saving_in_progress:
            self.logger.warning("Сохранение уже выполняется, повторный вызов игнорирован")
            return False

        # Сохраняем текущий entity_type и временно подменяем
        original_type = self._entity_type
        self._entity_type = entity_type
        
        self._saving_in_progress = True
        try:
            # Сохранение изменений внутри единой транзакции, Перезагружаем данные, Очищаем реестр от служебных ключей
            self._save_all_changes_impl_reload_clear_entity_registry()
            
            return True
        
        except Exception as e:
            self.logger.exception(f"Ошибка сохранения для типа {entity_type}: {e}")
            return False
        
        finally:
            self._entity_type = original_type
            self._saving_in_progress = False


