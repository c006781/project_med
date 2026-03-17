import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from datetime import date, time

from interfaces.cli.cli import create_cli 
#cli, patient, appointment, note, photo, init_db, sync_download, sync_upload, stats, menu
from app.dto import PatientDTO, AppointmentDTO, AppointmentNoteDTO, PhotoDTO
from app.exceptions import (
    PatientNotFoundError, PatientValidationError,
    AppointmentNotFoundError, AppointmentNoteNotFoundError,
    PhotoNotFoundError, PhotoFileError
)

# ----------------------------------------------------------------------
# Фикстуры для моков сервисов
# ----------------------------------------------------------------------

@pytest.fixture
def mock_patient_service():
    """
    Фикстура для замены сервиса пациентов.

    Возвращает экземпляр PatientService, который может быть использован в тестах.
    """
    with patch('interfaces.cli.cli.get_patient_service') as mock:
        service = MagicMock()
        mock.return_value = service
        yield service

@pytest.fixture
def mock_appointment_service():
    """
    Фикстура для замены сервиса приёмов.

    Возвращает экземпляр AppointmentService, который может быть использован в тестах.
    """
    with patch('interfaces.cli.cli.get_appointment_service') as mock:
        service = MagicMock()
        mock.return_value = service
        yield service

@pytest.fixture
def mock_note_service():
    """
    Фикстура для замены сервиса заметок.

    Возвращает экземпляр NoteService, который может быть использован в тестах.
    """
    with patch('interfaces.cli.cli.get_note_service') as mock:
        service = MagicMock()
        mock.return_value = service
        yield service

@pytest.fixture
def mock_photo_service():
    """
    Фикстура для замены сервиса фотографий.

    Возвращает экземпляр PhotoService, который может быть использован в тестах.
    """
    with patch('interfaces.cli.cli.get_photo_service') as mock:
        service = MagicMock()
        mock.return_value = service
        yield service

@pytest.fixture
def mock_sync_service():
    """
    Фикстура для замены сервиса синхронизации с Яндекс.Диском.

    Возвращает экземпляр SyncService, который может быть использован в тестах.
    """
    with patch('interfaces.cli.cli.get_sync_service') as mock:
        service = MagicMock()
        mock.return_value = service
        yield service

@pytest.fixture
def runner():
    """
    Возвращает экземпляр CliRunner, который может быть использован для запуска команд из интерфейса командной строки.
    """
    return CliRunner()

# ----------------------------------------------------------------------
# Тесты команд для пациентов
# ----------------------------------------------------------------------

def test_patient_list_no_filter(runner, mock_patient_service):
    """
    Тест на вывод списка пациентов без фильтрации.

    Описание теста:
    - Mock объект PatientService возвращает список из двух пациентов
    - Затем запускается команда 'patient list' и проверяется, что вывод содержит двух пациентов

    Ожидаемый результат:
    - код возврата команды equals 0
    - вывод содержит двух пациентов
    """
    # Mock объект PatientService возвращает список из двух пациентов
    mock_patient_service.get_patients_filtered.return_value = [
        PatientDTO(
            id=1, 
            first_name="Иван", 
            last_name="Петров", 
            birth_date=date(1990,1,1), 
            phone="123", 
            email="ivan@test.ru"
        ),
        PatientDTO(
            id=2, 
            first_name="Мария", 
            last_name="Иванова", 
            birth_date=date(1985,5,5), 
            phone="456", 
            email="maria@test.ru"
        ),
    ]

    # Затем запускается команда 'patient list' и проверяется, что вывод содержит двух пациентов
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # patient, 
        [
            'patient', 
            'list'
        ]
    )
    assert result.exit_code == 0
    assert "ID: 1, ФИО: Петров Иван" in result.output
    assert "ID: 2, ФИО: Иванова Мария" in result.output

def test_patient_list_with_filter(runner, mock_patient_service):
    """
    Тест на вывод списка пациентов с фильтрацией.

    Описание теста:
    - Mock объект PatientService возвращает список из одного пациента
    - Затем запускается команда 'patient list' c фильтрацией last_name:like:Петров
    - Проверяется, что вывод содержит одного пациента
    - Проверяется, что вызван метод get_patients_filtered с фильтром
    """
    mock_patient_service.get_patients_filtered.return_value = [
        PatientDTO(
            id=1, 
            first_name="Иван", 
            last_name="Петров", 
            birth_date=date(1990,1,1), 
            phone="123", 
            email="ivan@test.ru"
        )
    ]

    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # patient, 
        [
            'patient', 
            'list', 
            '--filter', 
            'last_name:like:Петров'
        ]
    )
    assert result.exit_code == 0
    mock_patient_service.get_patients_filtered.assert_called_once_with(
        [
            {
                'column': 'last_name', 
                'operator': 'like', 
                'value': 'Петров'
            }
        ], 60
    )
    assert "ID: 1" in result.output

def test_patient_list_fuzzy_filter(runner, mock_patient_service):
    """
    Тест на вывод списка пациентов с фильтрацией нечеткого поиска.

    Описание теста:
    - Mock объект PatientService возвращает список из одного пациента
    - Затем запускается команда 'patient list' c фильтрацией fuzzy:last_name:Петроф
    - Проверяется, что вывод содержит одного пациента
    - Проверяется, что вызван метод get_patients_filtered с фильтром
    """
    mock_patient_service.get_patients_filtered.return_value = [
        PatientDTO(
            id=1, 
            first_name="Иван", 
            last_name="Петров", 
            birth_date=date(1990,1,1), 
            phone="123", 
            email="ivan@test.ru"
        )
    ]
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # patient, 
        [
            'patient', 
            'list', 
            '--filter', 
            'fuzzy:last_name:Петроф', 
            '--fuzzy-threshold', 
            '70'
        ]
        )
    assert result.exit_code == 0
    mock_patient_service.get_patients_filtered.assert_called_once_with(
        [
            {
                'column': 'last_name', 
                'operator': 'fuzzy', 
                'value': 'Петроф'
            }
        ], 70
    )

