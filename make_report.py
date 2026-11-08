"""任务09：CLI 输入仓库地址与分析需求，让 Agent 生成带证据的项目分析报告。"""

import argparse
import json

from dotenv import load_dotenv

from agent import run_agent

DEFAULT_REPO = "https://github.com/23101943/github-project-agent"


def _repo_slug(repo: str) -> str:
    """把仓库地址或 owner/repo 统一成 23101943/github-project-agent 形式。"""
    text = repo.strip().rstrip("/")
    if "github.com/" in text:
        text = text.split("github.com/", 1)[1]
    return text[:-4] if text.endswith(".git") else text


def _default_question(repo: str) -> str:
    slug = _repo_slug(repo)
    return (
        f"分析仓库 {slug}（地址 {repo}）：先用 get_repo_info 和 get_file_tree 了解整体，"
        "再读取 agent.py、tools.py、github_client.py 等关键文件，"
        "最后输出一份带证据的项目分析报告，结构为「概况 / 结构 / 关键文件 / 结论与建议」，"
        "每条关键结论后标注对应工具调用步骤，例如 [见 trace step 2]。"
    )


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="生成带证据的 GitHub 项目分析报告")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub 仓库地址或 owner/repo")
    parser.add_argument("--question", default="", help="自定义分析需求；不传则使用默认报告需求")
    args = parser.parse_args()

    question = args.question.strip() or _default_question(args.repo.strip())
    report, trace_log = run_agent(question, max_steps=10)
    with open("REPORT.md", "w", encoding="utf-8") as f:
        f.write(report)
    with open("agent_trace.json", "w", encoding="utf-8") as f:
        json.dump(trace_log, f, ensure_ascii=False, indent=2)
    print(report)
    print("\n[已写入 REPORT.md 与 agent_trace.json]")


if __name__ == "__main__":
    main()
