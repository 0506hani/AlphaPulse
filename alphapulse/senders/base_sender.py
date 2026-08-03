"""
AlphaPulse - 발송기 추상 인터페이스

모든 발송기(텔레그램, 슬랙, 이메일 등)는 이 클래스를 상속합니다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Tuple

from alphapulse.storage.models import DailyReport


class BaseSender(ABC):
    """발송기 추상 기반 클래스"""

    @property
    @abstractmethod
    def sender_name(self) -> str:
        """발송기 이름 (로깅/식별용)"""
        ...

    @abstractmethod
    def send_report(self, report: DailyReport) -> bool:
        """
        DailyReport를 발송합니다.

        Args:
            report: 발송할 DailyReport 객체

        Returns:
            발송 성공 여부
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(sender={self.sender_name})"
