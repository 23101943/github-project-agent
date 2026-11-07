import argparse
import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from tools import TOOL_FUNCTIONS, TOOLS


def build_client() -> tuple[OpenAI, str]:
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("LLM_MODEL", "deepseek-flash")
    if not api_key:
        raise RuntimeError("缺少 LLM_API_KEY，请在 .env 中配置后重试。")
    return OpenAI(api_key=api_key, base_url=base_url), model


def run_agent(question: str, trace: bool = False, max_steps: int = 5) -> tuple[str, list]:
    client, model = build_client()
    messages = [
        {"role": "system", "content": "你是一个可以调用工具的助手，需要时间时请调用 get_current_time。"},
        {"role": "user", "content": question},
    ]
    trace_log = []

    for step in range(1, max_steps + 1):
        resp = client.chat.completions.create(model=model, messages=messages, tools=TOOLS)
        msg = resp.choices[0].message
        trace_log.append({"step": step, "assistant_content": msg.content, "tool_calls": msg.tool_calls and [tc.model_dump() for tc in msg.tool_calls]})

        if not msg.tool_calls:
            return msg.content or "", trace_log

        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            }
        )

        for tc in msg.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments or "{}")
            func = TOOL_FUNCTIONS.get(name)
            result = func(**args) if func else f"未知工具：{name}"
            trace_log.append({"step": step, "tool": name, "arguments": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)})

    return "已达最大步数，未得到最终回答。", trace_log


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="GitHub 项目分析 Agent")
    parser.add_argument("--trace", action="store_true", help="输出并保存执行轨迹 agent_trace.json")
    parser.add_argument("--question", default="", help="要问的问题；不传则交互输入")
    args = parser.parse_args()

    print("你好，我是 GitHub 项目分析 Agent，已经准备就绪。")
    question = args.question.strip() or input("你问点什么：").strip()
    if not question:
        print("没有输入问题。")
        return

    answer, trace_log = run_agent(question, trace=args.trace)
    print(answer)

    if args.trace:
        with open("agent_trace.json", "w", encoding="utf-8") as f:
            json.dump(trace_log, f, ensure_ascii=False, indent=2)
        print("执行轨迹已写入 agent_trace.json")


if __name__ == "__main__":
    main()
