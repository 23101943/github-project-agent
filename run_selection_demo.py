"""三类提问验证：模型是否为元数据/结构/内容分别选对工具。"""

import json

from dotenv import load_dotenv

from agent import run_agent

QUESTIONS = [
    "仓库 23101943/github-project-agent 的默认分支、主要语言和 star 数分别是多少？",
    "列出 23101943/github-project-agent 仓库 main 分支的全部文件路径。",
    "读取 23101943/github-project-agent 仓库 main 分支的 requirements.txt 内容。",
]


def main() -> None:
    load_dotenv()
    lines = []
    for question in QUESTIONS:
        answer, trace = run_agent(question, max_steps=3)
        calls = [
            {"tool": item["tool"], "arguments": item["arguments"]}
            for item in trace
            if item.get("tool")
        ]
        lines.append(f"Q: {question}\n工具调用: {json.dumps(calls, ensure_ascii=False)}\n最终回答: {answer}\n")
        print(lines[-1])

    with open("tool_selection_log.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("工具选择记录已写入 tool_selection_log.txt")


if __name__ == "__main__":
    main()
