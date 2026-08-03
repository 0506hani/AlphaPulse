"""
AlphaPulse - 텔레그램 메시지 포맷터

DailyReport 객체를 텔레그램 MarkdownV2 형식 문자열로 변환합니다.
4096자 제한에 맞게 메시지를 자동 분할합니다.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Tuple

from alphapulse.storage.models import DailyReport, NewsGroup, StockRecommend

# 텔레그램 메시지 최대 길이
TELEGRAM_MAX_LENGTH = 4000  # 여유 있게 4000으로 설정

# 요일 한국어 매핑
WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]

# 감성 이모지 매핑
SENTIMENT_EMOJI = {
    "positive": "📈",
    "negative": "📉",
    "neutral": "➡️",
    "mixed": "↕️",
}

# 세션별 이모지
SESSION_EMOJI = {
    "morning": "🌅",
    "evening": "🌆",
}


def _escape_md(text: str) -> str:
    """텔레그램 MarkdownV2 특수문자 이스케이프"""
    special_chars = r"_*[]()~`>#+-=|{}.!"
    for char in special_chars:
        text = text.replace(char, f"\\{char}")
    return text


def _fmt_stocks(stocks: List[StockRecommend], flag: str) -> str:
    """종목 목록 포맷"""
    if not stocks:
        return ""
    lines = []
    for stock in stocks:
        ticker = _escape_md(stock.ticker)
        name = _escape_md(stock.name)
        reason = _escape_md(stock.reason)
        lines.append(f"  • *{name}* \\({ticker}\\)\n    _{reason}_")
    return f"{flag} *관련 종목*\n" + "\n".join(lines)


def _fmt_sectors(sectors: List[str], label: str, color: str, reason: str) -> str:
    """업종 목록 포맷"""
    if not sectors:
        return ""
    sector_str = "\\, ".join(_escape_md(s) for s in sectors)
    reason_escaped = _escape_md(reason) if reason else ""
    result = f"{color} *{label}*: {sector_str}"
    if reason_escaped:
        result += f"\n  _{reason_escaped}_"
    return result


class TelegramFormatter:
    """텔레그램 MarkdownV2 메시지 포맷터"""

    def format_report(self, report: DailyReport) -> List[Tuple[str, List[str]]]:
        """
        DailyReport를 전체가 합쳐진 하나의 통합 메시지(또는 페이지 단위로 분할된 튜플 리스트)로 변환합니다.

        Returns:
            List of (message_text, []) tuples (URL은 텍스트 내에 마크다운으로 포함됨)
        """
        now = report.generated_at
        weekday = WEEKDAY_KR[now.weekday()]
        date_str = now.strftime(f"%Y\\-%m\\-%d")
        time_str = now.strftime("%H:%M")
        if report.session == "weekly":
            session_label = "주간 통합"
            session_emoji = "🗓️"
        else:
            session_label = "오전" if report.session == "morning" else "오후"
            session_emoji = SESSION_EMOJI.get(report.session, "📰")

        header = (
            f"{session_emoji} *AlphaPulse {session_label} 리포트*\n"
            f"📅 {date_str} \\({weekday}\\) {time_str} KST\n"
            f"📊 총 {report.total_articles_collected}개 기사 수집 → "
            f"{len(report.groups)}개 핵심 주제 분석\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )

        parts = [header]

        for idx, group in enumerate(report.groups, start=1):
            group_text = self._format_group(group, idx)
            parts.append(group_text)

        footer = (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 _AlphaPulse by AlphaVerse_\n"
            f"⚠️ _본 리포트는 AI 생성 정보로, 투자 조언이 아닙니다\\._"
        )
        parts.append(footer)

        full_text = "\n\n".join(parts)
        return self._split_unified_message(full_text)

    def _format_group(self, group: NewsGroup, idx: int) -> str:
        """단일 뉴스 그룹을 문자열로 변환 (링크 포함)"""
        sentiment_emoji = SENTIMENT_EMOJI.get(group.sentiment, "➡️")
        topic_escaped = _escape_md(group.topic)
        summary_escaped = _escape_md(group.summary)

        parts = []

        header = (
            f"{sentiment_emoji} *{idx}\\. {topic_escaped}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 *핵심 요약*\n{summary_escaped}"
        )
        parts.append(header)

        sectors_text = ""
        if group.beneficiary_sectors:
            sectors_text += "\n\n" + _fmt_sectors(
                group.beneficiary_sectors, "수혜 업종", "🟢", group.beneficiary_reason
            )
        if group.harmed_sectors:
            sectors_text += "\n" + _fmt_sectors(
                group.harmed_sectors, "피해 업종", "🔴", group.harmed_reason
            )
        if sectors_text:
            parts.append(sectors_text)

        if group.korean_stocks:
            parts.append("\n\n" + _fmt_stocks(group.korean_stocks, "🇰🇷"))

        if group.us_stocks:
            parts.append("\n" + _fmt_stocks(group.us_stocks, "🇺🇸"))

        # 인라인 버튼 대신 텍스트 내 링크 포함
        links_text = ""
        for i, url in enumerate(group.top_links[:2]):
            safe_url = url.replace(")", "\\)")
            links_text += f"[📰 원문{i+1}]({safe_url}) "
            
        if links_text:
            parts.append("\n\n🔗 " + links_text.strip())

        return "".join(parts)

    def _split_unified_message(self, text: str) -> List[Tuple[str, List[str]]]:
        """전체 통합 메시지를 TELEGRAM_MAX_LENGTH 이하로 분할하여 페이지 번호 부여"""
        if len(text) <= TELEGRAM_MAX_LENGTH:
            return [(text, [])]
            
        chunks = []
        current = ""
        chunk_limit = TELEGRAM_MAX_LENGTH - 100  # 페이지 헤더 길이 고려
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > chunk_limit:
                if current:
                    chunks.append(current.strip())
                current = line
            else:
                current += ("\n" if current else "") + line
        if current:
            chunks.append(current.strip())
            
        total_pages = len(chunks)
        result = []
        for i, chunk in enumerate(chunks, start=1):
            page_header = f"*\\[페이지 {i}/{total_pages}\\]*\n\n"
            result.append((page_header + chunk, []))
            
        return result
