# interfaces/gui/gui_window/mixins/patient_info_mixin.py

"""
Миксин для отображения информации о пациенте в верхней панели.
"""

import datetime
# from tkinter import Widget
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QScrollArea, QSizePolicy, QWidget
from PySide6.QtCore import Qt

from app.dto.field_configs import PATIENT_CONFIG
from app.utils.logger.logger import AppLogger


class PatientInfoMixin:
    """
    Создаёт и управляет панелью с данными пациента.
    Атрибуты (должны быть определены в классе-наследнике):
        patient_info_frame: QFrame
        info_value_widgets: dict[str, QLabel]
        current_patient_changed: Signal
        logger: AppLogger
        vertical_splitter: QSplitter (для обновления геометрии)
    """

    def _setup_patient_info_panel(self):
        """Создаёт панель с информацией о пациенте на основе PATIENT_CONFIG."""
        self.patient_info_frame = QFrame()
        self.patient_info_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.patient_info_frame.setMinimumHeight(70)   # минимальная высота
        self.patient_info_frame.setVisible(False)

        layout = QGridLayout(self.patient_info_frame)
        layout.setContentsMargins(5, 5, 5, 5)

        # Область прокрутки
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setMinimumHeight(10)
        layout.addWidget(scroll)

        content_widget = QWidget()
        scroll.setWidget(content_widget)

        grid = QGridLayout(content_widget)
        grid.setSpacing(5)

        self.info_value_widgets = {}
        row = 0

        for field_name, config in PATIENT_CONFIG.items():
            if config.get('hidden', False) or field_name == 'id':
                continue

            title = config.get('title', field_name.replace('_', ' ').title())

            label_title = QLabel(f"{title}:")
            label_title.setStyleSheet("font-weight: bold;")
            label_title.setAlignment(Qt.AlignTop)

            label_value = QLabel()
            label_value.setWordWrap(True)
            label_value.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

            grid.addWidget(label_title, row, 0, alignment=Qt.AlignTop)
            grid.addWidget(label_value, row, 1, alignment=Qt.AlignTop)

            self.info_value_widgets[field_name] = label_value
            row += 1

        grid.setColumnStretch(1, 1)
        grid.setRowStretch(row, 1)

        # Подключаем сигнал изменения пациента (сигнал должен быть определён в основном классе)
        self.current_patient_changed.connect(self._update_patient_info)

    def _update_patient_info(self, patient_dto):
        """
        Обновляет содержимое панели на основе DTO пациента.
        """
        self.logger.debug(f"_update_patient_info called, patient_dto: {patient_dto is not None}")
        if patient_dto:
            data = patient_dto.model_dump(exclude_none=True)
            for field_name, label in self.info_value_widgets.items():
                value = data.get(field_name)
                if value is None:
                    label.setText("—")
                else:
                    if isinstance(value, datetime.date):
                        label.setText(value.isoformat())
                    elif isinstance(value, datetime.time):
                        label.setText(value.strftime("%H:%M"))
                    else:
                        label.setText(str(value))
            self.patient_info_frame.setVisible(True)
            # Обновляем вертикальный сплиттер
            if hasattr(self, 'vertical_splitter'):
                self.vertical_splitter.update()
        else:
            # Очищаем все поля
            for label in self.info_value_widgets.values():
                label.setText("—")
            self.patient_info_frame.setVisible(False)