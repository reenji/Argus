"""Add users.email_verified_at; accounts created before it count as verified."""

from alembic import op
import sqlalchemy as sa


revision = "20261120_0004"
down_revision = "20261027_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    # Existing accounts signed up before verification existed; do not lock them out.
    op.execute("UPDATE users SET email_verified_at = created_at WHERE email_verified_at IS NULL")


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
