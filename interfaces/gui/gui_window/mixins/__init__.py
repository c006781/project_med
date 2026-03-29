# -*- coding: utf-8 -*-
"""
Пакет миксинов для главного окна.
"""

from .pages_creation_mixin import PagesCreationMixin
from .connections_mixin import ConnectionsMixin
from .delete_handlers_mixin import DeleteHandlersMixin
from .navigation_mixin import NavigationMixin
from .sync_mixin import SyncMixin

__all__ = [
    'PagesCreationMixin',
    'ConnectionsMixin',
    'DeleteHandlersMixin',
    'NavigationMixin',
    'SyncMixin',
]