def test_patient_list_empty(runner, mock_patient_service):
    """
    Тест на вывод пустого списка пациентов.

    Описание теста:
    - Mock объект PatientService возвращает пустой список пациентов
    - Затем запускается команда 'patient list'
    - Проверяется, что вывод содержит сообщение "Пациенты не найдены."
    """
    mock_patient_service.get_patients_filtered.return_value = []
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # patient,
        [
            'patient',
            'list'
        ]
        )
    assert result.exit_code == 0
    assert "Пациенты не найдены." in result.output

def test_patient_list_invalid_filter(runner):
    """
    Тест на вывод списка пациентов с неверным фильтром.

    Описание теста:
    - Запускается команда 'patient list' c фильтрацией wrongformat
    - Проверяется, что код возврата команды не равен 0
    - Проверяется, что вывод содержит сообщение "Неверный формат фильтра"
    """
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # patient, 
        [
            'patient', 
            'list', 
            '--filter', 
            'wrongformat'
        ]
    )
    assert result.exit_code != 0
    assert "Неверный формат фильтра" in result.output

def test_patient_get_success(runner, mock_patient_service):
    """
    Тест на вывод информации о пациенте.

    Описание теста:
    - Mock объект PatientService возвращает информацию о пациенте с id=1
    - Затем запускается команда 'patient get' c id=1
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит информацию о пациенте
    """
    # Mock объект PatientService возвращает информацию о пациенте с id=1
    mock_patient_service.get_patient_by_id.return_value = PatientDTO(
        id=1, 
        first_name="Иван", 
        last_name="Петров", 
        birth_date=date(1990,1,1), 
        phone="123", 
        email="ivan@test.ru"
    )
    
    # Затем запускается команда 'patient get' c id=1
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # patient, 
        [
            'patient', 
            'get', 
            '--id', 
            '1'
        ]
    )
    
    # Проверяется, что код возврата команды равен 0
    assert result.exit_code == 0
    
    # Проверяется, что вывод содержит информацию о пациенте
    assert "ID: 1" in result.output
    assert "Имя: Иван" in result.output
    assert "Фамилия: Петров" in result.output

def test_patient_get_not_found(runner, mock_patient_service):
    """
    Тест на вывод информации о пациенте, если пациент с указанным идентификатором не найден.

    Описание теста:
    - Mock объект PatientService выбрасывает исключение PatientNotFoundError при вызове get_patient_by_id с id=1
    - Затем запускается команда 'patient get' c id=1
    - Проверяется, что код возврата команды равен 0 (click обрабатывает исключение и выводит текст)
    - Проверяется, что вывод содержит сообщение "Пациент с идентификатором 1 не найден."
    """
    # Mock объект PatientService выбрасывает исключение PatientNotFoundError при вызове get_patient_by_id с id=1
    mock_patient_service.get_patient_by_id.side_effect = PatientNotFoundError(1)
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # patient, 
        [
            'patient', 
            'get', 
            '--id', 
            '1'
        ]
    )
    # Проверяется, что код возврата команды равен 0 (click обрабатывает исключение и выводит текст)
    assert result.exit_code == 0
    # Проверяется, что вывод содержит сообщение "Пациент с идентификатором 1 не найден."
    assert "Пациент с идентификатором 1 не найден." in result.output

def test_patient_create_success(runner, mock_patient_service):
    """
    Тест на создание пациента.

    Описание теста:
    - Mock объект PatientService возвращает информацию о созданном пациенте
    - Затем запускается команда 'patient create' c информацией о пациенте
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит информацию о созданном пациенте
    """
    mock_patient_service.create_patient.return_value = PatientDTO(
        # id автоматически присваивается
        id=3, 
        # имя
        first_name="Новый", 
        # фамилия
        last_name="Пациент", 
        # дата рождения
        birth_date=None, 
        # телефон
        phone="", 
        # электронная почта
        email=""
    )
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # patient, 
        [
            'patient', 
            'create', 
            '--first-name', 
            'Новый', 
            '--last-name', 
            'Пациент'
        ]
    )
    assert result.exit_code == 0
    assert "Пациент создан с ID: 3" in result.output

def test_patient_create_validation_error(runner, mock_patient_service):
    """
    Тест на создание пациента с ошибкой валидации.

    Описание теста:
    - Mock объект PatientService выбрасывает исключение PatientValidationError при вызове create_patient с пустым именем
    - Затем запускается команда 'patient create' с пустым именем
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "Ошибка валидации поля 'first_name': пустое."
    """
    # Mock объект PatientService выбрасывает исключение PatientValidationError при вызове create_patient с пустым именем
    mock_patient_service.create_patient.side_effect = PatientValidationError(
        "first_name", 
        "пустое"
    )
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # patient, 
        [
            'patient', 
            'create',
            '--first-name', 
            '', 
            '--last-name', 
            ''
        ]
    )
    # Проверяется, что код возврата команды равен 0
    assert result.exit_code == 0
    # Проверяется, что вывод содержит сообщение "Ошибка валидации поля 'first_name': пустое."
    assert "Ошибка валидации поля 'first_name': пустое." in result.output

