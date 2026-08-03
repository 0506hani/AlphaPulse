"""
AlphaPulse - LLM 추상 인터페이스

모든 LLM 구현체는 이 클래스를 상속합니다.
LLM 엔진 교체 시 이 인터페이스를 구현한 새 클래스를 추가하고
llm_factory.py에 등록하면 됩니다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLLM(ABC):
    """LLM 추상 기반 클래스"""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """LLM 제공자 이름 (로깅/식별용)"""
        ...

    @abstractmethod
    def generate(self, prompt: str, temperature: float = 0.3) -> str:
        """
        텍스트 생성 요청.

        Args:
            prompt: 입력 프롬프트
            temperature: 창의성 수준 (0=결정론적, 1=창의적)

        Returns:
            생성된 텍스트
        """
        ...

    def generate_json(self, prompt: str) -> str:
        """
        JSON 형식 응답 요청 (파싱 안정성을 위해 temperature=0.1 고정).

        Args:
            prompt: JSON 출력을 요구하는 프롬프트

        Returns:
            JSON 문자열
        """
        return self.generate(prompt, temperature=0.1)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(provider={self.provider_name})"
