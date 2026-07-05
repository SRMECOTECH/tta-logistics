"""Single source of truth for app settings, shared by the FastAPI backend and
the MCP server.

Precedence: DB value wins, except when the DB value is empty and the .env
default has a value (so pasting a key into .env later still works even though
settings were already seeded)."""
from .config import DEFAULT_SETTINGS
from .database import SessionLocal
from .models import AppSetting


def get_settings() -> dict:
    with SessionLocal() as db:
        rows = {s.key: s.value for s in db.query(AppSetting).all()}
    merged = dict(DEFAULT_SETTINGS)
    for key, value in rows.items():
        if value == "" and DEFAULT_SETTINGS.get(key):
            continue  # empty DB value -> fall back to .env default
        merged[key] = value
    return merged


def save_settings(updates: dict) -> None:
    with SessionLocal() as db:
        for key, value in updates.items():
            row = db.get(AppSetting, key)
            if row is None:
                db.add(AppSetting(key=key, value=str(value)))
            else:
                row.value = str(value)
        db.commit()


def seed_settings() -> None:
    with SessionLocal() as db:
        existing = {s.key for s in db.query(AppSetting).all()}
        for key, value in DEFAULT_SETTINGS.items():
            if key not in existing:
                db.add(AppSetting(key=key, value=str(value)))
        db.commit()
