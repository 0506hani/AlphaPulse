"""
AlphaPulse - 뉴스 수집기 테스트
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from alphapulse.collectors.rss_collector import RSSCollector, _detect_language, _get_trust_score
from alphapulse.storage.models import NewsArticle
from alphapulse.utils.deduplicator import Deduplicator


# ─────────────────────────────────────────────────────────────────────
# RSS Collector Tests
# ─────────────────────────────────────────────────────────────────────

class TestRSSCollector:
    """RSS 수집기 단위 테스트"""

    def test_source_name(self):
        collector = RSSCollector(feed_urls=["https://example.com/rss"])
        assert collector.source_name == "RSS Feeds"

    def test_trust_score_reuters(self):
        score = _get_trust_score("Reuters")
        assert score >= 8

    def test_trust_score_unknown(self):
        score = _get_trust_score("Some Unknown Blog")
        assert score == 5

    def test_language_detection_korean_domain(self):
        lang = _detect_language("https://www.yna.co.kr/news/123", "연합뉴스 기사")
        assert lang == "ko"

    def test_language_detection_english(self):
        lang = _detect_language("https://www.reuters.com/news/123", "Fed raises rates")
        assert lang == "en"

    def test_language_detection_korean_title(self):
        lang = _detect_language("https://unknown.com/news", "삼성전자 주가 상승")
        assert lang == "ko"

    @patch("feedparser.parse")
    def test_collect_empty_feed(self, mock_parse):
        """빈 피드 수집 테스트"""
        mock_parse.return_value = MagicMock(
            entries=[],
            bozo=False,
            feed=MagicMock(title="Test Feed"),
        )
        collector = RSSCollector(feed_urls=["https://example.com/rss"])
        articles = collector.collect()
        assert isinstance(articles, list)

    @patch("feedparser.parse")
    def test_collect_filters_old_articles(self, mock_parse):
        """오래된 기사 필터링 테스트"""
        old_time = (
            datetime(2020, 1, 1, tzinfo=timezone.utc).timetuple()
        )
        mock_entry = MagicMock()
        mock_entry.title = "Old Article"
        mock_entry.link = "https://example.com/old"
        mock_entry.published_parsed = old_time
        mock_entry.summary = "Old content"

        mock_parse.return_value = MagicMock(
            entries=[mock_entry],
            bozo=False,
            feed=MagicMock(title="Test Feed"),
        )

        collector = RSSCollector(
            feed_urls=["https://example.com/rss"],
            max_age_hours=24,
        )
        articles = collector.collect()
        assert len(articles) == 0, "오래된 기사는 제외되어야 합니다"


# ─────────────────────────────────────────────────────────────────────
# Deduplicator Tests
# ─────────────────────────────────────────────────────────────────────

def make_article(title: str, url: str, source: str = "Test") -> NewsArticle:
    return NewsArticle(
        title=title,
        url=url,
        source=source,
        published_at=datetime.now(timezone.utc),
    )


class TestDeduplicator:
    """중복 제거기 단위 테스트"""

    def test_url_deduplication(self):
        articles = [
            make_article("Article A", "https://example.com/news/1"),
            make_article("Article A Copy", "https://example.com/news/1"),  # URL 중복 → 제거
            make_article("Article B", "https://example.com/news/2"),  # 다른 URL
            make_article("Article C", "https://example.com/news/3"),  # 다른 URL
        ]
        dedup = Deduplicator()
        result = dedup.deduplicate(articles)
        # URL 중복 1개 제거 → 3개 남음 (유사도 중복 제거 전)
        # 제목들이 다르므로 최종 3개
        assert len(result) == 3

    def test_url_trailing_slash_dedup(self):
        articles = [
            make_article("Article A", "https://example.com/news/1/"),
            make_article("Article A", "https://example.com/news/1"),  # 같은 URL
        ]
        dedup = Deduplicator()
        result = dedup.deduplicate(articles)
        assert len(result) == 1

    def test_similarity_deduplication(self):
        # 거의 동일한 제목의 기사 (어휘 반복 비율 높음)
        articles = [
            make_article("삼성전자 3분기 영업이익 사상 최대 기록", "https://a.com/1"),
            make_article("삼성전자 3분기 영업이익 사상 최대 기록 달성", "https://b.com/2"),  # 거의 동일
            make_article("현대차 전기차 수출 확대 발표", "https://c.com/3"),  # 다른 주제
        ]
        dedup = Deduplicator(similarity_threshold=0.75)
        result = dedup.deduplicate(articles)
        # 유사한 한국어 기사 2개 중 1개 제거 → 2개 남음
        assert len(result) <= 2

    def test_empty_input(self):
        dedup = Deduplicator()
        result = dedup.deduplicate([])
        assert result == []

    def test_single_article(self):
        articles = [make_article("Single Article", "https://example.com/1")]
        dedup = Deduplicator()
        result = dedup.deduplicate(articles)
        assert len(result) == 1
