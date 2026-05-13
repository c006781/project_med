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

import os
import re
import shutil
import sys
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

from app.database.database import Database
from app.dto.dto_all import PatientDTO, AppointmentDTO
from app.services.services_all import (
    PatientService, 
    AppointmentService, 
    PhotoService
)
from app.repositories.repositories_all import PatientRepository
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

def normalize_text(text: str) -> str:
    """
    Очищает текст, но сохраняет переносы строк.

    - Заменяет \\r на \\n.
    - Удаляет лишние пробелы и табуляции, но не трогает \\n.
    - Убирает пустые строки в начале и конце.

    Args:
        text (str): Исходный текст.

    Returns:
        str: Очищенная строка с сохранёнными внутренними переносами.
    """

    if not text:
        return ""
    
    text = text.replace('\r', '\n')
    text = re.sub(r'[\t\x0b\x0c]', ' ', text)   # табуляции -> пробел
    lines = text.splitlines()

    # Убираем только пустые строки в начале и конце, внутренние сохраняем
    if lines:

        # убираем начальные пустые
        while lines and not lines[0].strip():
            lines.pop(0)

        # убираем конечные пустые
        while lines and not lines[-1].strip():
            lines.pop()

    return '\n'.join(lines)

def normalize_phone(phone_raw: str) -> Optional[str]:
    """"
    Приводит номер телефона к формату +7 (XXX) XXX-XX-XX.

    Поддерживает:
        - '999 999 99999' → +7 (999) 999-99-99
        - '951 164 9014' → +7 (951) 164-90-14
        - '8-999-123-45-67' → +7 (999) 123-45-67
        - '+79991234567' → +7 (999) 123-45-67
        - '9991234567' (10 цифр) → +7 (999) 123-45-67
        - '89991234567' (11 цифр, начинается с 8) → +7 (999) 123-45-67

    Args:
        phone_raw (str): Сырая строка телефона (может содержать пробелы, дефисы, скобки).

    Returns:
        Optional[str]: Отформатированный номер или None, если формат не распознан.
    """

    if not phone_raw:
        return None
    
    # Оставляем только цифры
    digits = re.sub(r'\D', '', phone_raw)
    if not digits:
        return None
    
    len_digits = len(digits)
    digits_0 = digits[0]
    
    # Если номер начинается с 8 или 9 и имеет 10 цифр, добавляем +7
    if len_digits == 10 and digits_0 in ('8', '9'):
        digits = '7' + digits

    # Если номер имеет 11 цифр и начинается с 8, заменяем на +7
    elif len_digits == 11 and digits_0 == '8':
        digits = '7' + digits[1:]

    # Если номер имеет 11 цифр и начинается с 7, оставляем как есть
    elif len_digits == 11 and digits_0 == '7':
        pass

    else:
        # Неподдерживаемый формат – возвращаем как есть (или None)
        return None

    # Форматируем: +7 (XXX) XXX-XX-XX
    # digits должно быть 11 цифр (7 + 10)
    if len(digits) == 11:
        return f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    
    return None

