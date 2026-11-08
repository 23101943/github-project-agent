import argparse
import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import OpenAI

from tools import TOOL_MAP, TOOLS


def build_client() -> tuple[OpenAI, str]:
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("LLM_MODEL", "deepseek-flash")
    if not api_key:
        raise RuntimeError("缺少 LLM_API_KEY，请在 .env 中配置后重试。")
    return OpenAI(api_key=api_key, base_url=base_url), model


SYSTEM_PROMPT = (
    "你是一个 GitHub 项目分析 Agent，可以调用工具获取真实数据。"
    "分析仓库时先用 get_repo_info 和 get_file_tree 了解整体，"
    "再用 get_file_content 读取关键文件；结论必须注明证据文件名，不要臆测。"
    "需要输出分析报告时，按「概况 / 结构 / 关键文件 / 结论与建议」组织，"
    "并在每条关键结论后标注对应的工具调用步骤，例如 [见 trace step 2]。"
)


def _result_summary(result) -> str:
    """把工具结果压成简短摘要：优先保留 ok/关键计数，再附前 120 字符。"""
    if isinstance(result, dict):
        parts = []
        for key in ("ok", "count", "lines", "size", "truncated", "error_type", "status"):
            if key in result:
                parts.append(f"{key}={result[key]}")
        text = json.dumps(result, ensure_ascii=False)
        head = text[:120]
        return f"{', '.join(parts)} | {head}" if parts else head
    text = str(result)
    return text[:160]


def run_agent(question: str, trace: bool = False, max_steps: int = 10) -> tuple[str, list]:
    client, model = build_client()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    trace_log = []
    step = 0

    while step < max_steps:
        step += 1
        resp = client.chat.completions.create(model=model, messages=messages, tools=TOOLS)
        msg = resp.choices[0].message
        trace_log.append({"step": step, "assistant_content": msg.content, "tool_calls": msg.tool_calls and [tc.model_dump() for tc in msg.tool_calls]})

        if not msg.tool_calls:
            trace_log.append({"step": step, "stop_reason": "final_answer"})
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
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            func = TOOL_MAP.get(name)
            if not func:
                result = f"未知工具：{name}"
            else:
                try:
                    result = func(**args)
                except Exception as exc:  # 工具异常回喂给模型，让循环继续而不是整体崩溃
                    result = f"工具调用失败：{exc.__class__.__name__}: {exc}"
            trace_log.append({
                "step": step,
                "tool_name": name,
                "arguments": args,
                "result_summary": _result_summary(result),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": f"[step {step}] {result}"})

    trace_log.append({"step": step, "stop_reason": "max_steps"})
    return f"已达到最大步数 {max_steps}，为保证安全停止执行；请缩小问题范围或提高 --max-steps。", trace_log


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="GitHub 项目分析 Agent")
    parser.add_argument("--trace", action="store_true", help="输出并保存执行轨迹 agent_trace.json")
    parser.add_argument("--question", default="", help="要问的问题；不传则交互输入")
    parser.add_argument("--max-steps", type=int, default=10, help="最大循环步数，超过后安全退出")
    args = parser.parse_args()

    print("你好，我是 GitHub 项目分析 Agent，已经准备就绪。")
    question = args.question.strip() or input("你问点什么：").strip()
    if not question:
        print("没有输入问题。")
        return

    answer, trace_log = run_agent(question, trace=args.trace, max_steps=args.max_steps)
    print(answer)

    if args.trace:
        with open("agent_trace.json", "w", encoding="utf-8") as f:
            json.dump(trace_log, f, ensure_ascii=False, indent=2)
        print("执行轨迹已写入 agent_trace.json")


if __name__ == "__main__":
    main()
