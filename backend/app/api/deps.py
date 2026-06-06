from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from app.api.scamdetect.ScanService import ScanService
from app.database.db import engine


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]


def get_scan_service(session: SessionDep) -> ScanService:
    return ScanService(session=session)


ScanServiceDep = Annotated[ScanService, Depends(get_scan_service)]
