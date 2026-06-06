# import base64
import uuid
from datetime import datetime, timezone

from sqlmodel import Field

from app.database.schemas.Translation import TranslationBase
from app.database.schemas.User import UserBase


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str


class Translation(TranslationBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=False
    )
    correct: int = Field(default=0, nullable=True)
    incorrect: int = Field(default=0, nullable=True)
