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
    def test_keeps_only_blobs_and_truncates_overlong_list(self):
        # 超长列表：250 个文件（> 200 上限），另有 1 个目录节点应被过滤
        tree = [{"path": f"f{i}.py", "type": "blob"} for i in range(250)]
        tree.append({"path": "src", "type": "tree"})
        use_fake({
            "/repos/o/r/git/trees/main": {"ok": True, "status": 200, "data": {"tree": tree}}
        })
        result = tools.get_file_tree("o", "r")
        self.assertEqual(result["count"], 250)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["files"]), 200)
        self.assertEqual(result["files"][-1], "f199.py")
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
        self.assertEqual(result["lines"], 1)

    def test_empty_file_is_friendly(self):
        use_fake({
            "/repos/o/r/contents/empty.txt": {
                "ok": True,
                "status": 200,
                "data": {"path": "empty.txt", "size": 0, "encoding": "base64", "content": ""},
            }
        })
        result = tools.get_file_content("o", "r", "empty.txt")
        self.assertTrue(result["ok"])
        self.assertEqual(result["content"], "")
        self.assertEqual(result["lines"], 0)
        self.assertFalse(result["truncated"])
        self.assertEqual(result["message"], "空文件。")

    def test_binary_content_returns_metadata_only(self):
        raw = b"\x00\x01\x02binary"
        use_fake({
            "/repos/o/r/contents/logo.bin": {
                "ok": True,
                "status": 200,
                "data": {
                    "path": "logo.bin",
                    "size": len(raw),
                    "encoding": "base64",
                    "content": base64.b64encode(raw).decode(),
                },
            }
        })
        result = tools.get_file_content("o", "r", "logo.bin")
        self.assertTrue(result["binary"])
        self.assertNotIn("content", result)
        self.assertIn("二进制", result["message"])

    def test_truncates_at_200_lines(self):
        raw = "".join(f"line{i}\n" for i in range(1, 251))
        use_fake({
            "/repos/o/r/contents/long.py": {
                "ok": True,
                "status": 200,
                "data": {
                    "path": "long.py",
                    "size": len(raw),
                    "encoding": "base64",
                    "content": base64.b64encode(raw.encode()).decode(),
                },
            }
        })
        result = tools.get_file_content("o", "r", "long.py")
        self.assertTrue(result["truncated"])
        self.assertEqual(result["lines"], 250)
        self.assertEqual(len(result["content"].splitlines()), 200)
        self.assertEqual(result["content"].splitlines()[-1], "line200")
        self.assertIn("仅返回前 200 行", result["message"])

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


class ToolRegistryTest(unittest.TestCase):
    """注册表与 Schema 一致：函数集合、必填参数、参数说明都要对得上。"""

    def test_functions_and_schema_names_match(self):
        schema_names = {spec["function"]["name"] for spec in tools.TOOLS}
        self.assertEqual(schema_names, set(tools.TOOL_MAP))

    def test_schema_required_and_descriptions(self):
        for spec in tools.TOOLS:
            fn = spec["function"]
            self.assertEqual(spec["type"], "function")
            self.assertTrue(fn["description"], f"{fn['name']} 缺少 description")
            params = fn["parameters"]
            self.assertEqual(params["type"], "object")
            props = params["properties"]
            for key in params.get("required", []):
                self.assertIn(key, props, f"{fn['name']} 必填参数 {key} 不在 properties 中")
            for key, meta in props.items():
                self.assertIn("description", meta, f"{fn['name']}.{key} 缺少参数说明")
                self.assertIn("type", meta, f"{fn['name']}.{key} 缺少参数类型")

    def test_schema_params_exist_in_function_signature(self):
        import inspect
        for spec in tools.TOOLS:
            fn = spec["function"]
            func = tools.TOOL_MAP[fn["name"]]
            allowed = set(inspect.signature(func).parameters)
            for key in fn["parameters"]["properties"]:
                self.assertIn(key, allowed, f"{fn['name']} Schema 中的 {key} 不在函数签名里")


if __name__ == "__main__":
    unittest.main()
