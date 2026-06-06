from app.database.schemas.Scan import TrustedContact

trusted_contacts_by_session: dict[str, list[TrustedContact]] = {}


def save_contacts(session_id: str, contacts: list[TrustedContact]) -> list[TrustedContact]:
    trusted_contacts_by_session[session_id] = contacts
    return contacts


def get_contacts(session_id: str) -> list[TrustedContact]:
    return trusted_contacts_by_session.get(session_id, [])
