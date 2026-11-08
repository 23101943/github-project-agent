"""任务08：多步 Loop 上限、安全退出与异常回喂的单测（全部 mock，不需要真实模型）。"""

import inspect
import json
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import agent


def _tool_call(name="get_current_time", arguments=None, call_id="call_1"):
    raw_args = json.dumps(arguments or {})
    payload = {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": raw_args},
        "index": 0,
    }
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=raw_args),
        model_dump=lambda: payload,
    )


def _message(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


class FakeCompletions:
    """按顺序返回预设消息；超出后重复最后一条，用于模拟“模型一直要求调工具”。"""

    def __init__(self, messages):
        self.messages = messages
        self.calls = 0
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        index = min(self.calls, len(self.messages) - 1)
        self.calls += 1
        return SimpleNamespace(choices=[SimpleNamespace(message=self.messages[index])])


def _fake_client(completions):
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


class AgentLoopTest(unittest.TestCase):
    def test_default_max_steps_is_10(self):
        default = inspect.signature(agent.run_agent).parameters["max_steps"].default
        self.assertEqual(default, 10)

    def test_stops_at_max_steps_without_infinite_loop(self):
        completions = FakeCompletions([_message(tool_calls=[_tool_call()])])
        client = _fake_client(completions)
        with patch.object(agent, "build_client", return_value=(client, "fake-model")):
            answer, trace = agent.run_agent("分析仓库", max_steps=3)

        self.assertIn("已达到最大步数 3", answer)
        self.assertEqual(completions.calls, 3)  # 只请求了 max_steps 次，证明不会死循环
        self.assertEqual(trace[-1]["stop_reason"], "max_steps")
        tool_records = [item for item in trace if "tool_name" in item]
        self.assertEqual(len(tool_records), 3)
        for record in tool_records:
            self.assertEqual(
                set(record),
                {"step", "tool_name", "arguments", "result_summary", "timestamp"},
            )
            self.assertEqual(record["tool_name"], "get_current_time")
            datetime.fromisoformat(record["timestamp"])  # 必须是合法的 ISO 8601 时间
            self.assertIsInstance(record["result_summary"], str)
        tool_messages = [m for m in completions.last_kwargs["messages"] if m["role"] == "tool"]
        self.assertEqual(len(tool_messages), 3)
        self.assertTrue(tool_messages[0]["content"].startswith("[step 1] "))

    def test_returns_final_answer_and_marks_stop_reason(self):
        completions = FakeCompletions([
            _message(tool_calls=[_tool_call()]),
            _message(content="最终回答"),
        ])
        client = _fake_client(completions)
        with patch.object(agent, "build_client", return_value=(client, "fake-model")):
            answer, trace = agent.run_agent("分析仓库")

        self.assertEqual(answer, "最终回答")
        self.assertEqual(completions.calls, 2)
        self.assertEqual(trace[-1], {"step": 2, "stop_reason": "final_answer"})

    def test_tool_exception_is_fed_back_and_loop_continues(self):
        def boom(**kwargs):
            raise RuntimeError("模拟工具失败")

        completions = FakeCompletions([
            _message(tool_calls=[_tool_call(name="boom")]),
            _message(content="已根据错误调整"),
        ])
        client = _fake_client(completions)
        with patch.object(agent, "build_client", return_value=(client, "fake-model")), \
                patch.dict(agent.TOOL_MAP, {"boom": boom}):
            answer, trace = agent.run_agent("分析仓库")

        self.assertEqual(answer, "已根据错误调整")
        tool_record = [item for item in trace if "tool_name" in item][0]
        self.assertEqual(tool_record["tool_name"], "boom")
        self.assertTrue(tool_record["result_summary"].startswith("工具调用失败：RuntimeError"))
        datetime.fromisoformat(tool_record["timestamp"])
        fed_back = [m for m in completions.last_kwargs["messages"] if m["role"] == "tool"][0]
        self.assertIn("[step 1] 工具调用失败：RuntimeError", fed_back["content"])
        self.assertEqual(completions.calls, 2)


if __name__ == "__main__":
    unittest.main()
