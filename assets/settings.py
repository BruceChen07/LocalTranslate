"""本地设置持久化（语言方向 / 语气 / 主题 / 空闲释放策略）。"""
from __future__ import annotations

import json
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"

DEFAULTS = {
    "direction": "中 → 英",
    "tone": "正式商务",
    "theme": "dark",
    "release": "30 秒",
}


def load() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    result = dict(DEFAULTS)
    if isinstance(data, dict):
        for key in DEFAULTS:
            if key in data:
                result[key] = data[key]
    return result


def save(settings: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {key: settings.get(key, DEFAULTS[key]) for key in DEFAULTS}
    SETTINGS_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
