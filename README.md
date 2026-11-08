# github-project-agent

一个可调用 GitHub 工具做真实仓库分析的多步 Agent（DeepSeek 模型 + GitHub REST API）。

## 本地运行说明

环境要求：Python 3.10+（用到 `zoneinfo` 与 `X | None` 类型注解）。

```powershell
# 1) 创建并激活虚拟环境
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2) 安装依赖
pip install -r requirements.txt

# 3) 配置环境变量（.env 已被 .gitignore 忽略，不要提交）
Copy-Item .env.example .env
```

`.env` 需要四项：

```
LLM_API_KEY=你的 DeepSeek Key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-flash
GITHUB_TOKEN=你的 GitHub PAT（只需 public_repo 读权限）
```

## 运行方式

```powershell
# 单测（全部 mock，不真调 GitHub）：5 个用例
.\venv\Scripts\python.exe -m unittest -v test_github_tools test_github_client

# 真实请求演示：仓库信息 / 文件树 / 文件内容
.\venv\Scripts\python.exe run_tools_demo.py

# 交互式分析
.\venv\Scripts\python.exe agent.py

# 一次性提问 + 保存执行轨迹 + 限制步数
.\venv\Scripts\python.exe agent.py --question "分析这个仓库的架构与主要风险" --trace --max-steps 6
```

真实演示的期望输出（本机实测）：仓库信息 `language=Python, default_branch=main, stars=0`；
文件树 `count=15, truncated=false`；读取 `github_client.py` 返回 `size=3951, truncated=false`。

完整的本机运行记录（命令 + 输出）见仓库根目录 `run_log.txt`。

## 目录结构

```
agent.py            CLI 入口与多步工具调用循环（--question/--trace/--max-steps）
tools.py            工具层：get_current_time / get_repo_info / get_file_tree / get_file_content + JSON Schema
github_client.py    HTTP 层：Token 鉴权、401/404/403+限流分类、Retry-After 退避一次
test_github_client.py / test_github_tools.py   14 个单测
run_tools_demo.py   真实请求演示脚本
run_selection_demo.py  三类提问验证模型工具选择（生成 tool_selection_log.txt）
make_report.py      生成带证据分析报告 REPORT.md
```

## 安全边界

- Token 只从环境变量读取，源码与提交记录中不含明文凭据。
- 工具派发走白名单 `TOOL_MAP`，模型无法调用任意函数。
- 文件内容上限 100KB、文件树上限 200 项，超出只返回元数据/截断标记。
- `--max-steps` 到点即停，避免无限循环。