def test_patient_update_success(runner, mock_patient_service):
    """
    Тест на обновление существующего пациента.

    Описание теста:
    - Mock объект PatientService возвращает существующего пациента при вызове get_patient_by_id
    - Mock объект PatientService возвращает обновленный пациента при вызове update_patient
    - Затем запускается команда 'patient update' c id=1, first_name='Новое'
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "Пациент ID 1 обновлён."
    """
    # Mock объект PatientService возвращает существующего пациента при вызове get_patient_by_id
    mock_patient_service.get_patient_by_id.return_value = PatientDTO(
        id=1, 
        first_name="Старое", 
        last_name="Имя", 
        birth_date=None, 
        phone="", 
        email=""
    )
    # Mock объект PatientService возвращает обновленный пациента при вызове update_patient
    mock_patient_service.update_patient.return_value = PatientDTO(
        id=1, 
        first_name="Новое", 
        last_name="Имя", 
        birth_date=None, 
        phone="", 
        email=""
    )
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # patient,
        [
            'patient', 
            'update', 
            '--id', 
            '1', 
            '--first-name', 
            'Новое'
        ]
    )
    assert result.exit_code == 0
    assert "Пациент ID 1 обновлён." in result.output

def test_patient_update_not_found(runner, mock_patient_service):
    """
    Тест на обновление пациента, если пациент с указанным идентификатором не найден.

    Описание теста:
    - Mock объект PatientService выбрасывает исключение PatientNotFoundError при вызове get_patient_by_id с id=1
    - Затем запускается команда 'patient update' c id=1, first_name='Новое'
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "Пациент с идентификатором 1 не найден."
    """
    # Mock объект PatientService выбрасывает исключение PatientNotFoundError при вызове get_patient_by_id с id=1
    mock_patient_service.get_patient_by_id.side_effect = PatientNotFoundError(1)
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # patient, 
        [
            'patient', 
            'update', 
            '--id', 
            '1', 
            '--first-name', 
            'Новое'
        ]
    )
    assert result.exit_code == 0
    assert "Пациент с идентификатором 1 не найден." in result.output

def test_patient_delete_success(runner, mock_patient_service):
    """
    Тест на удаление существующего пациента.

    Описание теста:
    - Затем запускается команда 'patient delete' c id=1
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что функция delete_patient была вызвана с параметром id=1
    - Проверяется, что вывод содержит сообщение "Пациент ID 1 удалён."
    """
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # patient, 
        [
            'patient', 
            'delete', 
            '--id', 
            '1'
        ]
    )
    assert result.exit_code == 0
    mock_patient_service.delete_patient.assert_called_once_with(1)
    assert "Пациент ID 1 удалён." in result.output

def test_patient_delete_not_found(runner, mock_patient_service):
    """
    Тест на удаление не существующего пациента.

    Описание теста:
    - Mock объект PatientService выбрасывает исключение PatientNotFoundError при вызове delete_patient с id=1
    - Затем запускается команда 'patient delete' c id=1
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "Пациент с идентификатором 1 не найден."
    """
    mock_patient_service.delete_patient.side_effect = PatientNotFoundError(1)
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # patient, 
        [
            'patient', 
            'delete', 
            '--id', 
            '1'
        ]
    )
    assert result.exit_code == 0
    assert "Пациент с идентификатором 1 не найден." in result.output

# ----------------------------------------------------------------------
# Тесты команд для приёмов
# ----------------------------------------------------------------------

def test_appointment_list_all(runner, mock_appointment_service):
    """
    Тест на получение списка всех приёмов.

    Описание теста:
    - Mock объект AppointmentService возвращает список всех приёмов
    - Затем запускается команда 'appointment list'
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "ID: 1, Пациент ID: 1" и "ID: 2"
    """
    mock_appointment_service.get_all.return_value = [
        AppointmentDTO(
            id=1, 
            patient_id=1, 
            date=date.today(), 
            time=time(10,0), 
            note_id=1, 
            patient_name="Петров Иван", 
            note_text="Заметка"
        ),
        AppointmentDTO(
            id=2, 
            patient_id=2, 
            date=date.today(), 
            time=time(11,0), 
            note_id=2, 
            patient_name="Иванова Мария", 
            note_text=""
        )
    ]
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # appointment, 
        [
            'appointment', 
            'list'
        ]
    )
    assert result.exit_code == 0
    # Проверяется, что вывод содержит сообщение "ID: 1, Пациент ID: 1"
    assert "ID: 1, Пациент ID: 1" in result.output
    # Проверяется, что вывод содержит сообщение "ID: 2"
    assert "ID: 2" in result.output

def test_appointment_list_by_patient(runner, mock_appointment_service):
    """
    Тест на получение списка приёмов по пациенту.

    Описание теста:
    - Mock объект AppointmentService возвращает список приёмов по пациенту с id=1
    - Затем запускается команда 'appointment list --patient-id 1'
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "ID: 1"
    - Проверяется, что mock объект AppointmentService вызывал метод get_appointments_by_patient с аргументом 1
    """
    mock_appointment_service.get_appointments_by_patient.return_value = [
        AppointmentDTO(
            id=1, 
            patient_id=1, 
            date=date.today(), 
            time=time(10,0), 
            note_id=1, 
            patient_name="Петров Иван", 
            note_text=""
        )
    ]
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # appointment, 
        [
            'appointment', 
            'list', 
            '--patient-id', 
            '1'
        ]
    )
    assert result.exit_code == 0
    mock_appointment_service.get_appointments_by_patient.assert_called_once_with(1)
    assert "ID: 1" in result.output

