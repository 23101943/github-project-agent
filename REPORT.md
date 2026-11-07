# 项目分析报告：23101943/github-project-agent

> 本报告由 `agent.py` 多步 Agent Loop 真实调用 GitHub 工具生成，证据为仓库元数据、`get_file_tree` 文件列表与 `get_file_content` 读取到的文件正文；运行记录见 `run_log.txt`、执行轨迹见 `agent_trace.json`，CI 见 https://github.com/23101943/github-project-agent/actions

## 1. 仓库概况

| 项目 | 值 | 证据 |
|---|---|---|
| 全名 | 23101943/github-project-agent | `get_repo_info` |
| 默认分支 / 语言 | main / Python | `get_repo_info` |
| Star / Fork / Open issues | 0 / 0 / 0 | `get_repo_info` |
| description | 未填写（`None`） | `get_repo_info` |
| 文件总数 | 15（含 `.github/workflows/tests.yml`、`README.md`、`REPORT.md`） | `get_file_tree` |

## 2. 架构：入口 / 工具层 / HTTP 层

```
agent.py            入口与 LLM 工具调用循环（argparse，--max-steps / --trace）
  └─ tools.py       工具实现 + JSON Schema（TOOL_FUNCTIONS / TOOLS）
      └─ github_client.py   httpx 封装：统一请求头、错误分类、限流退避一次
test_github_client.py / test_github_tools.py   14 条 mock 单测
run_tools_demo.py / make_report.py / run_log.txt / REPORT.md / agent_trace.json
```

调用链：`run_agent` → `chat.completions.create(tools=TOOLS)` → `tool_calls` → `TOOL_FUNCTIONS[name](**args)` → `_get_client().get(...)` → 结构化成 dict 回填 `role:"tool"` → 再次请求模型。整条链路不依赖框架，只有 `openai` + `httpx` 两个直接依赖。

## 3. 四个工具（`tools.py`）

| 工具 | 签名 | 后端调用 | 关键保护 |
|---|---|---|---|
| `get_current_time` | `(timezone="Asia/Shanghai")` | 无网络，`zoneinfo` | `ZoneInfoNotFoundError` 时对 Asia/Shanghai、UTC 做固定偏移兜底，其余抛 `ValueError` |
| `get_repo_info` | `(owner, repo)` | `GET /repos/{owner}/{repo}` | 只挑业务字段返回；错误 dict 原样透传 |
| `get_file_tree` | `(owner, repo, branch="main")` | `GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1` | 仅保留 `type=="blob"`；`count` 为过滤后全量；返回前 `MAX_TREE_ENTRIES=200` 项并合并 API 自带 `truncated` 标志 |
| `get_file_content` | `(owner, repo, path, ref="main", max_bytes=100_000, max_lines=200)` | `GET /repos/{owner}/{repo}/contents/{path}?ref=` | base64 解码；超 100KB 或 `encoding=="none"` 只回元数据；含 `\x00` 判二进制只回元数据；空文件返回 `message:"空文件。"`；超 200 行返回前 200 行并标注 `lines/truncated/message` |

设计一致性：工具失败不抛异常，统一返回 `{ok: False, status, error_type, message}`；`_get_client()` 懒加载模块级单例，避免重复建连。

## 4. 注册与 Schema（`TOOL_FUNCTIONS` + `TOOLS`）

- 双轨注册：`TOOL_FUNCTIONS` 提供 name→callable 分发，`TOOLS` 提供 OpenAI function-calling 的 JSON Schema 声明。
- 新增 `ToolRegistryTest` 三条断言保证两者不漂移：
  1. `test_functions_and_schema_names_match`：Schema 名称集合 == `TOOL_FUNCTIONS` 键集合；
  2. `test_schema_required_and_descriptions`：`type=="function"`、函数有 description、`required` 必须出现在 `properties`、每个参数都有 `type` 与 `description`；
  3. `test_schema_params_exist_in_function_signature`：Schema 里的参数必须真实存在于函数签名（防止模型传进无效参数）。
- `agent.py` 侧三重护栏：未知工具返回 `"未知工具：{name}"`；`func(**args)` 异常被 `except Exception` 捕获并回喂 `"工具调用失败：..."`；`max_steps` 用尽返回安全停止提示。

