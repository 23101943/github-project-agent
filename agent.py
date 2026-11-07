import os
from dotenv import load_dotenv
from openai import OpenAI


def main() -> None:
    load_dotenv()

    print("你好，我是 GitHub 项目分析 Agent，已经准备就绪。")

    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("LLM_MODEL", "deepseek-flash")

    if not api_key:
        print("缺少 LLM_API_KEY，请在 .env 中配置后重试。")
        return

    client = OpenAI(api_key=api_key, base_url=base_url)
    question = input("你问点什么：").strip()
    if not question:
        print("没有输入问题。")
        return

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是一个简洁的中文助手。"},
            {"role": "user", "content": question},
        ],
    )
    print(resp.choices[0].message.content)


if __name__ == "__main__":
    main()
