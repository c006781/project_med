# tests/test_dependencies_review_f1611.py

"""
Сверка модуля ``app.dependencies`` (Ф1.6.11, 2026-10-31): находки DP7, DP8
(``app/DEPENDENCIES.md``). Оба теста на коде до исправления падают.
"""

import app.dependencies as deps


def test_dp7_text_echo_zero_limit_means_no_limit() -> None:
    """DP7: ``if_str_limit=0`` — без ограничения (раньше превращался в 50); None — 50."""
    value = 'x' * 60
    assert deps.get_text_echo(
        {'a': value},           # длинное значение
        if_str_limit   =   0,   # без ограничения
    ) == [f'A: {value}']
    assert deps.get_text_echo(
        {'a': value},           # длинное значение
    ) == [f"A: {'x' * 50}..."]


def test_dp8_create_database_decorated() -> None:
    """DP8: декоратор журнала у ``create_database`` применён (раньше не было «@»)."""
    assert hasattr(deps.create_database, '__wrapped__')
