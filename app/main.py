#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Главное окно приложения.
"""



# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).


# Импорты ваших модулей

# def _add_package_name(
#     file_module: str = None,
#     levels_up: int = 3,           # <-- сколько уровней вверх до корня проекта
# ) -> None:
    
#     """
#     Что это (кратко): Добавляет корень проекта в sys.path и устанавливает правильный __package__.

#     Что это (максимально подробно): Эта функция настраивает окружение Python таким образом, чтобы можно было использовать относительные импорты (например, from .module import something) без необходимости запускать скрипт с флагом "-m" (как модуль). Она работает только если скрипт запущен напрямую (не импортирован). Функция получает абсолютный путь к текущему файлу, добавляет родительскую директорию в sys.path (список путей для поиска модулей), и устанавливает глобальную переменную __package__ как имя текущей директории. Это полезно в проектах с nested папками, где импорты могут сломаться.

#     Как работает: Сначала объявляется global __package__ для изменения системной переменной. Затем os.path.abspath(__file__) дает полный путь к скрипту, os.path.dirname убирает имя файла, оставляя папку. sys.path.append добавляет родительскую папку (dirname еще раз). Наконец, __package__ = basename(package_dir) — имя папки. Вызывается только в if __name__ == '__main__', чтобы не мешать, если скрипт импортирован.

#     Примеры запуска:
#     # В скрипте: if __name__ == '__main__': _add_package_name()
#     # После вызова: sys.path включает родительскую папку (например, '/path/to/modules'), __package__ = 'parsers_sheregeh'. Теперь относительные импорты работают.
#     # Если запустить как модуль (python -m script), функция не нужна, но она не навредит.
#     # Если не вызвать: относительный импорт from .module... может вызвать ImportError: attempted relative import with no known parent package.

#     :param file_module: (str) = обычно __file__  - указатель на путь к модулю, папку которого делаем пакетом для относительных импортов (содержит путь к текущему скрипту)
#     :param levels_up: (int) - на сколько уровней подниматься вверх до корня проекта
#                        (подберите под структуру вашего проекта)
#                        Примеры:
#                          2 → до папки app
#     """
#     if file_module is None:
#         file_module = __file__

#     # Получаем директорию текущего файла
#     current_dir = os.path.dirname(os.path.abspath(file_module))

#     # Поднимаемся на levels_up уровней вверх — это и будет корень проекта
#     project_root = current_dir
#     for _ in range(levels_up):
#         project_root = os.path.dirname(project_root)

#     # Добавляем корень проекта в начало sys.path (высокий приоритет)
#     if project_root not in sys.path:
#         sys.path.insert(0, project_root)

#     # Вычисляем правильное значение __package__
#     # Пример: /project_med/app/models/bd → "app.models.bd"
#     rel_path = os.path.relpath(current_dir, project_root)
    
#     if rel_path == '.':
#         package_name = ''
#     else:
#         package_name = rel_path.replace(os.sep, '.').strip('.')

#     # Устанавливаем __package__
#     global __package__
#     if package_name:
#         __package__ = package_name
#     else:
#         # Если мы в корне — можно оставить None или пустую строку
#         __package__ = None


# temp_from = 'app.controllers.conf.getenv'.split('.')
# temp_from = {
#     '.'.join(temp_from[x:]) for x in range(len(temp_from))
# }

# if len(
#     set(sys.modules.keys()).intersection(temp_from)
# ) == 0:
#     try:
#         from .controllers.conf.getenv import get_getenv as get_getenv
#     except ImportError as e:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(
#             file_module = __file__,
#             levels_up = 1,
#             # path_join = [
                
#             # ] + [
#             #     '.' for _ in range(1) # насколько шагов назад нужно
#             # ],
#         )

#         from .controllers.conf.getenv import get_getenv as get_getenv
# del temp_from

# temp_from = 'app.controllers.conf.get_config'.split('.')
# temp_from = {
#     '.'.join(temp_from[x:]) for x in range(len(temp_from))
# }

# if len(
#     set(sys.modules.keys()).intersection(temp_from)
# ) == 0:
#     try:
#         from .controllers.conf.get_config import get_config_env as get_config_env
#     except ImportError as e:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(
#             file_module = __file__,
#             levels_up = 3
#         )
#         from .controllers.conf.get_config import get_config_env as get_config_env
# del temp_from

# temp_from = 'app.network.thread_network'.split('.')
# temp_from = {
#     '.'.join(temp_from[x:]) for x in range(len(temp_from))
# }

# if len(
#     set(sys.modules.keys()).intersection(temp_from)
# ) == 0:
#     try:
#         from .network.thread_network import UploadThread , DownloadThread
#     except ImportError as e:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(
#             file_module = __file__,
#             levels_up = 1,
#             # path_join = [
                
