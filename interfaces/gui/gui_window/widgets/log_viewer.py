# interfaces/gui/gui_window/widgets/log_viewer.py
from PySide6.QtWidgets import QTextEdit
from PySide6.QtCore import Signal, Slot
import logging

from PySide6.QtWidgets import QTextEdit
from PySide6.QtCore import Signal, Slot
import logging

class LogViewer(QTextEdit):
    log_received = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumHeight(150)
        self.setVisible(False)
        self.log_received.connect(self._append_log)

    @Slot(str)
    def _append_log(self, message):
        self.append(message)


class LogViewerHandler(logging.Handler):
    def __init__(self, viewer, level=logging.NOTSET):
        super().__init__(level)
        self.viewer = viewer
        # Задайте нужный формат сообщений
        self.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

    def emit(self, record):
        msg = self.format(record)
        self.viewer.log_received.emit(msg)