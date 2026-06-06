"""Seed Redis with known SCAM and known-LEGIT messages for two-sided comparison.

    python -m app.seed
"""
from __future__ import annotations

from .services.redis_store import get_store

# (text, category)
SCAMS: list[tuple[str, str]] = [
    ("Your Apple ID has been locked. Click here to verify your account within 24 hours or it will be deleted.", "phishing"),
    ("Congratulations! You've won a $1000 Amazon gift card. Claim now by entering your card details.", "prize"),
    ("This is the IRS. You owe back taxes and will be arrested unless you pay immediately with gift cards.", "impersonation"),
    ("Your computer is infected with a virus! Call Microsoft support at this number right now.", "tech_support"),
    ("Hi Grandma, I'm in trouble and need you to send money urgently. Please don't tell mom and dad.", "grandparent"),
    ("Your package could not be delivered. Update your shipping info and pay a small fee: http://bit.ly/track-pkg", "package"),
    ("We detected unusual sign-in activity on your bank account. Confirm your password to secure it.", "phishing"),
    ("URGENT: Your Netflix payment failed. Re-enter your billing details to avoid suspension.", "phishing"),
]

# Legitimate, ordinary messages — including transactional/event mail that LOOKS unusual
# but is benign (the kind that was getting false-flagged).
LEGIT: list[tuple[str, str]] = [
    ("New message in WeaveHacks 4 from the event host on Luma. We are at capacity, stay posted for WeaveHacks 5. View Event. Sent from user.luma-mail.com.", "event"),
    ("Your Amazon order has shipped and will arrive Tuesday. Track your package in Your Orders.", "transactional"),
    ("The New York Times: Your morning briefing for today.", "newsletter"),
    ("Calendar invite: Dentist appointment Tuesday 10am.", "calendar"),
    ("Your monthly bank statement is ready. Log in to your account through the official app to view it.", "transactional"),
    ("Slack: Your coworker mentioned you in #engineering. Open Slack to reply.", "notification"),
    ("Receipt from Uber: Your trip on Saturday was $18.40. View receipt in the app.", "receipt"),
    ("Eventbrite: Your ticket for the Jazz Festival is confirmed. Add to calendar.", "event"),
]


def main() -> None:
    store = get_store()
    if store.r is None:
        print("Redis not reachable. Start Redis Stack and retry.")
        return
    store.ensure_index()
    ok = 0
    total = len(SCAMS) + len(LEGIT)
    for text, category in SCAMS:
        if store.add_example(text, label="scam", category=category):
            ok += 1
    for text, category in LEGIT:
        if store.add_example(text, label="legit", category=category):
            ok += 1
    print(f"Seeded {ok}/{total} examples ({len(SCAMS)} scam, {len(LEGIT)} legit).")


if __name__ == "__main__":
    main()
