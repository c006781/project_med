# DTO (app/dto) — заметки о реализации

> Файл для разработчиков: что делает модуль, как устроен, почему так и журнал проверок.
> Обновляется вместе с кодом.
> Последнее обновление: 2026-10-21, проходы 1–2 (ветка `rework-dto`).

| Файл | Назначение |
|---|---|
| [dto_all.py](dto_all.py) | `PatientDTO`, `AppointmentDTO`, `PhotoDTO` — из описаний таблиц (`app/schema/clinic.py`, `build_dto`); `AppointmentNoteDTO` — вручную |
| [field_configs.py](field_configs.py) | Конфигурации полей для форм/таблиц: `PATIENT_CONFIG`, `APPOINTMENT_CONFIG`, `PHOTO_CONFIG` — из описаний (`build_config`); `NOTE_CONFIG` — вручную; `get_note_fields`; `MODEL_CONFIG_MAP` (устарело) |
| [compute_fields.py](compute_fields.py) | `get_patient_full_name`, `join_name_parts` (не используется приложением) |
| Тесты | `tests/test_dto.py`, `tests/test_dto_review_pass1.py`, `tests/test_schema/` (совпадение с прежними DTO) |

---

## 1. Как устроено

* Новое поле или таблица — в описании `app/schema/clinic.py`; DTO и конфигурация полей
  строятся из него. Вручную остались заметки (`AppointmentNoteDTO`, `NOTE_CONFIG`) —
  ОСТАЛОСЬ.txt п. 4.4.
* `MODEL_CONFIG_MAP` и `get_note_fields` нужны только регистрации `_NOTE_USAGE_MODELS` в
  `app/dependencies.py`, которую никто не читает с DYN2 (сервис заметок узнаёт ссылки из
  схемы БД). Новую таблицу туда добавлять не нужно; удаление — шаг `dependencies`.

---

## 2. Журнал проверок

### Проход 1 (2026-10-21)

| # | Файл | Что было | Почему плохо | Исправление |
|---|---|---|---|---|
| DT1 | `compute_fields.py` | `" ".join([фамилия, имя, отчество])` | Отчество `None` → `TypeError` → «Ошибка загрузки» вместо ФИО | `join_name_parts` (пустые части пропускаются) |
| DT2 | `compute_fields.py` | Ветка «Пациент не найден» по `None` | `get_patient_by_id` бросает `PatientNotFoundError` → «Ошибка загрузки» | `except EntityNotFoundError` → «Пациент не найден» |
| DT3 | `field_configs.py` | Описание `get_note_fields` говорило о «полях с is_note» | Возвращает имена полей с id заметок | Описание, пример |
| DT4 | `dto_all.py` | 2 примера в докстрингах не проходили `doctest` | Документация врала | Примеры исправлены |
| DT5 | `field_configs.py`, сервисы (документация) | Инструкция «добавьте модель в `MODEL_CONFIG_MAP`» | Карта не используется с DYN2 | Пометка «устарело» здесь; описание сервисов — шаг «сервисы» |
| DT6 | (найдено) DTO из `app/schema` | Поля id заметок (`description_id` …) без `exclude=True` | Регрессия 2026-10-19: id попадают в `model_dump()` (строки наборов, черновики, сравнение «изменилось ли») | Исправляется в `app/schema` (ветка `rework-schema`) — генератор не переносит `exclude` |

Проверено и оставлено: неиспользуемые импорты `datetime`, `List` в `dto_all.py` (были
раньше — правило проекта). Тесты: `test_dto_review_pass1.py` (22); на старом коде 11 падают,
11 проходят (поведение, которое не менялось).

### Проход 2 (2026-10-21) — замечаний нет
