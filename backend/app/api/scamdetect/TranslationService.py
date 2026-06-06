import asyncio
import uuid

from fastapi import HTTPException
from sqlmodel import Session, select

from app.api.websocket.ConnectionManager import manager
from app.database.models import Translation
from app.database.schemas.Result import Result
from app.database.schemas.Translation import (
    TranslationDetail,
    TranslationsAdmin,
    TranslationSimple,
    TranslationsPublic,
    TranslationStatus,
)


class TranslationService:
    def __init__(self, session: Session):
        self.session = session
        self.manager = manager

    def get_translations_public(
        self,
    ) -> Result[TranslationsAdmin | TranslationsPublic, HTTPException]:
        try:
            translations = self.session.exec(
                select(Translation).where(Translation.public_status)
            ).all()
        except Exception as e:
            return Result(
                value=None, error=HTTPException(status_code=400, detail=str(e))
            )
        simple_translations = []
        for translation in translations:
            simple_translations.append(TranslationSimple.model_validate(translation))

        return Result(
            value=TranslationsPublic(translations=simple_translations), error=None
        )

    def get_translations_admin(
        self, super_user: bool = False
    ) -> Result[TranslationsAdmin, HTTPException]:
        if not super_user:
            return Result(
                value=None,
                error=HTTPException(status_code=403, detail="Action not allowed"),
            )
        try:
            translations = self.session.exec(select(Translation)).all()
        except Exception as e:
            return Result(
                value=None, error=HTTPException(status_code=400, detail=str(e))
            )
        detailed_translations = []
        for translation in translations:
            detailed_translations.append(TranslationDetail.model_validate(translation))

        return Result(
            value=TranslationsAdmin(translations=detailed_translations), error=None
        )

    async def translate(self, text: str, translate_id: str):
        """ """
        await self.manager.stream_response_chunk(
            translate_id=translate_id,
            chunk="",
            is_complete=False,
        )
        words = text.split()
        final_word = words[-1]
        for word in words:
            await self.manager.stream_response_chunk(
                translate_id=translate_id,
                chunk=word,
                is_complete=word == final_word,
            )
            await asyncio.sleep(5)
        translation = self.session.get(Translation, uuid.UUID(translate_id))
        assert translation
        translation.translation = text
        translation.status = TranslationStatus.COMPLETE
        self.session.add(translation)
        self.session.commit()

    def set_status(
        self, translation_id: uuid.UUID, status: bool
    ) -> Result[bool, HTTPException]:
        submission = self.session.get(Translation, translation_id)

        assert submission is not None
        submission.public_status = status
        try:
            self.session.add(submission)
            self.session.commit()
            return Result(value=True, error=None)
        except Exception as e:
            return Result(
                value=False,
                error=HTTPException(
                    status_code=403, detail=f"Error  {e}: not able to update status"
                ),
            )
