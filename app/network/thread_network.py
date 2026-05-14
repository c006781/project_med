# app/network/thread_network.py

# import os
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

    def __init__(
        self, 
        token: str, 
        remote_path: str, 
        local_path: str, 
        parent=None
    ):
        """
        Инициализация потока для скачивания файла с Диска.

        :param token: (str) OAuth-токен для авторизации.
        :param remote_path: (str) Путь к файлу на Яндекс.Диске.
        :param local_path: (str) Локальный путь для сохранения файла.
        :param parent: (QObject/None) Родительский объект (по умолчанию None).
        """

        super().__init__(parent)

        # сохраняем параметры для использования в run
        self.token = token
        self.remote_path = remote_path
        self.local_path = local_path

    def _progress_callback(self, current: int, total: int):
        """Колбэк для передачи прогресса в сигнал."""
        self.progress.emit(current, total)

    def run(self):
        """
        Запуск потока для скачивания файла с Диска.

        В этом методе происходит вызов функции yadisk_download_file с параметрами,
        сохраненными в __init__. Если функция работает успешно, то сигнал finished
        эмити код завершения (0 - успех), а если возникла ошибка, то сигнал error
        эмити сообщение об ошибке.
        """
        try:
            # Проверяем существование файла на Яндекс.Диске
            exists, msg = check_remote_file_exists(self.token, self.remote_path)
            if not exists:
                self.error.emit(msg)
                return

            # Вызов функции скачивания файла с Диска
            result = yadisk_download_file(
                # Токен для авторизации
                ya_token=self.token,
                # Путь к файлу на Яндекс.Диске
                ya_file_path=self.remote_path,
                # Локальный путь для сохранения файла
                local_file_path=self.local_path,
                # Выводить ошибки (True) или метки на ошибки (False)
                if_err=True,
                # Колбэк для передачи прогресса
                progress_callback=self._progress_callback
            )
            # Сигнал, эмитирующий код завершения (0 - успех)
            self.finished.emit(result)
        except Exception as e:
            # Сигнал, эмитирующий сообщение об ошибке
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

    def __init__(
        self, 
        token: str, 
        local_path: str, 
        remote_path: str, 
        parent=None, 
        overwrite = False,
    ):
        """
        Инициализация потока для загрузки файла на Диск.

        :param token: (str) OAuth-токен для авторизации.
        :param local_path: (str) Локальный путь к файлу, который будет загружен на Диск.
        :param remote_path: (str) Путь к файлу на Яндекс.Диске, куда будет загружен файл.
        :param parent: (QObject/None) Родительский объект (по умолчанию None).
        """
        super().__init__(parent)
        # сохраняем параметры для использования в run
        self.token = token
        self.local_path = local_path
        self.remote_path = remote_path
        self.overwrite = overwrite

    def _progress_callback(self, current: int, total: int):
        """
        Колбэк для передачи прогресса загрузки файла на Диск.
        Эмитируется изнутри функции run в потоке UploadThread.

        :param current: (int) Текущее значение прогресса (например, количество байт, уже переданных на Диск).
        :param total: (int) Общее количество байт, которое будет передано на Диск.
        """
        self.progress.emit(current, total)

    def run(self):
        """
        Запуск потока для загрузки файла на Диск.
        Функция run вызывает функцию yadisk_upload_file с параметрами,
        сохраненными в __init__, и передает прогресс загрузки
        в колбэк _progress_callback.
        Если возникнет какая-либо ошибка, то сообщение об ошибке
        передается в колбэк error.
        """
        try:
            # вызов функции yadisk_upload_file с параметрами,
            # сохраненными в __init__
            result = yadisk_upload_file(
                ya_token=self.token,
                local_file_path=self.local_path,
                ya_file_path=self.remote_path,
                if_err=True,
                overwrite=self.overwrite,
                progress_callback=self._progress_callback
            )
            # передача результата в колбэк finished
            self.finished.emit(result)
        except Exception as e:
            # передача сообщения об ошибке в колбэк error
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