def test_appointment_list_with_filter(runner, mock_appointment_service):
    """
    Тест на получение списка приёмов с фильтрацией.

    Описание теста:
    - Mock объект AppointmentService возвращает список приёмов с фильтрацией date:eq:2025-03-17
    - Затем запускается команда 'appointment list --filter date:eq:2025-03-17'
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "ID: 1"
    - Проверяется, что mock объект AppointmentService вызывал метод get_filtered с аргументом
    [
        {
            'column': 'date', 
            'operator': 'eq', 
            'value': '2025-03-17'
        }
    ], 60
    """
    mock_appointment_service.get_filtered.return_value = [
        AppointmentDTO(
            id=1, 
            patient_id=1, 
            date=date.today(), 
            time=time(10,0), 
            note_id=1, 
            patient_name="Петров Иван",
             note_text="осмотр"
        )
    ]
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # appointment, 
        [
            'appointment', 
            'list', 
            '--filter', 
            'date:eq:2025-03-17'
        ]
    )
    assert result.exit_code == 0
    mock_appointment_service.get_filtered.assert_called_once_with(
        [
            {
                'column': 'date', 
                'operator': 'eq', 
                'value': '2025-03-17'
            }
        ], 60
    )

def test_appointment_get_success(runner, mock_appointment_service):
    """
    Тест на получение информации о приёме.

    Описание теста:
    - Mock объект AppointmentService возвращает информацию о приёме с id=1
    - Затем запускается команда 'appointment get' c id=1
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит информацию о приёме
    """
    mock_appointment_service.get_appointment.return_value = AppointmentDTO(
        id=1, 
        patient_id=1, 
        date=date.today(), 
        time=time(10,0), 
        note_id=1, 
        patient_name="Петров Иван", 
        note_text="осмотр"
    )
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # appointment, 
        [
            'appointment', 
            'get', 
            '--id', 
            '1'
        ]
    )
    assert result.exit_code == 0
    assert "ID: 1" in result.output
    assert "Текст заметки: осмотр" in result.output

def test_appointment_get_not_found(runner, mock_appointment_service):
    """
    Тест на получение информации о не существующем приёме.

    Описание теста:
    - Mock объект AppointmentService выбрасывает исключение AppointmentNotFoundError при вызове get_appointment с id=1
    - Затем запускается команда 'appointment get' c id=1
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "Приём с идентификатором 1 не найден."
    """
    mock_appointment_service.get_appointment.side_effect = AppointmentNotFoundError(1)
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # appointment, 
        [
            'appointment', 
            'get', 
            '--id', 
            '1'
        ]
    )
    assert result.exit_code == 0
    assert "Приём с идентификатором 1 не найден." in result.output

def test_appointment_create_success(runner, mock_appointment_service):
    """
    Тест на создание приёма.

    Описание теста:
    - Mock объект AppointmentService возвращает информацию о созданном приёме
    - Затем запускается команда 'appointment create' с информацией о приёме
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит информацию о созданном приёме
    """
    mock_appointment_service.create_appointment.return_value = AppointmentDTO(
        # id автоматически присваивается
        id=5, 
        # id пациента
        patient_id=1, 
        # дата приёма
        date=date.today(), 
        # время приёма
        time=time(9,0), 
        # id заметки
        note_id=10, 
        # имя пациента
        patient_name="", 
        # текст заметки
        note_text=""
    )
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # appointment, 
        [
            'appointment', 
            'create', 
            '--patient-id',
            '1', 
            '--date', 
            '2025-03-17', 
            '--time', 
            '09:00', 
            '--note-text', 
            'новая заметка'
        ]
    )
    assert result.exit_code == 0
    assert "Приём создан с ID: 5" in result.output

def test_appointment_create_patient_not_found(runner, mock_appointment_service):
    """
    Тест на создание приёма с не существующим пациентом.

    Описание теста:
    - Mock объект AppointmentService выбрасывает исключение PatientNotFoundError при вызове create_appointment с id пациента=1
    - Затем запускается команда 'appointment create' с информацией о приёме
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "Пациент с идентификатором 1 не найден."
    """
    mock_appointment_service.create_appointment.side_effect = PatientNotFoundError(1)
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # appointment, 
        [
            'appointment', 
            'create', 
            '--patient-id', 
            '1', 
            '--date', 
            '2025-03-17'
        ]
    )
    assert result.exit_code == 0
    assert "Пациент с идентификатором 1 не найден." in result.output

def test_appointment_update_success(runner, mock_appointment_service):
    """
    Тест на обновление существующего приёма.

    Описание теста:
    - Mock объект AppointmentService возвращает существующий приём при вызове get_appointment
    - Mock объект AppointmentService возвращает обновленный приём при вызове update_appointment
    - Затем запускается команда 'appointment update' c информацией о приёме
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "Приём ID 1 обновлён."
    """
    # Mock объект AppointmentService возвращает существующий приём при вызове get_appointment
    mock_appointment_service.get_appointment.return_value = AppointmentDTO(
        id=1, 
        patient_id=1, 
        date=date(2025,1,1), 
        time=None, 
        note_id=1, 
        patient_name="", 
        note_text=""
    )
    # Mock объект AppointmentService возвращает обновленный приём при вызове update_appointment
    mock_appointment_service.update_appointment.return_value = AppointmentDTO(
        id=1, 
        patient_id=1, 
        date=date(2025,12,31), 
        time=time(18,0), 
        note_id=2, 
        patient_name="", 
        note_text="новая"
    )
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # appointment, 
        [
            'appointment', 
            'update', 
            '--id', 
            '1', 
            '--date', 
            '2025-12-31', 
            '--time', 
            '18:00', 
            '--note-text', 
            'новая'
        ]
    )
    assert result.exit_code == 0
    assert "Приём ID 1 обновлён." in result.output