## 5. 多步 Loop 与安全退出（实测）

`agent_trace.json` 记录一次真实运行，共 5 步、9 次工具调用：

```
step 1 | get_repo_info(23101943/github-project-agent)
step 1 | get_file_tree(23101943/github-project-agent)
step 2 | get_file_content(tools.py) · get_file_content(agent.py)
step 3 | get_file_content(test_github_tools.py) · (test_github_client.py) · (.github/workflows/tests.yml)
step 4 | get_file_content(github_client.py)
step 5 | assistant 输出最终报告
```

第 1 步先取仓库元数据与文件树，之后每一步都基于上一步结果决定读哪些文件——这是“结果驱动决策”而非固定脚本。

安全退出实测（`run_log.txt`）：

```
PS> .\venv\Scripts\python.exe agent.py --max-steps 1 --question "分析 23101943/github-project-agent"
已达到最大步数 1，为保证安全停止执行；请缩小问题范围或提高 --max-steps。
```

## 6. 测试与 CI

- `Ran 14 tests in 1.442s` / `OK`（`run_log.txt`），全部 mock，不需要 Token 与网络。
- `test_github_tools.py`：字段映射；250 blob + 1 tree → `count==250`、目录被过滤、`files` 恰 200 条、末项 `f199.py`；小文件解码；空文件；二进制；250 行 → 前 200 行（末行 `line200`，message 含“仅返回前 200 行”）；500KB 仅元数据；404 透传；以及 `ToolRegistryTest` 三条 Schema 一致性用例。
- `test_github_client.py`：401→`auth`、404→`not_found`、403 限流两次后返回 `rate_limit` 且 `sleep` 恰好调用 1 次。
- CI：`.github/workflows/tests.yml` 在 push 与手动触发时跑 `python -m unittest -v test_github_client test_github_tools`（Python 3.12，只装 `httpx`）。

## 7. 真实调用证据

`run_tools_demo.py`（需 `.env` 中的 `GITHUB_TOKEN`）实际返回：仓库信息 JSON（`full_name`、`default_branch=main`、`language=Python`）、文件树 15 项、`github_client.py` 正文（3951 字节，`truncated=false`）。`max-steps` 与 14 条单测输出一并写入 `run_log.txt`。

## 8. 风险与改进建议

1. **限流遥测被丢弃**：`github_client.get()` 成功时返回 `rate: last_rate`，但三个工具都重新组装 dict，`rate` 未透传，模型看不到剩余配额。
2. **默认分支硬编码**：`get_file_tree` / `get_file_content` 的默认分支固定为 `main`，未串联 `get_repo_info` 的 `default_branch`，对非 main 仓库第一步就会 404。
3. **路径/分支未做 URL 编码**：`path` 含空格、`#`、`?`，或分支名含 `/` 时会拼坏请求路径。
4. **`trace` 形参未使用**：`run_agent(question, trace=False, ...)` 内从未读取 `trace`，落盘只在 `main()` 中发生，签名有误导性。
5. **`tool_calls` 为空时 trace 记 `None` 而非 `[]`**：`msg.tool_calls and [...]` 的短路行为，下游消费需注意类型。
6. **`httpx.Client` 未关闭**：无 `close()`/上下文管理器，短脚本场景会泄漏连接。
7. **`agent.py` 循环本身无单测**：异常回喂、未知工具、`max_steps` 三条路径目前只有手工演示证据。
8. **`agent_trace.json` 未加入 `.gitignore`**：它是运行产物，入库后容易成为“陈旧事实”来源（本报告已用最新一次运行覆盖它）。

## 9. 结论

这是一个分层清晰、依赖极简（`openai` + `httpx`）的 GitHub 项目分析 Agent：工具层有明确的上下文预算（100KB / 200 行 / 200 项）与友好的空文件、二进制、超限、404 返回；注册表与 Schema 一致性已由单测守护；多步 Loop 能在 5 步内自主完成“概览 → 精读 → 交叉验证”的分析路径，并在 `--max-steps 1` 下按预期安全退出。主要短板是工具层与 Schema 的双轨手工同步（已加断言缓解）、分支/路径编码缺失，以及 `rate` 遥测未透传给模型。
