"""
LLM 客户端工具模块
封装 DeepSeek API 调用（兼容 OpenAI SDK）

v2.0 增强：
- 详细错误日志（捕获 APIConnectionError, TimeoutError, APIStatusError）
- 超时设置 180 秒，适配大 prompt
- 重试时打印具体异常信息
- 支持环境变量检查
"""

import os
import sys
import logging
from typing import Optional

from openai import OpenAI, APIConnectionError, APITimeoutError, APIStatusError, RateLimitError

# 确保项目根目录在 Python 路径中
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# 日志配置
logger = logging.getLogger("llm_client")


def check_env_variables() -> dict:
    """
    检查环境变量是否正确加载

    Returns:
        环境变量状态字典
    """
    env_status = {
        "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY", "未设置"),
        "BASE_URL": os.getenv("BASE_URL", "未设置"),
        "MODEL_NAME": os.getenv("MODEL_NAME", "未设置"),
    }

    # 隐藏 API Key 中间部分
    api_key = env_status["DEEPSEEK_API_KEY"]
    if api_key and api_key != "未设置" and len(api_key) > 10:
        env_status["DEEPSEEK_API_KEY"] = f"{api_key[:8]}...{api_key[-4:]}"

    return env_status


def get_llm_client() -> OpenAI:
    """
    获取 OpenAI 兼容的 LLM 客户端

    配置说明：
    - timeout=180.0: 3 分钟超时，适配写手官大 prompt
    - max_retries=3: 失败自动重试 3 次
    """
    api_key = os.getenv("DEEPSEEK_API_KEY", "sk-placeholder")
    base_url = os.getenv("BASE_URL", "https://api.deepseek.com")

    if api_key == "sk-placeholder":
        logger.warning("⚠️ DEEPSEEK_API_KEY 未设置，使用占位符")

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=180.0,      # 3 分钟超时
        max_retries=3,       # 失败自动重试 3 次
    )

    logger.info(f"LLM 客户端初始化完成: base_url={base_url}, model={os.getenv('MODEL_NAME', 'deepseek-chat')}")
    return client


def call_llm(
    prompt: str,
    system_prompt: str = "",
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: float = 180.0,
) -> tuple[str, Optional[str]]:
    """
    调用 LLM 获取响应

    Args:
        prompt: 用户提示
        system_prompt: 系统提示
        temperature: 温度参数
        max_tokens: 最大生成 token 数
        timeout: 超时时间（秒）

    Returns:
        (响应文本, 错误信息或 None)
    """
    client = get_llm_client()
    model = os.getenv("MODEL_NAME", "deepseek-chat")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # 记录请求信息
    prompt_len = len(prompt)
    logger.info(f"🚀 LLM 请求开始: model={model}, prompt_length={prompt_len}, max_tokens={max_tokens}")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

        content = response.choices[0].message.content
        usage = response.usage

        # 记录成功信息
        logger.info(
            f"✅ LLM 请求成功: "
            f"prompt_tokens={usage.prompt_tokens if usage else 'N/A'}, "
            f"completion_tokens={usage.completion_tokens if usage else 'N/A'}, "
            f"response_length={len(content)}"
        )

        return content, None

    except APITimeoutError as e:
        error_msg = f"⏰ LLM 请求超时: {str(e)}"
        logger.error(error_msg)
        logger.error(f"   超时设置: {timeout}s, prompt_length: {prompt_len}")
        return "", error_msg

    except APIConnectionError as e:
        error_msg = f"🔌 LLM 连接错误: {str(e)}"
        logger.error(error_msg)
        logger.error(f"   请检查网络连接和 BASE_URL: {os.getenv('BASE_URL')}")
        return "", error_msg

    except RateLimitError as e:
        error_msg = f"🚦 LLM 速率限制: {str(e)}"
        logger.error(error_msg)
        logger.error("   请稍后重试或检查 API 配额")
        return "", error_msg

    except APIStatusError as e:
        error_msg = f"❌ LLM API 状态错误: status_code={e.status_code}, {str(e)}"
        logger.error(error_msg)
        logger.error(f"   响应内容: {e.response.text if e.response else 'N/A'}")
        return "", error_msg

    except Exception as e:
        error_msg = f"💥 LLM 未知错误: {type(e).__name__}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return "", error_msg


class LLMClient:
    """
    LLM 客户端封装类，兼容 OpenAI SDK
    供 tag_extractor.py 等模块调用
    """

    def __init__(self):
        self.client = get_llm_client()
        self.model = os.getenv("MODEL_NAME", "deepseek-chat")

    def chat(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> tuple[str, Optional[str]]:
        """
        调用 LLM 获取响应

        Returns:
            (响应文本, 错误信息或 None)
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=180.0,
            )
            return response.choices[0].message.content, None

        except Exception as e:
            error_msg = f"LLM 调用失败: {type(e).__name__}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return "", error_msg


# 启动时检查环境变量
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    env_status = check_env_variables()
    print("=== 环境变量检查 ===")
    for key, value in env_status.items():
        print(f"  {key}: {value}")
