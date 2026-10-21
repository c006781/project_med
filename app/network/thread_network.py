# app/network/thread_network.py
"""
Потоки Qt для операций с Яндекс.Диском — чтобы окно не зависало на время передачи.

Все потоки — наследники :class:`YaDiskThread`: общие сигналы и обработка ошибок в одном
месте, конкретный поток задаёт только :meth:`YaDiskThread._operation`.

Сигналы (одинаковые у всех потоков):

* ``progress(int, int)`` — передано байт / всего (из колбэка ``yadisk``);
* ``finished(int)`` — операция завершилась, код :class:`~app.network.ya_dop.YaDiskResult`
  (текст — ``YaDiskResult.describe(code)``). Объявлен поверх ``QThread.finished()``:
  подключённые обработчики получают ровно один вызов — с кодом (проверено тестом
  ``test_finished_signal_emitted_once_with_code``);
* ``error(str)`` — исключение во время операции (текст для пользователя).

Как добавить операцию (например, удаление файла на Диске)::

    class RemoveThread(YaDiskThread):
        def __init__(
            self,
            token: str, # OAuth-токен
            remote_path: str, # что удалить
            parent: Optional[QObject] = None, # родитель Qt
        ):
            super().__init__(token=token, parent=parent)
            self.remote_path = remote_path

        def _operation(self) -> int:
            return yadisk_remove_file(
                ya_token=self.token, # токен
                ya_file_path=self.remote_path, # путь
                if_err=True, # ошибки — в сигнал error
            )

Пример::

    >>> thread = DownloadThread(                  # doctest: +SKIP
    ...     token='y0_...',                       # токен
    ...     remote_path='Папка/clinic.db',        # файл на Диске
    ...     local_path='./clinic.db',             # куда
    ... )
    >>> thread.finished.connect(on_finished)      # doctest: +SKIP
    >>> thread.error.connect(on_error)            # doctest: +SKIP
    >>> thread.start()                            # doctest: +SKIP
"""

from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal # pip install PySide6

from app.network.ya_dop import yadisk_download_file, yadisk_upload_file
# from app.network.ya_dop import (
#     check_remote_file_exists, # проверка файла на Диске перед скачиванием (DownloadThread.run)
#     yadisk_download_file,
#     yadisk_upload_file,
# )
# ↑ до rework-yadisk, проход 1 (2026-10-21): отдельная проверка файла перед скачиванием
#   больше не нужна — yadisk_download_file сама проверяет токен, наличие и тип (T1).


class YaDiskThread(QThread):
    """
    Базовый поток операции с Яндекс.Диском.

    Наследник реализует :meth:`_operation` (вызов функции из ``app.network.ya_dop`` с
    ``if_err=True`` и ``progress_callback=self._progress_callback``) и возвращает её код.
    :meth:`run` превращает результат в ``finished(code)``, исключение — в ``error(text)``.

    Attributes:
        progress (Signal): ``(int, int)`` — передано / всего байт.
        finished (Signal): ``(int)`` — код результата (``0`` — успех).
        error (Signal): ``(str)`` — текст ошибки.
        token (str): OAuth-токен.
    """

    progress = Signal(int, int)
    finished = Signal(int)
    error = Signal(str)

    def __init__(
        self,
        token: str, # OAuth-токен Яндекс.Диска
        parent: Optional[QObject] = None, # родитель Qt (по умолчанию нет)
    ):
        """
        Args:
            token (str): OAuth-токен.
            parent (Optional[QObject]): Родитель Qt.
        """
        super().__init__(parent)
        self.token = token

    def _progress_callback(
        self,
        current: int, # передано байт
        total: int, # всего байт
    ) -> None:
        """
        Колбэк прогресса для ``yadisk`` → сигнал ``progress``.

        Args:
            current (int): Передано байт.
            total (int): Всего байт.
        """
        self.progress.emit(current, total)

    def _operation(self) -> int:
        """
        Сама операция (реализует наследник).

        Returns:
            int: Код :class:`~app.network.ya_dop.YaDiskResult`.

        Raises:
            NotImplementedError: Не переопределено в наследнике.
        """
        raise NotImplementedError(f'{type(self).__name__}._operation не реализован')

    def run(self) -> None:
        """
        Выполняет :meth:`_operation` в потоке: код → ``finished``, исключение → ``error``.

        Пустой текст исключения (``raise ConnectionError()``) заменяется именем его типа,
        чтобы пользователь не увидел пустое окно ошибки.
        """
        try:
            result = self._operation()
        except Exception as exc:
            self.error.emit(str(exc) or type(exc).__name__)
            return
        self.finished.emit(int(result))


