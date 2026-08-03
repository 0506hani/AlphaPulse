"""
AlphaPulse - 뉴스 그룹화 및 요약 분석기

1단계: 키워드 기반 그룹화 (순수 Python - scikit-learn 불필요)
       scikit-learn이 설치된 경우 TF-IDF + K-Means 클러스터링으로 자동 업그레이드
2단계: Gemini LLM으로 각 그룹의 주제명, 3~5줄 요약, 신뢰도 링크 생성
"""

from __future__ import annotations

import json
import math
import re
import time
from collections import Counter, defaultdict
from typing import List, Optional

from alphapulse.analyzers.base_llm import BaseLLM
from alphapulse.config import settings
from alphapulse.storage.models import NewsArticle, NewsGroup
from alphapulse.utils.logger import logger

# scikit-learn은 선택적 의존성 (없어도 동작)
try:
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer
    _SKLEARN_AVAILABLE = True
    logger.debug("scikit-learn 사용 가능 - TF-IDF 클러스터링 활성화")
except ImportError:
    _SKLEARN_AVAILABLE = False
    logger.info("scikit-learn 미설치 - 키워드 기반 클러스터링 사용")


# 신뢰도 기반 소스 우선순위
TRUSTED_SOURCES = [
    "reuters", "bloomberg", "bbc", "cnbc", "ft",
    "연합뉴스", "yna", "한국경제", "매일경제",
]

# 키워드 기반 클러스터링에 사용할 카테고리 시드
CATEGORY_KEYWORDS = {
    "금리·통화정책": ["rate", "fed", "연준", "금리", "기준금리", "fomc", "inflation", "인플레이션", "monetary"],
    "주식·증시": ["stock", "market", "nasdaq", "dow", "kospi", "코스피", "주가", "증시", "shares", "equity"],
    "반도체·AI·기술": ["semiconductor", "chip", "ai", "반도체", "nvidia", "삼성", "인공지능", "tech", "technology"],
    "부동산·건설": ["real estate", "housing", "부동산", "아파트", "건설", "property", "mortgage"],
    "에너지·원자재": ["oil", "energy", "crude", "natural gas", "에너지", "원유", "copper", "gold", "원자재"],
    "지정학·무역": ["trade", "tariff", "china", "war", "중국", "무역", "관세", "geopolit", "sanction"],
    "기업실적·M&A": ["earnings", "revenue", "profit", "merger", "acquisition", "실적", "매출", "영업이익"],
    "환율·외환": ["dollar", "won", "yen", "환율", "달러", "원화", "currency", "forex"],
    "경제지표": ["gdp", "cpi", "ppi", "employment", "고용", "실업", "경제성장", "소비자물가"],
}


def _trust_score(source: str) -> int:
    """소스명으로 신뢰도 점수 계산"""
    s = source.lower()
    for i, trusted in enumerate(TRUSTED_SOURCES):
        if trusted in s:
            return len(TRUSTED_SOURCES) - i
    return 0


def _tokenize(text: str) -> List[str]:
    """간단한 토크나이저 (한/영 혼합)"""
    text = text.lower()
    # 영어 단어 + 한글 2글자 이상 추출
    tokens = re.findall(r"[a-z]+|[\uAC00-\uD7A3]{2,}", text)
    return [t for t in tokens if len(t) >= 2]


def _compute_tfidf_simple(
    texts: List[str], num_features: int = 500
) -> List[dict]:
    """
    순수 Python TF-IDF 구현 (scikit-learn 대체).
    각 문서에 대해 {term: tfidf_score} 딕셔너리 반환.
    """
    n_docs = len(texts)
    tokenized = [_tokenize(t) for t in texts]

    # IDF 계산
    df: dict[str, int] = Counter()
    for tokens in tokenized:
        for term in set(tokens):
            df[term] += 1
    idf = {
        term: math.log((n_docs + 1) / (count + 1)) + 1
        for term, count in df.items()
    }

    # TF-IDF 벡터 계산
    doc_vectors = []
    for tokens in tokenized:
        tf = Counter(tokens)
        total = max(len(tokens), 1)
        vec = {
            term: (count / total) * idf.get(term, 1)
            for term, count in tf.items()
        }
        doc_vectors.append(vec)

    return doc_vectors