#             # ] + [
#             #     '.' for _ in range(1) # насколько шагов назад нужно
#             # ],
#         )

#         from .network.thread_network import UploadThread , DownloadThread
# del temp_from




# Импорты модулей
def _add_package_name(
    file_module: str = None,
    levels_up: int = 3,           # <-- сколько уровней вверх до корня проекта
) -> None:
    
    """
    Что это (кратко): Добавляет корень проекта в sys.path и устанавливает правильный __package__.

    Что это (максимально подробно): Эта функция настраивает окружение Python таким образом, чтобы можно было использовать относительные импорты (например, from .module import something) без необходимости запускать скрипт с флагом "-m" (как модуль). Она работает только если скрипт запущен напрямую (не импортирован). Функция получает абсолютный путь к текущему файлу, добавляет родительскую директорию в sys.path (список путей для поиска модулей), и устанавливает глобальную переменную __package__ как имя текущей директории. Это полезно в проектах с nested папками, где импорты могут сломаться.

    Как работает: Сначала объявляется global __package__ для изменения системной переменной. Затем os.path.abspath(__file__) дает полный путь к скрипту, os.path.dirname убирает имя файла, оставляя папку. sys.path.append добавляет родительскую папку (dirname еще раз). Наконец, __package__ = basename(package_dir) — имя папки. Вызывается только в if __name__ == '__main__', чтобы не мешать, если скрипт импортирован.

    Примеры запуска:
    # В скрипте: if __name__ == '__main__': _add_package_name()
    # После вызова: sys.path включает родительскую папку (например, '/path/to/modules'), __package__ = 'parsers_sheregeh'. Теперь относительные импорты работают.
    # Если запустить как модуль (python -m script), функция не нужна, но она не навредит.
    # Если не вызвать: относительный импорт from .module... может вызвать ImportError: attempted relative import with no known parent package.

    :param file_module: (str) = обычно __file__  - указатель на путь к модулю, папку которого делаем пакетом для относительных импортов (содержит путь к текущему скрипту)
    :param levels_up: (int) - на сколько уровней подниматься вверх до корня проекта
                       (подберите под структуру вашего проекта)
                       Примеры:
                         2 → до папки app
    """
    if file_module is None:
        file_module = __file__

    # Получаем директорию текущего файла
    current_dir = os.path.dirname(os.path.abspath(file_module))

    # Поднимаемся на levels_up уровней вверх — это и будет корень проекта
    project_root = current_dir
    for _ in range(levels_up):
        project_root = os.path.dirname(project_root)

    # Добавляем корень проекта в начало sys.path (высокий приоритет)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Вычисляем правильное значение __package__
    # Пример: /project_med/app/models/bd → "app.models.bd"
    rel_path = os.path.relpath(current_dir, project_root)
    
    if rel_path == '.':
        package_name = ''
    else:
        package_name = rel_path.replace(os.sep, '.').strip('.')

    # Устанавливаем __package__
    global __package__
    if package_name:
        __package__ = package_name
    else:
        # Если мы в корне — можно оставить None или пустую строку
        __package__ = None


# try:
    # from .controllers.conf.get_config import get_config_env
from app.config.config_manager.manager import get_config_env
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 0)
#         # from .controllers.conf.get_config import get_config_env
#         from .controllers.config_manager.manager import get_config_env
#     except ImportError as e:
#         pass #  raise # e # pass

# try:
from app.network.thread_network import UploadThread , DownloadThread
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 0)
#         from .network.thread_network import UploadThread , DownloadThread
#     except ImportError as e:
#         pass #  raise # e # pass



# from .controllers.getenv.get_config import get_config_env
# from .network.thread_network import DownloadThread, UploadThread

