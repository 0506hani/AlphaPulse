"""
AlphaPulse - AI 분석기 테스트
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from alphapulse.analyzers.news_grouper import NewsGrouper, _trust_score
from alphapulse.analyzers.stock_analyzer import StockAnalyzer
from alphapulse.storage.models import NewsArticle, NewsGroup, StockRecommend


def make_article(title: str, source: str = "Reuters", url: str = "https://reuters.com/1") -> NewsArticle:
    return NewsArticle(
        title=title,
        content=title + " - 상세 내용",
        url=url,
        source=source,
        published_at=datetime.now(timezone.utc),
    )


def make_mock_llm(json_response: dict) -> MagicMock:
    """LLM Mock 생성"""
    mock_llm = MagicMock()
    mock_llm.generate_json.return_value = json.dumps(json_response, ensure_ascii=False)
    mock_llm.provider_name = "Mock LLM"
    return mock_llm


class TestNewsGrouper:
    """뉴스 그룹화기 테스트"""

    def test_trust_score_reuters(self):
        assert _trust_score("Reuters") > _trust_score("Unknown Blog")

    def test_group_and_summarize_empty(self):
        mock_llm = make_mock_llm({})
        grouper = NewsGrouper(llm=mock_llm, num_groups=3)
        result = grouper.group_and_summarize([])
        assert result == []

    def test_group_and_summarize_success(self):
        """정상 그룹화 테스트"""
        articles = [
            make_article(f"Fed rate hike news {i}", url=f"https://reuters.com/{i}")
            for i in range(10)
        ] + [
            make_article(f"삼성전자 실적 뉴스 {i}", source="연합뉴스", url=f"https://yna.co.kr/{i}")
            for i in range(10)
        ]

        mock_response = {
            "topic": "연준 금리 인상",
            "summary": "연준이 금리를 0.25%p 인상했습니다.",
            "sentiment": "negative",
        }
        mock_llm = make_mock_llm(mock_response)

        grouper = NewsGrouper(llm=mock_llm, num_groups=3)
        groups = grouper.group_and_summarize(articles)

        assert len(groups) > 0
        assert all(isinstance(g, NewsGroup) for g in groups)
        assert all(g.topic for g in groups)

    def test_summarize_group_json_fallback(self):
        """LLM JSON 파싱 실패 시 폴백 테스트"""
        mock_llm = MagicMock()
        mock_llm.generate_json.return_value = "Invalid JSON {{{"
        mock_llm.provider_name = "Mock LLM"

        articles = [make_article("Test article", url="https://test.com/1")]
        grouper = NewsGrouper(llm=mock_llm, num_groups=1)
        # 폴백: 예외 없이 NewsGroup 반환되어야 함
        group = grouper._summarize_group(articles)
        assert group is not None


class TestStockAnalyzer:
    """종목 분석기 테스트"""

    def _make_group(self, topic: str = "테스트 주제") -> NewsGroup:
        return NewsGroup(
            topic=topic,
            summary="테스트 요약 내용입니다.",
            articles=[make_article("Test", url="https://test.com/1")],
        )

    def test_analyze_groups_success(self):
        """정상 종목 분석 테스트"""
        mock_response = {
            "beneficiary_sectors": ["반도체", "IT"],
            "beneficiary_reason": "금리 인하로 성장주 수혜",
            "harmed_sectors": ["은행"],
            "harmed_reason": "금리 인하로 이자 마진 감소",
            "korean_stocks": [
                {"ticker": "005930", "name": "삼성전자", "reason": "반도체 수요 증가 수혜"},
            ],
            "us_stocks": [
                {"ticker": "NVDA", "name": "NVIDIA", "reason": "AI 반도체 수요 지속"},
            ],
        }
        mock_llm = make_mock_llm(mock_response)
        analyzer = StockAnalyzer(llm=mock_llm, request_interval=0)

        group = self._make_group()
        result = analyzer.analyze_groups([group])

        assert len(result) == 1
        assert "반도체" in result[0].beneficiary_sectors
        assert len(result[0].korean_stocks) == 1
        assert result[0].korean_stocks[0].ticker == "005930"
        assert result[0].us_stocks[0].ticker == "NVDA"

    def test_analyze_groups_json_error_preserved(self):
        """분석 실패 시 원본 그룹 보존 테스트"""
        mock_llm = MagicMock()
        mock_llm.generate_json.return_value = "INVALID"
        mock_llm.provider_name = "Mock LLM"

        analyzer = StockAnalyzer(llm=mock_llm, request_interval=0)
        group = self._make_group("원본 주제")
        result = analyzer.analyze_groups([group])

        assert len(result) == 1
        assert result[0].topic == "원본 주제"

    def test_stock_recommend_model(self):
        """StockRecommend 모델 생성 테스트"""
        stock = StockRecommend(
            ticker="005930",
            name="삼성전자",
            market="KR",
            reason="반도체 수요 증가",
        )
        assert stock.ticker == "005930"
        assert stock.market == "KR"
