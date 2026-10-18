# Наборы данных (DataSet / DataSource) — проект

> Статус: **проект на согласовании** (2026-10-18, ветка `rework-dataset`). Кода ещё нет.
> Идея — слой работы с данными в духе RAD Studio (Delphi/C++Builder, FireDAC), но
> независимый: переносится в другие проекты, где может не быть ни SQLAlchemy, ни Qt.

## 1. Что берём из RAD Studio и что — нет

| RAD Studio | Здесь | Примечание |
|---|---|---|
| `TFDConnection` | **источник хранилища** — объект, реализующий `DataBackend` | соединение — забота источника, ядро о нём не знает |
| `TFDTable` / `TFDQuery` | `DataSet` + источник «таблица» или «запрос» | запрос — именованный, параметры — значения, не текст SQL в форме |
| `TField` (подпись, видимость, только чтение, вычисляемое, подстановка) | `FieldDef` | описание полей — одно на набор; для приложения строится из `field_configs` |
| `CachedUpdates` / `ApplyUpdates` | черновики `app.utils.drafts` | уже есть: ветки, области сохранения, отмена/повтор, одна транзакция |
| `TDataSource` | `DataSource` | посредник между набором и экраном: извещения, «пауза» обновлений |
| `MasterSource` / `MasterFields` | `MasterDetailLink` | поле связи — из описания полей (внешний ключ) |
| `TDBGrid`, `TDBEdit`, `TDBNavigator`, `TDBImage` | пакет `dataset_qt` | отдельно от ядра |
| `LiveBindings` | `bind(виджет, источник, поле)` | одна функция на тип виджета |

**Не берём** (слабые места RAD): SQL в формах; общую на программу «текущую строку»
(у каждого набора — своя); логику в обработчиках форм (она в наборе — тестируется без
окна); работу только по одной строке (выделение нескольких строк — через черновики).

## 2. Пакеты

```
app/utils/dataset/          ЯДРО — только стандартная библиотека (как app/utils/drafts)
    fields.py      FieldDef, LookupDef, типы полей, проверка значений
    query.py       Query: условия, сортировка, окно (offset/limit), параметры запроса
    backend.py     DataBackend (протокол чтения) + запись через drafts.PersistenceAdapter
    memory.py      MemoryBackend — список словарей (тесты; проекты без БД)
    dbapi.py       DbApiTable / DbApiQuery — любая DB-API 2.0 база (sqlite3 из коробки)
    events.py      события набора, подписка без Qt
    dataset.py     DataSet: строки, текущая строка, состояние, правка, фильтр, сортировка, окно
    source.py      DataSource: посредник, пауза обновлений, смена набора на лету
    links.py       MasterDetailLink: главная → подчинённая
    lookup.py      подстановки (показать «Петров И.» по patient_id), с кешем

app/utils/dataset_qt/       Qt — только PySide6 + ядро
    table_model.py DataSetTableModel (аналог TDBGrid)
    bindings.py    bind(): QLineEdit, QPlainTextEdit, QSpinBox, QDateEdit, QCheckBox,
                   QComboBox (подстановка), QLabel (картинка)
    navigator.py   DataNavigator: первая/пред./след./последняя, добавить, удалить,
                   править, сохранить, отменить, обновить, отмена/повтор

app/dataset_app/            ПРИЛОЖЕНИЕ — знает о сервисах, DTO, field_configs
    service_backend.py  ServiceBackend: DataBackend поверх сервисов (get_page_filtered…)
    fields.py           FieldDef из field_configs
    factory.py          готовые наборы: пациенты, приёмы, фото — с черновиками и связями
```

Зависимости — строго вниз: ядро ни от чего; `dataset_qt` → ядро; приложение → ядро,
`dataset_qt`, черновики, сервисы. Проект без SQLAlchemy берёт ядро (+ `dataset_qt`) и
пишет свой источник или берёт `DbApiTable`/`MemoryBackend`.

## 3. Ядро

### 3.1. Источник (`DataBackend`)

