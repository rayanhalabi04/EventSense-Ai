"""Allow system-created escalations

Revision ID: 017_escalation_system_created_by
Revises: 016_auto_sent
Create Date: 2026-06-16
"""

from typing import Sequence, Union

from alembic import op


revision: str = "017_escalation_system_created_by"
down_revision: Union[str, None] = "016_auto_sent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "escalations",
        "created_by_user_id",
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "escalations",
        "created_by_user_id",
        nullable=False,
    )
