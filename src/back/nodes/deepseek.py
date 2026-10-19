from openai import AsyncOpenAI
from src.back.config import api_key, base_url, model_name

ds = AsyncOpenAI(api_key=api_key, base_url=base_url)


async def stream_dialogue(history, temperature: max = 0.7, max_tokens: int = 2048, usage_box: dict = None):
    """
    （原子）流式请求模型，逐字 yield 文本。
    usage_box 传入一个 dict，流结束后会把 token 用量写进去（供日志回填），
    :param history: 会话历史，拼接成了一整个字符串
    :param temperature: 设定温度值
    :param max_tokens: 设定最大token
    :param usage_box:
    :return: 生成器，流式返回模型的回复。对python程序调用方不可见
    """
    # print(usage_box)
    stream = await ds.chat.completions.create(
        model=model_name,
        messages=history,
        stream=True,
        temperature=temperature,
        extra_body={"thinking": {"type": "disabled"}},
    )
    async for chunk in stream:  # ← async for
        if chunk.usage and usage_box is not None:
            usage_box["prompt_tokens"] = chunk.usage.prompt_tokens
            usage_box["completion_tokens"] = chunk.usage.completion_tokens
            usage_box["total_tokens"] = chunk.usage.total_tokens
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


async def summarize_dialogue(history_text: str, old_memory: str, temperature: int = 0, max_tokens: int = 1024) -> str:
    """
    非流式滚动摘要：把待折叠段对话 + 旧前情压缩成新的前情提要（二轮 D15）
    :param history_text: 会话历史，拼接成了一整个字符串
    :param old_memory: 旧摘要
    :param temperature: 温度
    :param max_tokens: 最大token
    :return: 非流式一次性返回新摘要
    """
    system = ("你是对话摘要器，负责把一段对话压缩为「前情提要」。"
              "若提供了旧的前情提要，请将它与新内容融合，保留其中的关键信息。")
    user = (
        "退出剧情扮演模式，以第三人称视角将之前发生的事进行总结，简明扼要的描述事件。"
        "要求：仅使用简洁清晰的语言陈述客观事实，不加评判和修饰；"
        "保证关键剧情时间顺序正确，人物关系正确；"
        "保留关键事件和重要细节，省略冗余描述；"
        "合并重复或相似的事件；无需说明正在总结、用户要求总结。"
        f"\n\n旧的前情提要：\n{old_memory or '（无）'}"
        f"\n\n待总结的对话：\n{history_text}"
    )
    resp = await ds.chat.completions.create(
        model=model_name,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature,
        max_tokens=max_tokens,
        stream=False,
        extra_body={
            "thinking": {"type": "disabled"}
        }
    )
    return resp.choices[0].message.content.strip()
