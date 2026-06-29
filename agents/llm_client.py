"""
LLM 客户端工具模块
封装 DeepSeek API 调用（兼容 OpenAI SDK）
"""

import os
from openai import OpenAI


def get_llm_client() -> OpenAI:
    """获取 OpenAI 兼容的 LLM 客户端"""
    api_key = os.getenv("DEEPSEEK_API_KEY", "sk-placeholder")
    base_url = os.getenv("BASE_URL", "https://api.deepseek.com")
    return OpenAI(api_key=api_key, base_url=base_url)


def call_llm(prompt: str, system_prompt: str = "", temperature: float = 0.3) -> str:
    """
    调用 LLM 获取响应

    Args:
        prompt: 用户提示
        system_prompt: 系统提示
        temperature: 温度参数

    Returns:
        模型响应文本
    """
    client = get_llm_client()
    model = os.getenv("MODEL_NAME", "deepseek-chat")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content


class LLMClient:
    """
    LLM 客户端封装类，兼容 OpenAI SDK
    供 tag_extractor.py 等模块调用
    """

    def __init__(self):
        self.client = get_llm_client()
        self.model = os.getenv("MODEL_NAME", "deepseek-chat")

    def chat(self, prompt: str, system_prompt: str = "", temperature: float = 0.3) -> str:
        """
        调用 LLM 获取响应

        Args:
            prompt: 用户提示
            system_prompt: 系统提示
            temperature: 温度参数

        Returns:
            模型响应文本
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=2048,
        )
        return response.choices[0].message.content
