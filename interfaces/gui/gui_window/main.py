# interfaces/gui/gui_window/main.py

"""
Точка входа в графическое приложение.
Запускает главное окно, инициализирует необходимые компоненты.
"""
import os
import sys
# import os

# Добавляем корень проекта в sys.path, чтобы импортировать app.*
# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.utils.logger.logger import AppLogger

# from interfaces.gui.gui_window.main_window import MainWindow

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

def disable_loggers_for_dev_mode():
    """Применяет настройки отключения логгеров в режиме разработки."""
    # if os.getenv('DEV_MODE', '').lower() not in ('1', 'true', 'yes'):
    #     return

    # Список имён логгеров, которые нужно полностью отключить
    disabled = [
        # 'system',
        #         # 'user',
        #         # 'dependencies.py',
        #         # 'virtual_fields.py',
        #         # 'compute_fields.py',
        #         # 'filter_converter.py',
        # 'api',

        "virtual_fields.py",
        "compute_virtual_fields",
        "enrich_dto_with_computed_fields",
        "PhotoUploaderWidget",
        "DynamicEditForm",
        "DynamicEditPage",
        "FilterBar",
        "FilterColumnDialog",
        "TextPopupDelegate",
        "CompleterStringDelegate",
        "DateEditWidget",
        "WidgetFactory",
        "SettingsPage",
        "UpdateChecker",
        "api.virtual_fields.py",
        "AppUpdater",
        "AsyncImageLoader",
        "PhotoDelegate",


        "ImageThumbnailDelegate",
        "PhotoDelegate",
        "TextEditDelegate",
        "TextPopupDelegate",
        "StringDelegate",
        "DatePickerDelegate",
        "ComboBoxDelegate",
        "CompleterStringDelegate",
        "BoolDelegate",
        "TimePickerDelegate",

        "AsyncImageLoader",
        "PhotoUploaderWidget",
        "PhotoEditDialog",
        "LogViewer",
        "LogViewerHandler",
        "file_deletions.py",
        "LoadPageThread",
        "DynamicEditPage",
        "DynamicEditForm",
        # "UIMixin",
        "FilterMixin",
        "ControllerMixin",
        "BaseRepository",
        "PhotoRepository",
        "NoteService",
        "PatientService",
        # "AppointmentService",
        # "MainWindow",
        "PageManager",
        "UpdateChecker",
        "AppUpdater",
        "ParsingProgressDialog",
        "ParsingThread",
        "InstructionsDialog",

        "SelectionMixin",
        "gui_helpers.py",
        "UIMixin",
        "SelectionPaginationMixinMixin",
        "ActionManager",
        "EditModeMixin",
        "filtering.py",
        "gui.PaginatedTableModel",
        

        # "gui.PaginatedTableModel",
        # ... добавьте свои
    ]
    for name in disabled:
        AppLogger.add_disabled_logger(name)

    # # Дополнительно можно отключить консоль для групп (но не файл)
    # AppLogger.disable_group_console('gui.PaginatedTableModel.')
    # AppLogger.disable_group_console('gui.PaginationMixin.')

    # AppLogger.on_show_call_depth_global()

@AppLogger.get_instance(
    name = 'main.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    description="main",
    level=AppLogger._parse_log_level('DEBUG')
)
def main():
    """Главная функция запуска GUI."""
    disable_loggers_for_dev_mode()

    # Настройка High DPI (должна быть до создания QApplication)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)

    # Загружаем стили (если есть)
    # with open("interfaces/gui_window/resources/styles.qss", "r") as f:
    #     app.setStyleSheet(f.read())

    # Создаём главное окно

    from interfaces.gui.gui_window.main_window import MainWindow # тут, так как должно быть после создания QApplication
    window = MainWindow()
    window.show()

    # Логируем запуск
    logger = AppLogger.get_instance(
        name = 'gui',
        # share_file_with = 'user',
        enable_file_logging = 'user',
        use_name_in_filename = False, # 'user',
    )
    logger.info("GUI приложение запущено")

    sys.exit(app.exec())

if __name__ == "__main__":
    main()