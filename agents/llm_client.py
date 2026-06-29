"""
LLM 客户端工具模块
封装 DeepSeek API 调用（兼容 OpenAI SDK）

v3.0 增强：
- 详细错误日志（捕获 APIConnectionError, TimeoutError, APIStatusError）
- 超时设置 300 秒，适配超大 prompt
- 代理支持（HTTP_PROXY, HTTPS_PROXY）
- base_url 格式验证
- max_tokens 设置为 8192
- 请求前打印 prompt 摘要
"""

import os
import sys
import logging
from typing import Optional
from urllib.parse import urlparse

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
        "HTTP_PROXY": os.getenv("HTTP_PROXY", "未设置"),
        "HTTPS_PROXY": os.getenv("HTTPS_PROXY", "未设置"),
    }

    # 隐藏 API Key 中间部分
    api_key = env_status["DEEPSEEK_API_KEY"]
    if api_key and api_key != "未设置" and len(api_key) > 10:
        env_status["DEEPSEEK_API_KEY"] = f"{api_key[:8]}...{api_key[-4:]}"

    return env_status


def _normalize_base_url(url: str) -> str:
    """
    规范化 base_url，移除末尾斜杠和多余空格

    Args:
        url: 原始 URL

    Returns:
        规范化后的 URL
    """
    url = url.strip().rstrip("/")
    if not url.startswith("http"):
        url = "https://" + url
    return url


def get_llm_client() -> OpenAI:
    """
    获取 OpenAI 兼容的 LLM 客户端

    配置说明：
    - timeout=300.0: 5 分钟超时，适配超大 prompt
    - max_retries=3: 失败自动重试 3 次
    - 支持代理配置
    """
    api_key = os.getenv("DEEPSEEK_API_KEY", "sk-placeholder")
    base_url = os.getenv("BASE_URL", "https://api.deepseek.com")

    # 规范化 base_url
    base_url = _normalize_base_url(base_url)

    if api_key == "sk-placeholder":
        logger.warning("⚠️ DEEPSEEK_API_KEY 未设置，使用占位符")

    # 获取代理配置
    http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")

    # 构建客户端参数
    client_kwargs = {
        "api_key": api_key,
        "base_url": base_url,
        "timeout": 300.0,      # 5 分钟超时
        "max_retries": 3,       # 失败自动重试 3 次
    }

    # 如果有代理配置，添加到 http_client
    if http_proxy or https_proxy:
        try:
            import httpx
            proxy = https_proxy or http_proxy
            http_client = httpx.Client(
                proxy=proxy,
                timeout=httpx.Timeout(300.0),
                verify=False,  # 禁用 SSL 验证（代理环境可能需要）
            )
            client_kwargs["http_client"] = http_client
            logger.info(f"🌐 使用代理: {proxy}")
        except ImportError:
            logger.warning("⚠️ httpx 未安装，无法配置代理")

    client = OpenAI(**client_kwargs)

    logger.info(f"🚀 LLM 客户端初始化完成:")
    logger.info(f"   base_url: {base_url}")
    logger.info(f"   model: {os.getenv('MODEL_NAME', 'deepseek-chat')}")
    logger.info(f"   timeout: 300s")
    logger.info(f"   max_retries: 3")
    if http_proxy or https_proxy:
        logger.info(f"   proxy: {https_proxy or http_proxy}")

    return client


def call_llm(
    prompt: str,
    system_prompt: str = "",
    temperature: float = 0.3,
    max_tokens: int = 8192,
    timeout: float = 300.0,
) -> tuple[str, Optional[str]]:
    """
    调用 LLM 获取响应

    Args:
        prompt: 用户提示
        system_prompt: 系统提示
        temperature: 温度参数
        max_tokens: 最大生成 token 数（DeepSeek 支持 8192）
        timeout: 超时时间（秒）

    Returns:
        (响应文本, 错误信息或 None)
    """
    client = get_llm_client()
    model = os.getenv("MODEL_NAME", "deepseek-chat")
    base_url = os.getenv("BASE_URL", "https://api.deepseek.com")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # 记录请求信息（包含 prompt 摘要）
    prompt_len = len(prompt)
    prompt_preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
    logger.info(f"🚀 LLM 请求开始:")
    logger.info(f"   model: {model}")
    logger.info(f"   base_url: {base_url}")
    logger.info(f"   prompt_length: {prompt_len} 字符")
    logger.info(f"   max_tokens: {max_tokens}")
    logger.info(f"   timeout: {timeout}s")
    logger.info(f"   temperature: {temperature}")
    logger.info(f"   prompt_preview: {prompt_preview}")

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
        logger.info(f"✅ LLM 请求成功:")
        if usage:
            logger.info(f"   prompt_tokens: {usage.prompt_tokens}")
            logger.info(f"   completion_tokens: {usage.completion_tokens}")
            logger.info(f"   total_tokens: usage.prompt_tokens + usage.completion_tokens")
        logger.info(f"   response_length: {len(content)} 字符")

        return content, None

    except APITimeoutError as e:
        error_msg = f"⏰ LLM 请求超时 (timeout={timeout}s): {str(e)}"
        logger.error(error_msg)
        logger.error(f"   prompt_length: {prompt_len}")
        logger.error(f"   建议: 增加 timeout 或减少 prompt 长度")
        return "", error_msg

    except APIConnectionError as e:
        error_msg = f"🔌 LLM 连接错误: {str(e)}"
        logger.error(error_msg)
        logger.error(f"   base_url: {base_url}")
        logger.error(f"   请检查:")
        logger.error(f"   1. 网络连接是否正常")
        logger.error(f"   2. BASE_URL 是否正确: {base_url}")
        logger.error(f"   3. 是否需要配置代理 (HTTP_PROXY/HTTPS_PROXY)")
        logger.error(f"   4. 防火墙是否阻止了连接")
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
        max_tokens: int = 8192,
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
                timeout=300.0,
            )
            return response.choices[0].message.content, None

        except Exception as e:
            error_msg = f"LLM 调用失败: {type(e).__name__}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return "", error_msg


# 启动时检查环境变量
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    env_status = check_env_variables()
    print("\n=== 环境变量检查 ===")
    for key, value in env_status.items():
        print(f"  {key}: {value}")
    print("\n=== 测试 LLM 连接 ===")
    result, error = call_llm("Hello, this is a test.", max_tokens=50)
    if error:
        print(f"❌ 测试失败: {error}")
    else:
        print(f"✅ 测试成功: {result[:100]}")
