"""GitHub 工具层单测：用假客户端返回构造好的响应，不真调 API。"""

import base64
import unittest

import tools


class FakeClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        return self.payloads[path]


def use_fake(payloads):
    fake = FakeClient(payloads)
    tools._client = fake
    return fake


class RepoInfoTest(unittest.TestCase):
    def test_extracts_fields(self):
        use_fake({
            "/repos/o/r": {
                "ok": True,
                "status": 200,
                "data": {
                    "full_name": "o/r", "description": "demo", "default_branch": "main",
                    "language": "Python", "stargazers_count": 3, "forks_count": 1,
                    "open_issues_count": 0, "updated_at": "2026-11-07T10:00:00Z",
                    "html_url": "https://github.com/o/r",
                },
            }
        })
        info = tools.get_repo_info("o", "r")
        self.assertTrue(info["ok"])
        self.assertEqual(info["default_branch"], "main")
        self.assertEqual(info["stars"], 3)


class FileTreeTest(unittest.TestCase):
    def test_keeps_only_blobs_and_truncates(self):
        tree = [{"path": f"f{i}.py", "type": "blob"} for i in range(tools.MAX_TREE_ENTRIES + 5)]
        tree.append({"path": "src", "type": "tree"})
        use_fake({
            "/repos/o/r/git/trees/main": {"ok": True, "status": 200, "data": {"tree": tree}}
        })
        result = tools.get_file_tree("o", "r")
        self.assertEqual(result["count"], tools.MAX_TREE_ENTRIES + 5)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["files"]), tools.MAX_TREE_ENTRIES)
        self.assertNotIn("src", result["files"])


class FileContentTest(unittest.TestCase):
    def test_decodes_small_file(self):
        raw = "print('hi')\n"
        use_fake({
            "/repos/o/r/contents/a.py": {
                "ok": True,
                "status": 200,
                "data": {
                    "path": "a.py",
                    "size": len(raw),
                    "encoding": "base64",
                    "content": base64.b64encode(raw.encode()).decode(),
                },
            }
        })
        result = tools.get_file_content("o", "r", "a.py")
        self.assertFalse(result["truncated"])
        self.assertEqual(result["content"], raw)

    def test_oversize_returns_metadata_only(self):
        use_fake({
            "/repos/o/r/contents/big.py": {
                "ok": True,
                "status": 200,
                "data": {"path": "big.py", "size": 500_000, "encoding": "none", "content": ""},
            }
        })
        result = tools.get_file_content("o", "r", "big.py")
        self.assertTrue(result["truncated"])
        self.assertNotIn("content", result)

    def test_propagates_error(self):
        use_fake({
            "/repos/o/r/contents/missing.py": {
                "ok": False, "status": 404, "error_type": "not_found", "message": "资源不存在",
            }
        })
        result = tools.get_file_content("o", "r", "missing.py")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "not_found")


if __name__ == "__main__":
    unittest.main()
