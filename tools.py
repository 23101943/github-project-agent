"""工具层：Agent 可以调用的函数与对应的 JSON Schema。"""

import base64
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from github_client import GitHubClient

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


_client: GitHubClient | None = None


def _get_client() -> GitHubClient:
    global _client
    if _client is None:
        _client = GitHubClient()
    return _client


MAX_FILE_BYTES = 100_000
MAX_FILE_LINES = 200
MAX_TREE_ENTRIES = 200


def get_repo_info(owner: str, repo: str) -> dict:
    """返回仓库元数据：描述、默认分支、语言、star、更新时间等。"""
    result = _get_client().get(f"/repos/{owner}/{repo}")
    if not result.get("ok"):
        return result
    data = result["data"]
    return {
        "ok": True,
        "full_name": data.get("full_name"),
        "description": data.get("description"),
        "default_branch": data.get("default_branch"),
        "language": data.get("language"),
        "stars": data.get("stargazers_count"),
        "forks": data.get("forks_count"),
        "open_issues": data.get("open_issues_count"),
        "updated_at": data.get("updated_at"),
        "html_url": data.get("html_url"),
    }


def get_file_tree(owner: str, repo: str, branch: str = "main") -> dict:
    """返回分支的文件树（仅文件路径），条目过多时截断并标记 truncated。"""
    result = _get_client().get(f"/repos/{owner}/{repo}/git/trees/{branch}", params={"recursive": "1"})
    if not result.get("ok"):
        return result
    data = result["data"]
    files = [node["path"] for node in data.get("tree", []) if node.get("type") == "blob"]
    truncated = bool(data.get("truncated")) or len(files) > MAX_TREE_ENTRIES
    return {
        "ok": True,
        "branch": branch,
        "count": len(files),
        "truncated": truncated,
        "files": files[:MAX_TREE_ENTRIES],
    }


def get_file_content(owner: str, repo: str, path: str, ref: str = "main",
                     max_bytes: int = MAX_FILE_BYTES, max_lines: int = MAX_FILE_LINES) -> dict:
    """读取单个文件：base64 解码；超 200 行或超 100KB 时截断并标注；空文件/二进制友好返回。"""
    result = _get_client().get(f"/repos/{owner}/{repo}/contents/{path}", params={"ref": ref})
    if not result.get("ok"):
        return result
    data = result["data"]
    size = data.get("size", 0)
    if size > max_bytes or data.get("encoding") == "none":
        return {
            "ok": True,
            "path": data.get("path"),
            "size": size,
            "truncated": True,
            "message": f"文件 {size} 字节，超过上限 {max_bytes} 或非文本内容，仅返回元数据，请改用局部路径或缩小范围。",
        }

    raw = base64.b64decode(data.get("content", "") or "")
    if b"\x00" in raw:  # 二进制文件：解码后无意义的 NUL 字节，直接给元数据
        return {
            "ok": True,
            "path": data.get("path"),
            "size": size,
            "truncated": True,
            "binary": True,
            "message": f"文件 {size} 字节，判定为二进制内容，不做文本解码。",
        }

    content = raw.decode("utf-8", errors="replace")
    if content == "":
        return {
            "ok": True,
            "path": data.get("path"),
            "size": size,
            "lines": 0,
            "truncated": False,
            "content": "",
            "message": "空文件。",
        }

    lines = content.splitlines()
    if len(lines) > max_lines:
        return {
            "ok": True,
            "path": data.get("path"),
            "size": size,
            "lines": len(lines),
            "truncated": True,
            "content": "\n".join(lines[:max_lines]),
            "message": f"文件共 {len(lines)} 行，超过上限 {max_lines} 行，仅返回前 {max_lines} 行。",
        }

    return {
        "ok": True,
        "path": data.get("path"),
        "size": size,
        "lines": len(lines),
        "truncated": False,
        "content": content,
    }


TOOL_MAP = {
    "get_current_time": get_current_time,
    "get_repo_info": get_repo_info,
    "get_file_tree": get_file_tree,
    "get_file_content": get_file_content,
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
    },
    {
        "type": "function",
        "function": {
            "name": "get_repo_info",
            "description": "获取 GitHub 仓库的元数据（描述、默认分支、语言、star 数、更新时间）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "仓库所有者，例如 23101943"},
                    "repo": {"type": "string", "description": "仓库名，例如 github-project-agent"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_tree",
            "description": "列出仓库某个分支的全部文件路径，用于了解项目结构。",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "仓库所有者"},
                    "repo": {"type": "string", "description": "仓库名"},
                    "branch": {"type": "string", "description": "分支名，默认 main"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_content",
            "description": "读取仓库中单个文件的文本内容；超过大小上限时只返回元数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "仓库所有者"},
                    "repo": {"type": "string", "description": "仓库名"},
                    "path": {"type": "string", "description": "文件路径，例如 agent.py"},
                    "ref": {"type": "string", "description": "分支或 commit，默认 main"},
                },
                "required": ["owner", "repo", "path"],
            },
        },
    },
]