def normalize_patient_dto(dto: PatientDTO) -> PatientDTO:
    """
    Централизованная нормализация данных пациента.

    - ФИО: удаление лишних пробелов.
    - Телефон: приведение к формату +7 (...) ... .
    - Описание: удаление лишних пробелов.
    - Дата рождения: уже нормализована при создании DTO.

    Args:
        dto (PatientDTO): DTO пациента, возможно с неочищенными полями.

    Returns:
        PatientDTO: Тот же объект DTO после изменений (поля перезаписываются in-place).
    """

    if dto.first_name:
        dto.first_name = normalize_text(dto.first_name)

    if dto.last_name:
        dto.last_name = normalize_text(dto.last_name)

    if dto.middle_name:
        dto.middle_name = normalize_text(dto.middle_name)

    if dto.phone:
        dto.phone = normalize_phone(dto.phone)
        
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
        "Фамилия Имя Отчество [Год] [Телефон] [Контакт]"

    Пример:
        "Постольник Анастасия Александровна 2012г 951 164 9014 Анна тётя"

    Атрибуты класса:
        PATTERN (re.Pattern): Регулярное выражение для разбора строки пациента.
    """

    PATTERN = re.compile(
        r'^(?P<last_name>\S+)\s+(?P<first_name>\S+)\s+(?P<middle_name>\S+)?\s*'
        r'(?P<birth_year>\d{4})?г?\s*'
        r'(?P<phone>[\d\s]+)?\s*'
        r'(?P<contact>.*)$'
    )

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

        phone_raw = data.get('phone')
        phone = ''.join(phone_raw.split()) if phone_raw else None
        # phone = normalize_phone(phone) if phone_raw else None

        # Контактная информация (описание пациента) – то, что после телефона
        description = data.get('contact', '').strip()
        if not description:
            description = None

        return PatientDTO(
            first_name=data['first_name'].strip(),
            last_name=data['last_name'].strip(),
            middle_name=data.get('middle_name', '').strip() or None,
            birth_date=birth_date,
            phone=phone,
            description_text=description,
        )


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
            header = self._clean_text(cell.text).lower()
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
        self.temp_dir = os.path.join(
            os.path.dirname(self.file_path), 
            "temp_images"
        )
        os.makedirs(self.temp_dir, exist_ok=True)

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
    session,
    file_path: str,
    patient_service: PatientService,
    appointment_service: AppointmentService,
    photo_service: PhotoService,
    update_existing_patient: bool = False,
) -> bool:
    """
    Обрабатывает один Word-файл в рамках переданной сессии.

    Args:
        session: Сессия SQLAlchemy (управляется вызывающим кодом).
        file_path (str): Путь к .docx файлу.
        patient_service (PatientService): Сервис для работы с пациентами.
        appointment_service (AppointmentService): Сервис для работы с приёмами.
        photo_service (PhotoService): Сервис для работы с фотографиями.
        update_existing_patient (bool): Если True, при совпадении пациента его данные обновляются,
                                        иначе создаётся новый пациент.

    Returns:
        bool: True – успешная обработка, False – ошибка (исключение выбрасывается).

    Raises:
        ValueError: При ошибках структуры документа, отсутствии обязательных полей,
                    проблемах с датами и т.п.
    """
    temp_dir = None
    temps_path = []
    try:
        parser = WordFileParser(
            file_path, 
            field_metadata=appointment_service.get_field_metadata()
        )
        patient_dto, rows = parser.parse()

        temp_dir = parser.temp_dir

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
        patient_dto = normalize_patient_dto(patient_dto)

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
                session=session
            )
            patient_id = created.id

        # ----- СОЗДАНИЕ ПРИЁМОВ -----
        for row in normalized_rows:
            app_dto = AppointmentDTO(
                patient_id=patient_id,
                date=row['date'],
                reason_text=row.get('reason_text'),
                procedure_text=row.get('procedure_text'),
                recommendations_text=row.get('recommendations_text'),
                cost_procedure_text=row.get('cost_procedure_text'),
                note_text=row.get('note_text'),
            )

            saved = appointment_service.create_appointment(app_dto, session=session)

            # Обработка фото
            if 'photos' in row and row['photos']:
                for temp_path in row['photos']:
                    # 0==0
                    photo_service.add_photo_to_appointment(
                        saved.id, 
                        temp_path, 
                        row.get('note_text', ''), 
                        session=session
                    )

                    # 0==0

        return True
    except Exception as e:
        raise e
    
    finally:
        for temp_path in temps_path:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        if temp_dir:
            if os.path.exists(temp_dir):   
                # try:
                shutil.rmtree(
                    temp_dir,
                    ignore_errors=True
                )
                # except OSError as e:
                #     # print(f"Ошибка при удалении папки: {e}") 
                #     pass
        


# ----------------------------------------------------------------------
# Пакетная обработка (папка / список файлов)
# ----------------------------------------------------------------------

def batch_parse(
    folder_path: str,
    specific_files: List[str] = None,
    update_existing_patient : bool= False,
    db: Database = None,
    patient_service: PatientService = None,
    appointment_service: AppointmentService = None,
    photo_service: PhotoService = None,
    
    progress_callback_start: Optional[Callable[[List[str]], None]] = None,
    progress_callback_update: Optional[Callable[[str, str, str], None]] = None,

) -> Dict[str, Any]:
    """
    Обрабатывает все .docx файлы в папке (или указанные).
    Создаёт общий лог-файл parser.log в подпапке logs_parser.
    Каждый файл обрабатывается в отдельной транзакции.

    Args:
        folder_path (str): Путь к папке с файлами.
        specific_files (List[str], optional): Список имён файлов для обработки (без путей).
        update_existing_patient (bool): Обновлять ли данные существующего пациента.
        db (Database, optional): Экземпляр Database (если None – берётся из dependencies).
        patient_service (PatientService, optional): Сервис пациентов.
        appointment_service (AppointmentService, optional): Сервис приёмов.
        photo_service (PhotoService, optional): Сервис фото.

        progress_callback_start: вызывается перед началом, передаёт список всех имён файлов.
        progress_callback_update: вызывается после обработки каждого файла,
            параметры (file_name, status, error_msg). Статусы: 'processing', 'success', 'failed'.

    Returns:
        Dict[str, Any]: Словарь с результатами обработки:
            - total (int): Всего обработано файлов.
            - success (int): Успешно.
            - failed (int): С ошибками.
            - success_files (List[str]): Имена успешных файлов.
            - error_files (List[Dict]): Список словарей {file_name, error}.
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

    # Собираем файлы
    if specific_files:
        file_paths = [os.path.join(folder_path, f) for f in specific_files if f.endswith('.docx')]
    else:
        file_paths = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith('.docx')]

    if not file_paths:
        return {'total': 0, 'success': 0, 'failed': 0, 'success_files': [], 'error_files': []}

    # Создаём папку для логов
    log_dir = os.path.join(folder_path, "logs_parser")

    os.makedirs(log_dir, exist_ok=True)

    time_log = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = os.path.join(
        log_dir, 
        # f"parser_{timestamp}.log" # не используем, так как нужен общий лог
        f"parser.log" # делаем общий лог на файлы
    )

    results = {
        'total': len(file_paths),
        'success': 0,
        'failed': 0,
        'success_files': [],
        'error_files': []
    }

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
                "{err_mas_pars}",     # Сообщени ошибки парсинга (ЕСЛИ ЕСТЬ)
            ]
        ) + '\n'

        for file_path in file_paths:
            file_name = os.path.basename(file_path)
            with db.session_scope() as session:

                if progress_callback_update:
                    progress_callback_update(file_name, "processing", "")
                msg = None
                try:
                    success = parse_one_file(
                        session, file_path,
                        patient_service, 
                        appointment_service, 
                        photo_service,
                        update_existing_patient = update_existing_patient,
                    )

                except Exception as e:
                    success = False
                    msg = e

                log.write(
                    text_format_log.format(
                        time_log=time_log,
                        time_pars_log=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        file_name_pars=file_name,
                        status_pars='success' if success else 'failed',
                        err_mas_pars=str(msg) if msg else "",
                    )
                )

                if success:
                    results['success'] += 1
                    results['success_files'].append(file_name)
                    if progress_callback_update:
                        progress_callback_update(file_name, "success", "")
                else:
                    results['failed'] += 1
                    results['error_files'].append(
                        {
                            'file_name': file_name,
                            'error': msg,
                        }
                    )
                    if progress_callback_update:
                        progress_callback_update(file_name, "failed", msg)


                # if msg:
                #     raise msg

            # Автоматический коммит/откат уже выполнен внутри session_scope

    return results , log_dir


