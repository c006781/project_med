import os
from PySide6.QtCore import QThread, Signal # pip install PySide6

from app.network.ya_dop import yadisk_download_file, yadisk_upload_file

class DownloadThread(QThread):
    """
    Поток для скачивания файла с Диска.
    Сигналы:
        progress(current, total): обновление прогресса
        finished(code): код завершения (0 - успех)
        error(message): сообщение об ошибке
    """
    progress = Signal(int, int)
    finished = Signal(int)
    error = Signal(str)

    def __init__(self, token: str, remote_path: str, local_path: str, parent=None):
        super().__init__(parent)
        self.token = token
        self.remote_path = remote_path
        self.local_path = local_path

    def _progress_callback(self, current: int, total: int):
        """Колбэк для передачи прогресса в сигнал."""
        self.progress.emit(current, total)

    def run(self):
        try:
            result = yadisk_download_file(
                ya_token=self.token,
                ya_file_path=self.remote_path,
                local_file_path=self.local_path,
                if_err=True,
                progress_callback=self._progress_callback
            )
            self.finished.emit(result)  # result == 0 при успехе
        except Exception as e:
            self.error.emit(str(e))


class UploadThread(QThread):
    """
    Поток для загрузки файла на Диск.
    Сигналы:
        progress(current, total): обновление прогресса
        finished(code): код завершения (0 - успех)
        error(message): сообщение об ошибке
    """
    progress = Signal(int, int)
    finished = Signal(int)
    error = Signal(str)

    def __init__(self, token: str, local_path: str, remote_path: str, parent=None):
        super().__init__(parent)
        self.token = token
        self.local_path = local_path
        self.remote_path = remote_path

    def _progress_callback(self, current: int, total: int):
        self.progress.emit(current, total)

    def run(self):
        try:
            result = yadisk_upload_file(
                ya_token=self.token,
                local_file_path=self.local_path,
                ya_file_path=self.remote_path,
                if_err=True,
                progress_callback=self._progress_callback
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))




if __name__ == '__main__':
    

    # def update_progress( current, total):
    #     progress_bar.setMaximum(total)
    #     progress_bar.setValue(current)

    # def on_download_finished( code):
    #     if code == 0:
    #         status_label.setText("Скачивание завершено")
    #     else:
    #         status_label.setText(f"Ошибка {code}")

    # def on_error( message):
    #     status_label.setText(f"Ошибка: {message}")

    # download_thread = DownloadThread(
    #     token="ваш_токен",
    #     remote_path="/Проекты/отчёт.xlsx",
    #     local_path="./отчёт.xlsx",
    #     parent=self
    # )

    # download_thread.progress.connect(update_progress)
    # download_thread.finished.connect(on_download_finished)
    # download_thread.error.connect(on_error)
    # download_thread.start()
    pass
