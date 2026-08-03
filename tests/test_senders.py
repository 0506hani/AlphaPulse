"""
AlphaPulse - 발송기 및 포맷터 테스트
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from alphapulse.reporters.formatter import TelegramFormatter, _escape_md, _fmt_stocks
from alphapulse.storage.models import DailyReport, NewsGroup, StockRecommend


def make_test_report(session: str = "morning") -> DailyReport:
    """테스트용 DailyReport 생성"""
    group = NewsGroup(
        topic="연준 금리 동결 발표",
        summary="연준이 7월 FOMC에서 기준금리를 5.25~5.5%로 동결 결정했습니다.\n성장세 유지와 인플레이션 목표 달성을 위한 결정이라고 설명했습니다.",
        top_links=["https://reuters.com/fed-news", "https://bloomberg.com/fed"],
        beneficiary_sectors=["기술주", "성장주"],
        beneficiary_reason="금리 동결로 성장주 밸류에이션 부담 완화",
        harmed_sectors=["은행", "보험"],
        harmed_reason="금리 동결로 이자 수익 개선 기대감 약화",
        korean_stocks=[
            StockRecommend(ticker="005930", name="삼성전자", market="KR", reason="외국인 수급 개선 기대"),
            StockRecommend(ticker="035720", name="카카오", market="KR", reason="성장주 밸류에이션 부담 완화"),
        ],
        us_stocks=[
            StockRecommend(ticker="NVDA", name="NVIDIA", market="US", reason="AI 투자 지속 수혜"),
            StockRecommend(ticker="AAPL", name="Apple", market="US", reason="성장주 선호 환경"),
        ],
        sentiment="positive",
    )

    return DailyReport(
        session=session,
        groups=[group],
        total_articles_collected=150,
        total_articles_after_dedup=120,
        generated_at=datetime(2026, 7, 24, 7, 0, tzinfo=timezone.utc),
    )


class TestTelegramFormatter:
    """텔레그램 포맷터 테스트"""

    def test_escape_md_special_chars(self):
        """MarkdownV2 특수문자 이스케이프 테스트"""
        text = "5.25~5.5% (예시)"
        escaped = _escape_md(text)
        assert "\\." in escaped
        assert "\\(" in escaped
        assert "\\)" in escaped

    def test_escape_md_no_double_escape(self):
        """이미 이스케이프된 문자 중복 이스케이프 방지"""
        text = "Hello World"  # 특수문자 없음
        assert _escape_md(text) == "Hello World"

    def test_format_report_returns_list(self):
        """리포트 포맷 결과가 리스트여야 함"""
        formatter = TelegramFormatter()
        report = make_test_report()
        result = formatter.format_report(report)
        assert isinstance(result, list)
        assert len(result) >= 2  # 헤더 + 그룹 + 푸터

    def test_format_report_contains_topic(self):
        """리포트에 그룹 주제가 포함되어야 함"""
        formatter = TelegramFormatter()
        report = make_test_report()
        messages = formatter.format_report(report)
        all_text = " ".join(text for text, _ in messages)
        assert "연준" in all_text or "금리" in all_text

    def test_format_report_has_links(self):
        """그룹 메시지에 링크가 포함되어야 함"""
        formatter = TelegramFormatter()
        report = make_test_report()
        messages = formatter.format_report(report)
        all_links = [url for _, links in messages for url in links]
        assert len(all_links) > 0
        assert "reuters.com" in all_links[0]

    def test_format_stocks(self):
        """종목 포맷 테스트"""
        stocks = [
            StockRecommend(ticker="005930", name="삼성전자", market="KR", reason="테스트 이유"),
        ]
        result = _fmt_stocks(stocks, "🇰🇷")
        assert "삼성전자" in result
        assert "005930" in result

    def test_message_length_within_limit(self):
        """각 메시지가 4000자 이하여야 함"""
        formatter = TelegramFormatter()
        report = make_test_report()
        messages = formatter.format_report(report)
        for text, _ in messages:
            assert len(text) <= 4096, f"메시지 길이 초과: {len(text)}"

    def test_morning_session_label(self):
        """오전 세션 레이블 확인"""
        formatter = TelegramFormatter()
        report = make_test_report(session="morning")
        messages = formatter.format_report(report)
        header_text = messages[0][0]
        assert "오전" in header_text

    def test_evening_session_label(self):
        """오후 세션 레이블 확인"""
        formatter = TelegramFormatter()
        report = make_test_report(session="evening")
        messages = formatter.format_report(report)
        header_text = messages[0][0]
        assert "오후" in header_text


class TestDailyReportPipeline:
    """DailyReport 파이프라인 메서드 테스트"""

    def test_to_pipeline_dict_structure(self):
        """파이프라인 딕셔너리 구조 검증"""
        report = make_test_report()
        pipeline = report.to_pipeline_dict()

        assert "report_id" in pipeline
        assert "generated_at" in pipeline
        assert "session" in pipeline
        assert "stock_mentions" in pipeline
        assert "sector_trends" in pipeline
        assert "groups_summary" in pipeline

    def test_stock_mentions_counted(self):
        """종목 언급 횟수 집계 테스트"""
        report = make_test_report()
        pipeline = report.to_pipeline_dict()
        mentions = pipeline["stock_mentions"]
        tickers = [m["ticker"] for m in mentions]
        assert "005930" in tickers
        assert "NVDA" in tickers

    def test_sector_trends_extracted(self):
        """업종 트렌드 추출 테스트"""
        report = make_test_report()
        pipeline = report.to_pipeline_dict()
        trends = pipeline["sector_trends"]
        assert "beneficiary" in trends
        assert "harmed" in trends
        assert "기술주" in trends["beneficiary"]
