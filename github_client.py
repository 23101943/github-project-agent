"""GitHub API 客户端：自动带 Token、区分错误类型、限流退避一次。"""

import os
import time

import httpx

GITHUB_API = "https://api.github.com"


class GitHubClient:
    """封装 GitHub REST API 调用，错误以结构化 dict 返回，不静默吞掉。"""

    def __init__(self, token: str | None = None, base_url: str = GITHUB_API):
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self.base_url = base_url
        self.headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-project-agent",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"
        self.client = httpx.Client(base_url=self.base_url, headers=self.headers, timeout=20)
        self.last_rate = {}

    def _record_rate(self, resp: httpx.Response) -> None:
        self.last_rate = {
            "limit": resp.headers.get("X-RateLimit-Limit"),
            "remaining": resp.headers.get("X-RateLimit-Remaining"),
            "reset": resp.headers.get("X-RateLimit-Reset"),
        }

    def get(self, path: str, params: dict | None = None, _retried: bool = False) -> dict:
        if not self.token:
            return {
                "ok": False,
                "status": 401,
                "error_type": "missing_token",
                "message": "未配置 GITHUB_TOKEN，请在 .env 中设置后重试。",
            }

        try:
            resp = self.client.get(path, params=params)
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "status": 0,
                "error_type": "network",
                "message": f"网络请求失败：{exc.__class__.__name__}，请检查网络后重试。",
            }
        self._record_rate(resp)

        if resp.status_code == 401:
            return {
                "ok": False,
                "status": 401,
                "error_type": "auth",
                "message": "Token 无效或已过期，请重新生成。",
            }

        if resp.status_code == 404:
            return {
                "ok": False,
                "status": 404,
                "error_type": "not_found",
                "message": "资源不存在或当前 Token 无权访问。",
            }

        if resp.status_code == 403 or resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            remaining = resp.headers.get("X-RateLimit-Remaining")
            is_rate_limited = resp.status_code == 429 or remaining == "0" or retry_after is not None
            if is_rate_limited and not _retried:
                wait = int(retry_after) if retry_after and retry_after.isdigit() else 60
                time.sleep(wait)
                return self.get(path, params=params, _retried=True)
            return {
                "ok": False,
                "status": resp.status_code,
                "error_type": "rate_limit" if is_rate_limited else "forbidden",
                "message": "触发 GitHub 限流，已退避重试一次仍失败。" if is_rate_limited else "当前 Token 权限不足。",
                "retry_after": retry_after,
            }

        if resp.status_code >= 400:
            return {
                "ok": False,
                "status": resp.status_code,
                "error_type": "http_error",
                "message": f"GitHub 返回错误：{resp.status_code}",
            }

        try:
            data = resp.json()
        except ValueError:
            return {
                "ok": False,
                "status": resp.status_code,
                "error_type": "bad_response",
                "message": "GitHub 返回了非 JSON 内容，可能是网关错误页。",
            }

        return {
            "ok": True,
            "status": resp.status_code,
            "data": data,
            "rate": self.last_rate,
        }