class DownloadThread(YaDiskThread):
    """
    Поток скачивания файла с Яндекс.Диска (``yadisk_download_file``).

    Attributes:
        remote_path (str): Путь к файлу на Диске.
        local_path (str): Куда сохранить локально.
    """

    def __init__(
        self,
        token: str, # OAuth-токен
        remote_path: str, # путь к файлу на Диске
        local_path: str, # куда сохранить локально
        parent: Optional[QObject] = None, # родитель Qt
    ):
        """
        Args:
            token (str): OAuth-токен.
            remote_path (str): Путь к файлу на Диске.
            local_path (str): Локальный путь.
            parent (Optional[QObject]): Родитель Qt.
        """
        super().__init__(token=token, parent=parent)
        self.remote_path = remote_path
        self.local_path = local_path

    def _operation(self) -> int:
        """
        Скачивание; ошибки (нет файла, папка, токен, сеть) — исключением в ``error``.

        Returns:
            int: Код результата (``0`` — успех).
        """
        return yadisk_download_file(
            ya_token=self.token, # токен
            ya_file_path=self.remote_path, # откуда
            local_file_path=self.local_path, # куда
            if_err=True, # ошибки — исключением (→ сигнал error с понятным текстом)
            progress_callback=self._progress_callback, # прогресс → сигнал progress
        )


class UploadThread(YaDiskThread):
    """
    Поток загрузки файла на Яндекс.Диск (``yadisk_upload_file``).

    Attributes:
        local_path (str): Локальный файл.
        remote_path (str): Путь файла на Диске.
        overwrite (bool): Заменять файл на Диске, если он уже есть.
    """

    def __init__(
        self,
        token: str, # OAuth-токен
        local_path: str, # локальный файл
        remote_path: str, # путь файла на Диске
        parent: Optional[QObject] = None, # родитель Qt
        overwrite: bool = False, # заменить файл на Диске, если он уже есть
    ):
        """
        Args:
            token (str): OAuth-токен.
            local_path (str): Локальный файл.
            remote_path (str): Путь на Диске.
            parent (Optional[QObject]): Родитель Qt.
            overwrite (bool): Заменять существующий файл.
        """
        super().__init__(token=token, parent=parent)
        self.local_path = local_path
        self.remote_path = remote_path
        self.overwrite = overwrite

    def _operation(self) -> int:
        """
        Загрузка; ошибки — исключением в ``error``.

        Returns:
            int: Код результата (``0`` — успех).
        """
        return yadisk_upload_file(
            ya_token=self.token, # токен
            local_file_path=self.local_path, # что
            ya_file_path=self.remote_path, # куда
            if_err=True, # ошибки — исключением (→ сигнал error)
            overwrite=self.overwrite, # заменить существующий
            progress_callback=self._progress_callback, # прогресс → сигнал progress
        )


