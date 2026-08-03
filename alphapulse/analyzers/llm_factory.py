"""
AlphaPulse - LLM 팩토리

환경변수 LLM_PROVIDER 값에 따라 적절한 LLM 인스턴스를 반환합니다.
새 LLM 제공자 추가 시 이 파일에 등록만 하면 됩니다.
"""

from __future__ import annotations

from alphapulse.analyzers.base_llm import BaseLLM
from alphapulse.config import settings
from alphapulse.utils.logger import logger


def get_llm(provider: str | None = None) -> BaseLLM:
    """
    LLM 인스턴스 반환.

    Args:
        provider: LLM 제공자 이름 (None이면 settings.llm_provider 사용)
                  지원값: "gemini" | "openai" | "anthropic"

    Returns:
        초기화된 BaseLLM 구현체

    Raises:
        ValueError: 지원하지 않는 provider 지정 시
        ImportError: 필요한 라이브러리 미설치 시
    """
    provider = (provider or settings.llm_provider).lower().strip()
    logger.info(f"LLM 팩토리: provider={provider}")

    if provider == "gemini":
        from alphapulse.analyzers.gemini_llm import GeminiLLM
        return GeminiLLM()

    elif provider == "openai":
        try:
            from alphapulse.analyzers.openai_llm import OpenAILLM
            return OpenAILLM()
        except ImportError:
            raise ImportError(
                "OpenAI를 사용하려면 'pip install openai'를 실행하세요."
            )

    elif provider == "anthropic":
        try:
            from alphapulse.analyzers.anthropic_llm import AnthropicLLM
            return AnthropicLLM()
        except ImportError:
            raise ImportError(
                "Anthropic을 사용하려면 'pip install anthropic'를 실행하세요."
            )

    else:
        raise ValueError(
            f"지원하지 않는 LLM provider: '{provider}'. "
            f"지원 목록: gemini, openai, anthropic"
        )
