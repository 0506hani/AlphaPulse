import json
from typing import List
from alphapulse.analyzers.base_llm import BaseLLM
from alphapulse.storage.models import NewsGroup
from alphapulse.utils.logger import logger

class WeeklySummarizer:
    """주간 뉴스 요약 생성기"""
    def __init__(self, llm: BaseLLM):
        self._llm = llm
        
    def summarize_weekly(self, weekly_data: List[dict]) -> List[NewsGroup]:
        """
        주간 데이터(딕셔너리 리스트)를 받아서 LLM으로 주간 요약 그룹(5~7개)을 생성
        """
        if not weekly_data:
            return []

        # 데이터를 텍스트로 변환하여 프롬프트에 제공
        context_text = ""
        for item in weekly_data:
            date = item.get("generated_at", "")[:10]
            context_text += f"[{date}] {item.get('topic', 'N/A')}: {item.get('summary', 'N/A')}\n"

        prompt = f"""
당신은 최고 수준의 금융/경제 애널리스트입니다.
다음은 지난 일주일 동안 수집된 일일 뉴스 브리핑 요약본의 모음입니다.
이 데이터를 분석하여, 이번 주 시장을 관통하는 **가장 중요한 핵심 트렌드/이슈 5~7개**를 도출해 주세요.

[주간 데이터 모음]
{context_text}

[출력 요구사항 (JSON)]
결과는 반드시 아래 JSON 배열 형식이어야 합니다. 마크다운 없이 순수 JSON만 반환하세요.
[
  {{
    "topic": "트렌드를 대표하는 핵심 타이틀 (예: 금리 인하 기대감 상승)",
    "summary": "해당 트렌드가 시장과 경제에 미친 영향 3~4문장 요약",
    "sentiment": "positive",
    "beneficiary_sectors": ["반도체", "인공지능"],
    "harmed_sectors": ["전통금융"]
  }}
]
"""
        logger.info(f"주간 요약 생성 시작 (입력 데이터: {len(weekly_data)}건)")
        try:
            result_json = self._llm.generate_json(prompt)
            data_list = json.loads(result_json)
            
            groups = []
            for i, data in enumerate(data_list):
                groups.append(NewsGroup(
                    group_id=f"weekly_group_{i+1}",
                    topic=data.get("topic", "N/A"),
                    summary=data.get("summary", "N/A"),
                    sentiment=data.get("sentiment", "neutral"),
                    beneficiary_sectors=data.get("beneficiary_sectors", []),
                    harmed_sectors=data.get("harmed_sectors", []),
                    top_links=[],
                    korean_stocks=[],
                    us_stocks=[],
                ))
            logger.info(f"주간 요약 생성 완료: {len(groups)}개 트렌드")
            return groups
        except Exception as e:
            logger.error(f"주간 요약 생성 실패: {e}")
            return []