# Добавляем корень проекта в sys.path, чтобы импорты работали
# (если вы запускаете main.py напрямую)
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Импорты PySide6
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QToolBar, QStatusBar, QProgressBar, QLabel,
    QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Настройки окна
        self.setWindowTitle("Медицинская клиника")
        self.resize(1200, 800)

        # Загружаем конфигурацию из .env (пути, токены и т.д.)
        self.config = get_config_env()

        # === 1. Верхняя панель (ToolBar) =================================
        toolbar = QToolBar("Главная панель")
        toolbar.setMovable(False)  # чтобы нельзя было перетащить
        self.addToolBar(toolbar)

        # Кнопки основных действий
        btn_download = QAction("⬇ Скачать БД", self)
        btn_download.triggered.connect(self.on_download_clicked)
        toolbar.addAction(btn_download)

        btn_save = QAction("💾 Сохранить", self)
        btn_save.triggered.connect(self.on_save_clicked)
        toolbar.addAction(btn_save)

        btn_upload = QAction("⬆ Отправить на сервер", self)
        btn_upload.triggered.connect(self.on_upload_clicked)
        toolbar.addAction(btn_upload)

        toolbar.addSeparator()

        btn_settings = QAction("⚙ Настройки", self)
        btn_settings.triggered.connect(self.on_settings_clicked)
        toolbar.addAction(btn_settings)

        # === 2. Панель навигации (хлебные крошки и кнопка назад) =========
        nav_widget = QWidget()
        nav_layout = QHBoxLayout(nav_widget)
        nav_layout.setContentsMargins(5, 0, 5, 0)

        self.btn_back = QPushButton("← Назад")
        self.btn_back.clicked.connect(self.go_back)
        self.btn_back.setEnabled(False)  # сначала неактивна
        nav_layout.addWidget(self.btn_back)

        self.breadcrumbs = QLabel()
        nav_layout.addWidget(self.breadcrumbs)
        nav_layout.addStretch()

        # Добавляем виджет навигации в тулбар (справа от кнопок)
        toolbar.addWidget(nav_widget)

        # === 3. Центральная область — стек страниц =======================
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # Создаём несколько тестовых страниц, чтобы проверить навигацию
        self.create_test_pages()

        # === 4. Статус-бар с прогрессом ==================================
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(200)
        self.progress.setVisible(False)  # изначально скрыт
        status_bar.addPermanentWidget(self.progress)

        # Метка для отображения текущего статуса
        self.status_label = QLabel("Готов")
        status_bar.addWidget(self.status_label)

        # === 5. История навигации ========================================
        self.history = []          # список идентификаторов страниц (или самих виджетов)
        self.current_page_id = 0   # текущая страница (индекс в стеке)

        # Устанавливаем начальную страницу (например, главная)
        self.switch_page(0)

    # ----------------------------------------------------------------------
    # Создание тестовых страниц (для демонстрации навигации)
    # ----------------------------------------------------------------------
    def create_test_pages(self):
        # Страница 0: Пациенты
        page0 = QWidget()
        layout0 = QVBoxLayout(page0)
        layout0.addWidget(QLabel("Здесь будет список пациентов"))
        self.stack.addWidget(page0)

        # Страница 1: Настройки
        page1 = QWidget()
        layout1 = QVBoxLayout(page1)
        layout1.addWidget(QLabel("Здесь будут настройки"))
        self.stack.addWidget(page1)

        # Страница 2: О приложении
        page2 = QWidget()
        layout2 = QVBoxLayout(page2)
        layout2.addWidget(QLabel("Медицинская клиника v0.1"))
        self.stack.addWidget(page2)

        # Можно добавить ещё

    # ----------------------------------------------------------------------
    # Навигация
    # ----------------------------------------------------------------------
    def switch_page(self, index: int, add_to_history: bool = True):
        """
        Переключает стек на страницу с индексом index.
        Если add_to_history True, добавляет текущую страницу в историю.
        """
        if add_to_history and self.stack.currentIndex() != index:
            # Запоминаем текущую страницу перед уходом
            self.history.append(self.stack.currentIndex())
            # Активируем кнопку "Назад"
            self.btn_back.setEnabled(True)

        self.stack.setCurrentIndex(index)
        self.current_page_id = index
        self.update_breadcrumbs()

    def go_back(self):
        """Возврат на предыдущую страницу."""
        if self.history:
            prev_index = self.history.pop()
            self.stack.setCurrentIndex(prev_index)
            self.current_page_id = prev_index
            self.update_breadcrumbs()

        # Если история пуста, деактивируем кнопку
        if not self.history:
            self.btn_back.setEnabled(False)

    def update_breadcrumbs(self):
        """Обновляет текст хлебных крошек (показывает путь от корня до текущей страницы)."""
        # Для простоты показываем только название текущей страницы
        # В реальном проекте можно хранить имена страниц в словаре
        names = ["Пациенты", "Настройки", "О программе"]
        current = self.stack.currentIndex()
        if 0 <= current < len(names):
            self.breadcrumbs.setText(f" / {names[current]}")
        else:
            self.breadcrumbs.setText("")

    # ----------------------------------------------------------------------
    # Обработчики нажатий кнопок в шапке
    # ----------------------------------------------------------------------

    def on_download_clicked(self):
        """Скачивание БД с сервера (Яндекс.Диск)."""
        self.status_label.setText("Скачивание...")
        self.progress.setVisible(True)
        self.progress.setValue(0)

        # Получаем токен из конфига (в .env должен быть YANDEX_TOKEN)
        token = self.config.get('YANDEX_TOKEN', '')
        if not token:
            QMessageBox.warning(self, "Ошибка", "Токен Диска не найден в настройках.")
            self.progress.setVisible(False)
            self.status_label.setText("Готов")
            return

        # Путь на Яндекс.Диске и локальный путь (можно брать из настроек)
        remote_path = self.config.get('database_remote_path', '')
        if not local_path:
            QMessageBox.warning(self, "Ошибка", "Подожение Базы на Диске не найденно в настройках.")
            self.progress.setVisible(False)
            self.status_label.setText("Готов")
            return
        
        local_path = self.config.get('database_local_path', '')
        if not local_path:
            QMessageBox.warning(self, "Ошибка", "Подожение Базы не найденно в настройках.")
            self.progress.setVisible(False)
            self.status_label.setText("Готов")
            return
        
        # Создаём и запускаем поток скачивания
        self.download_thread = DownloadThread(token, remote_path, local_path)
        self.download_thread.progress.connect(self.update_progress)
        self.download_thread.finished.connect(self.on_download_finished)
        self.download_thread.error.connect(self.on_download_error)
        self.download_thread.start()

    def on_save_clicked(self):
        """Сохранение изменений в локальной БД."""
        # Здесь будет логика коммита сессии SQLAlchemy
        self.status_label.setText("Сохранение...")
        QTimer.singleShot(1000, lambda: self.status_label.setText("Готов"))  # заглушка
        QMessageBox.information(self, "Сохранение", "Данные сохранены (заглушка).")

    def on_upload_clicked(self):
        """Отправка локальной БД на сервер."""
        self.status_label.setText("Отправка...")
        self.progress.setVisible(True)
        self.progress.setValue(0)

        

        # Получаем токен из конфига (в .env должен быть YANDEX_TOKEN)
        token = self.config.get('YANDEX_TOKEN', '')
        if not token:
            QMessageBox.warning(self, "Ошибка", "Токен Диска не найден в настройках.")
            self.progress.setVisible(False)
            self.status_label.setText("Готов")
            return

        # Путь на Яндекс.Диске и локальный путь (можно брать из настроек)
        remote_path = self.config.get('database_remote_path', '')
        if not local_path:
            QMessageBox.warning(self, "Ошибка", "Подожение Базы на Диске не найденно в настройках.")
            self.progress.setVisible(False)
            self.status_label.setText("Готов")
            return
        
        local_path = self.config.get('database_local_path', '')
        if not local_path:
            QMessageBox.warning(self, "Ошибка", "Подожение Базы не найденно в настройках.")
            self.progress.setVisible(False)
            self.status_label.setText("Готов")
            return

        self.upload_thread = UploadThread(token, local_path, remote_path)
        self.upload_thread.progress.connect(self.update_progress)
        self.upload_thread.finished.connect(self.on_upload_finished)
        self.upload_thread.error.connect(self.on_upload_error)
        self.upload_thread.start()

    def on_settings_clicked(self):
        """Открыть страницу настроек."""
        # Предположим, страница настроек имеет индекс 1
        self.switch_page(1)

    # ----------------------------------------------------------------------
    # Слоты для работы с потоками и прогрессом
    # ----------------------------------------------------------------------
    def update_progress(self, current, total):
        """Обновление прогресс-бара."""
        self.progress.setMaximum(total)
        self.progress.setValue(current)

    def on_download_finished(self, code):
        """Завершение скачивания."""
        self.progress.setVisible(False)
        if code == 0:
            self.status_label.setText("Скачивание завершено")
            QMessageBox.information(self, "Успех", "База данных успешно скачана.")
        else:
            self.status_label.setText(f"Ошибка скачивания (код {code})")
            QMessageBox.critical(self, "Ошибка", f"Не удалось скачать файл. Код ошибки: {code}")

    def on_download_error(self, message):
        """Ошибка при скачивании."""
        self.progress.setVisible(False)
        self.status_label.setText("Ошибка скачивания")
        QMessageBox.critical(self, "Ошибка", f"Ошибка: {message}")

    def on_upload_finished(self, code):
        """Завершение отправки."""
        self.progress.setVisible(False)
        if code == 0:
            self.status_label.setText("Отправка завершена")
            QMessageBox.information(self, "Успех", "База данных успешно отправлена.")
        else:
            self.status_label.setText(f"Ошибка отправки (код {code})")
            QMessageBox.critical(self, "Ошибка", f"Не удалось отправить файл. Код ошибки: {code}")

    def on_upload_error(self, message):
        """Ошибка при отправке."""
        self.progress.setVisible(False)
        self.status_label.setText("Ошибка отправки")
        QMessageBox.critical(self, "Ошибка", f"Ошибка: {message}")


def main():
    app = QApplication(sys.argv)

    # Загружаем стиль (можно использовать стандартный или свой)
    app.setStyle('Fusion')

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()