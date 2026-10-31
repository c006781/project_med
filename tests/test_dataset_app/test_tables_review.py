# tests/test_dataset_app/test_tables_review.py

"""
Находки сверки ``app/tables`` и ``app/dataset_app`` (2026-10-31). Каждый тест падает на
коде до исправления.
"""

from app.tables import CLINIC, TableRegistry


def test_ts1_build_state_not_kept_on_shared_registry(services, providers):
    """TS1: кеши текстов ссылок сборки жили на общем реестре (CLINIC) — держались после сборки."""
    reg = TableRegistry([CLINIC.get(n) for n in CLINIC.names()] + [CLINIC.get(n) for n in CLINIC.shared_names()])
    first = reg.build(services=providers)
    assert not hasattr(reg, '_text_caches')
    second = reg.build(services=providers)
    first.open(); second.open()
    assert first.patients.fields['description_id'].display is not second.patients.fields['description_id'].display
    first.close(); second.close()
