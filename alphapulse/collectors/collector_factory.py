"""
AlphaPulse - 수집기 팩토리

설정에 따라 사용할 수집기 조합을 반환합니다.
향후 NewsAPI, 증권사 API 수집기 추가 시 이 파일만 수정하면 됩니다.
"""

from __future__ import annotations

from typing import List

from alphapulse.collectors.base_collector import BaseNewsCollector
from alphapulse.collectors.rss_collector import RSSCollector
from alphapulse.config import settings


def get_collectors() -> List[BaseNewsCollector]:
    """
    활성화된 수집기 목록 반환.

    현재 지원:
    - RSSCollector (기본 활성화)

    향후 추가 예정:
    - NewsAPICollector (NEWSAPI_KEY 설정 시 자동 활성화)
    - KRXCollector (한국거래소 데이터)
    """
    collectors: List[BaseNewsCollector] = []

    # RSS 수집기는 항상 활성화
    collectors.append(
        RSSCollector(
            feed_urls=settings.rss_feed_list,
            max_age_hours=settings.max_article_age_hours,
        )
    )

    return collectors
