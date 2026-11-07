# tests/test_settings_page/test_settings_page_update_check.py
"""
Флажок «Проверять обновления при запуске» на экране настроек.
"""
from app.config.config_manager.manager import UPDATE_CHECK_ON_START_KEY


def test_flag_loaded_and_saved(page):
    """Флажок показывает настройку и записывает bool."""
    page.config_manager[UPDATE_CHECK_ON_START_KEY] = False
    page._load_settings()
    assert page.update_check_on_start_check.isChecked() is False
    page.update_check_on_start_check.setChecked(True)
    page._sawe_new_config()
    assert page.config_manager[UPDATE_CHECK_ON_START_KEY] is True
