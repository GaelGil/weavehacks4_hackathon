"""Seed Redis with known SCAM and known-LEGIT messages for two-sided comparison.

python -m app.seed
"""

from __future__ import annotations

from .services.redis_store import get_store

# (text, category)
SCAMS: list[tuple[str, str]] = [
    (
        "Your Apple ID has been locked. Click here to verify your account within 24 hours or it will be deleted.",
        "phishing",
    ),
    (
        "Congratulations! You've won a $1000 Amazon gift card. Claim now by entering your card details.",
        "prize",
    ),
    (
        "This is the IRS. You owe back taxes and will be arrested unless you pay immediately with gift cards.",
        "impersonation",
    ),
    (
        "Your computer is infected with a virus! Call Microsoft support at this number right now.",
        "tech_support",
    ),
    (
        "Hi Grandma, I'm in trouble and need you to send money urgently. Please don't tell mom and dad.",
        "grandparent",
    ),
    (
        "Your package could not be delivered. Update your shipping info and pay a small fee: http://bit.ly/track-pkg",
        "package",
    ),
    (
        "We detected unusual sign-in activity on your bank account. Confirm your password to secure it.",
        "phishing",
    ),
    (
        "URGENT: Your Netflix payment failed. Re-enter your billing details to avoid suspension.",
        "phishing",
    ),
    (
        "Chase Fraud Alert: We noticed unusual activity on your account. Confirm your identity immediately to prevent suspension.",
        "phishing",
    ),
    (
        "PayPal Security Notice: Your account access has been limited. Log in now to restore full access.",
        "phishing",
    ),
    (
        "Dropbox shared file pending. Sign in to preview the secure document before it expires tonight.",
        "phishing",
    ),
    (
        "USPS: Your parcel is on hold due to an invalid address. Pay $2.99 to reschedule delivery.",
        "package",
    ),
    (
        "DHL Express could not complete delivery. Update your shipping address and customs payment here.",
        "package",
    ),
    (
        "FedEx final notice: your shipment will be returned unless you verify delivery details today.",
        "package",
    ),
    (
        "Windows Defender Alert: Trojan spyware detected. Call certified support now to secure your device.",
        "tech_support",
    ),
    (
        "Your browser has been locked for security reasons. Contact Apple support immediately at the number below.",
        "tech_support",
    ),
    (
        "You have been selected for a Walmart loyalty reward. Claim your free tablet by paying the shipping fee.",
        "prize",
    ),
    (
        "Congratulations winner! Your phone number was chosen for a cash prize. Reply with your banking details to receive it.",
        "prize",
    ),
    (
        "This is Officer Martin from the Social Security Administration. Your SSN is linked to criminal activity and will be suspended unless you act now.",
        "impersonation",
    ),
    (
        "Amazon Support: We detected a problem with your last purchase. Provide your one-time code so we can cancel the fraudulent order.",
        "impersonation",
    ),
    (
        "Hi Mom, I dropped my phone in water and this is my new number. I need you to send me $1,500 for an emergency bill right away.",
        "family_emergency",
    ),
    (
        "I am recruiting for a remote data entry role paying $45 an hour. You must first purchase training software from our vendor to begin.",
        "job",
    ),
    (
        "After reviewing your resume, we can offer you the job immediately. Deposit the enclosed check and send part of the funds to our equipment supplier.",
        "job",
    ),
    (
        "Elon Musk crypto giveaway: send 0.5 ETH and receive 5 ETH back instantly. Limited time only.",
        "crypto",
    ),
    (
        "Your wallet must be revalidated after a security update. Connect now and enter your recovery phrase to avoid losing access.",
        "crypto",
    ),
]

# Legitimate, ordinary messages — including transactional/event mail that LOOKS unusual
# but is benign (the kind that was getting false-flagged).
LEGIT: list[tuple[str, str]] = [
    (
        "New message in WeaveHacks 4 from the event host on Luma. We are at capacity, stay posted for WeaveHacks 5. View Event. Sent from user.luma-mail.com.",
        "event",
    ),
    (
        "Your Amazon order has shipped and will arrive Tuesday. Track your package in Your Orders.",
        "transactional",
    ),
    ("The New York Times: Your morning briefing for today.", "newsletter"),
    ("Calendar invite: Dentist appointment Tuesday 10am.", "calendar"),
    (
        "Your monthly bank statement is ready. Log in to your account through the official app to view it.",
        "transactional",
    ),
    (
        "Slack: Your coworker mentioned you in #engineering. Open Slack to reply.",
        "notification",
    ),
    (
        "Receipt from Uber: Your trip on Saturday was $18.40. View receipt in the app.",
        "receipt",
    ),
    (
        "Eventbrite: Your ticket for the Jazz Festival is confirmed. Add to calendar.",
        "event",
    ),
    (
        "GitHub: A sign-in was detected from a new device. If this was you, no action is needed. Review in your account security settings.",
        "notification",
    ),
    (
        "Google Calendar: Team sync starts in 30 minutes. Join with Google Meet.",
        "calendar",
    ),
    (
        "UPS: Your package is out for delivery and scheduled to arrive by 4 PM today. Track your package in the UPS app.",
        "transactional",
    ),
    (
        "Bank of America: A new statement is available. Please log in through the mobile app or official website to view it.",
        "banking",
    ),
    (
        "PayPal: You sent $18.25 to Jane Doe. View transaction details in your PayPal account.",
        "receipt",
    ),
    (
        "DocuSign: Review and sign the attached lease renewal document by Friday.",
        "transactional",
    ),
    (
        "Zoom: Your meeting with Product Review is scheduled for tomorrow at 2:00 PM. Join from the Zoom app.",
        "calendar",
    ),
    (
        "LinkedIn: You have 3 new messages and 5 profile views this week. See updates in the LinkedIn app.",
        "notification",
    ),
    (
        "Your Adobe subscription has renewed successfully. Download the invoice from your Adobe account.",
        "receipt",
    ),
    (
        "Southwest Airlines: Check in now for your flight to San Diego departing tomorrow at 8:10 AM.",
        "transactional",
    ),
    (
        "Notion: Alex shared the project roadmap with you. Open it in Notion.",
        "notification",
    ),
    (
        "Substack: New post from Platformer: AI policy and this week's industry updates.",
        "newsletter",
    ),
    (
        "Stripe receipt from Figma: Your payment of $15.00 was successful. View receipt.",
        "receipt",
    ),
    (
        "University notice: Registration for fall classes opens Monday. Meet with your advisor if you need help choosing courses.",
        "school",
    ),
    (
        "Luma: Your RSVP for Founder Demo Night is confirmed. Event details and updates will be sent here.",
        "event",
    ),
    (
        "Netflix: Your payment method was updated successfully. Manage your billing preferences in Account settings.",
        "transactional",
    ),
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
