"""github_client 的错误分支与限流重试单测（全部 mock，不真实调用 API）。"""

import unittest
from unittest import mock

import httpx

from github_client import GitHubClient


def fake_response(status_code: int, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code,
        headers=headers or {},
        request=httpx.Request("GET", "https://api.github.com/test"),
    )


class GitHubClientErrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = GitHubClient(token="fake-token")

    def test_401_returns_auth_error(self) -> None:
        with mock.patch.object(self.client.client, "get", return_value=fake_response(401)):
            result = self.client.get("/repos/a/b")
        self.assertEqual(result["error_type"], "auth")
        self.assertEqual(result["status"], 401)

    def test_403_rate_limit_retries_once_then_returns_error(self) -> None:
        responses = [
            fake_response(403, {"Retry-After": "1", "X-RateLimit-Remaining": "0"}),
            fake_response(403, {"Retry-After": "1", "X-RateLimit-Remaining": "0"}),
        ]
        with mock.patch.object(self.client.client, "get", side_effect=responses), \
                mock.patch("github_client.time.sleep") as sleep:
            result = self.client.get("/repos/a/b")
        self.assertEqual(result["error_type"], "rate_limit")
        self.assertEqual(sleep.call_count, 1)

    def test_404_returns_not_found(self) -> None:
        with mock.patch.object(self.client.client, "get", return_value=fake_response(404)):
            result = self.client.get("/repos/a/b")
        self.assertEqual(result["error_type"], "not_found")
        self.assertEqual(result["status"], 404)


if __name__ == "__main__":
    unittest.main()