def test_appointment_update_not_found(runner, mock_appointment_service):
    """
    Тест на обновление не существующего приёма.

    Описание теста:
    - Mock объект AppointmentService выбрасывает исключение AppointmentNotFoundError при вызове get_appointment
    - Затем запускается команда 'appointment update' c информацией о приёме
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "Приём с идентификатором 1 не найден."
    """
    mock_appointment_service.get_appointment.side_effect = AppointmentNotFoundError(1)
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # appointment, 
        [
            'appointment', 
            'update', 
            '--id', 
            '1'
        ]
    )
    assert result.exit_code == 0
    assert "Приём с идентификатором 1 не найден." in result.output

def test_appointment_delete_success(runner, mock_appointment_service):
    """
    Тест на удаление существующего приёма.

    Описание теста:
    - Mock объект AppointmentService вызывает метод delete_appointment с id=1
    - Затем запускается команда 'appointment delete' c id=1
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "Приём ID 1 удалён."
    """
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # appointment, 
        [
            'appointment', 
            'delete', 
            '--id', 
            '1'
        ]
    )
    assert result.exit_code == 0
    mock_appointment_service.delete_appointment.assert_called_once_with(1)
    assert "Приём ID 1 удалён." in result.output

# ----------------------------------------------------------------------
# Тесты команд для заметок
# ----------------------------------------------------------------------

def test_note_list(runner, mock_note_service):
    """
    Тест на получение списка всех заметок.

    Описание теста:
    - Mock объект NoteService возвращает список всех заметок
    - Затем запускается команда 'note list'
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "ID: 1, Текст: Заметка 1"
    - Проверяется, что вывод содержит сообщение "ID: 2"
    """
    mock_note_service.get_all.return_value = [
        AppointmentNoteDTO(
            id=1, 
            text="Заметка 1"
        ),
        AppointmentNoteDTO(
            id=2, 
            text="Заметка 2"
        ),
    ]
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # note, 
        [
            'note', 
            'list'
        ]
    )
    assert result.exit_code == 0
    assert "ID: 1, Текст: Заметка 1" in result.output
    assert "ID: 2" in result.output

def test_note_get_success(runner, mock_note_service):
    """
    Тест на получение информации о существующей заметке.

    Описание теста:
    - Mock объект NoteService возвращает информацию о заметке с id=1
    - Затем запускается команда 'note get' c id=1
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "ID: 1"
    - Проверяется, что вывод содержит сообщение "Текст:\nДлинный текст заметки"
    """
    mock_note_service.get_note.return_value = AppointmentNoteDTO(
        id=1, 
        text="Длинный текст заметки"
    )
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # note, 
        [
            'note', 
            'get', 
            '--id', 
            '1'
        ]
    )
    assert result.exit_code == 0
    assert "ID: 1" in result.output
    assert "Текст:\nДлинный текст заметки" in result.output

def test_note_get_not_found(runner, mock_note_service):
    """
    Тест на получение информации о не существующей заметке.

    Описание теста:
    - Mock объект NoteService выбрасывает исключение AppointmentNoteNotFoundError при вызове get_note с id=1
    - Затем запускается команда 'note get' c id=1
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "Заметка приёма с идентификатором 1 не найдена."
    """
    # Mock объект NoteService выбрасывает исключение AppointmentNoteNotFoundError при вызове get_note с id=1
    mock_note_service.get_note.side_effect = AppointmentNoteNotFoundError(1)
    # Затем запускается команда 'note get' c id=1
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # note, 
        [
            'note', 
            'get', 
            '--id', 
            '1'
        ]
    )
    # Проверяется, что код возврата команды равен 0
    assert result.exit_code == 0
    # Проверяется, что вывод содержит сообщение "Заметка приёма с идентификатором 1 не найдена."
    assert "Заметка приёма с идентификатором 1 не найдена." in result.output

def test_note_create(runner, mock_note_service):
    """
    Тест на создание новой заметки.

    Описание теста:
    - Mock объект NoteService возвращает созданную заметку с id=5
    - Затем запускается команда 'note create' c текстом новой заметки
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "Заметка создана с ID: 5"
    """
    mock_note_service.create_note.return_value = AppointmentNoteDTO(
        id=5, 
        text="новая заметка"
    )
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # note, 
        [
            'note', 
            'create', 
            'новая заметка'
        ]
    )
    assert result.exit_code == 0
    mock_note_service.create_note.assert_called_once_with("новая заметка")
    assert "Заметка создана с ID: 5" in result.output

def test_note_create_from_file(runner, mock_note_service, tmp_path):
    """
    Тест на создание новой заметки из текстового файла.

    Описание теста:
    - Mock объект NoteService возвращает созданную заметку с id=6
    - Создаётся временный файл с текстом "содержимое файла"
    - Затем запускается команда 'note create-from-file' c файлом
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "Заметка создана с ID: 6"
    """
    file = tmp_path / "note.txt"
    file.write_text("содержимое файла")
    mock_note_service.create_note_from_file.return_value = AppointmentNoteDTO(
        id=6, 
        text="содержимое файла"
    )
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # note, 
        [
            'note', 
            'create-from-file', 
            '--file', 
            str(file)
        ]
    )
    assert result.exit_code == 0
    mock_note_service.create_note_from_file.assert_called_once_with(str(file))
    assert "Заметка создана с ID: 6" in result.output

def test_note_update(runner, mock_note_service):
    """
    Тест на обновление существующей заметки.

    Описание теста:
    - Mock объект NoteService возвращает обновленную заметку с id=1
    - Затем запускается команда 'note update' c id=1 и текстом новой заметки
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "Заметка ID 1 обновлена."
    """
    mock_note_service.update_note.return_value = AppointmentNoteDTO(
        id=1, 
        text="обновлённый текст"
    )
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # note, 
        [
            'note', 
            'update', 
            '--id', 
            '1', 
            'обновлённый текст'
        ]
    )
    assert result.exit_code == 0
    mock_note_service.update_note.assert_called_once_with(
        1, 
        "обновлённый текст"
    )
    assert "Заметка ID 1 обновлена." in result.output