# ----------------------------------------------------------------------
# Точка входа для дебага
# ----------------------------------------------------------------------

def pars_start(
    folder = None,
    files = None , 
    update_existing_patient:bool = False ,

    progress_callback_start: Optional[Callable[[List[str]], None]] = None,
    progress_callback_update: Optional[Callable[[str, str, str], None]] = None,
) -> dict:
    """
    Точка входа для запуска парсера.

    Args:
        folder (str, optional): Путь к папке .
        files (List[str], optional): Список файлов .
        update_existing_patient (bool): Флаг обновления существующих пациентов.

    Returns:
        dict: Результат работы batch_parse (как указано выше) или пустой словарь при ошибке.
    """

    results = {'total': 0, 'success': 0, 'failed': 0, 'success_files': [], 'error_files': []}

    log_path = None
    if not files:
        files = get_all_docx_files(folder)
        if not files:
            # # raise ValueError("В указанной папке нет .docx файлов.")
            # print("В указанной папке нет .docx файлов.")
            return results

        # Путь к лог-файлу (предполагаем, что он лежит в той же папке)
        log_path = os.path.join(folder, "logs_parser", "parser.log")

        # Если лог существует, отфильтровываем уже обработанные файлы
        if os.path.exists(log_path):
            to_process = filter_unprocessed_files(files, log_path)
            # print(f"Из {len(files)} файлов уже обработано успешно: {len(files) - len(to_process)}")
            files = to_process

    if files:
        results, log_path = batch_parse(
            folder, 
            specific_files=files,
            update_existing_patient = update_existing_patient,

            progress_callback_start=progress_callback_start,
            progress_callback_update=progress_callback_update,
        )

        if log_path:
            results['log_path'] = log_path
    
    return results


