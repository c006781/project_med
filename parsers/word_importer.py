# parsers/word_importer.py
"""
Парсер Word-документов (.docx) для импорта пациентов и их приёмов.

Особенности:
    - Пациент из нескольких первых строк до первой таблицы.
    - Таблица с фиксированными колонками (дата, причина, процедура, рекомендации, стоимость, примечание, фото).
    - Поддержка нескольких таблиц (объединяются).
    - Извлечение встроенных изображений (фото) из последней колонки.
    - Транзакционное сохранение: один файл = один коммит БД.
    - Подробное логирование: файлы успехов и ошибок.
"""

import argparse
import os
import re
import shutil
# import sys
# ↑ до 2026-10-25 (Ф1.1.7): нужен был ручному разбору sys.argv — теперь argparse
import tempfile
import uuid
from datetime import date, datetime
from typing import (
    Callable, List, Optional, 
    Set, Tuple, Dict, 
    Any
)

from docx import Document # pip install python-docx
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn
from sqlalchemy.orm import Session

from app.database.database import Database
from app.database.database_shema.clinic import Patient
from app.dto.dto_all import PatientDTO, AppointmentDTO
from app.services.services_all import (
    PatientService, 
    AppointmentService, 
    PhotoService
)
from app.repositories.repositories_all import PatientRepository
from app.schema.clinic import patient_full_name
# from app.utils.logger.logger import AppLogger



