# tests/test_schema/test_notes_def.py

"""
Ф1.3.2: модель, DTO и настройки общих заметок строятся из описания ``NOTES``
(app/schema/clinic.py) и совпадают с написанными вручную до 2026-10-30 (снимок
legacy_snapshot_notes.py, снят до переключения).
"""

import pytest
from sqlalchemy.orm import declarative_base

from app.schema.clinic import CLINIC_DEFS, NOTES
from app.schema.define import NOTES_MODEL, NOTES_TABLE

from .legacy_snapshot_notes import SNAPSHOT
from .test_clinic_defs import config_snapshot, dto_snapshot, model_snapshot


@pytest.fixture(scope='module')
def generated_note_model():
    """Модель заметок на своей базе — вместе с таблицами клиники (связь с приёмом)."""
    base = declarative_base()
    # ссылки на классы держать: реестр классов SQLAlchemy хранит их слабо — выброшенные
    # модели удаляет сборщик мусора, и строки связей ('Photo', 'Appointment') не разрешаются
    models = [d.build_model(base) for d in CLINIC_DEFS]
    note = NOTES.build_model(base)
    base.registry.configure()
    yield note
    del models


def test_notes_names_match_note_fields():
    """Поля note() ссылаются на таблицу и модель описания NOTES."""
    assert NOTES.name == NOTES_TABLE and NOTES.model_name == NOTES_MODEL
    assert NOTES not in CLINIC_DEFS                 # не в реестре наборов — ПЛАН Ф1.3.4
    assert NOTES.service == 'get_note_service'


def test_generated_model_same_as_handwritten(generated_note_model):
    assert model_snapshot(generated_note_model) == SNAPSHOT['models']['AppointmentNote']


def test_generated_dto_and_config_same_as_handwritten():
    assert dto_snapshot(NOTES.build_dto()) == SNAPSHOT['dtos']['AppointmentNoteDTO']
    assert config_snapshot(NOTES.build_config()) == SNAPSHOT['configs']['NOTE_CONFIG']


def test_app_uses_generated_note_classes():
    """Приложение: модель, DTO и NOTE_CONFIG — из описания и совпадают со снимком."""
    from app.database.database_shema import clinic as models
    from app.dto import dto_all, field_configs

    model = models.AppointmentNote
    assert model.__module__ == models.__name__
    assert model_snapshot(model) == SNAPSHOT['models']['AppointmentNote']
    assert dto_all.AppointmentNoteDTO.__module__ == dto_all.__name__
    assert dto_snapshot(dto_all.AppointmentNoteDTO) == SNAPSHOT['dtos']['AppointmentNoteDTO']
    assert config_snapshot(field_configs.NOTE_CONFIG) == SNAPSHOT['configs']['NOTE_CONFIG']
    # связь приёма с заметкой и обратная — как были
    appointment_note = models.Appointment.__mapper__.relationships['note']
    assert appointment_note.mapper.class_ is model and appointment_note.back_populates is None
    assert model.__mapper__.relationships['appointments'].mapper.class_ is models.Appointment


def test_note_repr_like_before():
    from app.database.database_shema.clinic import AppointmentNote
    assert repr(AppointmentNote(id=1, text='Первичный осмотр')) == '<Note(id=1, text_preview=Первичный осмотр)>'
    assert repr(AppointmentNote(id=2, text='а' * 31)) == f"<Note(id=2, text_preview={'а' * 30}...)>"
    assert repr(AppointmentNote()) == '<Note(id=None, text_preview=)>'      # без текста — без ошибки


def test_note_dto_accepts_like_before():
    from app.dto import AppointmentNoteDTO
    dto = AppointmentNoteDTO(text='Первичный осмотр')
    assert dto.id is None and dto.text == 'Первичный осмотр'
    with pytest.raises(Exception):
        AppointmentNoteDTO()                                               # текст обязателен
    assert AppointmentNoteDTO.model_config.get('from_attributes') is True
