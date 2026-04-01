# interfaces/gui/gui_window/pages/mixins/__init__.py
"""
Пакет миксинов для главного окна.
"""

from .pages_creation_mixin import PagesCreationMixin
from .connections_mixin import ConnectionsMixin
from .delete_handlers_mixin import DeleteHandlersMixin
from .navigation_mixin import NavigationMixin
from .sync_mixin import SyncMixin
# 
# from .draft_mixin import DraftMixin
# from .patient_info_mixin import PatientInfoMixin
# from .right_panel_mixin import RightPanelMixin


__all__ = [
    'PagesCreationMixin',
    'ConnectionsMixin',
    'DeleteHandlersMixin',
    'NavigationMixin',
    'SyncMixin',
    # 'DraftMixin', 
    # 'PatientInfoMixin', 
    # 'RightPanelMixin',
]