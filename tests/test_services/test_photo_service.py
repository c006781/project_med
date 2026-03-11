# tests/test_services/test_photo_service.py


# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).

from datetime import date

# Импорты модулей
# def _add_package_name(
#     file_module: str = None,
#     levels_up: int = 3,           # <-- сколько уровней вверх до корня проекта
# ) -> None:
    
#     """
#     Что это (кратко): Добавляет корень проекта в sys.path и устанавливает правильный __package__.

#     Что это (максимально подробно): Эта функция настраивает окружение Python таким образом, чтобы можно было использовать относительные импорты (например, from .module import something) без необходимости запускать скрипт с флагом "-m" (как модуль). Она работает только если скрипт запущен напрямую (не импортирован). Функция получает абсолютный путь к текущему файлу, добавляет родительскую директорию в sys.path (список путей для поиска модулей), и устанавливает глобальную переменную __package__ как имя текущей директории. Это полезно в проектах с nested папками, где импорты могут сломаться.

#     Как работает: Сначала объявляется global __package__ для изменения системной переменной. Затем os.path.abspath(__file__) дает полный путь к скрипту, os.path.dirname убирает имя файла, оставляя папку. sys.path.append добавляет родительскую папку (dirname еще раз). Наконец, __package__ = basename(package_dir) — имя папки. Вызывается только в if __name__ == '__main__', чтобы не мешать, если скрипт импортирован.

#     Примеры запуска:
#     # В скрипте: if __name__ == '__main__': _add_package_name()
#     # После вызова: sys.path включает родительскую папку (например, '/path/to/modules'), __package__ = 'parsers_sheregeh'. Теперь относительные импорты работают.
#     # Если запустить как модуль (python -m script), функция не нужна, но она не навредит.
#     # Если не вызвать: относительный импорт from .module... может вызвать ImportError: attempted relative import with no known parent package.

#     :param file_module: (str) = обычно __file__  - указатель на путь к модулю, папку которого делаем пакетом для относительных импортов (содержит путь к текущему скрипту)
#     :param levels_up: (int) - на сколько уровней подниматься вверх до корня проекта
#                        (подберите под структуру вашего проекта)
#                        Примеры:
#                          2 → до папки app
#     """
#     if file_module is None:
#         file_module = __file__

#     # Получаем директорию текущего файла
#     current_dir = os.path.dirname(os.path.abspath(file_module))

#     # Поднимаемся на levels_up уровней вверх — это и будет корень проекта
#     project_root = current_dir
#     for _ in range(levels_up):
#         project_root = os.path.dirname(project_root)

#     # Добавляем корень проекта в начало sys.path (высокий приоритет)
#     if project_root not in sys.path:
#         sys.path.insert(0, project_root)

#     # Вычисляем правильное значение __package__
#     # Пример: /project_med/app/models/bd → "app.models.bd"
#     rel_path = os.path.relpath(current_dir, project_root)
    
#     if rel_path == '.':
#         package_name = ''
#     else:
#         package_name = rel_path.replace(os.sep, '.').strip('.')

#     # Устанавливаем __package__
#     global __package__
#     if package_name:
#         __package__ = package_name
#     else:
#         # Если мы в корне — можно оставить None или пустую строку
#         __package__ = None

# try:
#     from ...app.exceptions import AppointmentNotFoundError
# except ImportError:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 3)
#         from ...app.exceptions import AppointmentNotFoundError
#     except ImportError:
#         pass

from app.exceptions import AppointmentNotFoundError


# Сторонние библиотеки

import pytest # pip install pytest

def test_add_photo_to_appointment(photo_service, db_session, sample_patient, tmp_path):
    # Создаём приём
    from app.models.bd.models import Appointment
    app = Appointment(patient_id=sample_patient.id, date=date.today())
    db_session.add(app)
    db_session.commit()

    # Создаём временный файл-картинку
    img_path = tmp_path / "test.jpg"
    img_path.write_bytes(b"fake image content")

    # Добавляем фото
    photo_dto = photo_service.add_photo_to_appointment(
        appointment_id=app.id,
        source_file_path=str(img_path),
        description="Тестовое фото"
    )
    assert photo_dto.id is not None
    assert photo_dto.appointment_id == app.id
    assert photo_dto.description == "Тестовое фото"

    # Проверяем, что файл скопирован в хранилище
    stored_path = os.path.join(photo_service._storage_path, photo_dto.file_path)
    assert os.path.exists(stored_path)
    with open(stored_path, "rb") as f:
        assert f.read() == b"fake image content"

def test_add_photo_to_nonexistent_appointment(photo_service):
    with pytest.raises(AppointmentNotFoundError):
        photo_service.add_photo_to_appointment(9999, "dummy.jpg")