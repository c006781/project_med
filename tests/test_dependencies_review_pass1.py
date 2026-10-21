# tests/test_dependencies_review_pass1.py

"""
Тесты проверки модуля app.dependencies, проход 1 (2026-10-21).

DP2 — clear_services_cache сбрасывает кэш всех зарегистрированных поставщиков (раньше —
список вручную); DP3 — мёртвый реестр моделей с заметками убран.
"""

from functools import lru_cache

import app.dependencies as deps


def test_dp2_all_registered_providers_cached():
    """Все поставщики сервисов зарегистрированы и кэшируются."""
    names = [provider.__name__ for provider in deps._SERVICE_PROVIDERS]
    assert names == ['get_patient_service', 'get_appointment_service', 'get_note_service', 'get_photo_service']
    assert all(callable(getattr(provider, 'cache_clear', None)) for provider in deps._SERVICE_PROVIDERS)


def test_dp2_new_provider_cleared(monkeypatch):
    """Новый поставщик, помеченный декоратором, тоже сбрасывается — без правки clear_services_cache."""
    monkeypatch.setattr(deps, '_SERVICE_PROVIDERS', [])

    @deps.register_service_provider
    @lru_cache(maxsize=1)
    def get_new_service():
        return object()

    first = get_new_service()
    assert get_new_service() is first
    deps.clear_services_cache()
    assert get_new_service() is not first


def test_dp2_provider_without_cache_ignored(monkeypatch):
    """Поставщик без кэша — пропускается без ошибки."""
    monkeypatch.setattr(deps, '_SERVICE_PROVIDERS', [lambda: object()])
    deps.clear_services_cache()


def test_dp3_dead_note_registry_removed():
    """Реестра моделей с заметками больше нет (не читался с DYN2)."""
    assert not hasattr(deps, '_NOTE_USAGE_MODELS')
    assert not hasattr(deps, 'register_note_model')