def test_note_delete(runner, mock_note_service):
    """
    Тест на удаление существующей заметки.

    Описание теста:
    - Mock объект NoteService возвращает None при вызове delete_note с id=1
    - Затем запускается команда 'note delete' c id=1
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что функция delete_note была вызвана с параметром id=1
    - Проверяется, что вывод содержит сообщение "Заметка ID 1 удалена."
    """
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # note, 
        [
            'note', 
            'delete', 
            '--id', 
            '1'
        ]
    )
    assert result.exit_code == 0
    mock_note_service.delete_note.assert_called_once_with(1)
    assert "Заметка ID 1 удалена." in result.output


# ----------------------------------------------------------------------
# Тесты команд для фото
# ----------------------------------------------------------------------

def test_photo_list_all(runner, mock_photo_service):
    """
    Тест на получение списка всех фото.

    Описание теста:
    - Mock объект PhotoService возвращает список всех фото
    - Затем запускается команда 'photo list'
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит сообщение "ID: 1, Приём ID: 1, Файл: path1.jpg, Описание: desc1" и "ID: 2"
    """
    mock_photo_service.get_all.return_value = [
        PhotoDTO(
            id=1, 
            appointment_id=1, 
            file_path="path1.jpg", 
            description="desc1"
        ),
        PhotoDTO(
            id=2, 
            appointment_id=1, 
            file_path="path2.jpg", 
            description="desc2"
        ),
    ]
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # photo, 
        [
            'photo', 
            'list'
        ]
    )
    assert result.exit_code == 0
    assert "ID: 1, Приём ID: 1, Файл: path1.jpg, Описание: desc1" in result.output
    assert "ID: 2" in result.output

def test_photo_list_by_appointment(runner, mock_photo_service):
    """
    Тест на получение списка фото для приёма.

    Описание теста:
    - Mock объект PhotoService возвращает список фото для приёма с id=1
    - Затем запускается команда 'photo list' c id приёма
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что функция get_photos_for_appointment была вызвана с параметром id приёма
    """
    mock_photo_service.get_photos_for_appointment.return_value = [
        PhotoDTO(
            id=1, 
            appointment_id=1, 
            file_path="path1.jpg", 
            description="desc1"
        )
    ]
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # photo, 
        [
            'photo', 
            'list', 
            '--appointment-id', 
            '1'
        ]
    )
    assert result.exit_code == 0
    mock_photo_service.get_photos_for_appointment.assert_called_once_with(1)

def test_photo_add_success(runner, mock_photo_service, tmp_path):
    """
    Тест на добавление фото к приёму.

    Описание теста:
    - Mock объект PhotoService возвращает PhotoDTO с id=10
    - Затем запускается команда 'photo add' c id приёма, файлом и описанием
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что в выводе есть строка "Фото добавлено с ID: 10"
    """
    img = tmp_path / "test.jpg"
    img.write_bytes(b"data")
    mock_photo_service.add_photo_to_appointment.return_value = PhotoDTO(
        id=10, 
        appointment_id=1, 
        file_path="app1/test.jpg", 
        description="test"
    )
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # photo, 
        [
            'photo', 
            'add', 
            '--appointment-id', 
            '1', 
            '--file', str(img), 
            '--description', 
            'test'
        ]
    )
    assert result.exit_code == 0
    assert "Фото добавлено с ID: 10" in result.output

def test_photo_add_appointment_not_found(runner, mock_photo_service, tmp_path):
    """
    Тест на добавление фото к не существующему приёму.

    Описание теста:
    - Mock объект PhotoService выбрасывает исключение AppointmentNotFoundError при вызове add_photo_to_appointment
      с id приёма=1
    - Затем запускается команда 'photo add' c id приёма, файлом и описанием
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что в выводе есть строка "Приём с идентификатором 1 не найден."
    """
    img = tmp_path / "test.jpg"
    img.write_bytes(b"data")
    mock_photo_service.add_photo_to_appointment.side_effect = AppointmentNotFoundError(1)
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # photo, 
        [
            'photo', 
            'add', 
            '--appointment-id', 
            '1', 
            '--file', 
            str(img)
        ]
    )
    assert result.exit_code == 0
    assert "Приём с идентификатором 1 не найден." in result.output

def test_photo_add_file_error(runner, mock_photo_service, tmp_path):
    """
    Тест на добавление фото к приёму с ошибкой копирования файла.

    Описание теста:
    - Mock объект PhotoService выбрасывает исключение PhotoFileError при вызове add_photo_to_appointment
      с id приёма=1, файлом и описанием
    - Затем запускается команда 'photo add' c id приёма, файлом и описанием
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что в выводе есть строка "Ошибка копирования файла"
    """
    img = tmp_path / "test.jpg"
    img.write_bytes(b"data")
    mock_photo_service.add_photo_to_appointment.side_effect = PhotoFileError(
        str(img),  # путь к файлу
        "копирование",  # описание ошибки
        "ошибка"  # сообщение об ошибке
    )
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # photo, 
        [
            'photo', 
            'add', 
            '--appointment-id', 
            '1',
            '--file', 
            str(img)  # файл для добавления
        ]
    )
    assert result.exit_code == 0
    # assert "Ошибка копирования файла" in result.output
    assert "Ошибка копирование файла" in result.output

