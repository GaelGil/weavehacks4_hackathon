"""Seed Redis with a few known scam messages for vector search.

    python -m app.seed
"""
from __future__ import annotations

from .services.redis_store import get_store

SEED_SCAMS: list[tuple[str, str]] = [
    ("Your Apple ID has been locked. Click here to verify your account within 24 hours or it will be deleted.", "phishing"),
    ("Congratulations! You've won a $1000 Amazon gift card. Claim now by entering your card details.", "prize"),
    ("This is the IRS. You owe back taxes and will be arrested unless you pay immediately with gift cards.", "impersonation"),
    ("Your computer is infected with a virus! Call Microsoft support at this number right now.", "tech_support"),
    ("Hi Grandma, I'm in trouble and need you to send money urgently. Please don't tell mom and dad.", "grandparent"),
    ("Your package could not be delivered. Update your shipping info and pay a small fee: http://bit.ly/track-pkg", "package"),
    ("We detected unusual sign-in activity on your bank account. Confirm your password to secure it.", "phishing"),
    ("URGENT: Your Netflix payment failed. Re-enter your billing details to avoid suspension.", "phishing"),
]


def main() -> None:
    store = get_store()
    if store.r is None:
        print("Redis not reachable. Start Redis Stack and retry.")
        return
    store.ensure_index()
    ok = 0
    for text, category in SEED_SCAMS:
        if store.add_scam(text, category):
            ok += 1
    print(f"Seeded {ok}/{len(SEED_SCAMS)} scam vectors.")


if __name__ == "__main__":
    main()
