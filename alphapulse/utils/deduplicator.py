"""
AlphaPulse - 뉴스 중복 제거 유틸리티

URL 기반 정확 중복 제거 + 코사인 유사도 기반 유사 기사 제거.
scikit-learn이 설치된 경우 TF-IDF 벡터 사용, 없으면 순수 Python 구현 사용.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import List

from alphapulse.storage.models import NewsArticle
from alphapulse.utils.logger import logger

# scikit-learn은 선택적 의존성
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False


def _tokenize(text: str) -> List[str]:
    """한/영 혼합 간단 토크나이저"""
    text = text.lower()
    tokens = re.findall(r"[a-z]+|[\uAC00-\uD7A3]{2,}", text)
    return [t for t in tokens if len(t) >= 2]


def _cosine_sim_pure(a: str, b: str) -> float:
    """순수 Python 코사인 유사도 계산"""
    tokens_a = Counter(_tokenize(a))
    tokens_b = Counter(_tokenize(b))
    common = set(tokens_a.keys()) & set(tokens_b.keys())
    if not common:
        return 0.0
    dot = sum(tokens_a[t] * tokens_b[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in tokens_a.values()))
    norm_b = math.sqrt(sum(v * v for v in tokens_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class Deduplicator:
    """뉴스 기사 중복 제거기"""

    def __init__(self, similarity_threshold: float = 0.80):
        """
        Args:
            similarity_threshold: 이 값 이상이면 중복으로 판단 (0~1)
        """
        self.similarity_threshold = similarity_threshold

    def deduplicate(self, articles: List[NewsArticle]) -> List[NewsArticle]:
        """
        중복 제거 파이프라인:
        1단계: URL 정확 중복 제거
        2단계: 제목 유사도 기반 중복 제거

        Args:
            articles: 원본 기사 목록

        Returns:
            중복 제거된 기사 목록
        """
        if not articles:
            return []

        before_count = len(articles)

        # 1단계: URL 중복 제거
        unique_by_url = self._dedup_by_url(articles)
        logger.debug(f"URL 중복 제거: {before_count} → {len(unique_by_url)}개")

        # 2단계: 제목 유사도 중복 제거
        unique_final = self._dedup_by_similarity(unique_by_url)
        logger.info(
            f"중복 제거 완료: {before_count}개 → {len(unique_final)}개 "
            f"({before_count - len(unique_final)}개 제거)"
        )

        return unique_final

    def _dedup_by_url(self, articles: List[NewsArticle]) -> List[NewsArticle]:
        """URL 기반 정확 중복 제거"""
        seen_urls: set[str] = set()
        unique = []
        for article in articles:
            normalized_url = article.url.rstrip("/").split("?")[0]
            if normalized_url not in seen_urls:
                seen_urls.add(normalized_url)
                unique.append(article)
        return unique

    def _dedup_by_similarity(self, articles: List[NewsArticle]) -> List[NewsArticle]:
        """유사도 기반 중복 제거 (sklearn 있으면 TF-IDF, 없으면 순수 Python)"""
        if len(articles) <= 1:
            return articles

        if _SKLEARN_AVAILABLE:
            return self._dedup_sklearn(articles)
        else:
            return self._dedup_pure_python(articles)

    def _dedup_sklearn(self, articles: List[NewsArticle]) -> List[NewsArticle]:
        """scikit-learn TF-IDF 기반 중복 제거"""
        titles = [a.title for a in articles]
        try:
            vectorizer = TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(2, 4),
                max_features=5000,
                min_df=1,
            )
            tfidf_matrix = vectorizer.fit_transform(titles)
            similarity_matrix = sklearn_cosine(tfidf_matrix)
        except Exception as e:
            logger.warning(f"TF-IDF 유사도 계산 실패, 순수 Python으로 폴백: {e}")
            return self._dedup_pure_python(articles)

        removed: set[int] = set()
        for i in range(len(articles)):
            if i in removed:
                continue
            for j in range(i + 1, len(articles)):
                if j not in removed and similarity_matrix[i, j] >= self.similarity_threshold:
                    removed.add(j)

        return [a for idx, a in enumerate(articles) if idx not in removed]

    def _dedup_pure_python(self, articles: List[NewsArticle]) -> List[NewsArticle]:
        """순수 Python 코사인 유사도 기반 중복 제거 (O(n²), 소규모에 적합)"""
        # 기사 수가 너무 많으면 비효율적이므로 제한
        max_compare = min(len(articles), 300)
        articles_to_check = articles[:max_compare]
        rest = articles[max_compare:]

        removed: set[int] = set()
        for i in range(len(articles_to_check)):
            if i in removed:
                continue
            for j in range(i + 1, len(articles_to_check)):
                if j in removed:
                    continue
                sim = _cosine_sim_pure(articles_to_check[i].title, articles_to_check[j].title)
                if sim >= self.similarity_threshold:
                    removed.add(j)

        unique = [a for idx, a in enumerate(articles_to_check) if idx not in removed]
        return unique + rest
