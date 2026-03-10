# pip install PySide6 
from PySide6.QtWidgets import QMainWindow, QToolBar, QStatusBar, QProgressBar, QStackedWidget, QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Медицинская клиника")
        self.resize(1200, 800)

        # Шапка (тулбар)
        toolbar = QToolBar("Главная панель")
        self.addToolBar(toolbar)

        # Кнопки в шапке
        btn_download = toolbar.addAction("Скачать БД")
        btn_save = toolbar.addAction("Сохранить")
        btn_upload = toolbar.addAction("Отправить на сервер")
        toolbar.addSeparator()
        btn_settings = toolbar.addAction("Настройки")

        # Прогресс в статус-баре
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(200)
        self.progress.setVisible(False)
        status_bar.addPermanentWidget(self.progress)

        # Центральный виджет – стек страниц
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # Панель навигации (хлебные крошки и кнопка назад)
        nav_widget = QWidget()
        nav_layout = QHBoxLayout(nav_widget)
        nav_layout.setContentsMargins(5, 0, 5, 0)
        self.btn_back = QPushButton("← Назад")
        self.btn_back.clicked.connect(self.go_back)
        nav_layout.addWidget(self.btn_back)
        self.breadcrumbs = QLabel()
        nav_layout.addWidget(self.breadcrumbs)
        nav_layout.addStretch()

        # Добавляем навигацию в тулбар (можно вторую строку или в основной)
        # Проще создать отдельный виджет и добавить его в layout окна, но для простоты
        # поместим в тулбар как виджет
        toolbar.addWidget(nav_widget)

        # Стек истории переходов
        self.history = []  # список идентификаторов страниц (или самих виджетов)