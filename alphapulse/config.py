"""
AlphaPulse - 전체 설정 관리 모듈

환경변수(.env)를 로드하고 전체 시스템에서 사용하는 설정 싱글턴을 제공합니다.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# 프로젝트 루트 디렉토리
ROOT_DIR = Path(__file__).parent.parent


class Settings(BaseSettings):
    """AlphaPulse 전체 설정 - 환경변수 또는 .env 파일에서 로드"""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM 설정 ──────────────────────────────────────────────────────
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # ── 텔레그램 설정 ─────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @property
    def telegram_chat_id_list(self) -> List[str]:
        """다중 수신 텔레그램 채팅방 ID 목록 반환"""
        if not self.telegram_chat_id:
            return []
        return [chat_id.strip() for chat_id in self.telegram_chat_id.split(",") if chat_id.strip()]

    # ── 스케줄 설정 ───────────────────────────────────────────────────
    schedule_morning: str = "07:00"
    schedule_evening: str = "18:00"
    timezone: str = "Asia/Seoul"

    # ── 저장소 설정 ───────────────────────────────────────────────────
    db_path: str = "data/alphapulse.db"
    report_dir: str = "data/reports"
    cache_dir: str = "data/cache"
    log_dir: str = "logs"

    # ── 뉴스 수집 설정 ────────────────────────────────────────────────
    max_articles: int = 200
    max_article_age_hours: int = 24
    num_groups: int = 7

    # ── RSS 피드 소스 ─────────────────────────────────────────────────
    rss_feeds: str = (
        "https://feeds.reuters.com/reuters/businessNews,"
        "https://feeds.bbci.co.uk/news/business/rss.xml,"
        "https://www.cnbc.com/id/100003114/device/rss/rss.html,"
        "https://www.yna.co.kr/rss/economy.xml,"
        "https://www.hankyung.com/feed/economy,"
        "https://www.mk.co.kr/rss/30000001/"
    )

    @property
    def rss_feed_list(self) -> List[str]:
        """RSS 피드 URL 목록 반환"""
        return [url.strip() for url in self.rss_feeds.split(",") if url.strip()]

    @property
    def report_dir_path(self) -> Path:
        """리포트 디렉토리 절대 경로"""
        p = ROOT_DIR / self.report_dir
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def cache_dir_path(self) -> Path:
        """캐시 디렉토리 절대 경로"""
        p = ROOT_DIR / self.cache_dir
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def log_dir_path(self) -> Path:
        """로그 디렉토리 절대 경로"""
        p = ROOT_DIR / self.log_dir
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def db_path_absolute(self) -> Path:
        """데이터베이스 절대 경로"""
        p = ROOT_DIR / self.db_path
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def validate_required(self) -> None:
        """필수 설정값 검증 - 실행 전 호출"""
        errors = []
        if not self.gemini_api_key and self.llm_provider == "gemini":
            errors.append("GEMINI_API_KEY가 설정되지 않았습니다.")
        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")
        if not self.telegram_chat_id:
            errors.append("TELEGRAM_CHAT_ID가 설정되지 않았습니다.")
        if errors:
            raise ValueError("환경변수 설정 오류:\n" + "\n".join(f"  - {e}" for e in errors))


# 전역 싱글턴 인스턴스
settings = Settings()
