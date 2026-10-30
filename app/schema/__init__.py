# app/schema/__init__.py

"""
Описания таблиц: одно описание (``TableDef``) → модель SQLAlchemy, DTO, ``field_configs`` и
набор данных экрана.

* ``define`` — ``TableDef`` и поля-построители (``key``, ``column``, ``note``, ``fk``,
  ``children``, ``computed``, ``timestamp``);
* ``extras`` — свои столбцы набора (``mark``, ``calc``, ``total``) и связи (``ref``);
* ``clinic`` — таблицы клиники (``PATIENTS``, ``APPOINTMENTS``, ``PHOTOS``, ``CLINIC_DEFS``;
  заметки — ``NOTES``).

Слой ниже моделей и DTO: не импортирует ``app.database``, ``app.dto``, сборку
приложения и сервисы (их модули импортируют описания). Подробно —
``app/schema/IMPLEMENTATION.md``.
"""