def test_photo_delete_success(runner, mock_photo_service):
    """
    Тест на удаление фото.

    Описание теста:
    - Затем запускается команда 'photo delete' c id=1
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что функция delete_photo была вызвана с параметром id=1
    - Проверяется, что вывод содержит сообщение "Фото ID 1 удалено."
    """
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # photo, 
        [
            'photo', 
            'delete', 
            '--id', 
            '1'
        ]
    )
    assert result.exit_code == 0
    # Проверка, что функция delete_photo была вызвана с параметром id=1
    mock_photo_service.delete_photo.assert_called_once_with(1)
    # Проверка, что вывод содержит сообщение "Фото ID 1 удалено."
    assert "Фото ID 1 удалено." in result.output

def test_photo_delete_not_found(runner, mock_photo_service):
    """
    Тест на удаление не существующей фотографии.

    Описание теста:
    - Mock объект PhotoService выбрасывает исключение PhotoNotFoundError при вызове delete_photo с id=1
    - Затем запускается команда 'photo delete' c id=1
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что в выводе есть строка "Фотография с идентификатором 1 не найдена."
    """
    mock_photo_service.delete_photo.side_effect = PhotoNotFoundError(1)
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # photo, 
        [
            'photo', 
            'delete', 
            '--id', 
            '1'
        ]
    )
    assert result.exit_code == 0
    assert "Фотография с идентификатором 1 не найдена." in result.output

# ----------------------------------------------------------------------
# Тесты команд инициализации, синхронизации и статистики
# ----------------------------------------------------------------------

def test_init_db(runner):
    """
    Тест инициализации базы данных.

    Описание теста:
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что функция init_db была вызвана с параметрами recreate=False, test_data=True
    - Проверяется, что в выводе есть строка "База данных инициализирована."
    """
    with patch('interfaces.cli.cli.init_db_deps') as mock_init:
    
        cli = create_cli()  # создаём экземпляр CLI для теста
        result = runner.invoke( 
            cli,
            # init_db,
            [
                'init-db', 
                # 'init_db', 
            ]
        )
        # cli = create_cli()
        # print("Доступные команды:", list(cli.commands.keys()))
        # result = runner.invoke(cli, ['init_db'])
        # print(result.output)

        assert result.exit_code == 0
        mock_init.assert_called_once_with(recreate=False, test_data=True)
        assert "База данных инициализирована." in result.output

def test_init_db_with_options(runner):
    """
    Тест инициализации базы данных с параметрами.

    Описание теста:
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что функция init_db была вызвана с параметрами recreate=True, test_data=False
    - Проверяется, что в выводе есть строка "База данных инициализирована."
    """
    with patch('interfaces.cli.cli.init_db_deps') as mock_init:
    
        cli = create_cli()  # создаём экземпляр CLI для теста
        result = runner.invoke( 
            cli,
            # init_db, 
            [
                'init-db', 
                # 'init_db', 
                '--recreate', 
                '--no-test-data'
            ]
        )
        assert result.exit_code == 0
        mock_init.assert_called_once_with(recreate=True, test_data=False)

def test_sync_download_success(runner, mock_sync_service):
    """
    Тест на скачивание базы данных с Яндекс.Диска (асинхронно с отображением прогресса).

    Описание теста:
    - Mock объект SyncService возвращает 0 при вызове download_sync
    - Затем запускается команда 'sync download'
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что в выводе есть строка "Скачивание успешно завершено."
    """
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    mock_sync_service.download_sync.return_value = 0
    result = runner.invoke( 
        cli,
        # sync_download,
        [
            # 'sync_download', 
            'sync-download', 
        ]
    )
    assert result.exit_code == 0
    assert "Скачивание успешно завершено." in result.output

def test_sync_download_error(runner, mock_sync_service):
    """
    Тест на скачивание базы данных с Яндекс.Диска (асинхронно с отображением прогресса).

    Описание теста:
    - Mock объект SyncService возвращает 1 при вызове download_sync
    - Затем запускается команда 'sync download'
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что в выводе есть строка "Скачивание завершилось с ошибкой (код 1)"
    """
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    mock_sync_service.download_sync.return_value = 1
    result = runner.invoke( 
        cli,
        # sync_download,
        [
            # 'sync_download', 
            'sync-download', 
        ]
    )
    assert result.exit_code == 0
    assert "Скачивание завершилось с ошибкой (код 1)" in result.output

def test_sync_upload_success(runner, mock_sync_service):
    """
    Тест на загрузку базы данных на Яндекс.Диск (асинхронно с отображением прогресса).

    Описание теста:
    - Mock объект SyncService возвращает 0 при вызове upload_sync
    - Затем запускается команда 'sync upload'
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что в выводе есть строка "Загрузка успешно завершена."
    """
    # Mock объект SyncService возвращает 0 при вызове upload_sync
    mock_sync_service.upload_sync.return_value = 0
    
    # Затем запускается команда 'sync upload'
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # sync_upload,
        [
            # 'sync_upload', 
            'sync-upload', 
        ]
    )
    
    # Проверяется, что код возврата команды равен 0
    assert result.exit_code == 0
    
    # Проверяется, что в выводе есть строка "Загрузка успешно завершена."
    assert "Загрузка успешно завершена." in result.output

def test_sync_upload_error(runner, mock_sync_service):
    """
    Тест на загрузку базы данных на Яндекс.Диск (асинхронно с отображением прогресса).

    Описание теста:
    - Mock объект SyncService возвращает 2 при вызове upload_sync
    - Затем запускается команда 'sync upload'
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что в выводе есть строка "Загрузка завершилась с ошибкой (код 2)"
    """
    mock_sync_service.upload_sync.return_value = 2
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # sync_upload,
        [
            # 'sync_upload', 
            'sync-upload', 
        ]
    )
    assert result.exit_code == 0
    assert "Загрузка завершилась с ошибкой (код 2)" in result.output

