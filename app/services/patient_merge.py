# app/services/patient_merge.py
"""
Объединение пациентов-дублей (Ф1.6.10а; решения владельца 2026-10-25 и 2026-10-31).

Устроено в три части, чтобы логику можно было менять, не трогая остальное:

* ``MergeRules`` — правила: поля поиска дублей (ФИО + ПОЛНАЯ дата рождения), поля
  повторного приёма (дата и все тексты), какие пустые поля главного заполнять, какие
  заметки склеивать, переносить ли фото повторного приёма;
* ``build_merge_plan`` — чистая функция: по снимкам пациентов и правилам строит
  ``MergePlan`` («что будет сделано»), база не меняется — это и показывает экран (Ф2.4.3);
* ``PatientMergeService.merge_patients`` — резервная копия базы, затем одна транзакция:
  план строится заново и сверяется с подтверждённым, исполняется как есть.

Фото переносятся по ``id`` (меняется ``appointment_id``, файл на месте — DATA11); при
объединении ни один файл не удаляется. В журнал — только id и счётчики (S5): тексты
предупреждений (ФИО, даты) — для экрана.

Example:
    >>> merge = PatientMergeService(
    ...     db                    =   get_db(),                    # база
    ...     patient_service       =   get_patient_service(),       # пациенты
    ...     appointment_service   =   get_appointment_service(),   # приёмы
    ... )
    >>> plan = merge.plan_merge(12, [40])            # показать пользователю
    >>> merge.merge_patients(12, [40], expected = plan)   # после подтверждения
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.database.database import backup_sqlite_database
from app.database.database_shema.clinic import Appointment, Photo
from app.dto.dto_all import AppointmentDTO, PatientDTO
from app.exceptions.exceptions_all import PatientValidationError
from app.utils.logger import AppLogger
from app.utils.record_keys import (
    APPOINTMENT_KEY_FIELDS,
    PATIENT_KEY_FIELDS,
    appointment_key,
    normalize_text,
    record_key,
)


class MergePlanChangedError(PatientValidationError):
    """
    Данные пациентов изменились между показом плана и подтверждением — объединение не
    выполнено; план нужно построить и показать заново.

    Example:
        >>> str(MergePlanChangedError())   # doctest: +ELLIPSIS
        '...данные пациентов изменились...'
    """

    def __init__(self) -> None:
        """
        Создаёт ошибку с полем ``plan`` и понятной причиной.

        Example:
            >>> MergePlanChangedError().field
            'plan'
        """
        super().__init__(
            'plan',
            'данные пациентов изменились после показа плана — посмотрите план заново',
        )


@dataclass(frozen=True)
class MergeRules:
    """
    Правила объединения; поменять логику — поменять правила (решение владельца 2026-10-31).

    Args:
        duplicate_key_fields   : (tuple) Поля ключа «тот же пациент» (строки — без учёта
            регистра, «ё», пунктуации; дата — целиком).
        appointment_key_fields : (tuple) Поля повторного приёма: первое — дата, остальные — тексты.
        fill_empty_fields      : (tuple) Поля главного, которые заполняются из дублей, если пусты.
        join_note_fields       : (tuple) Заметки, которые склеиваются (разные тексты — все).
        note_separator         : (str) Разделитель склеенных текстов.
        move_photos_of_repeated: (bool) Фото повторного приёма — к его двойнику у главного;
            False — фото удаляются вместе с дублем.
        field_titles           : (dict) Названия полей для предупреждений.

    Example:
        >>> MergeRules().duplicate_key_fields
        ('last_name', 'first_name', 'middle_name', 'birth_date')
    """

    duplicate_key_fields    : Tuple[str, ...] = PATIENT_KEY_FIELDS
    appointment_key_fields  : Tuple[str, ...] = APPOINTMENT_KEY_FIELDS
    fill_empty_fields       : Tuple[str, ...] = ('middle_name', 'birth_date', 'phone')
    join_note_fields        : Tuple[str, ...] = ('description_text', 'comment_text')
    note_separator          : str = '\n'
    move_photos_of_repeated : bool = True
    field_titles            : Mapping[str, str] = field(
        default_factory = lambda: {
            'middle_name'      : 'Отчество',
            'birth_date'       : 'Дата рождения',
            'phone'            : 'Телефон',
            'description_text' : 'Описание',
            'comment_text'     : 'Комментарий',
        },
    )


@dataclass(frozen=True)
class PatientSnapshot:
    """
    Пациент с приёмами и id фото по приёмам — вход ``build_merge_plan``.

    Args:
        patient      : (PatientDTO) Пациент (с текстами заметок).
        appointments : (tuple) Приёмы (``AppointmentDTO`` с текстами).
        photo_ids    : (dict) Id приёма → id его фото по возрастанию.

    Example:
        >>> PatientSnapshot(patient, (), {}).patient.id
        12
    """

    patient      : PatientDTO
    appointments : Tuple[AppointmentDTO, ...]
    photo_ids    : Mapping[int, Tuple[int, ...]]


@dataclass(frozen=True)
class MovedAppointment:
    """Приём дубля, который переносится к главному (``appointment_id``, от кого, дата, фото)."""

    appointment_id  : int
    from_patient_id : int
    date            : Optional[date]
    photo_count     : int


@dataclass(frozen=True)
class SkippedAppointment:
    """Повторный приём дубля (совпал с ``twin_id``): не переносится; ``photo_ids`` — фото к двойнику."""

    appointment_id  : int
    from_patient_id : int
    twin_id         : int
    date            : Optional[date]
    photo_ids       : Tuple[int, ...]


@dataclass(frozen=True)
class FieldChange:
    """Новое значение поля главного: заполнение пустого (``source_ids`` — от кого) или склейка заметок."""

    field      : str
    value      : Any
    source_ids : Tuple[int, ...]


@dataclass(frozen=True)
class MergePlan:
    """
    Что будет сделано при объединении (показывается пользователю до подтверждения).

    Args:
        main_id       : (int) Главный пациент.
        duplicate_ids : (tuple) Дубли по порядку (удаляются).
        moved         : (tuple) Переносимые приёмы (``MovedAppointment``).
        skipped       : (tuple) Повторные приёмы (``SkippedAppointment``).
        changes       : (tuple) Изменения полей главного (``FieldChange``).
        warnings      : (tuple) Предупреждения для пользователя.

    Example:
        >>> plan.main_id, plan.duplicate_ids
        (12, (40,))
    """

    main_id       : int
    duplicate_ids : Tuple[int, ...]
    moved         : Tuple[MovedAppointment, ...]
    skipped       : Tuple[SkippedAppointment, ...]
    changes       : Tuple[FieldChange, ...]
    warnings      : Tuple[str, ...]


@dataclass(frozen=True)
class MergeResult:
    """Итог объединения: выполненный план и путь к резервной копии базы (None — копии нет)."""

    plan        : MergePlan
    backup_path : Optional[str]


def _is_empty(
    value : Any,  # значение поля
) -> bool: # пусто ли поле
    """
    Пусто ли значение: None или строка из пробелов.

    Args:
        value : (Any) Значение.

    Returns:
        (bool) True — пусто.

    Example:
        >>> _is_empty('  '), _is_empty(date(1985, 6, 14))
        (True, False)
    """
    return value is None or (isinstance(value, str) and not value.strip())


def _same_value(
    a : Any,  # первое значение
    b : Any,  # второе значение
) -> bool: # равны ли значения
    """
    Равны ли значения; строки — после ``normalize_text`` (пробелы не важны).

    Args:
        a : (Any) Первое значение.
        b : (Any) Второе значение.

    Returns:
        (bool) True — равны.

    Example:
        >>> _same_value('+7 999 ', '+7 999')
        True
    """
    if isinstance(a, str) and isinstance(b, str):
        return normalize_text(a) == normalize_text(b)
    return a == b


def _show(
    value : Any,  # значение поля
) -> str: # значение для текста предупреждения
    """
    Значение для текста предупреждения: дата — ``ДД.ММ.ГГГГ``, остальное — строкой.

    Args:
        value : (Any) Значение.

    Returns:
        (str) Текст.

    Example:
        >>> _show(date(1985, 6, 14))
        '14.06.1985'
    """
    if isinstance(value, date):
        return value.strftime('%d.%m.%Y')
    return str(value)


def join_texts(
    texts     : Sequence[Optional[str]],   # тексты по порядку (главный — первым)
    separator : str = '\n',                # разделитель
) -> str: # склеенный текст без повторов
    """
    Склеивает тексты по порядку без повторов.

    Пустые пропускаются; текст, совпадающий с уже взятым или целиком входящий в него
    (после ``normalize_text``), не повторяется; уже взятый текст, целиком входящий в
    новый, заменяется новым (на своём месте).

    Args:
        texts     : (Sequence[str/None]) Тексты.
        separator : (str) Разделитель.

    Returns:
        (str) Склеенный текст; '' — все пусты.

    Example:
        >>> join_texts(
        ...     ['аллергия', 'аллергия, астма', 'гипертония'],   # тексты
        ... )
        'аллергия, астма\\nгипертония'
    """
    kept: List[Tuple[str, str]] = []   # (нормализованный, исходный)
    for text in texts:
        norm = normalize_text(text)
        if not norm or any(norm in seen for seen, _ in kept):
            continue
        covered = [i for i, (seen, _) in enumerate(kept) if seen in norm]
        if covered: # новый текст содержит взятый — встаёт на его место
            kept[covered[0]] = (norm, text.strip())
            kept = [item for i, item in enumerate(kept) if i not in covered[1:]]
        else:
            kept.append((norm, text.strip()))
    return separator.join(original for _, original in kept)


def build_merge_plan(
    main       : PatientSnapshot,              # главный пациент
    duplicates : Sequence[PatientSnapshot],    # дубли по порядку
    rules      : MergeRules = MergeRules(),    # правила объединения
) -> MergePlan: # что будет сделано (база не меняется)
    """
    Строит план объединения по снимкам пациентов и правилам.

    Порядок:
        1. ключ дубля (``rules.duplicate_key_fields``) не совпал с главным — предупреждение
           (объединять отмеченных вручную можно);
        2. приёмы дублей по порядку (внутри — по дате и id): повторный (ключ
           ``rules.appointment_key_fields`` совпал с приёмом главного или уже перенесённым) —
           пропуск с предупреждением, его фото — к двойнику (``move_photos_of_repeated``);
           иначе — перенос;
        3. пустые поля главного (``fill_empty_fields``) — из первого дубля с непустым
           значением; другие непустые отличия — предупреждением (остаётся значение главного);
        4. заметки (``join_note_fields``) — ``join_texts`` (главный первым).

    Args:
        main       : (PatientSnapshot) Главный пациент.
        duplicates : (Sequence[PatientSnapshot]) Дубли.
        rules      : (MergeRules) Правила.

    Returns:
        (MergePlan) План.

    Example:
        >>> plan = build_merge_plan(
        ...     main_snapshot,        # главный
        ...     [duplicate_snapshot], # дубли
        ... )
        >>> [m.appointment_id for m in plan.moved]
        [101]
    """
    main_patient = main.patient
    warnings: List[str] = []
    main_key = record_key(main_patient, rules.duplicate_key_fields)

    def _ordered(appointments: Sequence[AppointmentDTO]) -> List[AppointmentDTO]:
        return sorted(appointments, key=lambda a: (a.date or date.min, a.id))

    # 1–2. Приёмы: повторы ищутся среди приёмов главного и уже перенесённых
    known: Dict[Tuple[Any, ...], int] = {}
    for appointment in _ordered(main.appointments):
        known.setdefault(appointment_key(appointment, rules.appointment_key_fields), appointment.id)

    moved: List[MovedAppointment] = []
    skipped: List[SkippedAppointment] = []
    for duplicate in duplicates:
        patient = duplicate.patient
        if record_key(patient, rules.duplicate_key_fields) != main_key:
            warnings.append(
                f"Пациент id {patient.id}: ФИО или дата рождения не совпадают с главным (id {main_patient.id})"
            )
        for appointment in _ordered(duplicate.appointments):
            photos = tuple(duplicate.photo_ids.get(appointment.id, ()))
            key = appointment_key(appointment, rules.appointment_key_fields)
            twin_id = known.get(key)
            if twin_id is None:
                known[key] = appointment.id
                moved.append(MovedAppointment(appointment.id, patient.id, appointment.date, len(photos)))
                continue
            photo_ids = photos if rules.move_photos_of_repeated else ()
            skipped.append(SkippedAppointment(appointment.id, patient.id, twin_id, appointment.date, photo_ids))
            text = (
                f"Приём {_show(appointment.date)} пациента id {patient.id} (приём id {appointment.id}) "
                f"совпадает с приёмом id {twin_id} — не переносится"
            )
            if photos:
                text += (
                    f"; фото ({len(photos)}) переносятся к приёму id {twin_id}"
                    if rules.move_photos_of_repeated else f"; фото ({len(photos)}) удаляются"
                )
            warnings.append(text)

    # 3. Пустые поля главного — из дублей; отличия — предупреждением
    changes: List[FieldChange] = []
    for name in rules.fill_empty_fields:
        title = rules.field_titles.get(name, name)
        current = getattr(main_patient, name, None)
        for duplicate in duplicates:
            value = getattr(duplicate.patient, name, None)
            if _is_empty(value):
                continue
            if _is_empty(current):
                current = value
                changes.append(FieldChange(name, value, (duplicate.patient.id,)))
            elif not _same_value(current, value):
                warnings.append(
                    f"{title}: у главного «{_show(current)}», у пациента id {duplicate.patient.id} "
                    f"«{_show(value)}» — остаётся значение главного"
                )

    # 4. Заметки — склейка разных текстов
    for name in rules.join_note_fields:
        main_text = getattr(main_patient, name, None)
        sources = [d for d in duplicates if not _is_empty(getattr(d.patient, name, None))]
        joined = join_texts(
            [main_text] + [getattr(d.patient, name) for d in sources],
            rules.note_separator,
        )
        if joined and not _same_value(joined, main_text or ''):
            changes.append(FieldChange(name, joined, tuple(d.patient.id for d in sources)))

    return MergePlan(
        main_id       = main_patient.id,
        duplicate_ids = tuple(d.patient.id for d in duplicates),
        moved         = tuple(moved),
        skipped       = tuple(skipped),
        changes       = tuple(changes),
        warnings      = tuple(warnings),
    )


class PatientMergeService:
    """
    Поиск пациентов-дублей и их объединение (Ф1.6.10а).

    Пользуется сервисами пациентов (чтение, правка полей и заметок, удаление дублей с
    чисткой заметок) и приёмов (приёмы с текстами); приёмы и фото переносит сам —
    сменой внешнего ключа в той же транзакции.

    Example:
        >>> merge = get_patient_merge_service()
        >>> [[p.id for p in group] for group in merge.find_possible_duplicates()]
        [[12, 40]]
    """

    def __init__(
        self,
        db                  : Any,                        # база: session_scope, engine
        patient_service     : Any,                        # PatientService
        appointment_service : Any,                        # AppointmentService
        rules               : Optional[MergeRules] = None,  # правила; None — MergeRules()
    ) -> None:
        """
        Создаёт сервис объединения.

        Args:
            db                  : (Database) База — сессии и движок (резервная копия).
            patient_service     : (PatientService) Сервис пациентов.
            appointment_service : (AppointmentService) Сервис приёмов.
            rules               : (MergeRules/None) Правила; None — по умолчанию.

        Example:
            >>> PatientMergeService(
            ...     db                    =   db,             # база
            ...     patient_service       =   patients,       # пациенты
            ...     appointment_service   =   appointments,   # приёмы
            ... ).rules.note_separator
            '\\n'
        """
        self._db = db
        self._patients = patient_service
        self._appointments = appointment_service
        self.rules = rules or MergeRules()
        self.logger = AppLogger.get_instance(
            name                 = 'PatientMergeService',
            enable_file_logging  = 'user',
            use_name_in_filename = False,
        )

    def find_possible_duplicates(
        self,
        session : Optional[Session] = None,   # внешняя сессия; None — своя
    ) -> List[List[PatientDTO]]: # группы возможных дублей
        """
        Возвращает группы пациентов с одинаковым ключом (``rules.duplicate_key_fields``).

        Группы — по ФИО (затем по id первого), внутри группы — по id; одиночки не входят.

        Args:
            session : (Session/None) Внешняя сессия; None — своя транзакция.

        Returns:
            (List[List[PatientDTO]]) Группы из двух и более пациентов.

        Example:
            >>> [[p.id for p in g] for g in merge.find_possible_duplicates()]
            [[12, 40], [7, 9, 31]]
        """
        groups: Dict[Tuple[Any, ...], List[PatientDTO]] = defaultdict(list)
        for patient in self._patients.get_all(session=session):
            groups[record_key(patient, self.rules.duplicate_key_fields)].append(patient)
        result = [sorted(group, key=lambda p: p.id) for group in groups.values() if len(group) > 1]
        result.sort(
            key = lambda group: (
                tuple(str(v) for v in record_key(group[0], self.rules.duplicate_key_fields)),
                group[0].id,
            ),
        )
        self.logger.debug(f"Возможные дубли: групп {len(result)}")
        return result

    def plan_merge(
        self,
        main_id       : int,             # главный пациент
        duplicate_ids : Sequence[int],   # дубли по порядку
    ) -> MergePlan: # что будет сделано (база не меняется)
        """
        Строит план объединения (только чтение) — его показывают пользователю.

        Args:
            main_id       : (int) Главный пациент.
            duplicate_ids : (Sequence[int]) Дубли.

        Returns:
            (MergePlan) План.

        Raises:
            PatientValidationError: Нет дублей, главный среди дублей, повтор id.
            PatientNotFoundError: Пациента нет в базе.

        Example:
            >>> merge.plan_merge(12, [40]).duplicate_ids
            (40,)
        """
        duplicate_ids = self._check_ids(main_id, duplicate_ids)
        with self._db.session_scope() as session:
            return self._plan(main_id, duplicate_ids, session)

    def merge_patients(
        self,
        main_id       : int,                         # главный пациент
        duplicate_ids : Sequence[int],               # дубли по порядку (удаляются)
        *,
        expected      : Optional[MergePlan] = None,  # план, который видел пользователь
        backup        : bool = True,                 # резервная копия базы перед объединением
    ) -> MergeResult: # итог объединения
        """
        Объединяет дублей с главным одной транзакцией.

        Порядок: проверка id → резервная копия базы (``backup_sqlite_database``, рядом с
        базой, метка ``merge``) → транзакция: план заново; ``expected`` задан и план другой —
        ``MergePlanChangedError``; перенос приёмов и фото повторных приёмов (по id, файлы на
        месте); поля и заметки главного (``PatientService.update`` — общие заметки не
        меняются на месте); удаление дублей (``delete_patient``: оставшиеся повторные приёмы
        и неиспользуемые заметки). Ошибка — откат всего; копия остаётся.

        Args:
            main_id       : (int) Главный пациент.
            duplicate_ids : (Sequence[int]) Дубли.
            expected      : (MergePlan/None) Подтверждённый план; None — без сверки.
            backup        : (bool) Делать резервную копию.

        Returns:
            (MergeResult) План и путь к копии.

        Raises:
            PatientValidationError: Неверные id.
            PatientNotFoundError: Пациента нет в базе.
            MergePlanChangedError: Данные изменились после показа плана.

        Example:
            >>> merge.merge_patients(
            ...     12,                      # главный
            ...     [40],                    # дубли
            ...     expected   =   plan,     # подтверждённый план
            ... ).backup_path
            'clinic.db.bak-20261031_211500-merge'
        """
        duplicate_ids = self._check_ids(main_id, duplicate_ids)
        backup_path = None
        engine = getattr(self._db, 'engine', None)
        if backup and engine is not None: # копия до транзакции: при сбое есть точка отката
            backup_path = backup_sqlite_database(
                engine,    # движок базы
                'merge',   # метка
            )
        with self._db.session_scope() as session:
            plan = self._plan(main_id, duplicate_ids, session)
            if expected is not None and plan != expected:
                raise MergePlanChangedError()
            self._execute(plan, session)
        self.logger.info(
            f"Объединены пациенты: главный id={plan.main_id}, дубли {list(plan.duplicate_ids)}; "
            f"приёмов перенесено {len(plan.moved)}, пропущено {len(plan.skipped)}, "
            f"полей изменено {len(plan.changes)}; копия: {'есть' if backup_path else 'нет'}"
        )
        return MergeResult(plan, backup_path)

    @staticmethod
    def _check_ids(
        main_id       : int,             # главный пациент
        duplicate_ids : Sequence[int],   # дубли
    ) -> Tuple[int, ...]: # дубли кортежем
        """
        Проверяет id: дубли есть, без повторов, главный не среди них.

        Args:
            main_id       : (int) Главный пациент.
            duplicate_ids : (Sequence[int]) Дубли.

        Returns:
            (Tuple[int, ...]) Дубли.

        Raises:
            PatientValidationError: Нарушено условие.

        Example:
            >>> PatientMergeService._check_ids(12, [40])
            (40,)
        """
        duplicate_ids = tuple(duplicate_ids)
        if not duplicate_ids:
            raise PatientValidationError('duplicate_ids', 'не выбраны пациенты для объединения')
        if main_id in duplicate_ids:
            raise PatientValidationError('duplicate_ids', 'главный пациент указан среди дублей')
        if len(set(duplicate_ids)) != len(duplicate_ids):
            raise PatientValidationError('duplicate_ids', 'пациент указан дважды')
        return duplicate_ids

    def _snapshot(
        self,
        patient_id : int,       # пациент
        session    : Session,   # сессия транзакции
    ) -> PatientSnapshot: # пациент с приёмами и фото
        """
        Снимок пациента: DTO, приёмы с текстами, id фото по приёмам.

        Args:
            patient_id : (int) Пациент.
            session    : (Session) Сессия.

        Returns:
            (PatientSnapshot) Снимок.

        Raises:
            PatientNotFoundError: Пациента нет.

        Example:
            >>> merge._snapshot(12, session).patient.id
            12
        """
        patient = self._patients.get_by_id(patient_id, session=session)
        appointments = tuple(self._appointments.get_appointments_by_patient(patient_id, session=session))
        photo_ids: Dict[int, List[int]] = defaultdict(list)
        if appointments:
            rows = session.query(
                Photo.id,
                Photo.appointment_id,
            ).filter(
                Photo.appointment_id.in_([a.id for a in appointments]),
            ).order_by(
                Photo.id,
            )
            for photo_id, appointment_id in rows:
                photo_ids[appointment_id].append(photo_id)
        return PatientSnapshot(
            patient      = patient,
            appointments = appointments,
            photo_ids    = {k: tuple(v) for k, v in photo_ids.items()},
        )

    def _plan(
        self,
        main_id       : int,               # главный пациент
        duplicate_ids : Tuple[int, ...],   # дубли
        session       : Session,           # сессия транзакции
    ) -> MergePlan: # план по текущим данным
        """
        Снимки пациентов и ``build_merge_plan`` по правилам сервиса.

        Args:
            main_id       : (int) Главный пациент.
            duplicate_ids : (Tuple[int, ...]) Дубли.
            session       : (Session) Сессия.

        Returns:
            (MergePlan) План.

        Example:
            >>> merge._plan(12, (40,), session).main_id
            12
        """
        return build_merge_plan(
            self._snapshot(main_id, session),                          # главный
            [self._snapshot(pid, session) for pid in duplicate_ids],   # дубли
            self.rules,                                                # правила
        )

    def _execute(
        self,
        plan    : MergePlan,   # план (построен в этой же транзакции)
        session : Session,     # сессия транзакции
    ) -> None:
        """
        Исполняет план: перенос приёмов и фото, поля главного, удаление дублей.

        Перед удалением дублей — ``flush`` и ``expire_all``: коллекции приёмов дублей,
        загруженные при снимке, иначе удалили бы и перенесённые приёмы.

        Args:
            plan    : (MergePlan) План.
            session : (Session) Сессия.

        Example:
            >>> merge._execute(plan, session)
        """
        for move in plan.moved:
            session.get(Appointment, move.appointment_id).patient_id = plan.main_id
        for skip in plan.skipped:
            for photo_id in skip.photo_ids: # фото повторного приёма — к двойнику (файл на месте)
                session.get(Photo, photo_id).appointment_id = skip.twin_id
        session.flush()

        if plan.changes:
            main = self._patients.get_by_id(plan.main_id, session=session)
            self._patients.update(
                main.model_copy(update={c.field: c.value for c in plan.changes}),   # новые значения
                session = session,
            )
            session.flush()

        session.expire_all()
        for duplicate_id in plan.duplicate_ids:
            self._patients.delete_patient(duplicate_id, session=session)
