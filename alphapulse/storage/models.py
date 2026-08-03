"""
AlphaPulse - 핵심 데이터 모델 정의

Pydantic 기반으로 타입 안전한 데이터 구조를 정의합니다.
AlphaFuture, AlphaTrader 등 향후 모듈과의 파이프라인 연동을 위한
공통 스키마 역할을 합니다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field
import pytz

def kst_now() -> datetime:
    return datetime.now(pytz.timezone('Asia/Seoul'))


def generate_id() -> str:
    """UUID 기반 고유 ID 생성"""
    return str(uuid.uuid4())


class NewsArticle(BaseModel):
    """개별 뉴스 기사 모델"""

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()}
    )

    id: str = Field(default_factory=generate_id)
    title: str
    content: str = ""           # 기사 본문 요약 또는 전문
    url: str
    source: str                 # 출처 이름 (예: Reuters, 연합뉴스)
    published_at: datetime
    language: str = "unknown"   # 언어 코드 (ko, en 등)
    category: Optional[str] = None  # 수집 시점 카테고리


class StockRecommend(BaseModel):
    """종목 추천 모델"""

    ticker: str                 # 티커 심볼 (예: 005930, NVDA)
    name: str                   # 종목명 (예: 삼성전자, NVIDIA)
    market: str                 # 시장 구분 (KR, US)
    reason: str                 # 1줄 선택 이유


class NewsGroup(BaseModel):
    """그룹화된 뉴스 주제 모델 - AlphaFuture/AlphaTrader 연동 핵심 단위"""

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()}
    )

    group_id: str = Field(default_factory=generate_id)
    topic: str                              # 핵심 주제명
    summary: str                            # 3~5줄 요약
    articles: List[NewsArticle] = Field(default_factory=list)
    top_links: List[str] = Field(default_factory=list)     # 신뢰도 높은 원본 링크 1~2개
    beneficiary_sectors: List[str] = Field(default_factory=list)  # 수혜 업종
    harmed_sectors: List[str] = Field(default_factory=list)       # 피해 업종
    beneficiary_reason: str = ""            # 수혜 업종 이유
    harmed_reason: str = ""                 # 피해 업종 이유
    korean_stocks: List[StockRecommend] = Field(default_factory=list)  # 국내 종목 3~5개
    us_stocks: List[StockRecommend] = Field(default_factory=list)      # 미국 종목 3~5개
    sentiment: str = "neutral"              # positive | negative | neutral | mixed


class DailyReport(BaseModel):
    """일일 리포트 최상위 모델 - JSON/DB 저장 단위"""

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()}
    )

    report_id: str = Field(default_factory=generate_id)
    generated_at: datetime = Field(default_factory=kst_now)
    session: str                    # "morning" | "evening"
    groups: List[NewsGroup] = Field(default_factory=list)
    total_articles_collected: int = 0
    total_articles_after_dedup: int = 0
    status: str = "success"        # success | partial | failed
    error_message: Optional[str] = None

    def to_pipeline_dict(self) -> dict:
        """
        AlphaFuture, AlphaTrader 연동용 파이프라인 딕셔너리 반환.
        향후 모듈이 이 형식으로 데이터를 조회합니다.
        """
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at.isoformat(),
            "session": self.session,
            "stock_mentions": self._extract_stock_mentions(),
            "sector_trends": self._extract_sector_trends(),
            "groups_summary": [
                {
                    "topic": g.topic,
                    "sentiment": g.sentiment,
                    "korean_tickers": [s.ticker for s in g.korean_stocks],
                    "us_tickers": [s.ticker for s in g.us_stocks],
                }
                for g in self.groups
            ],
        }

    def _extract_stock_mentions(self) -> list:
        """전체 리포트에서 언급된 종목 추출 (중복 카운팅 포함)"""
        mentions = {}
        for group in self.groups:
            for stock in group.korean_stocks + group.us_stocks:
                key = stock.ticker
                if key not in mentions:
                    mentions[key] = {
                        "ticker": stock.ticker,
                        "name": stock.name,
                        "market": stock.market,
                        "count": 0,
                        "reasons": [],
                    }
                mentions[key]["count"] += 1
                mentions[key]["reasons"].append(stock.reason)
        return sorted(mentions.values(), key=lambda x: x["count"], reverse=True)

    def _extract_sector_trends(self) -> dict:
        """수혜/피해 업종 트렌드 추출"""
        beneficiary = {}
        harmed = {}
        for group in self.groups:
            for sector in group.beneficiary_sectors:
                beneficiary[sector] = beneficiary.get(sector, 0) + 1
            for sector in group.harmed_sectors:
                harmed[sector] = harmed.get(sector, 0) + 1
        return {"beneficiary": beneficiary, "harmed": harmed}
