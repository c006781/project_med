# tests/test_config/test_review_pass4.py

"""
Тесты исправлений проверки модуля конфигурации, проход 4 (2026-10-15).

Номера (AP7, CLI1) — журнал проверок в ``app/config/IMPLEMENTATION.md`` §6.
"""

import logging
import os

import pytest


@pytest.fixture
def applier_with_logger_state(monkeypatch):
    """
    ConfigApplier без __init__ и подмена AppLogger: текущий конфиг логгеров задаётся
    тестом, вызовы configure() собираются в список.
    """
    import app.config.config_applier as ca
    state = {'current': {}, 'configured': []}
    monkeypatch.setattr(ca.AppLogger, 'current_app_config',
                        classmethod(lambda cls: dict(state['current'])))
    monkeypatch.setattr(ca.AppLogger, 'configure',
                        classmethod(lambda cls, cfg: state['configured'].append(cfg)))
    a = ca.ConfigApplier.__new__(ca.ConfigApplier)
    a.logger = logging.getLogger('test.applier')
    return a, state


def test_ap7_personal_level_change_applied(applier_with_logger_state):
    """AP7: изменённый персональный уровень (<имя>_LEVEL) применяется."""
    a, state = applier_with_logger_state
    state['current'] = {'LOG_LEVEL': 'INFO', 'ConfigApplier_LEVEL': 'DEBUG'}
    assert a.apply_logging({'LOG_LEVEL': 'INFO', 'ConfigApplier_LEVEL': 'ERROR'}) is True
    assert len(state['configured']) == 1


def test_ap7_personal_level_removed_applied(applier_with_logger_state):
    """AP7: персональный уровень удалён из файла — тоже изменение."""
    a, state = applier_with_logger_state
    state['current'] = {'LOG_LEVEL': 'INFO', 'ConfigApplier_LEVEL': 'ERROR'}
    assert a.apply_logging({'LOG_LEVEL': 'INFO'}) is True


def test_ap7_nothing_changed(applier_with_logger_state):
    """AP7 не даёт ложных срабатываний: всё совпадает — configure не вызывается."""
    a, state = applier_with_logger_state
    cfg = {'LOG_LEVEL': 'INFO', 'ConfigApplier_LEVEL': 'ERROR', 'system_LEVEL': 'DEBUG'}
    state['current'] = dict(cfg)
    assert a.apply_logging(dict(cfg)) is False
    assert state['configured'] == []


def test_cli1_apply_settings_reports_errors():
    """CLI1: команда apply_settings проверяет applier.errors, а не печатает «применены» всегда."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    text = open(os.path.join(root, 'interfaces/cli/cli.py'), encoding='utf-8').read()
    body = text[text.index('def apply_settings'):]
    body = body[:body.index('@cli.command()')]
    code = '\n'.join(l for l in body.splitlines() if not l.strip().startswith('#'))
    assert 'if applier.errors:' in code
