"""
AlphaPulse - 종목 영향 분석기

각 뉴스 그룹에 대해 LLM을 통해:
- 수혜 업종 / 피해 업종 및 이유
- 관련 국내 종목 3~5개 (코스피/코스닥)
- 관련 미국 종목 3~5개 (NYSE/NASDAQ)
를 분석합니다.
"""

from __future__ import annotations

import json
import time
from typing import List

from alphapulse.analyzers.base_llm import BaseLLM
from alphapulse.storage.models import NewsGroup, StockRecommend
from alphapulse.utils.logger import logger


class StockAnalyzer:
    """종목 영향 분석기 - LLM 학습 지식 기반"""

    def __init__(self, llm: BaseLLM, request_interval: float = 13.0):
        """
        Args:
            llm: 사용할 LLM 인스턴스
            request_interval: LLM API 호출 간격 (초) - Rate Limit 방지
        """
        self.llm = llm
        self.request_interval = request_interval

    def analyze_groups(self, groups: List[NewsGroup]) -> List[NewsGroup]:
        """
        모든 뉴스 그룹에 대해 단 1회의 LLM 호었로 일괄 종목 영향 분석을 수행합니다.

        Args:
            groups: 요약이 완료된 NewsGroup 목록

        Returns:
            종목 분석이 추가된 NewsGroup 목록
        """
        logger.info(f"종목 분석 시작 (일괄 처리): {len(groups)}개 그룹")
        return self._batch_analyze_all(groups)

    def _batch_analyze_all(self, groups: List[NewsGroup]) -> List[NewsGroup]:
        """
        모든 그룹을 단 1회의 LLM 호었로 일괄 종목 분석합니다.
        실패 시 개별 분석(_analyze_single_group)으로 폴백합니다.
        """
        topics_text = "\n\n".join(
            f"{i + 1}. 주제: {g.topic}\n   요약: {g.summary[:200]}"
            for i, g in enumerate(groups)
        )
        n = len(groups)

        prompt = f"""당신은 한국 및 미국 주식시장 전문 애널리스트입니다.
아래 {n}개의 뉴스 주제를 각각 분석하여 투자 영향을 말해주세요.

{topics_text}

분석 지침:
- 수혜/피해 업종: 각 2~4개
- 국내 종목: 코스피/코스닥 3~5개, 실제 존재 종목만
- 미국 종목: NYSE/NASDAQ 3~5개, 실제 존재 종목만
- ticker: 한국은 6자리 숫자(005930), 미국은 알파벳 심볼(NVDA)
- reason: 30자 이내 간결한 1줄

아래 JSON 배열 형식으로만 응답하세요. JSON 외 다른 텍스트는 절대 포함하지 마세요. 배열 원소는 반드시 {n}개여야 합니다.

[
  {{
    "beneficiary_sectors": ["업쉘1", "업쉘2"],
    "beneficiary_reason": "수혜 이유 1~2줄",
    "harmed_sectors": ["업쉘1", "업쉘2"],
    "harmed_reason": "피해 이유 1~2줄",
    "korean_stocks": [
      {{"ticker": "005930", "name": "삼성전자", "reason": "선택 이유"}}
    ],
    "us_stocks": [
      {{"ticker": "NVDA", "name": "NVIDIA", "reason": "선택 이유"}}
    ]
  }},
  ... (전체 {n}개)
]"""

        try:
            raw_json = self.llm.generate_json(prompt)
            data_list = json.loads(raw_json)

            if not isinstance(data_list, list):
                raise ValueError(f"응답이 JSON 배열이 아닙니다: {type(data_list)}")

            analyzed_groups = []
            for group, data in zip(groups, data_list):
                group.beneficiary_sectors = data.get("beneficiary_sectors", [])
                group.beneficiary_reason = data.get("beneficiary_reason", "")
                group.harmed_sectors = data.get("harmed_sectors", [])
                group.harmed_reason = data.get("harmed_reason", "")
                group.korean_stocks = [
                    StockRecommend(
                        ticker=s.get("ticker", ""),
                        name=s.get("name", ""),
                        market="KR",
                        reason=s.get("reason", ""),
                    )
                    for s in data.get("korean_stocks", [])[:5]
                    if s.get("ticker") and s.get("name")
                ]
                group.us_stocks = [
                    StockRecommend(
                        ticker=s.get("ticker", ""),
                        name=s.get("name", ""),
                        market="US",
                        reason=s.get("reason", ""),
                    )
                    for s in data.get("us_stocks", [])[:5]
                    if s.get("ticker") and s.get("name")
                ]
                analyzed_groups.append(group)

            logger.info(f"일괄 종목 분석 성공: {len(analyzed_groups)}개 그룹")
            return analyzed_groups

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"일괄 종목 분석 JSON 파싱 실패: {e} — 개별 분석으로 폴백")
            return self._fallback_individual_analyze(groups)
        except Exception as e:
            logger.error(f"일괄 종목 분석 실패: {e} — 개별 분석으로 폴백")
            return self._fallback_individual_analyze(groups)

    def _fallback_individual_analyze(self, groups: List[NewsGroup]) -> List[NewsGroup]:
        """
        일괄 분석 실패 시 개별 호었 폴백 (그룹 간 13초 간격).
        """
        analyzed_groups = []
        for idx, group in enumerate(groups):
            logger.info(f"폴백 개별 종목 분석 {idx + 1}/{len(groups)}: {group.topic}")
            try:
                enriched_group = self._analyze_single_group(group)
                analyzed_groups.append(enriched_group)
            except Exception as e:
                logger.error(f"그룹 '{group.topic}' 종목 분석 실패: {e}")
                analyzed_groups.append(group)
            if idx < len(groups) - 1:
                time.sleep(self.request_interval)
        logger.info(f"폴백 종목 분석 완료: {len(analyzed_groups)}개 그룹")
        return analyzed_groups

    def _analyze_single_group(self, group: NewsGroup) -> NewsGroup:
        """단일 뉴스 그룹 종목 분석"""
        prompt = f"""당신은 한국 및 미국 주식시장 전문 애널리스트입니다.
아래 뉴스 주제와 요약을 바탕으로 투자 영향을 분석해 주세요.

=== 뉴스 주제 ===
주제: {group.topic}

=== 핵심 요약 ===
{group.summary}

=== 분석 지침 ===
- 수혜/피해 업종은 각 2~4개, 이유는 간결하고 구체적으로
- 국내 종목: 코스피/코스닥 상장 종목 3~5개, 실제 존재하는 종목만 제시
- 미국 종목: NYSE/NASDAQ 상장 종목 3~5개, 실제 존재하는 종목만 제시
- ticker는 한국 종목의 경우 6자리 숫자(예: 005930), 미국은 알파벳 심볼(예: NVDA)
- reason은 30자 이내 간결한 1줄

아래 JSON 형식으로만 응답하세요. JSON 외 다른 텍스트는 절대 포함하지 마세요.

{{
  "beneficiary_sectors": ["업종1", "업종2"],
  "beneficiary_reason": "수혜 업종들이 이 뉴스에서 수혜를 받는 이유 (1~2줄)",
  "harmed_sectors": ["업종1", "업종2"],
  "harmed_reason": "피해 업종들이 이 뉴스에서 피해를 받는 이유 (1~2줄)",
  "korean_stocks": [
    {{"ticker": "005930", "name": "삼성전자", "reason": "선택 이유 1줄"}},
    {{"ticker": "000660", "name": "SK하이닉스", "reason": "선택 이유 1줄"}}
  ],
  "us_stocks": [
    {{"ticker": "NVDA", "name": "NVIDIA", "reason": "선택 이유 1줄"}},
    {{"ticker": "AAPL", "name": "Apple", "reason": "선택 이유 1줄"}}
  ]
}}"""

        try:
            raw_json = self.llm.generate_json(prompt)
            data = json.loads(raw_json)

            # 국내 종목 파싱
            korean_stocks = [
                StockRecommend(
                    ticker=s.get("ticker", ""),
                    name=s.get("name", ""),
                    market="KR",
                    reason=s.get("reason", ""),
                )
                for s in data.get("korean_stocks", [])
                if s.get("ticker") and s.get("name")
            ]

            # 미국 종목 파싱
            us_stocks = [
                StockRecommend(
                    ticker=s.get("ticker", ""),
                    name=s.get("name", ""),
                    market="US",
                    reason=s.get("reason", ""),
                )
                for s in data.get("us_stocks", [])
                if s.get("ticker") and s.get("name")
            ]

            # NewsGroup에 분석 결과 추가
            group.beneficiary_sectors = data.get("beneficiary_sectors", [])
            group.beneficiary_reason = data.get("beneficiary_reason", "")
            group.harmed_sectors = data.get("harmed_sectors", [])
            group.harmed_reason = data.get("harmed_reason", "")
            group.korean_stocks = korean_stocks[:5]
            group.us_stocks = us_stocks[:5]

            return group

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"종목 분석 JSON 파싱 실패 [{group.topic}]: {e}")
            return group
        except Exception as e:
            logger.error(f"종목 분석 예외 [{group.topic}]: {e}")
            return group
