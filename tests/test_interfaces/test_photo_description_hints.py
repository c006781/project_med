# tests/test_interfaces/test_photo_description_hints.py
"""Подсказки описаний фото в окне приёмов: пустые значения не показываются."""

from types import SimpleNamespace

from interfaces.gui.gui_window.pages.appointment_list_page import AppointmentListPage


# страница-заглушка: сервис фото отдаёт заданные значения
def _page(
    values : list,   # значения, которые вернёт сервис
) -> SimpleNamespace:
    return SimpleNamespace(
        photo_service   =   SimpleNamespace(
            get_unique_values   =   lambda field: values,    # имя поля не важно
        ),
    )


def test_none_is_not_a_hint():
    """Фото без описания не даёт подсказку со строкой 'None'."""
    hints = AppointmentListPage._photo_description_hints(
        _page(['снимок', None, 'зуб']),
    )
    assert hints == ['снимок', 'зуб']


def test_values_become_strings():
    """Значения приводятся к строкам, как раньше; пустой список остаётся пустым."""
    assert AppointmentListPage._photo_description_hints(_page([12])) == ['12']
    assert AppointmentListPage._photo_description_hints(_page([])) == []