def test_stats(runner):
    """
    Тест на отображение статистики по базе данных.

    Описание теста:
    - Mock объект get_db возвращает Mock объект Database
    - Mock объект Database.session_scope возвращает Mock объект Session
    - Mock объект Session.query возвращает Mock объект Query
    - Mock объект Query.count возвращает 10, 5, 3, 7
    - Затем запускается команда 'stats'
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что в выводе есть строка "Пациентов: 10"
    - Проверяется, что в выводе есть строка "Приёмов: 5"
    - Проверяется, что в выводе есть строка "Заметок: 3"
    - Проверяется, что в выводе есть строка "Фотографий: 7"
    """
    with patch('interfaces.cli.cli.get_db') as mock_get_db:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_session = MagicMock()
        mock_db.session_scope.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.count.side_effect = [10, 5, 3, 7]
    
        cli = create_cli()  # создаём экземпляр CLI для теста
        result = runner.invoke( 
            cli,
            # stats,
            [
                'stats', 
            ]
        )
        assert result.exit_code == 0
        assert "Пациентов: 10" in result.output
        assert "Приёмов: 5" in result.output
        assert "Заметок: 3" in result.output
        assert "Фотографий: 7" in result.output

# ----------------------------------------------------------------------
# Тесты интерактивного меню (базовые)
# ----------------------------------------------------------------------

def test_menu_patient_flow(runner, monkeypatch, mock_patient_service):
    """
    Тест на интерактивное меню пациентов.

    Описание теста:
    - Эмулируем ввод: выбрать категорию пациентов (1), затем выход из меню пациентов (0), затем выход из программы (0)
    - Проверяется, что команда выполнилась без ошибок
    """
    # Эмулируем ввод: выбрать категорию пациентов (1), затем выход из меню пациентов (0), затем выход из программы (0)
    inputs = iter(['1', '0', '0'])
    monkeypatch.setattr('builtins.input', lambda _: next(inputs))
    
    with patch('interfaces.cli.cli.click.pause', return_value=None):  # чтобы не ждать нажатия
    
        cli = create_cli()  # создаём экземпляр CLI для теста
        result = runner.invoke( 
            cli,
            # menu, 
            [
                'menu', 
            ],
            input='\n'.join(['1', '0', '0'])
        )
    # Просто проверяем, что команда выполнилась без ошибок
    assert result.exit_code == 0
    # Можно проверить, что было вызвано меню пациентов (косвенно)
    # Но из-за сложности интерактивных тестов достаточно, что не упало

def test_menu_appointment_flow(runner, monkeypatch):
    """
    Тест на интерактивное меню приёмов.

    Описание теста:
    - Эмулируем ввод: выбрать категорию приёмов (2), затем выход из меню приёмов (0), затем выход из программы (0)
    - Проверяется, что команда выполнилась без ошибок
    """
    # Эмулируем ввод: выбрать категорию приёмов (2), затем выход из меню приёмов (0), затем выход из программы (0)
    inputs = iter(['2', '0', '0'])
    monkeypatch.setattr(
        'builtins.input', lambda _: next(inputs)
    )
    
    with patch('interfaces.cli.cli.click.pause'):  # чтобы не ждать нажатия
        cli = create_cli()  # создаём экземпляр CLI для теста
        result = runner.invoke( 
            cli,
            # menu,
            [
                'menu', 
            ], 
            input='\n'.join(['2', '0', '0'])
        )

    # Просто проверяем, что команда выполнилась без ошибок
    assert result.exit_code == 0
    # Можно проверить, что было вызвано меню приёмов (косвенно)
    # Но из-за сложности интерактивных тестов достаточно, что не упало

# ----------------------------------------------------------------------
# Тесты для обработки ошибок ввода в командах
# ----------------------------------------------------------------------

def test_patient_create_missing_required(runner):
    """
    Тест на создание пациента без обязательных полей.

    Описание теста:
    - Команда 'patient create' запускается без --first-name и --last-name
    - Проверяется, что код возврата команды не равен 0
    - Проверяется, что вывод содержит информацию о том, что какие поля обязательны
    """
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # patient, 
        [
            'patient', 
            'create'
            # без --first-name и --last-name
        ]
    )  
    assert result.exit_code != 0
    assert "Missing option" in result.output or "requires" in result.output

def test_appointment_create_invalid_date(runner):
    """
    Тест на создание приёма с неправильной датой.

    Описание теста:
    - Команда 'appointment create' запускается с неправильной датой (2025/03/17)
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит информацию о том, что дата имеет неправильный формат
    """
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli,
        # appointment,
        [
            'appointment', 
            'create', 
            '--patient-id', 
            '1', 
            '--date', 
            '2025/03/17'
        ]
    )
    assert result.exit_code == 0  # click обрабатывает ошибку внутри команды
    assert "Неверный формат даты" in result.output

def test_appointment_create_invalid_time(runner):
    """
    Тест на создание приёма с неправильным временем.

    Описание теста:
    - Команда 'appointment create' запускается с неправильным временем (25:00)
    - Проверяется, что код возврата команды равен 0
    - Проверяется, что вывод содержит информацию о том, что время имеет неправильный формат
    """
    
    cli = create_cli()  # создаём экземпляр CLI для теста
    result = runner.invoke( 
        cli, 
        # appointment, 
        [
            'appointment', 
            'create', 
            '--patient-id', 
            '1', 
            '--date', '2025-03-17', 
            '--time', 
            '25:00'
        ]
    )
    assert result.exit_code == 0
    assert "Неверный формат времени" in result.output