# ↓ до rework-yadisk, проход 1 (2026-10-21): прежняя реализация потоков (T1 — дублирование
#   кода двух потоков, двойная проверка токена/файла при скачивании).
#
# # import os
# from PySide6.QtCore import QThread, Signal # pip install PySide6
#
# from app.network.ya_dop import (
#     check_remote_file_exists, # проверка файла на Диске перед скачиванием (DownloadThread.run)
#     yadisk_download_file,
#     yadisk_upload_file,
# )
# # from app.network.ya_dop import yadisk_download_file, yadisk_upload_file
# # ↑ до rework-yadisk (2026-10-21): check_remote_file_exists не импортировалась — DownloadThread.run
# #   сразу падал с «name 'check_remote_file_exists' is not defined», скачивание БД не работало.
#
# class DownloadThread(QThread):
#     """
#     Поток для скачивания файла с Диска.
#     Сигналы:
#         progress(current, total): обновление прогресса
#         finished(code): код завершения (0 - успех)
#         error(message): сообщение об ошибке
#     """
#     progress = Signal(int, int)
#     finished = Signal(int)
#     error = Signal(str)
#
#     def __init__(
#         self, 
#         token: str, 
#         remote_path: str, 
#         local_path: str, 
#         parent=None
#     ):
#         """
#         Инициализация потока для скачивания файла с Диска.
#
#         :param token: (str) OAuth-токен для авторизации.
#         :param remote_path: (str) Путь к файлу на Яндекс.Диске.
#         :param local_path: (str) Локальный путь для сохранения файла.
#         :param parent: (QObject/None) Родительский объект (по умолчанию None).
#         """
#
#         super().__init__(parent)
#
#         # сохраняем параметры для использования в run
#         self.token = token
#         self.remote_path = remote_path
#         self.local_path = local_path
#
#     def _progress_callback(self, current: int, total: int):
#         """Колбэк для передачи прогресса в сигнал."""
#         self.progress.emit(current, total)
#
#     def run(self):
#         """
#         Запуск потока для скачивания файла с Диска.
#
#         В этом методе происходит вызов функции yadisk_download_file с параметрами,
#         сохраненными в __init__. Если функция работает успешно, то сигнал finished
#         эмити код завершения (0 - успех), а если возникла ошибка, то сигнал error
#         эмити сообщение об ошибке.
#         """
#         try:
#             # Проверяем существование файла на Яндекс.Диске
#             exists, msg = check_remote_file_exists(self.token, self.remote_path)
#             if not exists:
#                 self.error.emit(msg)
#                 return
#
#             # Вызов функции скачивания файла с Диска
#             result = yadisk_download_file(
#                 # Токен для авторизации
#                 ya_token=self.token,
#                 # Путь к файлу на Яндекс.Диске
#                 ya_file_path=self.remote_path,
#                 # Локальный путь для сохранения файла
#                 local_file_path=self.local_path,
#                 # Выводить ошибки (True) или метки на ошибки (False)
#                 if_err=True,
#                 # Колбэк для передачи прогресса
#                 progress_callback=self._progress_callback
#             )
#             # Сигнал, эмитирующий код завершения (0 - успех)
#             self.finished.emit(result)
#         except Exception as e:
#             # Сигнал, эмитирующий сообщение об ошибке
#             self.error.emit(str(e))
#
#
# class UploadThread(QThread):
#     """
#     Поток для загрузки файла на Диск.
#     Сигналы:
#         progress(current, total): обновление прогресса
#         finished(code): код завершения (0 - успех)
#         error(message): сообщение об ошибке
#     """
#     progress = Signal(int, int)
#     finished = Signal(int)
#     error = Signal(str)
#
#     def __init__(
#         self, 
#         token: str, 
#         local_path: str, 
#         remote_path: str, 
#         parent=None, 
#         overwrite = False,
#     ):
#         """
#         Инициализация потока для загрузки файла на Диск.
#
#         :param token: (str) OAuth-токен для авторизации.
#         :param local_path: (str) Локальный путь к файлу, который будет загружен на Диск.
#         :param remote_path: (str) Путь к файлу на Яндекс.Диске, куда будет загружен файл.
#         :param parent: (QObject/None) Родительский объект (по умолчанию None).
#         """
#         super().__init__(parent)
#         # сохраняем параметры для использования в run
#         self.token = token
#         self.local_path = local_path
#         self.remote_path = remote_path
#         self.overwrite = overwrite
#
#     def _progress_callback(self, current: int, total: int):
#         """
#         Колбэк для передачи прогресса загрузки файла на Диск.
#         Эмитируется изнутри функции run в потоке UploadThread.
#
#         :param current: (int) Текущее значение прогресса (например, количество байт, уже переданных на Диск).
#         :param total: (int) Общее количество байт, которое будет передано на Диск.
#         """
#         self.progress.emit(current, total)
#
#     def run(self):
#         """
#         Запуск потока для загрузки файла на Диск.
#         Функция run вызывает функцию yadisk_upload_file с параметрами,
#         сохраненными в __init__, и передает прогресс загрузки
#         в колбэк _progress_callback.
#         Если возникнет какая-либо ошибка, то сообщение об ошибке
#         передается в колбэк error.
#         """
#         try:
#             # вызов функции yadisk_upload_file с параметрами,
#             # сохраненными в __init__
#             result = yadisk_upload_file(
#                 ya_token=self.token,
#                 local_file_path=self.local_path,
#                 ya_file_path=self.remote_path,
#                 if_err=True,
#                 overwrite=self.overwrite,
#                 progress_callback=self._progress_callback
#             )
#             # передача результата в колбэк finished
#             self.finished.emit(result)
#         except Exception as e:
#             # передача сообщения об ошибке в колбэк error
#             self.error.emit(str(e))
#
#
#
#
# if __name__ == '__main__':
#     
#
#     # def update_progress( current, total):
#     #     progress_bar.setMaximum(total)
#     #     progress_bar.setValue(current)
#
#     # def on_download_finished( code):
#     #     if code == 0:
#     #         status_label.setText("Скачивание завершено")
#     #     else:
#     #         status_label.setText(f"Ошибка {code}")
#
#     # def on_error( message):
#     #     status_label.setText(f"Ошибка: {message}")
#
#     # download_thread = DownloadThread(
#     #     token="ваш_токен",
#     #     remote_path="/Проекты/отчёт.xlsx",
#     #     local_path="./отчёт.xlsx",
#     #     parent=self
#     # )
#
#     # download_thread.progress.connect(update_progress)
#     # download_thread.finished.connect(on_download_finished)
#     # download_thread.error.connect(on_error)
#     # download_thread.start()
#     pass
