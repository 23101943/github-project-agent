"""工具层：Agent 可以调用的函数与对应的 JSON Schema。"""

from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_FALLBACK_OFFSETS = {
    "Asia/Shanghai": 8,
    "UTC": 0,
}


def get_current_time(timezone: str = "Asia/Shanghai") -> str:
    """返回指定 IANA 时区的当前时间，格式：YYYY-MM-DD HH:MM:SS 时区名。"""
    try:
        tz = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        if timezone not in _FALLBACK_OFFSETS:
            raise ValueError(f"未知时区：{timezone}")
        tz = dt_timezone(timedelta(hours=_FALLBACK_OFFSETS[timezone]), timezone)
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")


TOOL_FUNCTIONS = {
    "get_current_time": get_current_time,
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取指定 IANA 时区的当前日期与时间，用于需要实时时间的回答。",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "IANA 时区名，例如 Asia/Shanghai",
                    }
                },
                "required": [],
            },
        },
    }
]
