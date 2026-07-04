"""Add reports table.

Revision ID: 20250115_0002
Revises: 20250115_0001
Create Date: 2025-01-15 00:01:00.000000

Description:
    Adds the reports table for storing generated report file metadata.
    Each pipeline run can generate multiple reports (quality, business summary)
    in multiple formats (CSV, Excel).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20250115_0002"
down_revision: Union[str, None] = "20250115_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the reports table."""
    op.create_table(
        "reports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_type", sa.String(50), nullable=False),
        sa.Column("file_format", sa.String(10), server_default="csv", nullable=False),
        sa.Column("dataset_type", sa.String(50), nullable=True),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("is_archived", sa.Boolean, server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "report_type IN ('data_quality','business_summary')",
            name="ck_reports_type",
        ),
        sa.CheckConstraint(
            "file_format IN ('csv','xlsx')",
            name="ck_reports_format",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Generated report file metadata — one row per report file",
    )
    op.create_index("ix_reports_pipeline_run_id", "reports", ["pipeline_run_id"])
    op.create_index("ix_reports_report_type", "reports", ["report_type"])


def downgrade() -> None:
    """Drop the reports table."""
    op.drop_table("reports")
