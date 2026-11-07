"""任务09：让 Agent 读取真实仓库并生成带证据的项目分析报告。"""

import json

from dotenv import load_dotenv

from agent import run_agent

QUESTION = (
    "分析仓库 23101943/github-project-agent：先用 get_repo_info 和 get_file_tree 了解整体，"
    "再读取 agent.py、tools.py、github_client.py，最后输出一份带证据的项目分析报告，"
    "每条结论注明来源文件。"
)


def main() -> None:
    load_dotenv()
    report, trace_log = run_agent(QUESTION, max_steps=8)
    with open("REPORT.md", "w", encoding="utf-8") as f:
        f.write(report)
    with open("agent_trace.json", "w", encoding="utf-8") as f:
        json.dump(trace_log, f, ensure_ascii=False, indent=2)
    print(report)
    print("\n[已写入 REPORT.md 与 agent_trace.json]")


if __name__ == "__main__":
    main()
