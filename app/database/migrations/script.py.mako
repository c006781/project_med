# app/database/migrations/versions/${up_revision}.py

"""
${message}

Ревизия: ${up_revision}
Предыдущая: ${down_revision | comma,n}
Создана: ${create_date}

Что меняет и почему: (заполнить)
"""

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    """
    Применение миграции.

    Returns:
        None

    Пример:
        >>> upgrade()     # вызывает Alembic
    """
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """
    Откат миграции.

    Returns:
        None

    Пример:
        >>> downgrade()   # вызывает Alembic
    """
    ${downgrades if downgrades else "pass"}
