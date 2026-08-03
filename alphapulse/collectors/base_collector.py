"""
AlphaPulse - 뉴스 수집기 추상 인터페이스

모든 뉴스 수집기는 이 클래스를 상속하여 구현합니다.
새로운 수집 소스(NewsAPI, Twitter, 증권사 API 등)를 추가할 때
이 인터페이스를 구현하기만 하면 파이프라인에 바로 연결됩니다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from alphapulse.storage.models import NewsArticle


class BaseNewsCollector(ABC):
    """뉴스 수집기 추상 기반 클래스"""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """수집기 이름 (로깅/식별용)"""
        ...

    @abstractmethod
    def collect(self) -> List[NewsArticle]:
        """
        뉴스 기사를 수집하여 반환합니다.

        Returns:
            수집된 NewsArticle 목록
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(source={self.source_name})"
