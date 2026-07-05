"""Thin client for the FastAPI backend, with Streamlit caching.

Pages keep calling paths like "/api/kpis"; this client rewrites them to the
canonical versioned contract "/api/v1/kpis" and attaches the X-API-Key header."""
import os
import sys
from pathlib import Path

import requests
import streamlit as st

BASE_URL = os.getenv("TTA_API_URL", "http://127.0.0.1:8000")


def _resolve_api_key() -> str:
    """Same default logic as the backend: TTA_API_KEY env first, then the
    shared settings store (works because UI and backend run on one machine)."""
    key = os.getenv("TTA_API_KEY", "")
    if key:
        return key
    try:
        root = str(Path(__file__).resolve().parents[2])
        if root not in sys.path:
            sys.path.insert(0, root)
        from backend.settings_store import get_settings
        return get_settings().get("api_key", "")
    except Exception:
        return ""


API_KEY = _resolve_api_key()


class ApiError(Exception):
    pass


def _v1(path: str) -> str:
    if path.startswith("/api/") and not path.startswith("/api/v1/"):
        return "/api/v1" + path[len("/api"):]
    return path


def _request(method: str, path: str, **kwargs):
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    try:
        resp = requests.request(method, f"{BASE_URL}{_v1(path)}", timeout=180,
                                headers=headers, **kwargs)
    except requests.ConnectionError:
        raise ApiError(
            f"Backend not reachable at {BASE_URL}. Start it with run.bat (or: "
            f"python -m uvicorn backend.main:app --port 8000)"
        )
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise ApiError(f"{detail}")
    return resp.json()


@st.cache_data(ttl=120, show_spinner=False)
def get(path: str, params: dict | None = None):
    return _request("GET", path, params=params)


def get_fresh(path: str, params: dict | None = None):
    return _request("GET", path, params=params)


def post(path: str, json: dict | None = None, files=None):
    return _request("POST", path, json=json, files=files)


def put(path: str, json: dict):
    return _request("PUT", path, json=json)


def guard(fn, *args, **kwargs):
    """Run an API call; on failure show the error and stop the page."""
    try:
        return fn(*args, **kwargs)
    except ApiError as e:
        st.error(f"⚠️ {e}")
        st.stop()
