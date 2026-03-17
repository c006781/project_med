import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from app.exceptions import PhotoFileError, PhotoNotFoundError

import logging
# def test_photo_service_missing_file_on_disk(photo_service, sample_photo, db_session, caplog):
#     # Файл не существует
#     # Убедимся, что путь в sample_photo указывает на несуществующий файл
#     # В фикстуре sample_photo мы создавали файл, но можно его удалить
#     full_path = Path(photo_service._storage_path) / sample_photo.file_path
#     if full_path.exists():
#         full_path.unlink()

#     with caplog.at_level('WARNING'):
#         photos = photo_service.get_photos_for_appointment(sample_photo.appointment_id)

#     assert len(photos) == 1
#     assert photos[0].id == sample_photo.id

#     # Проверяем наличие предупреждения в логе
#     warning_messages = [record.message for record in caplog.records if record.levelname == 'WARNING']
#     assert any(
#         "отсутствует на диске" in msg for msg in warning_messages
#     ), f"Предупреждение не найдено. Логи: {caplog.text}"
    
#     # # Проверяем, что было предупреждение в логе
#     # assert any("отсутствует на диске" in record.message for record in caplog.records)

# def test_photo_service_missing_file_on_disk(photo_service, sample_photo, db_session, caplog):
#     full_path = Path(photo_service._storage_path) / sample_photo.file_path
#     if full_path.exists():
#         full_path.unlink()

#     # Указываем имя логгера (можно взять из экземпляра)
#     with caplog.at_level(logging.WARNING, logger=photo_service.logger.name):
#         photos = photo_service.get_photos_for_appointment(sample_photo.appointment_id)

#     assert len(photos) == 1
#     assert photos[0].id == sample_photo.id

#     # Ищем в записях caplog (не только по уровню, так как мы уже ограничили уровень)
#     warning_messages = [record.message for record in caplog.records]
#     assert any("отсутствует на диске" in msg for msg in warning_messages), "Предупреждение не найдено"

# def test_photo_service_missing_file_on_disk(photo_service, sample_photo, db_session, capsys):
#     full_path = Path(photo_service._storage_path) / sample_photo.file_path
#     if full_path.exists():
#         full_path.unlink()

#     photos = photo_service.get_photos_for_appointment(sample_photo.appointment_id)

#     assert len(photos) == 1
#     assert photos[0].id == sample_photo.id

#     captured = capsys.readouterr()
#     assert "отсутствует на диске" in captured.err

# def test_photo_service_missing_file_on_disk(photo_service, sample_photo, db_session, caplog):
#     full_path = Path(photo_service._storage_path) / sample_photo.file_path
#     if full_path.exists():
#         full_path.unlink()

#     # Временно разрешаем propagate, чтобы caplog мог перехватить сообщения
#     logger = photo_service.logger
#     old_propagate = logger.propagate
#     logger.propagate = True
#     caplog.clear()
    
#     with caplog.at_level(logging.WARNING):
#         photos = photo_service.get_photos_for_appointment(sample_photo.appointment_id)
    
#     logger.propagate = old_propagate

#     assert len(photos) == 1
#     assert photos[0].id == sample_photo.id

#     warning_messages = [record.message for record in caplog.records if record.levelname == 'WARNING']
#     assert any("отсутствует на диске" in msg for msg in warning_messages), "Предупреждение не найдено" 

def test_photo_service_missing_file_on_disk(photo_service, sample_photo, db_session, caplog):
    """
    Тест на отсутствие файла на диске при получении фото по приёму.

    Проверяет, что при отсутствии файла на диске будет выдано предупреждение в логе.
    """
    full_path = Path(photo_service._storage_path) / sample_photo.file_path
    if full_path.exists():
        full_path.unlink()

    std_logger = photo_service.logger.logger  # стандартный логгер
    old_propagate = std_logger.propagate
    std_logger.propagate = True
    caplog.clear()

    with caplog.at_level(logging.WARNING):
        photos = photo_service.get_photos_for_appointment(sample_photo.appointment_id)

    std_logger.propagate = old_propagate

    assert len(photos) == 1
    assert photos[0].id == sample_photo.id

    warning_messages = [record.message for record in caplog.records if record.levelname == 'WARNING']
    assert any("отсутствует на диске" in msg for msg in warning_messages), "Предупреждение не найдено"


def test_photo_service_generate_target_path(photo_service):
    """
    Тест на генерацию пути к файлу фотографии.

    Проверяет, что при вызове _generate_target_path будет сгенерирован путь в формате
    <storage>/app_<app_id>/<photo_id>_test_image_<8hex>.jpg
    """
    source = "/tmp/test_image.jpg"
    app_id = 123
    photo_id = 456
    path = photo_service._generate_target_path(source, app_id, photo_id)
    # Ожидаемый формат: <storage>/app_123/456_test_image_<8hex>.jpg
    storage = photo_service._storage_path
    assert path.startswith(os.path.join(storage, f"app_{app_id}"))
    filename = os.path.basename(path)
    assert filename.startswith(f"{photo_id}_test_image_")
    assert filename.endswith(".jpg")
    # assert len(filename.split('_')[2]) == 8  # уникальный идентификатор
    assert len(filename.split('_')[3].split('.')[0]) == 8  # уникальный идентификатор

def test_photo_service_delete_photo_file_missing(photo_service, sample_photo, db_session):
    # Удаляем файл вручную перед вызовом delete
    """
    Тест на удаление файла фотографии, если файла не существует на диске.

    Проверяет, что при отсутствии файла на диске удаление записи пройдёт успешно.
    """
    full_path = Path(photo_service._storage_path) / sample_photo.file_path
    if full_path.exists():
        full_path.unlink()
    # Удаление записи должно пройти успешно (файла нет)
    photo_service.delete_photo(sample_photo.id)
    db_session.commit()
    with pytest.raises(PhotoNotFoundError):
        photo_service.get_by_id(sample_photo.id)