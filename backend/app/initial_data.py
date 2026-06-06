import logging

from sqlmodel import Session

from app.database.db import engine, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init() -> None:
    with Session(engine) as session:
        init_db(session)


def main() -> None:
    logger.info("Running backend initialization")
    init()
    logger.info("Backend initialization complete")


if __name__ == "__main__":
    main()
