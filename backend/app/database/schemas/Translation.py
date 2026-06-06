import uuid
from enum import Enum

from pydantic import field_validator
from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel


class TranslationStatus(Enum):
    INPROGRESS = "inporgress"
    FAILED = "failed"
    COMPLETE = "completed"


class TranslationResponseType(Enum):
    TRANSLATION_CHUNK = "translation_chunk"


class TranslationBase(SQLModel):
    src: str = Field(sa_column=Column(Text, nullable=False))
    translation: str | None = Field(sa_column=Column(Text, nullable=True))
    status: TranslationStatus = Field(
        default=TranslationStatus.COMPLETE, nullable=False
    )
    public_status: bool = Field(default=False, nullable=False)

    @field_validator("src")
    @classmethod
    def validate_word_count(cls, v: str) -> str:
        word_count = len(v.split())
        if word_count < 5:
            raise ValueError(
                f"Input must contain at least 5 words. You entered {word_count} word(s)."
            )
        return v


class TranslationRequest(TranslationBase):
    pass


class TranslationResponse(TranslationBase):
    id: uuid.UUID


class TranslationSimple(SQLModel):
    src: str
    translation: str | None


class TranslationDetail(TranslationBase):
    id: uuid.UUID
    correct: int
    incorrect: int


class TranslationsAdmin(SQLModel):
    translations: list[TranslationDetail]


class TranslationsPublic(SQLModel):
    translations: list[TranslationSimple]


class TranslationUpdate(SQLModel):
    id: uuid.UUID
    new_status: bool