def pars_start_args(
    folder = None,
    files = None ,     
) -> dict:
    """
    Точка входа для запуска парсера из командной строки (для отладки и автономного использования).

    Поддерживаемые аргументы командной строки:
        --folder <path>               Обязательный путь к папке с .docx файлами.
        --files file1.docx,file2.docx Опциональный список файлов (если не указан, берутся все .docx).
        --update_existing_patient     Флаг: обновлять данные существующего пациента.
        --help                        Показать справку.

    Args:
        folder (str, optional): Путь к папке (будет переопределён аргументом --folder).
        files (List[str], optional): Список файлов (будет переопределён аргументом --files).

    Returns:
        dict: Результат работы pars_start (как указано выше) или пустой словарь при ошибке.
    """
    
    # import sys
    # Пример использования:
    # python -m parsers.word_importer --folder /path/to/files --files file1.docx file2.docx
    # или: python -m parsers.word_importer --folder /path/to/files (все файлы)

    # folder = None
    _files = []
    update_existing_patient = False

    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == '--folder' :
            if folder is None:
                folder = args[i+1]

        elif arg == '--update_existing_patient':
            update_existing_patient = True

        elif arg == '--files' and i+1 < len(args):
            if files is None:
                # _files = args[i+1].split(',')
                _files = [f for f in args[i+1].split(',') if f.strip()] 

        elif arg == '--help':
            print("Usage: python word_importer.py --folder <path> [--files file1.docx,file2.docx]")
            sys.exit(0)

    if files is None:
        files = _files

    if not folder:
        print("Укажите папку с файлами: --folder /path/to/docx")
        sys.exit(1)

    results = pars_start(
        folder = folder,
        files = files,
        update_existing_patient = update_existing_patient,
    )

    return results
    

if __name__ == "__main__":   
    # Пример вызова: python word_importer.py --folder /path/to/docx --files тест1.docx
    
    pars_start_args(
        folder = '/home/admin-rkc/Git/My_cods/project_med/doc',
        files = 'тест1.docx',
    )