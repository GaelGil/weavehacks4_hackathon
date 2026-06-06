import uuid
from datetime import datetime, timezone

from sqlmodel import Field

from app.database.schemas.Scan import ScanBase


class Scan(ScanBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=False
    )
