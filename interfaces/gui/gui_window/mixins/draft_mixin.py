# interfaces/gui/gui_window/mixins/draft_mixin.py

"""
Миксин для управления черновиками заметок и фотографий.
"""

from app.utils.logger.logger import AppLogger
from PySide6.QtCore import QTimer


class DraftMixin:
    """
    Содержит логику сохранения и восстановления черновиков для приёмов.
    Атрибуты (должны быть определены в классе-наследнике):
        _draft_photos: dict[int, dict]   # черновики фото
        _draft_note_text: dict[int, str] # черновики заметок
        _loading_right_panel: bool       # блокировка сигналов при загрузке
        note_text_edit                   # QTextEdit
        photo_widget                     # PhotoUploaderWidget
        selected_dto                     # текущий выбранный DTO
        logger                           # AppLogger
    """

    def _save_current_draft(self) -> None:
        """Сохраняет текущее состояние правой панели в черновики для выбранного приёма."""
        if not self.selected_dto or self.selected_dto.id is None:
            return

        aid = self.selected_dto.id
        # Заметка
        self._draft_note_text[aid] = self.note_text_edit.toPlainText()
        # Фото
        self._draft_photos[aid] = self.photo_widget.dump_state()
        self.logger.debug(f"Сохранён черновик для приёма {aid}: pending={self._draft_photos[aid]['pending_photos']}")

    def _load_draft_for_appointment(self, appointment_id: int, dto) -> None:
        """
        Загружает черновик или свежие данные из БД в правую панель.
        """
        self.logger.info(f"_load_draft_for_appointment для ID={appointment_id}. "
                         f"Есть черновик: {appointment_id in self._draft_photos}")

        self._loading_right_panel = True
        try:
            self.note_text_edit.blockSignals(True)
            self.photo_widget.blockSignals(True)

            # заметка
            note_text = self._draft_note_text.get(appointment_id)
            if note_text is not None:
                self.note_text_edit.setText(note_text)
                self.logger.debug("Загружена заметка из черновика")
            else:
                self.note_text_edit.setText(dto.note_text or "")

            # фото
            if appointment_id in self._draft_photos:
                self.logger.info("Загружаем СОСТОЯНИЕ ИЗ ЧЕРНОВИКА")
                self.photo_widget.load_state(self._draft_photos[appointment_id])
            else:
                self.logger.info("Черновика нет → загружаем свежие фото из БД через set_existing_photos")
                self.photo_widget.set_existing_photos(dto.photos or [])

            self.logger.info(f"_load_draft_for_appointment завершён для {appointment_id}. "
                             f"Строк в таблице фото: {self.photo_widget.table.rowCount() if hasattr(self.photo_widget, 'table') else 'N/A'}")

        finally:
            self.note_text_edit.blockSignals(False)
            self.photo_widget.blockSignals(False)
            self._loading_right_panel = False

    def _on_draft_changed(self):
        """При любом изменении в правой панели обновляем черновик текущего приёма."""
        if not self.edit_mode:
            return
        if not self.selected_dto or self.selected_dto.id is None:
            return
        if self._loading_right_panel:
            return

        self._save_current_draft()
        self._mark_current_row_modified()

    def _clear_drafts(self):
        """Полностью очищает все черновики."""
        self._draft_photos.clear()
        self._draft_note_text.clear()
        self.logger.debug("Черновики очищены")