def _cosine_similarity_sparse(v1: dict, v2: dict) -> float:
    """희소 벡터 코사인 유사도"""
    common_terms = set(v1.keys()) & set(v2.keys())
    if not common_terms:
        return 0.0
    dot = sum(v1[t] * v2[t] for t in common_terms)
    norm1 = math.sqrt(sum(x * x for x in v1.values()))
    norm2 = math.sqrt(sum(x * x for x in v2.values()))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def _keyword_cluster(
    articles: List[NewsArticle], num_groups: int
) -> List[List[NewsArticle]]:
    """
    순수 Python 키워드 기반 클러스터링.
    각 기사를 CATEGORY_KEYWORDS와 매칭하여 그룹화.
    """
    groups: dict[str, List[NewsArticle]] = defaultdict(list)
    unmatched: List[NewsArticle] = []

    for article in articles:
        text = (article.title + " " + article.content[:300]).lower()
        best_category = None
        best_score = 0

        for category, keywords in CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > best_score:
                best_score = score
                best_category = category

        if best_category and best_score > 0:
            groups[best_category].append(article)
        else:
            unmatched.append(article)

    # 미분류 기사를 가장 작은 그룹에 분산 배치
    for i, article in enumerate(unmatched):
        min_group = min(groups.keys(), key=lambda k: len(groups[k])) if groups else "기타"
        if min_group:
            groups[min_group].append(article)
        else:
            groups["기타"].append(article)

    # 빈 그룹 제거, 크기 순 정렬, num_groups 제한
    non_empty = [(k, v) for k, v in groups.items() if v]
    non_empty.sort(key=lambda x: len(x[1]), reverse=True)
    result = [articles for _, articles in non_empty[:num_groups]]

    # 그룹 수가 너무 적으면 큰 그룹을 분할
    if len(result) < 2 and articles:
        mid = len(articles) // 2
        result = [articles[:mid], articles[mid:]]

    return result


def _sklearn_cluster(
    articles: List[NewsArticle], num_groups: int
) -> List[List[NewsArticle]]:
    """scikit-learn TF-IDF + K-Means 클러스터링"""
    texts = [f"{a.title} {a.content[:200]}" for a in articles]
    actual_k = min(num_groups, len(articles))

    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4),
        max_features=5000,
        min_df=1,
        sublinear_tf=True,
    )
    tfidf_matrix = vectorizer.fit_transform(texts)

    kmeans = KMeans(n_clusters=actual_k, random_state=42, n_init=10, max_iter=300)
    labels = kmeans.fit_predict(tfidf_matrix)

    clusters: dict[int, List[NewsArticle]] = {}
    for article, label in zip(articles, labels):
        clusters.setdefault(int(label), []).append(article)

    return [
        sorted(v, key=lambda a: (_trust_score(a.source), a.published_at), reverse=True)
        for v in sorted(clusters.values(), key=len, reverse=True)
    ]


