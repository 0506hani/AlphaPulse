"""
AlphaPulse - Google Gemini LLM 구현

google-generativeai 라이브러리를 사용하여 Gemini API를 연동합니다.
기본 모델: gemini-2.0-flash (빠른 응답 + 무료 티어 지원)
"""

from __future__ import annotations

import re
import time

import google.generativeai as genai

from alphapulse.analyzers.base_llm import BaseLLM
from alphapulse.config import settings
from alphapulse.utils.logger import logger


class GeminiLLM(BaseLLM):
    """Google Gemini API LLM 구현체"""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        max_retries: int = 5,
        retry_delay: float = 13.0,
    ):
        """
        Args:
            api_key: Gemini API 키 (None이면 settings에서 로드)
            model_name: 사용할 모델명 (None이면 settings에서 로드)
            max_retries: API 호출 실패 시 최대 재시도 횟수
            retry_delay: 재시도 간격 (초)
        """
        self._api_key = api_key or settings.gemini_api_key
        self._model_name = model_name or settings.gemini_model
        self._max_retries = max_retries
        self._retry_delay = retry_delay

        # Gemini API 초기화
        genai.configure(api_key=self._api_key)
        self._model = genai.GenerativeModel(
            model_name=self._model_name,
            generation_config={
                "temperature": 0.3,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 8192,
            },
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
        )
        logger.info(f"Gemini LLM 초기화 완료: 모델={self._model_name}")

    @property
    def provider_name(self) -> str:
        return f"Google Gemini ({self._model_name})"

    @staticmethod
    def _parse_retry_delay(error_msg: str, fallback: float = 30.0) -> float:
        """429 에러 메시지에서 retry_delay 초를 파싱합니다."""
        # 'Please retry in 29.117186909s' 패턴 추출
        match = re.search(r"retry in (\d+\.?\d*)s", str(error_msg))
        if match:
            return float(match.group(1)) + 2.0  # 여유 2초 추가
        return fallback

    def generate(self, prompt: str, temperature: float = 0.3) -> str:
        """
        Gemini API로 텍스트 생성.
        429 Rate Limit 시 API 지시 대기시간 준수 후 재시도.
        """
        for attempt in range(1, self._max_retries + 1):
            try:
                # temperature 오버라이드 (요청별로 다를 수 있음)
                generation_config = genai.types.GenerationConfig(
                    temperature=temperature,
                    top_p=0.95,
                    max_output_tokens=8192,
                )
                response = self._model.generate_content(
                    prompt,
                    generation_config=generation_config,
                )
                result = response.text.strip()
                logger.debug(f"Gemini 응답 수신 ({len(result)} chars)")
                return result

            except Exception as e:
                error_str = str(e)
                is_rate_limit = "429" in error_str or "quota" in error_str.lower()

                logger.warning(f"Gemini API 오류 (시도 {attempt}/{self._max_retries}): {e}")

                if attempt < self._max_retries:
                    if is_rate_limit:
                        # API가 알려주는 retry_delay를 정확히 준수
                        sleep_time = self._parse_retry_delay(error_str, fallback=self._retry_delay)
                        logger.info(f"Rate Limit 대기: {sleep_time:.1f}초 후 재시도...")
                    else:
                        sleep_time = self._retry_delay * (2 ** (attempt - 1))  # 지수 백오프
                        logger.info(f"{sleep_time:.1f}초 후 재시도...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"Gemini API 최대 재시도 초과: {e}")
                    raise

        return ""  # 도달 불가 (위에서 raise)

    def generate_json(self, prompt: str) -> str:
        """JSON 출력 전용 - JSON 코드 블록 자동 정리"""
        raw = self.generate(prompt, temperature=0.1)
        return self._clean_json_response(raw)

    def _clean_json_response(self, raw: str) -> str:
        """마크다운 코드 블록 등 불필요한 포맷 제거"""
        # ```json ... ``` 블록 추출
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
        if match:
            return match.group(1).strip()
        # 그냥 {} 또는 [] 로 시작하는 경우
        raw = raw.strip()
        if raw.startswith(("{", "[")):
            return raw
        # 마지막 수단: 첫 { 또는 [ 부터 끝까지 추출
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start_idx = raw.find(start_char)
            end_idx = raw.rfind(end_char)
            if start_idx != -1 and end_idx > start_idx:
                return raw[start_idx : end_idx + 1]
        return raw