def get_successful_files_from_log(log_file_path: str) -> Set[str]:
    """
    Извлекает из лог-файла имена файлов, которые были успешно обработаны.

    Лог-файл имеет строки, начинающиеся с метки '!!>>', далее поля разделены табуляцией:
        0: '!!>>'
        1: время запуска парсера
        2: время обработки файла
        3: имя файла
        4: статус ('success' или 'failed')
        5: сообщение об ошибке (может быть пустым)

    Args:
        log_file_path (str): Путь к файлу лога (обычно parser.log)

    Returns:
        Set[str]: Множество имён файлов, помеченных как 'success'.
    """

    successful = set()
    if not os.path.exists(log_file_path):
        return successful

    with open(log_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line.startswith('!!>>'):
                continue

            parts = line.split('\t')
            if len(parts) < 5:
                # Недостаточно полей – пропускаем
                continue

            # parts[0] = '!!>>'
            # parts[1] = time_log
            # parts[2] = time_pars
            # parts[3] = file_name
            # parts[4] = status
            file_name = parts[3]
            status = parts[4]

            if status == 'success':
                successful.add(file_name)

    return successful


def filter_unprocessed_files(all_files: List[str], log_file_path: str) -> List[str]:
    """
    Возвращает список файлов, которые ещё НЕ были успешно обработаны,
    на основе лог-файла.

    Args:
        all_files (List[str]): Список имён файлов (без путей), которые планируется обработать.
        log_file_path (str): Путь к лог-файлу.

    Returns:
        List[str]: Список файлов, отсутствующих в успешных записях лога.
    """

    successful = get_successful_files_from_log(log_file_path)

    return [f for f in all_files if f not in successful]

def get_all_docx_files(folder_path: str) -> List[str]:
    """
    Возвращает список имён всех .docx файлов в папке,
    исключая временные/системные файлы (начинающиеся с '~$' или '~lock.' и заканчивающиеся на .docx#).

    Args:
        folder_path (str): Путь к папке с файлами.

    Returns:
        List[str]: Список имён .docx файлов (без системных).
    """

    pattern = re.compile(r'^~.*\.docx#?$', re.IGNORECASE)
    all_files = []
    for f in os.listdir(folder_path):
        if not f.lower().endswith('.docx'):
            continue

        if pattern.match(f):
            continue

        all_files.append(f)

    return all_files

# ----------------------------------------------------------------------
# Нормализация и очистка текста (с сохранением переносов строк)
# ----------------------------------------------------------------------

def normalize_text(
    text : Optional[str],  # исходный текст (None — как пустой)
) -> str:
    """
    Очищает текст, но сохраняет переносы строк.

    - Заменяет ``\\r\\n`` и ``\\r`` на ``\\n``.
    - В каждой строке убирает пробелы по краям и сворачивает повторные пробельные
      символы (пробелы, табуляции, неразрывные пробелы) в один пробел; ``\\n`` не трогает.
    - Убирает пустые строки в начале и конце; внутренние пустые строки сохраняет
      (строка из одних пробелов становится пустой).

    Args:
        text (Optional[str]): Исходный текст.

    Returns:
        str: Очищенная строка с сохранёнными внутренними переносами.

    Пример:
        >>> normalize_text('  Тест  1 1\\r\\n причина ')
        'Тест 1 1\\nпричина'
        >>> normalize_text(None)
        ''
    """

    if not text:
        return ""

    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # W1: пробелы по краям строки и повторные внутри — убрать (split() без аргумента
    # режет по любым пробельным символам, включая табуляции и неразрывный пробел)
    lines = [
        ' '.join(line.split())
        for line in text.split('\n')
    ]
    # text = text.replace('\r', '\n')
    # text = re.sub(r'[\t\x0b\x0c]', ' ', text)   # табуляции -> пробел
    # lines = text.splitlines()
    # ↑ до 2026-10-25 (W1): описание обещало убирать лишние пробелы, но пробелы по краям
    #   и повторные оставались («  Иван  » попадал в ФИО); \r\n давал пустую строку.

    # Убираем только пустые строки в начале и конце, внутренние сохраняем
    if lines:

        # убираем начальные пустые
        while lines and not lines[0].strip():
            lines.pop(0)

        # убираем конечные пустые
        while lines and not lines[-1].strip():
            lines.pop()

    return '\n'.join(lines)

# Первая цифра 10-значного номера РФ без кода страны: 3, 4, 8 — коды городов, 9 — мобильные
# (W3, 2026-10-25; было только 8 и 9 — городские 495…, 3842… без «8» терялись)
_RU_NATIONAL_FIRST_DIGITS = '3489'

# Длины кода города, которые меняют вид номера: +7 (3842) 12-34-56, +7 (38451) 2-34-56
_LONG_AREA_CODE_LENGTHS = (4, 5)


def _area_code_length(
    phone_raw  : str,  # номер как в тексте (с пробелами, скобками, дефисами)
    prefix_len : int,  # сколько цифр кода страны в номере (0 — нет, 1 — «8» или «7»)
) -> Optional[int]:
    """
    Длина кода города по исходной группировке номера (W3).

    Код — цифры в скобках, а без скобок — первая группа цифр после кода страны
    (группа — цифры подряд, разделённые пробелами или дефисами). Если код страны слит
    с кодом города (``'8495…'``) или групп нет, — длина неизвестна.

    Args:
        phone_raw (str): Номер как в тексте.
        prefix_len (int): Число цифр кода страны в номере (0 или 1).

    Returns:
        Optional[int]: Длина кода города или None, если по записи её не понять.

    Пример:
        >>> _area_code_length('8 (3842) 12-34-56', 1)
        4
        >>> _area_code_length('8 3842 123456', 1)
        4
        >>> _area_code_length('951 164 9014', 0)
        3
        >>> _area_code_length('83842123456', 1) is None
        True
    """

    # Код в скобках
    in_brackets = re.search(
        r'\(\s*(\d+)\s*\)',
        phone_raw,
    )
    if in_brackets:
        return len(in_brackets.group(1))

    groups = re.findall(
        r'\d+',
        phone_raw,
    )

    # Код страны — отдельной группой («8 3842 …», «+7 3842 …»), иначе код не выделен
    if prefix_len:
        if len(groups) < 2 or len(groups[0]) != prefix_len:
            return None
        groups = groups[1:]

    # Одна группа — номер слитно, группировки нет
    if len(groups) < 2:
        return None

    return len(groups[0])


def normalize_phone(
    phone_raw : Optional[str],  # номер как в тексте (пробелы, дефисы, скобки, +)
) -> Optional[str]:
    """
    Приводит номер телефона РФ к виду ``+7 (XXX) XXX-XX-XX``.

    Распознаёт 11 цифр с ``7`` или ``8`` в начале и 10 цифр без кода страны (первая цифра —
    3, 4, 8 или 9). Код города из 4–5 цифр, выделенный в записи скобками или отдельной
    группой, сохраняется: ``+7 (3842) 12-34-56``, ``+7 (38451) 2-34-56`` (W3). Остальное
    (городской без кода, добавочный, другие страны) — не распознаётся: решение владельца
    2026-10-25 — только номера РФ, нераспознанный не записывается (сообщение —
    ``normalize_patient_dto``, W2).

    Поддерживает:
        - '951 164 9014' → +7 (951) 164-90-14
        - '8-999-123-45-67' → +7 (999) 123-45-67
        - '+79991234567' → +7 (999) 123-45-67
        - '9991234567' (10 цифр) → +7 (999) 123-45-67
        - '89991234567' (11 цифр, начинается с 8) → +7 (999) 123-45-67
        - '8 (3842) 12-34-56' → +7 (3842) 12-34-56
        - '4951234567' → +7 (495) 123-45-67

    Args:
        phone_raw (Optional[str]): Сырая строка телефона.

    Returns:
        Optional[str]: Отформатированный номер или None, если формат не распознан.

    Пример:
        >>> normalize_phone('8 (3842) 12-34-56')
        '+7 (3842) 12-34-56'
        >>> normalize_phone('12-34-56') is None
        True
    """
    # Было в описании (до 2026-10-25): '999 999 99999' → +7 (999) 999-99-99 — неверно:
    # это 11 цифр с 9 в начале, номер не распознавался и не распознаётся.

    if not phone_raw:
        return None

    # Оставляем только цифры
    digits = re.sub(r'\D', '', phone_raw)

    # Национальный номер (10 цифр) без кода страны
    if len(digits) == 11 and digits[0] in ('7', '8'):
        national = digits[1:]

    elif len(digits) == 10 and digits[0] in _RU_NATIONAL_FIRST_DIGITS:
        national = digits

    else:
        # Неподдерживаемый формат (W2: вызывающий сообщает пользователю)
        return None

    # Код города из 4–5 цифр — номер по исходной группировке (W3)
    code_len = _area_code_length(
        phone_raw,
        len(digits) - 10,
    )
    if code_len in _LONG_AREA_CODE_LENGTHS:
        code, rest = national[:code_len], national[code_len:]
        if len(rest) == 6:
            return f"+7 ({code}) {rest[0:2]}-{rest[2:4]}-{rest[4:6]}"
        return f"+7 ({code}) {rest[0:1]}-{rest[1:3]}-{rest[3:5]}"

    return f"+7 ({national[0:3]}) {national[3:6]}-{national[6:8]}-{national[8:10]}"

    # if not digits:
    #     return None
    #
    # len_digits = len(digits)
    # digits_0 = digits[0]
    #
    # # Если номер начинается с 8 или 9 и имеет 10 цифр, добавляем +7
    # if len_digits == 10 and digits_0 in ('8', '9'):
    #     digits = '7' + digits
    #
    # # Если номер имеет 11 цифр и начинается с 8, заменяем на +7
    # elif len_digits == 11 and digits_0 == '8':
    #     digits = '7' + digits[1:]
    #
    # # Если номер имеет 11 цифр и начинается с 7, оставляем как есть
    # elif len_digits == 11 and digits_0 == '7':
    #     pass
    #
    # else:
    #     # Неподдерживаемый формат – возвращаем как есть (или None)
    #     return None
    #
    # # Форматируем: +7 (XXX) XXX-XX-XX
    # # digits должно быть 11 цифр (7 + 10)
    # if len(digits) == 11:
    #     return f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    #
    # return None
    # ↑ до 2026-10-25 (W3): код города из 4–5 цифр («8 (3842) 12-34-56») выводился как
    #   +7 (384) 212-34-56 (цифры верны, вид неверный); 10 цифр с кодом города на 3 и 4
    #   (без «8») не распознавались.

def normalize_patient_dto(
    dto      : PatientDTO,                   # DTO пациента из шапки документа
    warnings : Optional[List[str]] = None,   # куда добавить предупреждения (None — не собирать)
) -> PatientDTO:
    """
    Централизованная нормализация данных пациента.

    - ФИО: удаление лишних пробелов.
    - Телефон: приведение к формату +7 (...) ... . Нераспознанный номер не записывается
      (поле — None), в ``warnings`` — предупреждение с исходным текстом и ФИО (W2,
      решение владельца 2026-10-25: пациент импортируется, пользователю сообщается).
    - Описание: удаление лишних пробелов.
    - Дата рождения: уже нормализована при создании DTO.

    Args:
        dto (PatientDTO): DTO пациента, возможно с неочищенными полями.
        warnings (Optional[List[str]]): Список для предупреждений; None — не собирать.

    Returns:
        PatientDTO: Тот же объект DTO после изменений (поля перезаписываются in-place).

    Пример:
        >>> found = []
        >>> dto = normalize_patient_dto(
        ...     PatientDTO(last_name='Иванов', first_name='Иван', phone='12-34-56'),
        ...     warnings = found,
        ... )
        >>> dto.phone is None, found
        (True, ['Телефон не распознан: «12-34-56» (пациент Иванов Иван) — не записан'])
    """

    if dto.first_name:
        dto.first_name = normalize_text(dto.first_name)

    if dto.last_name:
        dto.last_name = normalize_text(dto.last_name)

    if dto.middle_name:
        dto.middle_name = normalize_text(dto.middle_name)

    if dto.phone:
        phone_raw = dto.phone
        dto.phone = normalize_phone(phone_raw)

        # W2: нераспознанный номер не записываем, но сообщаем (исходный текст и пациент)
        if dto.phone is None and warnings is not None:
            warnings.append(
                f"Телефон не распознан: «{phone_raw}» "
                f"(пациент {patient_full_name(dto)}) — не записан"
            )

    if dto.description_text:
        dto.description_text = normalize_text(dto.description_text)

    return dto

def normalize_appointment_row(row: Dict, parser: 'WordFileParser') -> Dict:
    """
    Нормализует данные строки таблицы:
    - Преобразует дату из строки в datetime.date.
    - Очищает все текстовые поля.
    - Возвращает словарь с теми же ключами, но с обработанными значениями.

    Args:
        row (Dict): Словарь, представляющий строку таблицы (поля из документа).
        parser (WordFileParser): Экземпляр парсера, предоставляющий метод parse_date().

    Returns:
        Dict: Нормализованный словарь, где дата преобразована в date, тексты очищены,
              а поле 'photos' остаётся без изменений.
    """

    normalized = {}
    for key, value in row.items():
        if key == 'date':
            try:
                normalized[key] = parser.parse_date(value) if value else None
            except ValueError:
                normalized[key] = None  # или можно поднять исключение, но лучше пропустить строку

        elif key == 'photos':
            normalized[key] = value  # список путей – не трогаем

        else:
            normalized[key] = normalize_text(value) if value else None

    return normalized

def normalize_match(s: str) -> str:
    """
    Приводит строку к единому формату для сравнения:
    - нижний регистр
    - замена 'ё' на 'е'
    - удаление знаков препинания
    - нормализация пробелов

    Args:
        s (str): Исходная строка.

    Returns:
        str: Нормализованная строка, пригодная для сопоставления заголовков таблиц.
    """

    if not s:
        return ""
    
    s = s.lower()
    s = s.replace('ё', 'е')
    s = re.sub(r'[^\w\s]', '', s)      # удаляем всё, кроме букв, цифр, пробелов
    s = re.sub(r'\s+', ' ', s).strip() # сворачиваем множественные пробелы
    
    return s

# ----------------------------------------------------------------------
# Извлечение данных пациента из текста (исправленный класс)
# ----------------------------------------------------------------------


class PatientInfoExtractor:
    """
    Извлекает данные пациента из первых строк документа до первой таблицы.

    Ожидаемый формат строки:
        "Фамилия Имя [Отчество] [Год[г]] [Телефон] [Контакт]"

    Отчество — слово, которое не начинается с цифры, «+» или «(»; год — ровно 4 цифры
    (за ними не цифра), с пометкой «г» / «г.» или без; телефон — с цифры, «+» или «(»,
    внутри цифры, пробелы, скобки, дефисы, в конце цифра. Телефон сохраняется как в
    тексте (с группировкой — для кода города, W3), приводит его ``normalize_phone``.

    Пример:
        "Постольник Анастасия Александровна 2012г 951 164 9014 Анна тётя"

    Атрибуты класса:
        PATTERN (re.Pattern): Регулярное выражение для разбора строки пациента.
    """

    PATTERN = re.compile(
        r'^(?P<last_name>\S+)\s+(?P<first_name>\S+)'
        r'(?:\s+(?P<middle_name>(?![\d+(])\S+))?'          # отчество — не год и не телефон
        r'(?:\s+(?P<birth_year>\d{4})(?!\d)'               # год — ровно 4 цифры (W6)
        r'(?:\s*г\.?(?!\w))?)?'                            # пометка «г» / «г.», не начало слова
        r'(?:\s+(?P<phone>\+?\(?\d[\d\s()\-]*\d))?'        # телефон с +, скобками, дефисами (W5)
        r'\s*(?P<contact>.*)$'
    )
    # PATTERN = re.compile(
    #     r'^(?P<last_name>\S+)\s+(?P<first_name>\S+)\s+(?P<middle_name>\S+)?\s*'
    #     r'(?P<birth_year>\d{4})?г?\s*'
    #     r'(?P<phone>[\d\s]+)?\s*'
    #     r'(?P<contact>.*)$'
    # )
    # ↑ до 2026-10-25 (W5, W6): телефон — только цифры и пробелы («+7 …», «8-999-…»,
    #   «8 (3842) …» уходили в описание); год без «г» склеивался с телефоном
    #   («… 89991234567» → год 8999, телефон 1234567); без отчества год становился
    #   отчеством; «Фамилия Имя» без продолжения не распознавалась.

    @classmethod
    def extract(cls, text: str) -> Optional[PatientDTO]:
        """
        Извлекает DTO пациента из текста перед первой таблицей.

        Args:
            text (str): Текст, извлечённый из абзацев до первой таблицы.

        Returns:
            Optional[PatientDTO]: DTO с заполненными полями (first_name, last_name, ...)
                                  или None, если формат не распознан.
        """

        if not text:
            return None
        
        lines = text.strip().splitlines()
        if not lines:
            return None
        
        first_line = lines[0].strip()
        match = cls.PATTERN.match(first_line)
        if not match:
            return None

        data = match.groupdict()
        birth_year = data.get('birth_year')
        birth_date = None
        if birth_year:
            try:
                birth_date = date(int(birth_year), 1, 1)

            except ValueError:
                pass

        # Телефон — как в тексте, пробелы свёрнуты: группировка нужна normalize_phone (W3)
        phone_raw = data.get('phone')
        phone = ' '.join(phone_raw.split()) if phone_raw else None
        # phone = ''.join(phone_raw.split()) if phone_raw else None
        # ↑ до 2026-10-25 (W5): пробелы убирались — код города из 4–5 цифр не выделить
        # phone = normalize_phone(phone) if phone_raw else None

        # Контактная информация (описание пациента) – то, что после телефона
        description = (data.get('contact') or '').strip()
        if not description:
            description = None

        return PatientDTO(
            first_name       = data['first_name'].strip(),
            last_name        = data['last_name'].strip(),
            middle_name      = (data.get('middle_name') or '').strip() or None,  # группа может не совпасть — None
            birth_date       = birth_date,
            phone            = phone,
            description_text = description,
        )
        # middle_name=data.get('middle_name', '').strip() or None,
        # ↑ до 2026-10-25 (W6): отчество стало необязательным — группа может быть None


# ----------------------------------------------------------------------
# Парсер Word-файла (динамический маппинг столбцов + сохранение переносов)
# ----------------------------------------------------------------------

class WordFileParser:
    """
    Парсит один .docx файл: извлекает пациента, все строки таблиц и фото.

    Атрибуты:
        file_path (str): Путь к .docx файлу.
        doc (Document): Объект документа python-docx.
        field_metadata (List[Dict[str, Any]]): Метаданные полей из сервиса (для динамического маппинга).
        required_fields (List[str]): Список обязательных полей, полученный из field_metadata.
        mapping (Dict[str, str]): Словарь соответствия нормализованных заголовков → имена полей DTO.
    """

    # Словарь синонимов для каждого поля (для fallback-поиска)
    FIELD_SYNONYMS = {
        "date": ["дата", "дата приема", "дата приёма", "date", "день"],
        "reason_text": ["причина", "причина обращения", "жалобы", "reason"],
        "procedure_text": ["процедура", "выполненная процедура", "назначение", "procedure", "манипуляция"],
        "recommendations_text": ["рекомендации", "рекомендации и дата сл. приёма", "советы", "recommendations"],
        "cost_procedure_text": ["стоимость", "стоимость процедуры", "цена", "cost"],
        "note_text": ["примечание", "заметка", "note", "комментарий"],
        "photos": ["фото", "фотография", "изображение", "рисунок", "photo", "image", "приложение"],
    }
    
    def __init__(
        self, 
        file_path: str, 
        field_metadata: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Инициализирует парсер.

        Args:
            file_path (str): Путь к .docx файлу.
            field_metadata (Optional[List[Dict[str, Any]]]): Метаданные полей (из appointment_service.get_field_metadata()).
                Если не указаны, используется fallback-маппинг.
        """
        
        self.file_path = file_path
        self.doc = Document(file_path)
        self.field_metadata = field_metadata or {}
        self.required_fields = [] # возможно нужно разделить на ТБ к которым идёт обращение

        self.temp_dir = None

        # self.column_mapping = self._build_mapping_from_config()
        if not field_metadata:
            # fallback – использовать стандартные названия столбцов
            self.mapping = { # Точные названия столбцов (как в шаблоне)
                normalize_match("дата приема"): "date",
                normalize_match("причина обращения"): "reason_text",
                normalize_match("выполненная процедура"): "procedure_text",
                normalize_match("рекомендации и дата сл. приёма"): "recommendations_text",
                normalize_match("стоимость процедуры"): "cost_procedure_text",
                normalize_match("примечание"): "note_text",
                normalize_match("фото"): "photos",
            }

        else:
            self.mapping = {}
            for field in field_metadata:
                # пропускаем не редактируемые  (hidden=True)
                if not field.get('editable', False):
                    continue

                if field.get('required', False):
                    self.required_fields.append(field['name'])

                title = field.get('title', '').lower()
                if title:
                    norm_title = normalize_match(title)
                    self.mapping[norm_title] = field['name']

        # 0==0

    def _fallback_column_search(self, headers: List[str]) -> Dict[str, int]:
        """
        Расширенный поиск индексов столбцов по синонимам (FIELD_SYNONYMS).

        Args:
            headers (List[str]): Список заголовков столбцов (очищенных, но не нормализованных).

        Returns:
            Dict[str, int]: Словарь {имя_поля: индекс} для найденных полей.
        """
        
        fallback_mapping = {}
        # Приводим заголовки к нормализованному виду (нижний регистр, без пунктуации)
        normalized_headers = [normalize_match(header) for header in headers]

        for field_name, synonyms in self.FIELD_SYNONYMS.items():
            found_idx = None

            for idx, norm_header in enumerate(normalized_headers):
                if any(normalize_match(syn) in norm_header or norm_header == normalize_match(syn) for syn in synonyms):
                    found_idx = idx
                    break

            if found_idx is not None:
                fallback_mapping[field_name] = found_idx
                # self.logger.debug(f"Fallback: поле '{field_name}' сопоставлено столбцу {found_idx} ('{headers[found_idx]}')")
        
        return fallback_mapping

    def validate_required_fields(self, row_dict: Dict[str, Any]) -> None:
        """
        Проверяет, что все обязательные поля присутствуют в словаре и не пусты.

        Args:
            row_dict (Dict[str, Any]): Словарь строки таблицы.

        Raises:
            ValueError: Если отсутствует или пусто какое-либо обязательное поле.
        """

        missing = []
        for field_name in self.required_fields:
            value = row_dict.get(field_name)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(field_name)

        if missing:
            # Преобразуем имена полей в заголовки для читаемости (по возможности)
            titles = []
            for field in self.field_metadata:
                if field['name'] in missing:
                    titles.append(field.get('title', field['name']))

            raise ValueError(f"Отсутствуют или пусты обязательные поля: {', '.join(titles)}")


    # def _build_mapping_from_config(self) -> Dict[str, str]:
    #     """
    #     Строит маппинг заголовков столбцов (на основе title из field_configs)
    #     к именам полей DTO.
    #     """
    #     mapping = {}
    #     for field_name, config in self.field_configs.items():
    #         title = config.get('title', '').lower()
    #         if title:
    #             mapping[title] = field_name
    #     # Если конфигурация не задана или не содержит title, используем стандартные названия
    #     if not mapping:
    #         return {
    #             "дата приема": "date",
    #             "причина обращения": "reason_text",
    #             "выполненная процедура": "procedure_text",
    #             "рекомендации и дата сл. приёма": "recommendations_text",
    #             "стоимость процедуры": "cost_procedure_text",
    #             "примечание": "note_text",
    #             "фото": "photos",
    #         }
    #     return mapping

    def parse(self) -> Tuple[Optional[PatientDTO], List[Dict[str, Any]]]:
        """
        Основной метод парсинга файла.

        Returns:
            Tuple[Optional[PatientDTO], List[Dict[str, Any]]]:
                - DTO пациента (может быть None, если шапка не распознана)
                - Список строк таблиц, каждая строка – словарь с ключами:
                    date (str), reason_text (str, opt), procedure_text (str, opt),
                    recommendations_text (str, opt), cost_procedure_text (str, opt),
                    note_text (str, opt), photos (List[str], opt).
        """

        # Текст до первой таблицы
        pre_table_text = self._extract_text_before_first_table()
        patient = PatientInfoExtractor.extract(pre_table_text) if pre_table_text else None

        # Все таблицы документа (объединяем)
        tables = self.doc.tables
        if not tables:
            return patient, []

        all_rows = []
        for table in tables:
            rows = self._extract_rows_from_table(table)
            all_rows.extend(rows)
        
        return patient, all_rows

    def _extract_text_before_first_table(self) -> str:
        """Возвращает текст из всех абзацев до первой таблицы."""

        text_parts = []
        for element in self.doc.element.body:
            if element.tag.endswith('p'):
                para = Paragraph(element, self.doc)
                txt = para.text.strip()
                if txt:
                    text_parts.append(txt)

            elif element.tag.endswith('tbl'):
                break

        return "\n".join(text_parts)

    def _extract_rows_from_table(self, table: Table) -> List[Dict[str, Any]]:
        """
        Извлекает строки из одной таблицы (пропуская заголовок).

        Returns:
            List[Dict[str, Any]]: Список строк (каждая как словарь).
        """

        if len(table.rows) < 2:
            return []
        
        header_row = table.rows[0]
        col_indexes = self._map_columns(header_row)
        rows_data = []
        for row in table.rows[1:]:
            if self._is_row_empty(row):
                continue

            row_dict = {}
            for col_name, idx in col_indexes.items():
                if idx >= len(row.cells):
                    continue

                cell = row.cells[idx]

                # Текст
                text = self._clean_text(cell.text)
                if text:
                    row_dict[col_name] = text

                # Фото (только для колонки 'photos')
                if col_name == 'photos':
                    photos = self._extract_images_from_cell(cell)
                    if photos:
                        row_dict['photos'] = photos

            if row_dict:
                rows_data.append(row_dict)

        return rows_data

    def _cell_contains_images(self, cell) -> bool:
        """
        Проверяет, содержит ли ячейка встроенные изображения (drawing).

        Returns:
            bool: True, если есть хотя бы один тег w:drawing.
        """

        return len(cell._element.findall('.//' + qn('w:drawing'))) > 0

    def _map_columns(self, header_row) -> Dict[str, int]:
        """
        Определяет соответствие столбцов полям.
        Сначала пробует стандартный поиск (по self.mapping).
        Если какие-то поля не найдены, запускает fallback-поиск по синонимам.
        Если поле 'photos' всё ещё не найдено, ищет столбец с вложениями.

        Returns:
            Dict[str, int]: Словарь {имя_поля: индекс_столбца}.
        """
        
        headers = [self._clean_text(cell.text) for cell in header_row.cells]
        mapping = {}

        # Стандартный поиск
        for idx, cell in enumerate(header_row.cells):
            # W9: заголовок — тем же normalize_match, что и ключи self.mapping
            header = normalize_match(cell.text)
            # header = self._clean_text(cell.text).lower()
            # ↑ до 2026-10-25 (W9): ключи mapping нормализованы (ё → е, без пунктуации), а
            #   заголовок — только в нижнем регистре: «Дата приёма» не совпадала с title
            for pattern, field_name in self.mapping.items():
                if pattern in header:
                    mapping[field_name] = idx
                    break

        # Проверяем, все ли нужные поля найдены
        required_for_import = ["date", "photos"]  # дата и фото – минимально необходимые
        missing_fields = [f for f in required_for_import if f not in mapping]

        if missing_fields:
            # Запускаем fallback-поиск только для недостающих полей
            fallback = self._fallback_column_search(headers)
            for f in missing_fields:
                if f in fallback:
                    mapping[f] = fallback[f]
                    # self.logger.warning(f"Поле '{f}' найдено через fallback: столбец {fallback[f]}")
                # else:
                    # self.logger.warning(f"Поле '{f}' не найдено ни стандартным, ни fallback-поиском")

        # Если поле photos всё ещё не найдено – можно попробовать поискать по наличию вложенных изображений
        if "photos" not in mapping:
            for idx, cell in enumerate(header_row.cells):
                if self._cell_contains_images(cell):
                    mapping["photos"] = idx
                    # self.logger.warning(f"Столбец {idx} определён как фото по наличию встроенных изображений")

                    break

        return mapping

    def _is_row_empty(self, row) -> bool:
        """Проверяет, что все ячейки строки пусты (не содержат текста)."""

        return all(not cell.text.strip() for cell in row.cells)

    def _clean_text(self, text: str) -> str:
        """Очищает текст, сохраняя переносы строк (для полей таблицы)."""

        if not text:
            return ""
        
        text = text.replace('\r', '\n')
        text = re.sub(r'[\t\x0b\x0c]', ' ', text)
        lines = text.splitlines()

        # Убираем пустые строки в начале и конце, внутренние сохраняем
        while lines and not lines[0].strip():
            lines.pop(0)

        while lines and not lines[-1].strip():
            lines.pop()

        return '\n'.join(lines)

    def _extract_images_from_cell(self, cell) -> List[str]:
        """
        Извлекает все встроенные изображения из ячейки.
        Сохраняет их во временную папку и возвращает список абсолютных путей.

        Returns:
            List[str]: Список путей к временным файлам изображений.
        """

        images = []

        # W8: своя временная папка в системной временной (одна на файл), не в папке документов
        if self.temp_dir is None:
            self.temp_dir = tempfile.mkdtemp(prefix='project_med_docx_')
        # self.temp_dir = os.path.join(
        #     os.path.dirname(self.file_path),
        #     "temp_images"
        # )
        # os.makedirs(self.temp_dir, exist_ok=True)
        # ↑ до 2026-10-25 (W8): папка temp_images в папке документов удалялась целиком
        #   (shutil.rmtree в parse_one_file) — одноимённая папка пользователя стиралась;
        #   запись в папку документов (может быть общей / только для чтения).

        for drawing in cell._element.findall('.//' + qn('w:drawing')):
            blip = drawing.find('.//' + qn('a:blip'))
            if blip is not None:
                r_id = blip.get(qn('r:embed'))
                if r_id:
                    image_part = cell.part.related_parts.get(r_id)
                    if image_part and hasattr(image_part, 'image'):
                        img = image_part.image
                        ext = img.ext
                        filename = f"{uuid.uuid4().hex}.{ext}"
                        path = os.path.join(self.temp_dir, filename)

                        with open(path, 'wb') as f:
                            f.write(img.blob)

                        images.append(path)
        return images

    @staticmethod
    def parse_date(date_str: str) -> date:
        """
        Преобразует строку с датой в объект datetime.date.

        Поддерживаемые форматы:
            - DD.MM.YY (14.03.26 → 2026-03-14)
            - DD.MM.YYYY (14.03.2026)
            - YYYY-MM-DD

        Args:
            date_str (str): Строка с датой.

        Returns:
            date: Объект date.

        Raises:
            ValueError: Если формат не распознан.
        """

        date_str = date_str.strip()

        if re.match(r'\d{1,2}\.\d{1,2}\.\d{2}$', date_str):
            d, m, y_s = map(int, date_str.split('.'))
            y = 2000 + y_s if y_s < 100 else y_s
            return date(y, m, d)
        
        if re.match(r'\d{1,2}\.\d{1,2}\.\d{4}$', date_str):
            d, m, y = map(int, date_str.split('.'))
            return date(y, m, d)
        
        try:
            return date.fromisoformat(date_str)
        
        except ValueError:
            raise ValueError(f"Неверный формат даты: {date_str}")

# ----------------------------------------------------------------------
# Вспомогательные функции для работы с пациентом
# ----------------------------------------------------------------------

def find_matching_patient(session, patient_dto: PatientDTO) -> Optional['Patient']:
    """
    Ищет пациента, у которого совпадают все непустые поля из patient_dto.

    Args:
        session: Сессия SQLAlchemy.
        patient_dto (PatientDTO): DTO пациента, полученный из Word-файла.

    Returns:
        Optional[Patient]: ORM-объект пациента, если найден, иначе None.
    """

    repo = PatientRepository(session)
    candidates = repo.get_all()
    for p in candidates:
        match = True

        if patient_dto.last_name and p.last_name != patient_dto.last_name:
            match = False

        if match and patient_dto.first_name and p.first_name != patient_dto.first_name:
            match = False

        if match and patient_dto.middle_name and p.middle_name != patient_dto.middle_name:
            match = False

        if match and patient_dto.birth_date and p.birth_date != patient_dto.birth_date:
            match = False

        if match and patient_dto.phone and p.phone != patient_dto.phone:
            match = False

        if match and patient_dto.description_text and p.description_text != patient_dto.description_text:
            match = False

        if match:

            return p
        
    return None

def update_patient_if_needed(
    existing_patient: 'Patient', 
    patient_dto: PatientDTO, 
    session
) -> PatientDTO:
    """
    Обновляет поля существующего пациента значениями из DTO, если они отличаются.

    Args:
        existing_patient (Patient): ORM-объект существующего пациента.
        patient_dto (PatientDTO): DTO с новыми данными (из Word-файла).
        session: Сессия SQLAlchemy.

    Returns:
        PatientDTO: Обновлённый DTO после синхронизации с БД.
    """

    updated = False
    if patient_dto.last_name and existing_patient.last_name != patient_dto.last_name:
        existing_patient.last_name = patient_dto.last_name
        updated = True

    if patient_dto.first_name and existing_patient.first_name != patient_dto.first_name:
        existing_patient.first_name = patient_dto.first_name
        updated = True

    if patient_dto.middle_name and existing_patient.middle_name != patient_dto.middle_name:
        existing_patient.middle_name = patient_dto.middle_name
        updated = True

    if patient_dto.birth_date and existing_patient.birth_date != patient_dto.birth_date:
        existing_patient.birth_date = patient_dto.birth_date
        updated = True

    if patient_dto.phone and existing_patient.phone != patient_dto.phone:
        existing_patient.phone = patient_dto.phone
        updated = True

    if patient_dto.description_text and existing_patient.description_text != patient_dto.description_text:
        existing_patient.description_text = patient_dto.description_text
        updated = True
    
    if updated:
        session.flush()
        # Обновляем DTO, чтобы отразить изменения
        return PatientDTO.model_validate(existing_patient)
    
    return patient_dto

# ----------------------------------------------------------------------
# Обработка одного файла (с транзакцией)
# ----------------------------------------------------------------------

def parse_one_file(
    session                 : Session,                      # сессия SQLAlchemy (транзакцией управляет вызывающий)
    file_path               : str,                          # путь к .docx
    patient_service         : PatientService,               # сервис пациентов
    appointment_service     : AppointmentService,           # сервис приёмов
    photo_service           : PhotoService,                 # сервис фото
    update_existing_patient : bool = False,                 # искать совпадающего пациента и обновлять его
    warnings                : Optional[List[str]] = None,   # куда добавить предупреждения (W2); None — не собирать
) -> bool:
    """
    Обрабатывает один Word-файл в рамках переданной сессии.

    Порядок: разбор файла (``WordFileParser``) → нормализация пациента и строк → проверка
    обязательных полей → поиск / создание пациента → приёмы → фото. Временные файлы фото
    и их папка удаляются в любом случае (W8 — папка своя, системная временная).

    Args:
        session (Session): Сессия SQLAlchemy (управляется вызывающим кодом).
        file_path (str): Путь к .docx файлу.
        patient_service (PatientService): Сервис для работы с пациентами.
        appointment_service (AppointmentService): Сервис для работы с приёмами.
        photo_service (PhotoService): Сервис для работы с фотографиями.
        update_existing_patient (bool): Если True, при совпадении пациента его данные обновляются,
                                        иначе создаётся новый пациент.
        warnings (Optional[List[str]]): Список для предупреждений — нераспознанный телефон
            (W2: телефон не записан, пациент импортирован); None — не собирать.

    Returns:
        bool: True – успешная обработка (при ошибке — исключение).

    Raises:
        ValueError: При ошибках структуры документа, отсутствии обязательных полей,
                    проблемах с датами и т.п.

    Пример:
        >>> found = []
        >>> with db.session_scope() as session:
        ...     parse_one_file(
        ...         session,
        ...         'doc/Иванов.docx',
        ...         patient_service,
        ...         appointment_service,
        ...         photo_service,
        ...         warnings = found,
        ...     )
        True
    """

    parser = None
    temps_path = []
    try:
        parser = WordFileParser(
            file_path,
            field_metadata = appointment_service.get_field_metadata(),  # заголовки столбцов — по title полей
        )
        patient_dto, rows = parser.parse()

        for row in rows:
            if 'photos' in row and row['photos']:
                for temp_path in row['photos']:
                    temps_path.append(temp_path)

        if not patient_dto:
            raise ValueError("Не удалось извлечь данные пациента (отсутствует шапка)")

        if not rows:
            raise ValueError("Не удалось извлечь данные приёмов (отсутствует таблица)")

        # ----- ЦЕНТРАЛИЗОВАННАЯ НОРМАЛИЗАЦИЯ ДАННЫХ -----
        # ----- НОРМАЛИЗАЦИЯ ДАННЫХ ПАЦИЕНТА -----
        # W2: нераспознанный телефон — предупреждение в warnings, телефон не записывается
        patient_dto = normalize_patient_dto(
            patient_dto,
            warnings = warnings,  # список вызывающего (None — не собирать)
        )
        # patient_dto = normalize_patient_dto(patient_dto)
        # ↑ до 2026-10-25 (W2): нераспознанный телефон терялся молча

        # ----- НОРМАЛИЗАЦИЯ И ПРОВЕРКА СТРОК ТАБЛИЦЫ -----
        normalized_rows = []
        for row in rows:
            norm_row = normalize_appointment_row(row, parser)

            # Проверяем обязательные поля
            try:
                parser.validate_required_fields(norm_row)
            except ValueError as e:
                # Добавляем в сообщение имя файла и исходные данные строки для отладки
                raise ValueError(f"В файле {os.path.basename(file_path)}: {e}. Данные строки: {row}") from e

            for key in row.keys(): # Проверяем, что все обязательные поля были нормализованы
                if key in parser.required_fields:
                    if (
                        row.get(key, None) is not None
                    ) and (
                        norm_row.get(key, None) is None
                    ):
                        raise ValueError(f"В файле {os.path.basename(file_path)}: Не удалось нормализовать строку: {row}")

            # # Пропускаем строки, где дата не распарсилась
            # if norm_row.get('date') is None:
            #     continue

            normalized_rows.append(norm_row)

        if not normalized_rows:
            raise ValueError("После нормализации не осталось корректных строк с приёмами")

        # ----- ПОИСК ИЛИ СОЗДАНИЕ ПАЦИЕНТА -----
        existing = None
        if update_existing_patient:
            existing = find_matching_patient(session, patient_dto)

        if existing:
            patient_id = existing.id
            if update_existing_patient:
                # Обновляем найденного пациента данными из DTO
                patient_dto = update_patient_if_needed(existing, patient_dto, session)

        else:
            created = patient_service.create(
                patient_dto,
                session = session,  # транзакция файла
            )
            patient_id = created.id

        # ----- СОЗДАНИЕ ПРИЁМОВ -----
        for row in normalized_rows:
            app_dto = AppointmentDTO(
                patient_id           = patient_id,                        # пациент файла
                date                 = row['date'],                       # дата приёма (обязательна)
                reason_text          = row.get('reason_text'),            # причина обращения
                procedure_text       = row.get('procedure_text'),         # выполненная процедура
                recommendations_text = row.get('recommendations_text'),   # рекомендации
                cost_procedure_text  = row.get('cost_procedure_text'),    # стоимость процедуры
                note_text            = row.get('note_text'),              # примечание
            )

            saved = appointment_service.create_appointment(
                app_dto,
                session = session,  # транзакция файла
            )

            # Обработка фото
            if 'photos' in row and row['photos']:
                for temp_path in row['photos']:
                    # 0==0
                    photo_service.add_photo_to_appointment(
                        saved.id,                    # приём
                        temp_path,                   # временный файл рисунка
                        row.get('note_text', ''),    # описание фото — примечание строки
                        session = session,           # транзакция файла
                    )

                    # 0==0

        return True
    except Exception as e:
        raise e

    finally:
        for temp_path in temps_path:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        # W8: временная папка — своя (tempfile.mkdtemp в WordFileParser), удаляется целиком;
        # берётся у парсера и тогда, когда parse() упал посередине
        temp_dir = parser.temp_dir if parser is not None else None
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(
                temp_dir,
                ignore_errors = True,  # не мешать результату файла
            )
        # temp_dir = None  (в начале)  …  temp_dir = parser.temp_dir  (после parser.parse())
        # if temp_dir:
        #     if os.path.exists(temp_dir):
        #         # try:
        #         shutil.rmtree(
        #             temp_dir,
        #             ignore_errors=True
        #         )
        #         # except OSError as e:
        #         #     # print(f"Ошибка при удалении папки: {e}")
        #         #     pass
        # ↑ до 2026-10-25 (W8): папка temp_images была в папке документов (rmtree стирал
        #   одноимённую папку пользователя); при ошибке внутри parse() не удалялась.



# ----------------------------------------------------------------------
# Пакетная обработка (папка / список файлов)
# ----------------------------------------------------------------------

def _empty_results() -> Dict[str, Any]:
    """
    Пустой словарь результатов пакетной обработки (общий вид для всех веток).

    Returns:
        Dict[str, Any]: ``total``, ``success``, ``failed`` — 0; ``success_files``,
        ``error_files``, ``warnings`` — пустые списки.

    Пример:
        >>> _empty_results()['warnings']
        []
    """

    return {
        'total'         : 0,
        'success'       : 0,
        'failed'        : 0,
        'success_files' : [],
        'error_files'   : [],
        'warnings'      : [],   # W2: [{'file_name': ..., 'warning': ...}]
    }


def batch_parse(
    folder_path              : str,                                             # папка с .docx
    specific_files           : Optional[List[str]] = None,                      # имена файлов; None — все необработанные (W7)
    update_existing_patient  : bool = False,                                    # обновлять совпадающего пациента
    db                       : Optional[Database] = None,                       # база (None — из app.dependencies)
    patient_service          : Optional[PatientService] = None,                 # сервис пациентов (None — из app.dependencies)
    appointment_service      : Optional[AppointmentService] = None,             # сервис приёмов (None — из app.dependencies)
    photo_service            : Optional[PhotoService] = None,                   # сервис фото (None — из app.dependencies)

    progress_callback_start  : Optional[Callable[[List[str]], None]] = None,    # до начала: имена всех файлов
    progress_callback_update : Optional[Callable[[str, str, str], None]] = None,  # по файлу: имя, статус, сообщение
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Обрабатывает .docx файлы папки (указанные или все необработанные).

    Создаёт общий лог-файл ``parser.log`` в подпапке ``logs_parser``. Каждый файл
    обрабатывается в отдельной транзакции.

    Без ``specific_files`` берутся все ``.docx`` папки, кроме временных ``~$…`` и уже
    успешно обработанных по журналу (W7 — так вызывает окно).

    Args:
        folder_path (str): Путь к папке с файлами.
        specific_files (Optional[List[str]]): Список имён файлов для обработки (без путей).
        update_existing_patient (bool): Обновлять ли данные существующего пациента.
        db (Optional[Database]): Экземпляр Database (если None – берётся из dependencies).
        patient_service (Optional[PatientService]): Сервис пациентов.
        appointment_service (Optional[AppointmentService]): Сервис приёмов.
        photo_service (Optional[PhotoService]): Сервис фото.
        progress_callback_start: Вызывается перед началом, передаёт список всех имён файлов.
        progress_callback_update: Вызывается до и после обработки каждого файла,
            параметры (file_name, status, message) — все строки. Статусы: 'processing',
            'success' (message — предупреждения через «; » или пусто), 'failed'
            (message — текст ошибки).

    Returns:
        Tuple[Dict[str, Any], Optional[str]]: Результаты и папка журнала (None — файлов нет).
            Результаты:
            - total (int): Всего обработано файлов.
            - success (int): Успешно.
            - failed (int): С ошибками.
            - success_files (List[str]): Имена успешных файлов.
            - error_files (List[Dict]): Список словарей {file_name, error} (error — исключение).
            - warnings (List[Dict]): Список словарей {file_name, warning} — предупреждения
              успешных файлов (W2: телефон не распознан и не записан).

    Пример:
        >>> results, log_dir = batch_parse('doc')
        >>> results['success'], os.path.basename(log_dir)
        (4, 'logs_parser')
    """

    if db is None:
        from app.dependencies import get_db # циклы
        db = get_db()

    if patient_service is None:
        from app.dependencies import get_patient_service # циклы
        patient_service = get_patient_service()

    if appointment_service is None:
        from app.dependencies import get_appointment_service # циклы
        appointment_service = get_appointment_service()

    if photo_service is None:
        from app.dependencies import get_photo_service # циклы
        photo_service = get_photo_service()

    # Папка и файл журнала: общий журнал на все запуски
    log_dir = os.path.join(folder_path, "logs_parser")
    log_file = os.path.join(log_dir, "parser.log")
    # log_file = os.path.join(
    #     log_dir,
    #     # f"parser_{timestamp}.log" # не используем, так как нужен общий лог
    #     f"parser.log" # делаем общий лог на файлы
    # )
    # ↑ до 2026-10-25 (W7): путь журнала нужен до выбора файлов (фильтр по журналу)

    # Собираем файлы
    if specific_files:
        file_paths = [os.path.join(folder_path, f) for f in specific_files if f.endswith('.docx')]
    else:
        # W7: все .docx без временных «~$…» и без успешно обработанных по журналу — как pars_start
        file_names = filter_unprocessed_files(
            get_all_docx_files(folder_path),   # .docx папки без временных
            log_file,                          # журнал прошлых запусков
        )
        file_paths = [os.path.join(folder_path, f) for f in file_names]
        # file_paths = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith('.docx')]
        # ↑ до 2026-10-25 (W7): окно (specific_files=None) импортировало заново уже
        #   обработанные файлы (дубли пациентов) и временные файлы Word «~$…».

    if not file_paths:
        # W7: всегда пара (результаты, папка журнала) — окно распаковывает её
        return _empty_results(), None
        # return {'total': 0, 'success': 0, 'failed': 0, 'success_files': [], 'error_files': []}
        # ↑ до 2026-10-25 (W7): словарь вместо пары — окно падало «too many values to unpack»

    # Создаём папку для логов
    os.makedirs(log_dir, exist_ok=True)

    time_log = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    results = _empty_results()
    results['total'] = len(file_paths)

    # Вызываем callback начала
    if progress_callback_start:
        all_names = [os.path.basename(p) for p in file_paths]
        progress_callback_start(all_names)

    with open(log_file, 'a', encoding='utf-8') as log:
        #  Описание: "!!>>\tВремя запуска парсера\tВремя файла\tФайл\tСтатус\tСообщение\n")
        # !!>> - метка начала лога (на всякий случай если ошибка с переносами)

        text_format_log = "\t".join(
            [
                "!!>>",               # !!>> - метка начала лога (на всякий случай если ошибка с переносами)
                "{time_log}",         # Время запуска парсера
                "{time_pars_log}",    # Время парсера файла
                "{file_name_pars}",   # Время файла
                "{status_pars}",      # Статус парсинга
                "{err_mas_pars}",     # Сообщени ошибки парсинга (ЕСЛИ ЕСТЬ); у успешного — предупреждения (W2)
            ]
        ) + '\n'

        for file_path in file_paths:
            file_name = os.path.basename(file_path)
            file_warnings: List[str] = []   # W2: предупреждения этого файла
            with db.session_scope() as session:

                if progress_callback_update:
                    progress_callback_update(file_name, "processing", "")
                msg = None
                try:
                    success = parse_one_file(
                        session,                                            # транзакция файла
                        file_path,                                          # файл
                        patient_service,                                    # сервисы
                        appointment_service,
                        photo_service,
                        update_existing_patient = update_existing_patient,  # обновлять совпадающего
                        warnings                = file_warnings,            # W2: предупреждения
                    )

                except Exception as e:
                    success = False
                    msg = e

                # W2: предупреждения успешного файла — в журнал, результаты и колбэк; у файла
                # с ошибкой они не нужны (по нему ничего не записано)
                warning_text = '; '.join(file_warnings) if success else ''

                log.write(
                    text_format_log.format(
                        time_log       = time_log,                                       # запуск
                        time_pars_log  = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),   # файл
                        file_name_pars = file_name,                                      # имя файла
                        status_pars    = 'success' if success else 'failed',             # статус
                        err_mas_pars   = str(msg) if msg else warning_text,              # ошибка / предупреждения
                    )
                )

                if success:
                    results['success'] += 1
                    results['success_files'].append(file_name)
                    for warning in file_warnings:
                        results['warnings'].append(
                            {
                                'file_name' : file_name,
                                'warning'   : warning,
                            }
                        )
                    if progress_callback_update:
                        progress_callback_update(file_name, "success", warning_text)
                else:
                    results['failed'] += 1
                    results['error_files'].append(
                        {
                            'file_name': file_name,
                            'error': msg,
                        }
                    )
                    # W10: в колбэк — текст ошибки (сигнал окна Signal(str, str, str)
                    # превращал исключение в пустую строку: «❌ Ошибка:» без текста)
                    if progress_callback_update:
                        progress_callback_update(file_name, "failed", str(msg))
                    # if progress_callback_update:
                    #     progress_callback_update(file_name, "failed", msg)
                    # ↑ до 2026-10-25 (W10): передавалось исключение, а не строка


                # if msg:
                #     raise msg

            # Автоматический коммит/откат уже выполнен внутри session_scope

    return results , log_dir


def format_results(
    results : Dict[str, Any],   # результаты batch_parse / pars_start
) -> str:
    """
    Текст итогов импорта для пользователя: счётчики, ошибки, предупреждения, журнал.

    Args:
        results (Dict[str, Any]): Результаты ``batch_parse`` / ``pars_start``.

    Returns:
        str: Многострочный текст (без завершающего переноса).

    Пример:
        >>> print(format_results({'total': 1, 'success': 1, 'failed': 0, 'error_files': [],
        ...     'warnings': [{'file_name': 'а.docx', 'warning': 'Телефон не распознан'}]}))
        Обработано файлов: 1
        Успешно: 1
        Ошибок: 0
        Предупреждения:
          а.docx: Телефон не распознан
    """

    lines = [
        f"Обработано файлов: {results.get('total', 0)}",
        f"Успешно: {results.get('success', 0)}",
        f"Ошибок: {results.get('failed', 0)}",
    ]

    for error in results.get('error_files', []):
        lines.append(f"  {error['file_name']}: {error['error']}")

    if results.get('warnings'):
        lines.append("Предупреждения:")
        for warning in results['warnings']:
            lines.append(f"  {warning['file_name']}: {warning['warning']}")

    if results.get('log_path'):
        lines.append(f"Журнал: {results['log_path']}")

    return '\n'.join(lines)


# ----------------------------------------------------------------------
# Точка входа для дебага
# ----------------------------------------------------------------------

def pars_start(
    folder                   : Optional[str] = None,                            # папка с .docx (нужна)
    files                    : Optional[List[str]] = None,                      # имена файлов; None — все необработанные
    update_existing_patient  : bool = False,                                    # обновлять совпадающего пациента

    progress_callback_start  : Optional[Callable[[List[str]], None]] = None,    # до начала: имена всех файлов
    progress_callback_update : Optional[Callable[[str, str, str], None]] = None,  # по файлу: имя, статус, сообщение
) -> Dict[str, Any]:
    """
    Точка входа для запуска парсера.

    Без ``files`` берутся все необработанные ``.docx`` папки (отбор — в ``batch_parse``).

    Args:
        folder (Optional[str]): Путь к папке.
        files (Optional[List[str]]): Список имён файлов.
        update_existing_patient (bool): Флаг обновления существующих пациентов.
        progress_callback_start: Как в ``batch_parse``.
        progress_callback_update: Как в ``batch_parse``.

    Returns:
        Dict[str, Any]: Результаты ``batch_parse`` и ``log_path`` — путь к ``parser.log``
        (если файлы обрабатывались).

    Пример:
        >>> print(format_results(pars_start('doc')))
        Обработано файлов: 0
        Успешно: 0
        Ошибок: 0
    """

    results, log_dir = batch_parse(
        folder,
        specific_files           = files or None,              # None — отбор в batch_parse (W7)
        update_existing_patient  = update_existing_patient,

        progress_callback_start  = progress_callback_start,
        progress_callback_update = progress_callback_update,
    )

    if log_dir:
        results['log_path'] = os.path.join(log_dir, "parser.log")

    return results

    # results = {'total': 0, 'success': 0, 'failed': 0, 'success_files': [], 'error_files': []}
    #
    # log_path = None
    # if not files:
    #     files = get_all_docx_files(folder)
    #     if not files:
    #         # # raise ValueError("В указанной папке нет .docx файлов.")
    #         # print("В указанной папке нет .docx файлов.")
    #         return results
    #
    #     # Путь к лог-файлу (предполагаем, что он лежит в той же папке)
    #     log_path = os.path.join(folder, "logs_parser", "parser.log")
    #
    #     # Если лог существует, отфильтровываем уже обработанные файлы
    #     if os.path.exists(log_path):
    #         to_process = filter_unprocessed_files(files, log_path)
    #         # print(f"Из {len(files)} файлов уже обработано успешно: {len(files) - len(to_process)}")
    #         files = to_process
    #
    # if files:
    #     results, log_path = batch_parse(
    #         folder,
    #         specific_files=files,
    #         update_existing_patient = update_existing_patient,
    #
    #         progress_callback_start=progress_callback_start,
    #         progress_callback_update=progress_callback_update,
    #     )
    #
    #     if log_path:
    #         results['log_path'] = log_path
    #
    # return results
    # ↑ до 2026-10-25 (W7): отбор необработанных файлов — теперь в batch_parse (там же для
    #   окна); log_path был папкой журнала, а не файлом.


def pars_start_args(
    folder : Optional[str] = None,          # папка, если не задана --folder
    files  : Optional[List[str]] = None,    # файлы, если не заданы --files
    argv   : Optional[List[str]] = None,    # аргументы командной строки (None — sys.argv[1:])
) -> Dict[str, Any]:
    """
    Точка входа для запуска парсера из командной строки (для отладки и автономного использования).

    Поддерживаемые аргументы командной строки:
        --folder <path>               Путь к папке с .docx файлами (обязателен, если не передан в вызове).
        --files file1.docx,file2.docx Опциональный список файлов (если не указан, берутся все необработанные .docx).
        --update_existing_patient     Флаг: обновлять данные существующего пациента.
        --help                        Показать справку.

    Аргументы командной строки главнее параметров вызова (Ф1.1.7: раньше папка из вызова
    перекрывала ``--folder``, и в ``pars_start.py`` был зашит путь Linux). Нет папки или
    папки не существует — сообщение и выход с кодом 2 (``argparse``).

    Args:
        folder (Optional[str]): Путь к папке (будет переопределён аргументом --folder).
        files (Optional[List[str]]): Список файлов (будет переопределён аргументом --files).
        argv (Optional[List[str]]): Аргументы (для тестов); None — ``sys.argv[1:]``.

    Returns:
        Dict[str, Any]: Результат работы ``pars_start``.

    Пример:
        >>> results = pars_start_args(argv=['--folder', 'doc', '--files', 'а.docx,б.docx'])
    """

    # Пример использования:
    # python pars_start.py --folder /path/to/files --files file1.docx,file2.docx
    # или: python pars_start.py --folder /path/to/files (все необработанные файлы)

    arg_parser = argparse.ArgumentParser(
        prog        = 'pars_start.py',                                       # имя в справке
        description = 'Импорт пациентов и приёмов из Word (.docx) в базу.',  # о программе
    )
    arg_parser.add_argument(
        '--folder',
        help = 'папка с .docx файлами',
    )
    arg_parser.add_argument(
        '--files',
        help = 'имена файлов через запятую (по умолчанию — все необработанные .docx папки)',
    )
    arg_parser.add_argument(
        '--update_existing_patient',
        action = 'store_true',                                 # флаг без значения
        help   = 'обновлять данные совпадающего пациента',
    )
    args = arg_parser.parse_args(argv)

    # Командная строка главнее параметров вызова
    folder = args.folder or folder
    if args.files:
        files = [f.strip() for f in args.files.split(',') if f.strip()]

    if not folder:
        arg_parser.error("укажите папку с файлами: --folder <путь>")

    if not os.path.isdir(folder):
        arg_parser.error(f"папки нет: {folder}")

    results = pars_start(
        folder                  = folder,                     # папка
        files                   = files,                      # файлы (None — все необработанные)
        update_existing_patient = args.update_existing_patient,
    )

    return results

    # _files = []
    # update_existing_patient = False
    #
    # args = sys.argv[1:]
    # for i, arg in enumerate(args):
    #     if arg == '--folder' :
    #         if folder is None:
    #             folder = args[i+1]
    #
    #     elif arg == '--update_existing_patient':
    #         update_existing_patient = True
    #
    #     elif arg == '--files' and i+1 < len(args):
    #         if files is None:
    #             # _files = args[i+1].split(',')
    #             _files = [f for f in args[i+1].split(',') if f.strip()]
    #
    #     elif arg == '--help':
    #         print("Usage: python word_importer.py --folder <path> [--files file1.docx,file2.docx]")
    #         sys.exit(0)
    #
    # if files is None:
    #     files = _files
    #
    # if not folder:
    #     print("Укажите папку с файлами: --folder /path/to/docx")
    #     sys.exit(1)
    #
    # results = pars_start(
    #     folder = folder,
    #     files = files,
    #     update_existing_patient = update_existing_patient,
    # )
    #
    # return results
    # ↑ до 2026-10-25 (Ф1.1.7): папка из вызова перекрывала --folder (pars_start.py с
    #   зашитым путём Linux не давал задать папку); «--folder» последним — IndexError.


if __name__ == "__main__":
    # Пример вызова: python -m parsers.word_importer --folder <папка> [--files тест1.docx]
    from app.config.logging_setup import setup_logging

    # Логгеры не читают конфиг сами: передаём его до любой работы (как pars_start.py)
    setup_logging()

    print(
        format_results(
            pars_start_args(),
        )
    )

    # pars_start_args(
    #     folder = '/home/admin-rkc/Git/My_cods/project_med/doc',
    #     files = 'тест1.docx',
    # )
    # ↑ до 2026-10-25 (Ф1.1.7): зашитый путь Linux; files — строка, а не список (перебор
    #   по буквам — ни одного файла).
