#!/usr/bin/env python3
"""
Pulls business-relevant emails from Gmail and writes data.json
for the JuicyVisuals / juicymedia.co dashboard.

Filters OUT newsletters, marketing, and account-noise emails.
Filters IN anything that looks like real client/business correspondence:
outreach you sent, replies from brands/venues, contracts, invoices,
payment confirmations, booking/event mentions.

Auth: uses a Gmail OAuth refresh token stored as GitHub Secrets:
  GMAIL_CLIENT_ID
  GMAIL_CLIENT_SECRET
  GMAIL_REFRESH_TOKEN
"""

import os
import json
from datetime import datetime, timedelta

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# ─────────────────────────────────────────────
# CONFIG — tune these lists as your business grows
# ─────────────────────────────────────────────

BLOCKLIST_DOMAINS = [
    "rhodeskin.com",
    "hello.klarna.com",
    "audio.com",
    "accounts.google.com",
    "google.com",
    "mailer-daemon@googlemail.com",
]

BUSINESS_KEYWORDS = [
    "invoice", "payment", "paid", "deposit", "contract", "agreement",
    "booking", "quote", "proposal", "collab", "collaboration",
    "partnership", "event", "shoot", "shoot date", "confirmed",
    "terms", "brief", "rate card", "availability",
]

KNOWN_CONTACTS = [
    "ampvox.co.uk",
    "framego.io",
    "casafrequency",
]

DAYS_BACK = 60

# ─────────────────────────────────────────────

def get_gmail_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def is_blocked(sender):
    sender = sender.lower()
    return any(domain in sender for domain in BLOCKLIST_DOMAINS)


def is_known_contact(sender):
    sender = sender.lower()
    return any(c in sender for c in KNOWN_CONTACTS)


def has_business_keyword(text):
    text = text.lower()
    return any(kw in text for kw in BUSINESS_KEYWORDS)


def classify(subject, snippet, sender):
    text = f"{subject} {snippet}".lower()
    if any(k in text for k in ["invoice", "payment", "paid", "deposit"]):
        return "earnings"
    if any(k in text for k in ["booking", "event", "shoot", "confirmed", "availability"]):
        return "timeline"
    if any(k in text for k in ["proposal", "collab", "partnership", "quote", "brief"]):
        return "pipeline"
    return "general"


def fetch_business_emails():
    service = get_gmail_service()
    query = f"newer_than:{DAYS_BACK}d"

    results = []
    page_token = None

    while True:
        resp = service.users().messages().list(
            userId="me", q=query, pageToken=page_token, maxResults=100
        ).execute()

        for msg_ref in resp.get("messages", []):
            msg = service.users().messages().get(
                userId="me", id=msg_ref["id"], format="metadata",
                metadataHeaders=["Subject", "From", "Date"]
            ).execute()

            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            sender = headers.get("From", "")
            subject = headers.get("Subject", "")
            snippet = msg.get("snippet", "")
            date = headers.get("Date", "")

            if is_blocked(sender):
                continue

            if not (is_known_contact(sender) or has_business_keyword(f"{subject} {snippet}")):
                continue

            results.append({
                "id": msg_ref["id"],
                "sender": sender,
                "subject": subject,
                "snippet": snippet,
                "date": date,
                "section": classify(subject, snippet, sender),
            })

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return results


def main():
    emails = fetch_business_emails()

    data = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "pipeline": [e for e in emails if e["section"] == "pipeline"],
        "timeline": [e for e in emails if e["section"] == "timeline"],
        "earnings": [e for e in emails if e["section"] == "earnings"],
        "general": [e for e in emails if e["section"] == "general"],
        "stats": {
            "total_business_emails": len(emails),
        },
    }

    with open("data.json", "w") as f:
        json.dump(data, f, indent=2)

    print(f"Wrote {len(emails)} business emails to data.json")


if __name__ == "__main__":
    main()