```python
class DataBackend(Protocol):
    def fields(self) -> Sequence[FieldDef]: ...            # описание полей (может быть пустым — тогда из набора)
    def key_field(self) -> str: ...                         # 'id'
    def fetch(self, query: Query) -> Page: ...              # Page(rows: list[dict], total: int | None)
    def get(self, key) -> Optional[dict]: ...               # одна строка (подстановки, обновление строки)
    capabilities: Capabilities                              # filter/sort/count/write — что умеет сам
```

Запись — тем же адаптером, что у черновиков (`PersistenceAdapter`: `transaction`,
`create`, `update`, `delete`): один способ записи на весь проект.

Чего источник не умеет (`capabilities`), набор делает сам в памяти: сортирует, фильтрует
загруженное. Так `MemoryBackend` и простой REST-источник работают без лишнего кода.

### 3.2. Набор (`DataSet`)

* **Окно строк**: загружается страница (`page_size`), дальше — по требованию
  (`fetch_more`, «бесконечная» прокрутка таблицы) — как `get_page` сейчас.
* **Текущая строка** и **состояние**: `BROWSE` / `EDIT` / `INSERT` (+ `INACTIVE`).
  Навигация: `first/prior/next/last/move_to(i)/locate(ключ)`.
* **Правка**: `edit()` → значения в буфер → `post()` / `cancel()`; `insert()`/`append()`;
  `delete()`. Проверка полей (`required`, тип, свои проверки) — при `post()`.
* **Куда пишет `post()`**: режим `cached` (по умолчанию) — в черновики (`DraftStore`),
  сохранение — `apply(scope)` через готовый план черновиков; режим `direct` — сразу через
  адаптер записи.
* **Вычисляемые поля** — функция от строки; **подстановки** — через `lookup.py`.
* **Фильтр и сортировка** — `set_filter(...)`, `set_order(...)` → перечитать окно.
* Ключ записи, а не номер строки, — «якорь» текущей строки: после перечитывания курсор
  возвращается на ту же запись, если она осталась.

### 3.3. События

Без Qt: подписка функцией. Виды: `opened`, `closed`, `refreshed` (окно перечитано),
`rows_inserted`/`rows_removed` (добавились строки окна), `row_changed(i, поля)`,
`current_changed(старая, новая)`, `state_changed`, `error`. `DataSource.disable()` —
пауза извещений (массовая правка без перерисовки), `enable()` — одно `refreshed`.

### 3.4. Главная → подчинённая

```python
appointments.link_master(patients_source)          # поле связи — из FieldDef (ссылка на patients)
```
Сменилась текущая строка пациентов — приёмы перечитываются с условием
`patient_id = текущий.id`. Новый пациент (ещё в черновике, id < 0) — приёмы пустые, но
добавлять можно: черновики уже связывают ребёнка с несохранённым родителем.

## 4. Как это ляжет на приложение

* `ServiceBackend` — поверх `get_page_filtered` (фильтры, сортировка, окно, количество),
  `get_by_id`; запись — существующий `ServiceAdapter` черновиков (одна транзакция).
* `FieldDef` строятся из `field_configs` (подписи, видимость, `compute`, заметки,
  подстановки по `eager_load`) — второй раз поля не описываем.
* «Одно описание таблицы» (следующий шаг после ядра): из одного описания — модель,
  DTO, `field_configs` и `FieldDef`; с автомиграциями новая таблица — это одно описание.
* Экраны: сначала одна пилотная пара «пациенты → приёмы» на новом слое рядом со старой
  (как делали с черновиками), затем остальные.

## 5. Порядок работ

1. Ядро: поля, запрос, `MemoryBackend`, набор, события, источник, связь, подстановки —
   с тестами (без Qt, без БД).
2. `DbApiTable`/`DbApiQuery` (sqlite3) — проверка, что ядро работает с настоящей базой
   без SQLAlchemy.
3. Приложение: `ServiceBackend`, поля из `field_configs`, наборы с черновиками.
4. `dataset_qt`: модель таблицы, привязки, навигатор (тесты на offscreen QApplication).
5. Пилотный экран «пациенты → приёмы».
6. Проверочные проходы до чистого, как обычно.
