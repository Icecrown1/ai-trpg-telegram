"""Server-side validation of Telegram WebApp initData (HMAC-SHA256).

Spec: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
hash       = HMAC_SHA256(key=secret_key, msg=data_check_string)
"""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException

from .config import TELEGRAM_BOT_TOKEN, ALLOW_DEV_AUTH

MAX_AGE_SECONDS = 24 * 3600


def validate_init_data(init_data: str) -> dict:
    """Return the parsed `user` object if initData is authentic, else raise."""
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        raise HTTPException(401, "Bad initData")

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise HTTPException(401, "No hash in initData")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", TELEGRAM_BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calc_hash, received_hash):
        raise HTTPException(401, "initData signature mismatch")

    auth_date = int(pairs.get("auth_date", "0"))
    if auth_date and time.time() - auth_date > MAX_AGE_SECONDS:
        raise HTTPException(401, "initData expired")

    try:
        return json.loads(pairs["user"])
    except Exception:
        raise HTTPException(401, "No user in initData")


def get_tg_user(x_telegram_init_data: str = Header(default="")) -> dict:
    """FastAPI dependency: authenticated Telegram user from the request header."""
    if x_telegram_init_data:
        return validate_init_data(x_telegram_init_data)
    if ALLOW_DEV_AUTH:
        return {"id": 1, "username": "dev", "first_name": "Dev"}
    raise HTTPException(401, "Missing X-Telegram-Init-Data header")
