"""真实请求演示：用本地 Token 调用仓库信息 / 文件树 / 文件内容三个工具。"""

import json

from dotenv import load_dotenv

import tools

load_dotenv()

OWNER, REPO = "23101943", "github-project-agent"


def show(title, data):
    print(f"\n== {title} ==")
    print(json.dumps(data, ensure_ascii=False, indent=1)[:1200])


show("仓库信息", tools.get_repo_info(OWNER, REPO))
show("文件树", tools.get_file_tree(OWNER, REPO))
content = tools.get_file_content(OWNER, REPO, "github_client.py")
show("文件内容 github_client.py",
     {"ok": content.get("ok"), "size": content.get("size"),
      "truncated": content.get("truncated"), "head": (content.get("content") or "")[:200]})
