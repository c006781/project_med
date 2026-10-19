# tests/test_schema/test_clinic_defs.py

"""
Описания таблиц клиники (app/schema/clinic.py) дают те же модели, DTO и field_configs, что
были написаны вручную (снимок legacy_snapshot.py): столбцы, типы, комментарии, индексы,
связи, поля и порядок DTO, настройки полей и их порядок, поведение функций настроек.
"""

from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base

from app.schema.clinic import APPOINTMENTS, CLINIC_DEFS, PATIENTS, PHOTOS
from app.schema.define import rebuild_dtos

from .legacy_snapshot import SNAPSHOT


@pytest.fixture(scope='module')
def generated():
    """Модели (на своей базе, рядом — модель заметок), DTO и настройки из описаний."""
    base = declarative_base()

    class AppointmentNote(base):
        __tablename__ = 'appointments_notes'
        id = sa.Column(sa.Integer, primary_key=True)
        text = sa.Column(sa.Text, nullable=False)

    models = {d.model_name: d.build_model(base) for d in CLINIC_DEFS}
    sa.orm.configure_mappers()
    dtos = {d.dto_name: d.build_dto() for d in CLINIC_DEFS}
    rebuild_dtos(*dtos.values())
    configs = {f'{d.entity.upper()}_CONFIG': d.build_config() for d in CLINIC_DEFS}
    return models, dtos, configs


def model_snapshot(model):
    table = model.__table__
    return {
        'table': table.name,
        'columns': [(c.name, repr(c.type), c.nullable, c.primary_key, sorted(fk.target_fullname for fk in c.foreign_keys),
                     c.comment, c.default is not None) for c in table.columns],
        'indexes': sorted((i.name, tuple(c.name for c in i.columns), i.unique) for i in table.indexes),
        'relationships': sorted((r.key, r.mapper.class_.__name__, r.direction.name, str(sorted(r.cascade)),
                                 r.back_populates, tuple(sorted(c.name for c in r._calculated_foreign_keys)))
                                for r in model.__mapper__.relationships),
    }


def dto_snapshot(dto):
    return [(name, str(f.annotation).replace('typing.', ''), repr(f.default), f.description)
            for name, f in dto.model_fields.items()]


def config_snapshot(config):
    def clean(v):
        if callable(v):
            return '<fn>'
        if isinstance(v, dict):
            return {k: clean(x) for k, x in v.items()}
        return v
    return [(k, clean(v)) for k, v in config.items()]


@pytest.mark.parametrize('name', ['Patient', 'Appointment', 'Photo'])
def test_models_same_as_handwritten(generated, name):
    models, _, _ = generated
    assert model_snapshot(models[name]) == SNAPSHOT['models'][name]


@pytest.mark.parametrize('name', ['PatientDTO', 'AppointmentDTO', 'PhotoDTO'])
def test_dtos_same_as_handwritten(generated, name):
    _, dtos, _ = generated
    got = dto_snapshot(dtos[name])
    expected = SNAPSHOT['dtos'][name]
    # ссылка на DTO фото: у написанного вручную — ForwardRef('PhotoDTO'), у сгенерированного —
    # тоже ссылка по имени; сравниваются имена полей, типы, умолчания, описания
    def normalize(rows):
        return [(n, t.replace("ForwardRef('PhotoDTO')", 'PhotoDTO').replace('app.schema.define.PhotoDTO', 'PhotoDTO')
                 .replace('app.dto.dto_all.PhotoDTO', 'PhotoDTO'), d, s) for n, t, d, s in rows]

    assert normalize(got) == normalize(expected)


@pytest.mark.parametrize('name', ['PATIENT_CONFIG', 'APPOINTMENT_CONFIG', 'PHOTO_CONFIG'])
def test_configs_same_as_handwritten(generated, name):
    _, _, configs = generated
    assert config_snapshot(configs[name]) == SNAPSHOT['configs'][name]


def test_config_functions_behave_the_same(generated):
    _, _, configs = generated
    note = SimpleNamespace(text='аллергия')
    for config in configs.values():
        for field, cfg in config.items():
            if cfg.get('is_note'):
                assert cfg['compute']['func'](note) == 'аллергия' and cfg['compute']['func'](None) is None
    name = configs['APPOINTMENT_CONFIG']['patient_name']['compute']['func']
    assert name(SimpleNamespace(last_name='Петров', first_name='Иван', middle_name=None)) == 'Петров Иван'
    formatter = configs['APPOINTMENT_CONFIG']['has_photos']['sql_compute']['formatter']
    assert formatter(3) == '3 фото' and formatter(0) == '❌'


def test_dto_accepts_like_before(generated):
    _, dtos, _ = generated
    patient = dtos['PatientDTO'](last_name='П', first_name='И')
    assert patient.id is None and patient.birth_date is None
    with pytest.raises(Exception):
        dtos['PatientDTO'](first_name='И')                       # фамилия обязательна
    appointment = dtos['AppointmentDTO'](patient_id=1, date='2026-10-19',
                                         photos=[{'appointment_id': 1, 'file_path': 'a.png'}])
    assert appointment.photos[0].file_path == 'a.png'


def test_each_build_gets_own_config_dicts():
    first, second = PHOTOS.build_config(), PHOTOS.build_config()
    first['description']['width']['stretch'] = False
    assert second['description']['width']['stretch'] is True     # изменение одной копии не задевает другую


def test_definition_errors():
    from app.schema.define import TableDef, key
    with pytest.raises(ValueError, match='повторяется'):
        TableDef('t', 'T', 'TDTO', (key(), key()))
    with pytest.raises(ValueError, match='неизвестные'):
        TableDef('t', 'T', 'TDTO', (key(),), config_order=('nope',)).build_config()
    assert PATIENTS.service == 'get_patient_service' and APPOINTMENTS.entity == 'appointment'
