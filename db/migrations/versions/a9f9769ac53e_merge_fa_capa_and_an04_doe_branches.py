"""merge fa_capa and an04 doe branches

Revision ID: a9f9769ac53e
Revises: 8aaac1ba4a8b, f361e9578062
Create Date: 2026-09-14 16:24:13.791379

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9f9769ac53e'
down_revision: Union[str, Sequence[str], None] = ('8aaac1ba4a8b', 'f361e9578062')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
