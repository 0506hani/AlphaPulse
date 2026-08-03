"""
AlphaPulse - RSS 피드 뉴스 수집기

feedparser를 사용하여 설정된 RSS 피드에서 최신 뉴스를 수집합니다.
국내외 주요 금융/경제 미디어 RSS를 지원합니다.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import urlparse

import feedparser

from alphapulse.collectors.base_collector import BaseNewsCollector
from alphapulse.config import settings
from alphapulse.storage.models import NewsArticle
from alphapulse.utils.logger import logger


# 신뢰도 점수 기반 소스 우선순위 매핑
SOURCE_TRUST_SCORES: dict[str, int] = {
    "reuters": 10,
    "bbc": 9,
    "cnbc": 8,
    "bloomberg": 10,
    "연합뉴스": 10,
    "yna": 10,
    "한국경제": 9,
    "hankyung": 9,
    "매일경제": 9,
    "mk": 9,
    "yonhap": 10,
}


def _get_trust_score(source: str) -> int:
    """소스명 기반 신뢰도 점수 반환"""
    source_lower = source.lower()
    for key, score in SOURCE_TRUST_SCORES.items():
        if key in source_lower:
            return score
    return 5  # 기본 점수


def _detect_language(url: str, title: str) -> str:
    """URL 도메인과 제목으로 언어 추정"""
    korean_domains = ["yna.co.kr", "hankyung.com", "mk.co.kr", "chosun.com", "joongang.co.kr"]
    domain = urlparse(url).netloc.lower()
    for kd in korean_domains:
        if kd in domain:
            return "ko"
    # 한글 포함 여부로 판단
    if any("\uAC00" <= c <= "\uD7A3" for c in title):
        return "ko"
    return "en"


def _parse_date(entry) -> Optional[datetime]:
    """feedparser 엔트리에서 날짜 파싱"""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def _extract_content(entry) -> str:
    """피드 엔트리에서 본문 텍스트 추출"""
    # content 필드 우선
    if hasattr(entry, "content") and entry.content:
        return entry.content[0].get("value", "")[:2000]
    # summary 필드 차선
    summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
    return summary[:2000]


class RSSCollector(BaseNewsCollector):
    """RSS 피드 기반 뉴스 수집기"""

    def __init__(
        self,
        feed_urls: Optional[List[str]] = None,
        max_age_hours: Optional[int] = None,
        max_per_feed: int = 50,
        request_timeout: int = 15,
    ):
        """
        Args:
            feed_urls: RSS 피드 URL 목록 (None이면 settings에서 로드)
            max_age_hours: 이 시간보다 오래된 기사 제외 (None이면 settings에서 로드)
            max_per_feed: 피드당 최대 수집 기사 수
            request_timeout: HTTP 요청 타임아웃 (초)
        """
        self.feed_urls = feed_urls or settings.rss_feed_list
        self.max_age_hours = max_age_hours or settings.max_article_age_hours
        self.max_per_feed = max_per_feed
        self.request_timeout = request_timeout
        self._cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.max_age_hours)

    @property
    def source_name(self) -> str:
        return "RSS Feeds"

    def collect(self) -> List[NewsArticle]:
        """모든 RSS 피드에서 뉴스 수집"""
        all_articles: List[NewsArticle] = []
        logger.info(f"RSS 수집 시작: {len(self.feed_urls)}개 피드")

        for feed_url in self.feed_urls:
            try:
                articles = self._collect_from_feed(feed_url)
                all_articles.extend(articles)
                logger.debug(f"[{feed_url}] {len(articles)}개 수집")
                time.sleep(0.3)  # 서버 부하 방지
            except Exception as e:
                logger.warning(f"피드 수집 실패 [{feed_url}]: {e}")

        logger.info(f"RSS 수집 완료: 총 {len(all_articles)}개")
        return all_articles

    def _collect_from_feed(self, feed_url: str) -> List[NewsArticle]:
        """단일 RSS 피드에서 기사 수집"""
        # feedparser로 피드 파싱
        feed = feedparser.parse(
            feed_url,
            agent="AlphaPulse/1.0 (Investment Analysis Bot)",
            request_headers={"Accept-Language": "ko,en;q=0.9"},
        )

        if feed.bozo and not feed.entries:
            raise ValueError(f"피드 파싱 실패: {getattr(feed, 'bozo_exception', 'unknown')}")

        source_name = getattr(feed.feed, "title", urlparse(feed_url).netloc)
        articles = []

        for entry in feed.entries[: self.max_per_feed]:
            article = self._parse_entry(entry, source_name, feed_url)
            if article:
                articles.append(article)

        return articles

    def _parse_entry(
        self, entry, source_name: str, feed_url: str
    ) -> Optional[NewsArticle]:
        """RSS 엔트리 → NewsArticle 변환"""
        title = getattr(entry, "title", "").strip()
        url = getattr(entry, "link", "").strip()

        if not title or not url:
            return None

        # 날짜 파싱 및 나이 필터링
        published_at = _parse_date(entry)
        if published_at is None:
            published_at = datetime.now(timezone.utc)  # 날짜 없으면 현재 시각

        if published_at < self._cutoff_time:
            return None  # 너무 오래된 기사 제외

        content = _extract_content(entry)
        language = _detect_language(url, title)

        # 결정론적 ID (같은 URL은 항상 같은 ID)
        article_id = hashlib.md5(url.encode()).hexdigest()

        return NewsArticle(
            id=article_id,
            title=title,
            content=content,
            url=url,
            source=source_name,
            published_at=published_at,
            language=language,
        )
