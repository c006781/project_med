# tests/test_schema/test_define_children.py

"""
Ф1.3.1: ``children`` с явным внешним ключом и без каскада (обратная сторона ссылки — как
``AppointmentNote.appointments``), ключ ``init_from_extra`` у поля описания.
"""

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base

from app.schema.define import TableDef, children, column, key


@pytest.fixture()
def two_keys_models():
    """
    Владелец (``owners``) и подчинённые (``items``) с двумя ключами на владельца:
    ``main_id`` — связь с обратной стороной, ``other_id`` — без неё.
    """
    base = declarative_base()
    owners = TableDef(
        'owners',                                   # таблица
        'Owner',                                    # модель
        'OwnerDTO',                                 # DTO
        fields = (
            key(),
            column(
                'text',                             # имя
                sa.Text(),                          # тип
                'Текст',                            # подпись
                nullable        =   False,          # обязательное
                init_from_extra =   'text',         # значение при переходе со страницы
            ),
            children(
                'items',                                    # связь
                'Item',                                     # модель подчинённых
                'main',                                     # связь подчинённых с владельцем
                cascade         =   None,                   # без каскада удаления
                foreign_keys    =   '[Item.main_id]',       # один из двух ключей
                dto             =   False,                  # не в DTO
                config          =   False,                  # не в настройках
            ),
        ),
    )
    owner = owners.build_model(base)

    class Item(base):
        __tablename__ = 'items'
        id = sa.Column(sa.Integer, primary_key=True)
        main_id = sa.Column(sa.Integer, sa.ForeignKey('owners.id'))
        other_id = sa.Column(sa.Integer, sa.ForeignKey('owners.id'))
        main = sa.orm.relationship('Owner', foreign_keys=[main_id])

    base.registry.configure()
    return owners, owner, Item


def test_children_explicit_foreign_key_and_default_cascade(two_keys_models):
    _, owner, _ = two_keys_models
    rel = owner.__mapper__.relationships['items']
    assert sorted(c.name for c in rel._calculated_foreign_keys) == ['main_id']
    assert sorted(rel.cascade) == ['merge', 'save-update']        # каскад SQLAlchemy по умолчанию
    assert rel.back_populates == 'main'
    assert rel.direction.name == 'ONETOMANY'


def test_children_default_cascade_unchanged():
    spec = children('photos', 'Photo', 'appointment', child_dto='PhotoDTO')
    assert spec.cascade == 'all, delete-orphan' and spec.foreign_keys is None


def test_init_from_extra_goes_to_config(two_keys_models):
    owners, _, _ = two_keys_models
    config = owners.build_config()
    assert config['text']['init_from_extra'] == 'text'
    assert 'items' not in config