class NewsGrouper:
    """뉴스 그룹화 및 AI 요약 분석기"""

    def __init__(self, llm: BaseLLM, num_groups: int | None = None):
        """
        Args:
            llm: 사용할 LLM 인스턴스
            num_groups: 생성할 그룹 수 (None이면 settings에서 로드)
        """
        self.llm = llm
        self.num_groups = num_groups or settings.num_groups
        self._use_sklearn = _SKLEARN_AVAILABLE

    def group_and_summarize(self, articles: List[NewsArticle]) -> List[NewsGroup]:
        """
        뉴스 기사를 그룹화하고 LLM으로 요약합니다.
        전체 그룹을 단 1회의 LLM 호었로 일괄 처리합니다 (API 호었 횟수 최소화).

        Args:
            articles: 중복 제거된 기사 목록

        Returns:
            요약이 완료된 NewsGroup 목록
        """
        if not articles:
            logger.warning("그룹화할 기사가 없습니다.")
            return []

        method = "TF-IDF(sklearn)" if self._use_sklearn else "키워드 기반"
        logger.info(
            f"뉴스 그룹화 시작: {len(articles)}개 기사 → {self.num_groups}개 그룹 목표 "
            f"[{method}]"
        )

        # 1단계: 클러스터링
        clustered_groups = self._cluster_articles(articles)
        logger.info(f"클러스터링 완료: {len(clustered_groups)}개 그룹 생성")

        # 2단계: LLM 일괄 요약 (1회 호었으로 전체 그룹 처리)
        logger.info(f"LLM 일괄 요약 시작 (단 1회 호었)...")
        news_groups = self._batch_summarize_all(clustered_groups)

        logger.info(f"그룹화 & 요약 완료: {len(news_groups)}개 그룹")
        return news_groups

    def _batch_summarize_all(self, clustered_groups: List[List[NewsArticle]]) -> List[NewsGroup]:
        """
        모든 그룹을 단 1회의 LLM 호었로 일괄 요약합니다.
        실패 시 개별 요약(_summarize_group)으로 폴백합니다.
        """
        # 각 그룹의 대표 기사 5개 + 메타데이터 준비
        groups_text_parts = []
        group_metadata = []

        for idx, cluster_articles in enumerate(clustered_groups):
            representative = cluster_articles[:5]
            articles_text = "\n".join(
                f"  [{i + 1}] 제목: {a.title[:80]} | 출처: {a.source}"
                for i, a in enumerate(representative)
            )
            groups_text_parts.append(
                f"### 그룹 {idx + 1} ({len(cluster_articles)}개 기사)\n{articles_text}"
            )
            top_articles = sorted(
                cluster_articles,
                key=lambda a: _trust_score(a.source),
                reverse=True,
            )[:2]
            group_metadata.append({
                "articles": cluster_articles,
                "top_links": [a.url for a in top_articles],
            })

        all_groups_text = "\n\n".join(groups_text_parts)
        n = len(clustered_groups)

        prompt = f"""당신은 전문 금융 뉴스 분석가입니다.
아래 {n}개의 뉴스 그룹을 각각 분석하여 요약해 주세요.

{all_groups_text}

위 {n}개 그룹을 분석하여 아래 JSON 배열 형식으로만 응답하세요.
JSON 외 다른 텍스트는 절대 포함하지 마세요. 배열 원소는 반드시 {n}개여야 합니다.

[
  {{
    "topic": "핵심 주제를 10~20자 이내로 명확하게",
    "summary": "핵심 내용을 3~5줄로 요약. 투자자에게 중요한 정보 위주.",
    "sentiment": "positive 또는 negative 또는 neutral 또는 mixed 중 하나"
  }},
  ... (전체 {n}개)
]"""

        try:
            raw_json = self.llm.generate_json(prompt)
            data_list = json.loads(raw_json)

            if not isinstance(data_list, list):
                raise ValueError(f"응답이 JSON 배열이 아닙니다: {type(data_list)}")

            news_groups = []
            for i, data in enumerate(data_list[:n]):
                meta = group_metadata[i]
                news_groups.append(NewsGroup(
                    topic=data.get("topic", f"주제 {i + 1}"),
                    summary=data.get("summary", ""),
                    articles=meta["articles"],
                    top_links=meta["top_links"],
                    sentiment=data.get("sentiment", "neutral"),
                ))

            logger.info(f"일괄 요약 성공: {len(news_groups)}/{n}개 그룹")
            return news_groups

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"일괄 요약 JSON 파싱 실패: {e} — 개별 요약으로 폴백")
            return self._fallback_individual_summarize(clustered_groups, group_metadata)
        except Exception as e:
            logger.error(f"일괄 요약 실패: {e} — 개별 요약으로 폴백")
            return self._fallback_individual_summarize(clustered_groups, group_metadata)

    def _fallback_individual_summarize(
        self,
        clustered_groups: List[List[NewsArticle]],
        group_metadata: Optional[List[dict]] = None,
    ) -> List[NewsGroup]:
        """
        일괄 요약 실패 시 개별 호었 폴백 (그룹 간 13초 간격).
        """
        RPM_INTERVAL = 13.0
        news_groups = []
        for idx, cluster_articles in enumerate(clustered_groups):
            logger.info(f"폴백 개별 요약 {idx + 1}/{len(clustered_groups)}...")
            group = self._summarize_group(cluster_articles)
            if group:
                news_groups.append(group)
            if idx < len(clustered_groups) - 1:
                logger.info(f"  Rate Limit 대기: {RPM_INTERVAL}초...")
                time.sleep(RPM_INTERVAL)
        return news_groups

    def _cluster_articles(self, articles: List[NewsArticle]) -> List[List[NewsArticle]]:
        """클러스터링 메서드 선택 및 실행"""
        try:
            if self._use_sklearn:
                return _sklearn_cluster(articles, self.num_groups)
            else:
                return _keyword_cluster(articles, self.num_groups)
        except Exception as e:
            logger.warning(f"클러스터링 실패, 키워드 기반으로 재시도: {e}")
            try:
                return _keyword_cluster(articles, self.num_groups)
            except Exception as e2:
                logger.warning(f"키워드 클러스터링도 실패, 균등 분할: {e2}")
                chunk_size = max(1, len(articles) // self.num_groups)
                return [
                    articles[i: i + chunk_size]
                    for i in range(0, len(articles), chunk_size)
                ][: self.num_groups]

    def _summarize_group(self, articles: List[NewsArticle]) -> Optional[NewsGroup]:
        """LLM으로 그룹 요약 생성"""
        if not articles:
            return None

        # 대표 기사 최대 8개만 LLM에 전달 (토큰 절약)
        representative = articles[:8]
        articles_text = "\n\n".join(
            f"[기사 {i + 1}] 출처: {a.source}\n제목: {a.title}\n내용: {a.content[:500]}\nURL: {a.url}"
            for i, a in enumerate(representative)
        )

        # 신뢰도 높은 링크 상위 2개 선정
        top_articles = sorted(articles, key=lambda a: _trust_score(a.source), reverse=True)[:2]
        top_links = [a.url for a in top_articles]

        prompt = f"""당신은 전문 금융 뉴스 분석가입니다.
아래 뉴스 기사들은 동일한 주제를 다루는 기사들입니다.

=== 기사 목록 ===
{articles_text}

위 기사들을 분석하여 아래 JSON 형식으로만 응답하세요. JSON 외 다른 텍스트는 절대 포함하지 마세요.

{{
  "topic": "핵심 주제를 10~20자 이내로 명확하게 작성",
  "summary": "핵심 내용을 3~5줄로 요약. 투자자에게 중요한 정보 위주로 작성.",
  "sentiment": "positive 또는 negative 또는 neutral 또는 mixed 중 하나"
}}"""

        try:
            raw_json = self.llm.generate_json(prompt)
            data = json.loads(raw_json)

            return NewsGroup(
                topic=data.get("topic", "주제 미분류"),
                summary=data.get("summary", ""),
                articles=articles,
                top_links=top_links,
                sentiment=data.get("sentiment", "neutral"),
            )

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"그룹 요약 JSON 파싱 실패: {e}")
            # 폴백: 첫 기사 제목을 주제로 사용
            return NewsGroup(
                topic=articles[0].title[:30] if articles else "뉴스 그룹",
                summary="요약 생성 실패 - 원문을 확인해 주세요.",
                articles=articles,
                top_links=top_links,
            )
        except Exception as e:
            logger.error(f"그룹 요약 실패: {e}")
            return None
