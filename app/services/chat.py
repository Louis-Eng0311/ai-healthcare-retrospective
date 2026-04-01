from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx
import redis.asyncio as redis

from app.dtos.chat import (
    ChatFeedbackCreateData,
    ChatFeedbackCreateResponse,
    ChatMessageCreateData,
    ChatMessageCreateResponse,
    ChatMessageItem,
    ChatMessageListData,
    ChatMessageListResponse,
    ChatSessionCreateData,
    ChatSessionCreateResponse,
    RequesterRole,
)
from app.models.chat import ChatFeedback, ChatMessage, ChatSession, ChatSessionMemory
from app.models.dur import DurAlert
from app.models.guides import Guide, GuideStatus
from app.models.hospital_schedules import HospitalSchedule
from app.models.medications import PatientMed
from app.models.patients import Patient, PatientProfile
from app.models.schedules import IntakeLog, MedSchedule, MedScheduleTime
from app.models.users import User
from app.services.kids_client import KIDSClient
from app.services.mfds import MfdsService
from app.services.rag import (
    build_rag_context,
    extract_external_blocks,
    extract_guide_blocks,
    extract_meds_blocks,
    extract_profile_blocks,
    extract_schedule_blocks,
)
from app.services.role_utils import user_has_role

logger = logging.getLogger(__name__)

CHAT_DISCLAIMER = "본 답변은 의료 자문이 아닌 참고용 정보입니다."
CHAT_HISTORY_TURNS = int((os.getenv("CHAT_HISTORY_TURNS", "8") or "8").strip())
CHAT_MAX_MESSAGE_CHARS = int((os.getenv("CHAT_MAX_MESSAGE_CHARS", "2000") or "2000").strip())
REDIS_URL = (os.getenv("REDIS_URL", "redis://localhost:6379/0") or "").strip()
CHAT_WORKER_QUEUE = (os.getenv("CHAT_WORKER_QUEUE", "chat_tasks") or "").strip()
CHAT_SLOW_REPLY_SECONDS = float((os.getenv("CHAT_SLOW_REPLY_SECONDS", "3.0") or "3.0").strip())
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
FAST_SYNC_INTENTS = {
    "tonight_check",
    "med_list",
    "schedule",
    "schedule_order",
    "adherence_priority",
    "hospital_schedule",
    "profile_summary",
    "profile_body",
}
EXTERNAL_EVIDENCE_INTENTS = {
    "external_med",
    "medication_caution",
}

_EMERGENCY_KEYWORDS = [
    "숨이 차",
    "호흡곤란",
    "숨쉬기 힘들",
    "숨쉬기가 힘들",
    "숨을 쉬기 힘들",
    "숨 못 쉬",
    "가슴 통증",
    "의식이 흐려",
    "실신",
    "경련",
    "피가 나",
    "출혈",
    "극심한 통증",
    "응급실",
    "119",
]
_DIRECT_EMERGENCY_SYMPTOM_KEYWORDS = [
    "숨이 차",
    "호흡곤란",
    "숨쉬기 힘들",
    "숨쉬기가 힘들",
    "숨을 쉬기 힘들",
    "숨 못 쉬",
    "가슴 통증",
    "의식이 흐려",
    "실신",
    "경련",
    "피가 나",
    "출혈",
    "극심한 통증",
]
_EMERGENCY_EXPLORATION_KEYWORDS = [
    "119를 생각",
    "119를 불러",
    "119에 연락",
    "병원이나 119",
    "응급으로 봐야",
    "응급 신호",
    "응급 상황인지",
    "위험하면",
    "기준으로",
    "어떤 증상",
]

_PROFILE_SMOKING_KEYWORDS = ["담배", "흡연", "몇 갑", "주에 평균", "주간 흡연"]
_PROFILE_ALCOHOL_KEYWORDS = ["술", "음주", "몇 병", "주간 음주"]
_PROFILE_SLEEP_KEYWORDS = ["수면", "잠", "몇 시간"]
_PROFILE_EXERCISE_KEYWORDS = ["운동", "몇 분", "운동량"]
_PROFILE_CONDITION_KEYWORDS = ["기저질환", "건강 상태", "질환", "질병", "지병", "아픈 곳"]
_PROFILE_ALLERGY_KEYWORDS = ["알레르기", "알레지", "알러지"]
_PROFILE_HOSPITALIZATION_KEYWORDS = ["입원", "퇴원", "입퇴원", "입원 여부", "퇴원일"]
_PROFILE_BODY_KEYWORDS = ["bmi", "BMI", "체중", "몸무게", "키", "키 몸무게", "건강프로필", "건강 프로필"]
_PROFILE_SUMMARY_KEYWORDS = ["건강프로필 요약", "건강 프로필 요약", "프로필 요약", "내 프로필 요약"]
_SCHEDULE_KEYWORDS = ["복약스케줄", "복약 스케줄", "언제 먹", "언제 복용", "몇 시", "스케줄", "일정"]
_HOSPITAL_SCHEDULE_KEYWORDS = [
    "병원 예약",
    "병원 일정",
    "외래 예약",
    "외래 일정",
    "검사 예약",
    "검사 일정",
    "진료 예약",
    "진료 일정",
    "예약 언제",
    "언제였지",
    "다음 병원",
    "다음 외래",
    "다음 진료",
    "병원 가는 날",
]
_GUIDE_SUMMARY_KEYWORDS = ["가이드", "가이드 요약", "생활 가이드", "복약 가이드"]
_MED_LIST_KEYWORDS = [
    "복용하고있는 약",
    "복용하고 있는 약",
    "먹고 있는 약",
    "내가 먹는 약",
    "먹는 약",
    "먹어야 할 약",
    "먹어야 하는 약",
    "복용해야 할 약",
    "복용해야 하는 약",
    "현재 약",
    "약 목록",
    "무슨 약을",
]
_MED_TIME_SPLIT_KEYWORDS = [
    "아침, 저녁",
    "아침, 저녁으로",
    "아침 저녁",
    "아침 저녁으로",
    "아침과 저녁",
    "아침/저녁",
    "나눠서",
    "구분해서",
    "언제 먹는 약",
]
_MED_REGULARITY_KEYWORDS = ["매일 먹는 약", "매일 먹어야", "꼭 매일", "정해진 시간에 먹는 약", "매일 복용"]
_PRN_KEYWORDS = ["매일 먹는 약이야", "열날 때만", "열 날 때만", "필요할 때만", "필요 시", "매일 먹어야 해"]
_CAREGIVER_CHECK_KEYWORDS = [
    "보호자가 꼭 확인",
    "보호자가 확인",
    "오늘 확인해야",
    "꼭 확인해야 할 것",
    "체크리스트",
    "관리 포인트",
    "체크포인트",
    "오늘 복약에서",
]
_ALLERGY_FOOD_KEYWORDS = [
    "알레르기",
    "음식으로 조심",
    "음식 조심",
    "먹지 않도록",
    "음식으로 특히",
    "조심해야 하는 음식",
    "음식으로 특히 조심",
    "먹으면 안",
]
_MISSED_DOSE_KEYWORDS = [
    "놓쳤다면",
    "놓쳤으면",
    "놓쳤고",
    "놓쳤는데",
    "복약을 놓쳤",
    "지금 바로 먹여",
    "바로 먹여도",
    "깜빡",
    "복용을 놓쳤",
]
_LIFESTYLE_TOP_KEYWORDS = [
    "생활관리",
    "생활 관리",
    "생활관리에서",
    "생활 관리에서",
    "생활관리 요약",
    "생활 관리 요약",
    "중요한 것 3가지",
    "중요한 것 세 가지",
    "중요한 것만 3가지",
    "세 가지만",
    "세 가지",
    "3가지만",
    "3가지",
]
_SESSION_SUMMARY_KEYWORDS = ["한 줄로 요약", "지금까지 대화", "상태를 요약", "요약해줘"]
_EMERGENCY_GUIDANCE_KEYWORDS = [
    "119를 생각",
    "119에 연락",
    "병원이나 119",
    "응급으로 봐야",
    "응급 신호",
    "어떤 증상",
    "위험하면",
    "병원 가야",
]
_TONIGHT_CHECK_KEYWORDS = [
    "오늘 밤",
    "오늘 저녁",
    "취침 전",
    "오늘 밤에",
    "꼭 챙겨야",
    "오늘 꼭 챙겨",
    "오늘 내가 먹어야",
    "오늘 먹어야 할",
    "오늘 먹어야하는",
    "오늘 약 뭐",
    "오늘 복용할 약",
]
_SCHEDULE_ORDER_KEYWORDS = ["순서대로", "정리해줘", "정리해 줘", "아침에 약이 너무 많", "복용 순서"]
_ADHERENCE_PRIORITY_KEYWORDS = [
    "제일 중요한 약",
    "놓치면 안 되는 약",
    "까먹",
    "놓치면 안",
    "자주 까먹",
    "최근 놓친 약",
    "최근 놓친",
]
_SYMPTOM_CAUSE_KEYWORDS = ["약 때문", "부작용일 수도", "의심해야", "원인일 수도", "때문일 수도"]
_SYMPTOM_WORDS = [
    "어지러",
    "식은땀",
    "멍",
    "출혈",
    "두드러기",
    "발진",
    "기침",
    "숨",
    "호흡",
    "복통",
    "배 아",
    "배아",
    "속쓰림",
    "속 쓰림",
    "속이 쓰",
    "속이 안 좋",
    "속 안 좋",
    "속이 안좋",
    "속 안좋",
    "메스껍",
    "메슥",
    "울렁",
    "구역",
    "구토",
    "토할 것 같",
]
_SYMPTOM_GUIDANCE_KEYWORDS = [
    "어떻게",
    "어떡",
    "해야",
    "해?",
    "해",
    "대처",
    "대처법",
    "괜찮",
    "확인",
    "봐야",
    "병원",
]
_CLARIFICATION_RESET_PREFIXES = ["그건 아니", "그건아니", "아니고", "아니", "말고", "그게 아니라", "그게아니라"]
_OBSERVATION_CHECK_KEYWORDS = ["뭘 더 봐", "무엇을 더 봐", "뭘 봐야", "상태가 뭐", "상태", "확인해야 할 상태"]
_FIRST_CHECK_KEYWORDS = ["먼저 뭘 확인", "먼저 무엇을 확인", "먼저 확인해야", "먼저 뭘 봐야"]
_SCHOOL_OBSERVATION_KEYWORDS = ["학교", "선생님", "봐달라", "봐 달라", "어떤 증상", "등교"]
_COLD_MED_CAUTION_KEYWORDS = ["감기약", "새로 먹", "새로 먹게", "조심해야 할 성분", "조심해야 할 상황", "조심할 성분"]
_RASH_KEYWORDS = ["두드러기", "발진", "두드러기처럼", "발진이 생기", "약 먹고 나서 발진"]
_MEDICATION_CAUTION_KEYWORDS = [
    "주의사항",
    "주의할 점",
    "주의해야 할 점",
    "주의해야할 점",
    "조심",
    "부작용",
    "상호작용",
    "금기",
    "주의점",
    "조심할 점",
]
_DAILY_CHAT_KEYWORDS = [
    "안녕",
    "반가워",
    "고마워",
    "감사",
    "이름이 뭐",
    "너 이름",
    "누구야",
    "오늘 어때",
    "오늘 하루",
    "기분 어때",
    "너 뭐해",
    "뭘 하는",
    "뭐 하는 애",
    "뭐하는 애",
    "뭐하는 애니",
    "잘 자",
    "좋은 아침",
]
_BOT_CAPABILITY_KEYWORDS = [
    "뭘 할 수",
    "무엇을 할 수",
    "뭐 도와줄 수",
    "뭘 도와주는",
    "뭐 도와주는",
    "어떤 걸 도와줄 수",
    "어떤걸 도와줄 수",
    "무엇을 도와줄 수",
    "뭘 도와줄 수",
    "도와줄 수 있어",
    "어떤 질문",
    "어떤 걸 물어",
    "무엇을 물어",
]
_MED_DETAIL_KEYWORDS = ["어떤 약", "무슨 약", "뭐하는 약", "설명해줘", "설명해 줘", "약 설명"]
_FOLLOWUP_MED_REFERENCES = ["그 약", "이 약", "그거", "이거", "저 약", "해당 약"]
_AFFIRMATIVE_SHORT_REPLIES = ["어", "응", "네", "넵", "예", "맞아", "그래", "맞아요", "그렇지", "좋아"]


def _normalize_user_message(content: str) -> str:
    normalized = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _mask_log_value(value: str, *, keep: int = 12) -> str:
    clean = _normalize_user_message(value)
    if len(clean) <= keep:
        return clean
    return clean[:keep] + "..."


def _extract_bracketed_drug_name(message: str) -> str | None:
    normalized = _normalize_user_message(message)
    match = re.fullmatch(r"[\(\[\{＜<]\s*([가-힣A-Za-z0-9+\-_/\.]{2,60})\s*[\)\]\}＞>]", normalized)
    if not match:
        return None
    candidate = str(match.group(1) or "").strip()
    if len(candidate) < 2:
        return None
    return candidate


_GENERAL_CAUTION_KEYWORDS = [
    "주의",
    "조심",
    "주의할 게",
    "조심할 게",
    "주의해야",
    "조심해야",
    "주의해",
    "조심해",
    "먼저 뭐 봐야",
    "먼저 무엇을 봐야",
    "먼저 확인해야",
]
_MED_QUERY_STOPWORDS = {
    "약",
    "알려줘",
    "알려",
    "설명해줘",
    "설명",
    "대해서",
    "에대해서",
    "정보",
    "어떤약이야",
    "어떤약이니",
    "무슨약",
    "무슨약이야",
    "무슨약이니",
    "뭐야",
    "뭐니",
}
_PERSONALIZED_INTENTS = {
    "profile_body",
    "profile_summary",
    "profile_guidance",
    "profile_smoking",
    "profile_alcohol",
    "profile_sleep",
    "profile_exercise",
    "profile_conditions",
    "profile_allergies",
    "profile_hospitalization",
    "med_list",
    "med_detail",
    "med_time_split",
    "med_regularity",
    "med_prn",
    "schedule",
    "hospital_schedule",
    "medication_caution",
    "general_caution",
    "tonight_check",
    "schedule_order",
    "adherence_priority",
    "observation_check",
    "school_observation",
    "self_check",
    "caregiver_check",
    "session_summary",
}
_CONDITION_TREATMENT_KEYWORDS = [
    "좋은약",
    "좋은 약",
    "어떤 약",
    "무슨 약",
    "치료약",
    "치료 약",
    "도움 되는 약",
    "도움되는 약",
    "지금 먹는 약",
    "꾸준히 챙겨",
    "꾸준히 먹",
    "매일 먹는 약",
    "주 1회 약",
    "나눠서 말해",
]
_EXTERNAL_MED_FOLLOWUP_KEYWORDS = [
    "혹시 아나",
    "아나해서",
    "아나 해서",
    "알아?",
    "알아",
    "궁금해",
    "궁금해서",
    "처방받은 약은 아닌데",
    "처방받은약은아닌데",
]
_EXTERNAL_DRUG_STOPWORDS = {
    "아이",
    "내",
    "내가",
    "기록",
    "기록에는",
    "없는",
    "약인데",
    "독감",
    "감기",
    "치료",
    "치료로",
    "자주",
    "듣는",
    "새로",
    "처방",
    "처방받은",
    "처방받을",
    "수도",
    "있는데",
    "주의",
    "주의할",
    "특히",
    "같이",
    "복용",
    "부작용",
    "용도",
    "주의사항",
    "약",
    "점",
    "상태",
    "내용",
    "정보좀",
    "설명",
    "하는지",
    "하는지는",
    "언제인지",
    "어디로",
    "가야",
    "장소도",
    "알려줘",
    "알려",
}
_EXTERNAL_DRUG_SUFFIXES = ["정", "시럽", "캡슐", "현탁액", "산", "주사", "크림", "패치", "정제", "액", "연질캡슐"]
_EXTERNAL_DRUG_CONTEXT_KEYWORDS = ["용도", "부작용", "주의사항", "정보", "처방", "감기", "독감"]
_EXTERNAL_DRUG_QUERY_KEYWORDS = [
    "무슨약",
    "무슨 약",
    "뭐야",
    "어떤 약",
    "알려줘",
    "설명해줘",
    "설명해 줘",
    "정보",
    "용도",
    "부작용",
    "주의사항",
]
_CONDITION_MED_KEYWORDS: dict[str, list[str]] = {
    "골다공증": ["리세드론", "알렌드론", "칼슘", "비타민D", "알파칼시돌"],
    "고혈압": ["암로디핀", "텔미사르탄", "비소프롤롤"],
    "당뇨": ["메트포르민", "글리메피리드"],
    "고지혈증": ["로수바스타틴", "로수젯"],
    "빈혈": ["훼럼", "철분"],
    "천식": ["몬테루카스트"],
}


def _compact_text(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isalnum() or ("가" <= ch <= "힣"))


def _contains_keyword(message: str, keyword: str) -> bool:
    original = str(message or "").strip()
    if keyword in original:
        return True
    return _compact_text(keyword) in _compact_text(original)


def _contains_any(message: str, keywords: list[str]) -> bool:
    return any(_contains_keyword(message, keyword) for keyword in keywords)


def _strip_korean_postposition(token: str) -> str:
    clean = str(token or "").strip()
    for suffix in (
        "이에요",
        "예요",
        "이야",
        "야",
        "이니",
        "니",
        "은",
        "는",
        "이",
        "가",
        "을",
        "를",
        "에",
        "도",
        "만",
    ):
        if clean.endswith(suffix) and len(clean) > len(suffix) + 1:
            return clean[: -len(suffix)]
    return clean


def _extract_med_query_tokens(message: str) -> list[str]:
    normalized = str(message or "").strip()
    if not normalized:
        return []

    candidates = [normalized]
    for token in re.split(r"[\s,./()]+", normalized):
        stripped = _strip_korean_postposition(token)
        compact = _compact_text(stripped)
        if len(compact) < 2:
            continue
        if compact.lower() in {item.lower() for item in _MED_QUERY_STOPWORDS}:
            continue
        candidates.append(stripped)

    return _dedupe_lines(candidates, limit=8)


def _find_best_med_match(
    *,
    query: str,
    meds: list[dict[str, Any]],
    threshold: float = 0.72,
) -> dict[str, Any] | None:
    tokens = _extract_med_query_tokens(query)
    if not tokens or not meds:
        return None

    exact_candidates = [_compact_text(token).lower() for token in tokens]
    for med in meds:
        med_name = str(med.get("display_name") or "").strip()
        compact_name = _compact_text(med_name).lower()
        if not compact_name:
            continue
        if any(compact_name in token or token in compact_name for token in exact_candidates if len(token) >= 2):
            return med

    best_med: dict[str, Any] | None = None
    best_score = 0.0
    for med in meds:
        med_name = str(med.get("display_name") or "").strip()
        compact_name = _compact_text(med_name).lower()
        if len(compact_name) < 2:
            continue
        for token in exact_candidates:
            if len(token) < 2:
                continue
            score = SequenceMatcher(None, token, compact_name).ratio()
            if score > best_score:
                best_score = score
                best_med = med

    return best_med if best_score >= threshold else None


def _split_text_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    raw = str(value or "").strip()
    if not raw:
        return []

    if raw.startswith("[") and raw.endswith("]"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass

    return [
        item.strip().strip('"').strip("'") for chunk in raw.splitlines() for item in chunk.split(",") if item.strip()
    ]


def _append_unique(items: list[str], value: str | None) -> None:
    clean = str(value or "").strip()
    if clean and clean not in items:
        items.append(clean)


def _first_clean_line(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    for line in raw.splitlines():
        clean = line.strip().lstrip("-").strip()
        if clean:
            return clean
    return raw


def _summarize_text(value: str | None, *, max_sentences: int = 2) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    compact = re.sub(r"(?<=[.!?])(?=[가-힣A-Za-z0-9])", " ", raw)
    compact = compact.replace("이 약을 복용하기 전에", ". 이 약을 복용하기 전에")
    compact = compact.replace("정해진 용법과 용량을 잘 지키십시오.", "정해진 용법과 용량을 잘 지키십시오. ")
    compact = re.sub(r"\s+", " ", compact)
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+|(?<=다\.)\s*", compact) if item.strip()]
    if not sentences:
        return compact
    return " ".join(sentences[:max_sentences]).strip()


def _dedupe_lines(items: list[str], *, limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for item in items:
        clean = str(item or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        results.append(clean)
        if limit is not None and len(results) >= limit:
            break
    return results


def _choose_korean_particle(word: str, pair: tuple[str, str]) -> str:
    text = str(word or "").strip()
    if not text:
        return pair[1]
    last = text[-1]
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        has_batchim = (code - 0xAC00) % 28 != 0
        return pair[0] if has_batchim else pair[1]
    return pair[1]


def _with_particle(word: str, pair: tuple[str, str]) -> str:
    text = str(word or "").strip()
    return text + _choose_korean_particle(text, pair)


class ChatServiceError(Exception):
    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass
class PatientChatContext:
    patient_id: int
    profile: PatientProfile | None
    latest_guide: Guide | None
    meds: list[dict[str, Any]]
    schedules: list[dict[str, Any]]
    hospital_schedules: list[HospitalSchedule]
    dur_alerts: list[dict[str, Any]]
    adherence_summary: dict[str, Any]
    recent_messages: list[ChatMessage]
    session_memory: ChatSessionMemory | None
    kids_evidence: list[dict[str, Any]]
    rag_context: list[dict[str, Any]]


@dataclass
class QuestionAnalysis:
    raw_message: str
    intents: list[str]
    primary_intent: str
    target_med: dict[str, Any] | None
    external_drug_name: str | None
    target_condition: str | None
    time_period: str | None
    is_emergency: bool
    emergency_message: str | None
    answer_mode: str


@dataclass
class ChatPlan:
    topic: str
    requested_fields: list[str]
    referenced_drug_name: str | None
    needs_clarification: bool
    clarification_question: str | None
    use_record_data: list[str]
    answer_style: str


def _harmonize_chat_plan(*, analysis: QuestionAnalysis, plan: ChatPlan | None) -> ChatPlan | None:
    if not plan:
        return None

    primary = analysis.primary_intent

    if primary == "daily":
        return None

    # These domains are more stable when answered from local medical data and
    # deterministic policy instead of planner-led clarifications.
    if primary in {
        "external_med",
        "medication_caution",
        "profile_guidance",
        "tonight_check",
        "schedule_order",
        "adherence_priority",
    }:
        return None

    if primary == "hospital_schedule":
        plan.topic = "hospital_schedule"
        return plan

    if primary in {"med_detail", "med_prn", "med_time_split", "med_regularity"}:
        if analysis.target_med:
            plan.topic = "current_meds" if primary == "med_detail" else "med_schedule"
            plan.referenced_drug_name = (
                str(analysis.target_med.get("display_name") or "").strip() or plan.referenced_drug_name
            )
            return plan
        return None

    if primary in {"med_list", "schedule", "tonight_check", "schedule_order", "adherence_priority"}:
        plan.topic = "med_schedule" if primary != "med_list" else "current_meds"
        return plan

    if primary in {
        "profile_body",
        "profile_summary",
        "profile_guidance",
        "profile_smoking",
        "profile_alcohol",
        "profile_sleep",
        "profile_exercise",
        "profile_conditions",
        "profile_allergies",
        "profile_hospitalization",
    }:
        plan.topic = "profile"
        requested = set(plan.requested_fields)
        if primary == "profile_body":
            requested.update({"body_metrics"})
        elif primary == "profile_summary":
            requested.update({"summary"})
        elif primary == "profile_guidance":
            requested = {"guidance", "lifestyle", "risk"}
        elif primary == "profile_smoking":
            requested.add("smoking")
        elif primary == "profile_alcohol":
            requested.add("alcohol")
        elif primary == "profile_sleep":
            requested.add("sleep")
        elif primary == "profile_exercise":
            requested.add("exercise")
        elif primary == "profile_conditions":
            requested.add("conditions")
        elif primary == "profile_allergies":
            requested.add("allergies")
        elif primary == "profile_hospitalization":
            requested.add("hospitalization")
        plan.requested_fields = list(requested)
        return plan

    if primary == "condition_general":
        plan.topic = "condition_general"
        if analysis.target_condition and not plan.referenced_drug_name:
            plan.referenced_drug_name = analysis.target_condition
        return plan

    if primary in {"general_caution", "lifestyle_top", "session_summary", "self_check", "caregiver_check"}:
        return None

    return plan


# 요청자 역할 판별
async def _resolve_requester_role(user_id: int) -> RequesterRole:
    # Louis수정(코드삭제): Patient row 존재 여부만으로 역할을 판별하면 보호자+본인프로필 계정이 PATIENT로 오인됨
    if await user_has_role(user_id, "ADMIN"):
        return RequesterRole.ADMIN

    # Louis수정(기능추가): 역할 테이블 기준으로 우선 판별해 보호자가 연동 환자에 정상 접근하도록 수정
    if await user_has_role(user_id, "CAREGIVER", "GUARDIAN"):
        return RequesterRole.CAREGIVER

    if await user_has_role(user_id, "PATIENT"):
        return RequesterRole.PATIENT

    patient_exists = await Patient.filter(user_id=user_id).exists()
    if patient_exists:
        return RequesterRole.PATIENT

    return RequesterRole.ADMIN


# 프롬프트 파일 읽기
def _read_prompt_template(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise RuntimeError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


def _has_openai_api_key() -> bool:
    return bool((os.getenv("OPENAI_API_KEY", "") or "").strip())


# 응급 키워드 감지
def _detect_emergency(message: str) -> tuple[bool, str | None]:
    normalized = (message or "").strip()
    if _contains_any(normalized, _DIRECT_EMERGENCY_SYMPTOM_KEYWORDS):
        return (
            True,
            "응급 상황이 의심됩니다. 즉시 119 또는 가까운 응급실/의료기관에 연락해 주세요.",
        )

    if _contains_any(normalized, ["119", "응급실", "응급"]) and _contains_any(
        normalized, _EMERGENCY_EXPLORATION_KEYWORDS
    ):
        return False, None

    for keyword in ["응급실", "119"]:
        if keyword in normalized:
            return (
                True,
                "응급 상황이 의심됩니다. 즉시 119 또는 가까운 응급실/의료기관에 연락해 주세요.",
            )
    return False, None


# 현재 연도
def date_today_year() -> int:
    from datetime import date

    return date.today().year


# 연령대 분류
def _resolve_audience(profile: PatientProfile | None) -> str:
    birth_year = getattr(profile, "birth_year", None)
    if not birth_year:
        return "adult"

    age = date_today_year() - int(birth_year)

    if age <= 12:
        return "child"
    if 13 <= age <= 18:
        return "teen"
    if age >= 65:
        return "senior"
    return "adult"


# 설명 라벨
def _audience_label(audience: str) -> str:
    if audience == "child":
        return "아이용 아주 쉬운 설명"
    if audience == "teen":
        return "청소년용 쉬운 설명"
    if audience == "senior":
        return "고령자용 주의 강화 설명"
    return "성인용 일반 설명"


# 추가 안전 문구
def _extra_safety_text(audience: str) -> str:
    if audience == "child":
        return "아이의 경우 보호자 확인이 중요하며 어려운 의학용어를 피한다."
    if audience == "teen":
        return "청소년은 이해하기 쉬운 설명으로 답하고 복약 실수를 줄이도록 돕는다."
    if audience == "senior":
        return "65세 이상은 어지러움, 낙상, 복약 시간 혼동, 보호자 확인 필요성을 함께 고려한다."
    return "제공된 근거 범위 안에서 일반 성인 기준으로 설명한다."


# 건강 프로필 텍스트 구성
def _build_profile_text(profile: PatientProfile | None) -> str:
    if not profile:
        return "등록된 건강 프로필 없음"

    lines: list[str] = []
    if getattr(profile, "birth_year", None):
        lines.append(f"- 출생연도: {profile.birth_year}")
    if getattr(profile, "sex", None):
        lines.append(f"- 성별: {profile.sex}")
    if getattr(profile, "height_cm", None) is not None:
        lines.append(f"- 키(cm): {profile.height_cm}")
    if getattr(profile, "weight_kg", None) is not None:
        lines.append(f"- 체중(kg): {profile.weight_kg}")
    if getattr(profile, "bmi", None) is not None:
        lines.append(f"- BMI: {profile.bmi}")
    if getattr(profile, "conditions", None):
        lines.append(f"- 기저질환/상태: {profile.conditions}")
    if getattr(profile, "allergies", None):
        lines.append(f"- 알레르기: {profile.allergies}")
    if getattr(profile, "notes", None):
        lines.append(f"- 메모: {profile.notes}")
    if getattr(profile, "is_smoker", None) is not None:
        lines.append(f"- 흡연 여부: {'예' if profile.is_smoker else '아니오'}")
    if getattr(profile, "avg_cig_packs_per_week", None) is not None:
        lines.append(f"- 주간 흡연량: {profile.avg_cig_packs_per_week}갑")
    if getattr(profile, "avg_alcohol_bottles_per_week", None) is not None:
        lines.append(f"- 주간 음주량: {profile.avg_alcohol_bottles_per_week}병")
    if getattr(profile, "avg_sleep_hours_per_day", None) is not None:
        lines.append(f"- 평균 수면 시간: {profile.avg_sleep_hours_per_day}시간")
    if getattr(profile, "avg_exercise_minutes_per_day", None) is not None:
        lines.append(f"- 평균 운동 시간: {profile.avg_exercise_minutes_per_day}분")
    if getattr(profile, "is_hospitalized", None) is not None:
        lines.append(f"- 입원 여부: {'예' if profile.is_hospitalized else '아니오'}")

    return "\n".join(lines) if lines else "등록된 건강 프로필 없음"


def _bmi_category_text(bmi: Any) -> str | None:
    try:
        value = float(bmi)
    except Exception:
        return None

    if value < 18.5:
        return "저체중 범위"
    if value < 23:
        return "정상 범위"
    if value < 25:
        return "과체중 범위"
    return "비만 범위"


def _build_profile_summary_lines(profile: PatientProfile) -> list[str]:
    lines: list[str] = []
    conditions = _split_text_items(getattr(profile, "conditions", None))
    allergies = _split_text_items(getattr(profile, "allergies", None))

    body_chunks: list[str] = []
    if getattr(profile, "height_cm", None) is not None:
        body_chunks.append(f"키 {profile.height_cm}cm")
    if getattr(profile, "weight_kg", None) is not None:
        body_chunks.append(f"몸무게 {profile.weight_kg}kg")
    if getattr(profile, "bmi", None) is not None:
        bmi_category = _bmi_category_text(profile.bmi)
        if bmi_category:
            body_chunks.append(f"BMI {profile.bmi}({bmi_category})")
        else:
            body_chunks.append(f"BMI {profile.bmi}")
    if body_chunks:
        lines.append(", ".join(body_chunks))

    lifestyle_chunks: list[str] = []
    if getattr(profile, "avg_sleep_hours_per_day", None) is not None:
        lifestyle_chunks.append(f"수면 {profile.avg_sleep_hours_per_day}시간")
    if getattr(profile, "avg_exercise_minutes_per_day", None) is not None:
        lifestyle_chunks.append(f"운동 {profile.avg_exercise_minutes_per_day}분")
    if getattr(profile, "is_smoker", None) is not None:
        smoker_text = "흡연 중" if profile.is_smoker else "비흡연"
        packs = getattr(profile, "avg_cig_packs_per_week", None)
        if packs is not None:
            smoker_text += f", 주간 흡연량 {packs}갑"
        lifestyle_chunks.append(smoker_text)
    if getattr(profile, "avg_alcohol_bottles_per_week", None) is not None:
        lifestyle_chunks.append(f"주간 음주량 {profile.avg_alcohol_bottles_per_week}병")
    if lifestyle_chunks:
        lines.append("생활 습관: " + ", ".join(lifestyle_chunks))

    if conditions:
        lines.append("건강 상태: " + ", ".join(conditions[:3]))
    if allergies:
        lines.append("알레르기: " + ", ".join(allergies[:3]))
    if getattr(profile, "is_hospitalized", None) is not None:
        admission_text = "입원 중" if profile.is_hospitalized else "현재 입원 기록 없음"
        if getattr(profile, "discharge_date", None):
            admission_text += f", 퇴원일 {profile.discharge_date}"
        lines.append("입원 정보: " + admission_text)
    if getattr(profile, "notes", None):
        note = _summarize_text(profile.notes, max_sentences=1)
        if note:
            lines.append("메모: " + note)

    return lines


def _build_profile_guidance_points(*, profile: PatientProfile | None, guide: Guide | None) -> list[str]:
    points: list[str] = []
    if profile:
        sleep_hours = getattr(profile, "avg_sleep_hours_per_day", None)
        exercise_minutes = getattr(profile, "avg_exercise_minutes_per_day", None)
        smoker = getattr(profile, "is_smoker", None)
        cig_packs = getattr(profile, "avg_cig_packs_per_week", None)
        alcohol = getattr(profile, "avg_alcohol_bottles_per_week", None)
        conditions = _split_text_items(getattr(profile, "conditions", None))
        allergies = _split_text_items(getattr(profile, "allergies", None))
        notes = _summarize_text(getattr(profile, "notes", None), max_sentences=1)

        if sleep_hours is not None:
            if float(sleep_hours) < 6:
                points.append(
                    f"현재 기록상 수면은 하루 평균 {sleep_hours}시간으로 짧은 편이라 수면 부족 원인을 먼저 점검하는 것이 좋습니다."
                )
            elif float(sleep_hours) > 9:
                points.append(
                    f"현재 기록상 수면은 하루 평균 {sleep_hours}시간으로 긴 편이라 피로감이나 복용약 영향도 함께 확인해 볼 수 있습니다."
                )
            else:
                points.append(f"현재 기록상 수면은 하루 평균 {sleep_hours}시간입니다.")

        if exercise_minutes is not None:
            if int(exercise_minutes) < 20:
                points.append(
                    f"운동은 하루 평균 {exercise_minutes}분으로 적은 편이라 가벼운 활동량 유지 여부를 같이 보는 것이 좋습니다."
                )
            else:
                points.append(f"운동은 하루 평균 {exercise_minutes}분으로 기록되어 있습니다.")

        if smoker is True:
            if cig_packs is not None:
                points.append(
                    f"흡연 중이며 주간 흡연량은 {cig_packs}갑으로 기록되어 있어 증상 변화나 약 복용 시 주의사항을 함께 확인하는 것이 좋습니다."
                )
            else:
                points.append("흡연 중으로 기록되어 있어 호흡기 증상이나 약물 주의사항을 함께 보는 것이 좋습니다.")
        elif smoker is False:
            points.append("흡연은 하지 않는 것으로 기록되어 있습니다.")

        if alcohol is not None:
            points.append(
                f"주간 음주량은 {alcohol}병으로 기록되어 있어 복용 중 약과의 음주 주의가 필요한지 같이 확인할 수 있습니다."
            )

        if conditions:
            points.append("현재 건강 상태로는 " + ", ".join(conditions[:2]) + "가 기록되어 있습니다.")
        if allergies:
            points.append("알레르기 정보는 " + ", ".join(allergies[:2]) + "입니다.")
        if getattr(profile, "is_hospitalized", None) is True:
            discharge_date = getattr(profile, "discharge_date", None)
            if discharge_date:
                points.append(f"현재 입원/퇴원 정보도 중요합니다. 기록상 퇴원일은 {discharge_date}입니다.")
            else:
                points.append("현재 입원 중으로 기록되어 있어 병원 지시사항을 우선 확인하는 것이 좋습니다.")
        if notes:
            points.append("건강 메모: " + notes)

    if guide and isinstance(guide.content_json, dict):
        for section in guide.content_json.get("sections") or []:
            title = str(section.get("title") or "")
            body = str(section.get("body") or "").strip()
            if ("생활" in title or "주의" in title or "복약" in title) and body:
                first_line = _first_clean_line(body)
                if first_line:
                    points.append(first_line)
            if len(points) >= 8:
                break

    return _dedupe_lines(points, limit=6)


def _build_adherence_guidance_points(*, adherence_summary: dict[str, Any] | None) -> list[str]:
    if not adherence_summary:
        return []

    points: list[str] = []
    missed = int(adherence_summary.get("missed", 0) or 0)
    taken = int(adherence_summary.get("taken", 0) or 0)
    pending = int(adherence_summary.get("pending", 0) or 0)
    recent_missed_names = adherence_summary.get("recent_missed_names") or []
    recent_lines = adherence_summary.get("recent_lines") or []

    if missed > 0:
        if recent_missed_names:
            names = ", ".join(
                _dedupe_lines([str(name).strip() for name in recent_missed_names if str(name).strip()], limit=3)
            )
            points.append(
                f"최근 복약 기록에서는 놓친 약이 있어 {names}부터 다시 일정대로 챙기는지 확인하는 것이 좋습니다."
            )
        else:
            points.append("최근 복약 기록에서는 놓친 일정이 있어 미복용이 반복되지 않는지 먼저 확인하는 것이 좋습니다.")
    elif taken > 0:
        points.append(
            "최근 복약 기록상 이미 복용한 일정이 있어 현재 복약 흐름은 어느 정도 이어지고 있는 것으로 보입니다."
        )

    if pending > 0:
        points.append(
            f"아직 복용 대기 상태로 남아 있는 일정이 {pending}건 있어 오늘 남은 약도 함께 확인하는 것이 좋습니다."
        )

    for line in recent_lines[:2]:
        clean = str(line).strip()
        if clean:
            points.append("최근 복약 상태: " + clean)

    return _dedupe_lines(points, limit=3)


def _build_profile_guidance_sections(
    *,
    message: str,
    profile: PatientProfile | None,
    guide: Guide | None,
    adherence_summary: dict[str, Any] | None,
) -> tuple[list[str], list[str], list[str]]:
    normalized = (message or "").strip()
    current_points: list[str] = []
    general_points: list[str] = []
    next_points: list[str] = []

    if profile:
        sleep_hours = getattr(profile, "avg_sleep_hours_per_day", None)
        exercise_minutes = getattr(profile, "avg_exercise_minutes_per_day", None)
        smoker = getattr(profile, "is_smoker", None)
        cig_packs = getattr(profile, "avg_cig_packs_per_week", None)
        alcohol = getattr(profile, "avg_alcohol_bottles_per_week", None)
        conditions = _split_text_items(getattr(profile, "conditions", None))
        allergies = _split_text_items(getattr(profile, "allergies", None))

        if _contains_any(normalized, _PROFILE_SLEEP_KEYWORDS) and sleep_hours is not None:
            current_points.append(f"현재 기록상 수면은 하루 평균 {sleep_hours}시간입니다.")
            if float(sleep_hours) < 6:
                next_points.append(
                    "수면 시간이 짧은 편이라 최근 증상 변화나 복용약 영향이 있는지도 함께 확인하는 것이 좋습니다."
                )
            elif float(sleep_hours) > 9:
                next_points.append(
                    "수면 시간이 긴 편이라 피로감이 계속되는지, 복용약 이후 졸림이 심해지지는 않는지 같이 보는 것이 좋습니다."
                )

        if _contains_any(normalized, _PROFILE_EXERCISE_KEYWORDS) and exercise_minutes is not None:
            current_points.append(f"현재 기록상 운동은 하루 평균 {exercise_minutes}분입니다.")
            if int(exercise_minutes) < 20:
                next_points.append(
                    "운동량이 적은 편이라 무리 없는 범위에서 가벼운 활동을 유지하는지 함께 보는 것이 좋습니다."
                )

        if _contains_any(normalized, _PROFILE_SMOKING_KEYWORDS):
            if smoker is True and cig_packs is not None:
                current_points.append(f"현재 기록상 흡연 중이며 주간 흡연량은 {cig_packs}갑입니다.")
            elif smoker is True:
                current_points.append("현재 기록상 흡연 중으로 되어 있습니다.")
            elif smoker is False:
                current_points.append("현재 기록상 흡연하지 않는 것으로 되어 있습니다.")

        if _contains_any(normalized, _PROFILE_ALCOHOL_KEYWORDS) and alcohol is not None:
            current_points.append(f"현재 기록상 주간 음주량은 {alcohol}병입니다.")

        if not current_points:
            if conditions:
                current_points.append("현재 건강 상태로는 " + ", ".join(conditions[:2]) + "가 기록되어 있습니다.")
            if allergies:
                current_points.append("알레르기 정보는 " + ", ".join(allergies[:2]) + "입니다.")
            if sleep_hours is not None:
                current_points.append(f"수면은 하루 평균 {sleep_hours}시간으로 기록되어 있습니다.")
            if exercise_minutes is not None:
                current_points.append(f"운동은 하루 평균 {exercise_minutes}분으로 기록되어 있습니다.")

    if guide and isinstance(guide.content_json, dict):
        for section in guide.content_json.get("sections") or []:
            title = str(section.get("title") or "")
            body = str(section.get("body") or "").strip()
            if not body:
                continue
            if _contains_any(normalized, _PROFILE_SLEEP_KEYWORDS) and ("수면" in title or "수면" in body):
                line = _first_clean_line(body)
                if line:
                    general_points.append(line)
            elif _contains_any(normalized, _PROFILE_EXERCISE_KEYWORDS) and ("운동" in title or "활동" in body):
                line = _first_clean_line(body)
                if line:
                    general_points.append(line)
            elif _contains_any(normalized, _PROFILE_SMOKING_KEYWORDS) and ("흡연" in title or "흡연" in body):
                line = _first_clean_line(body)
                if line:
                    general_points.append(line)
            elif _contains_any(normalized, _PROFILE_ALCOHOL_KEYWORDS) and ("음주" in title or "음주" in body):
                line = _first_clean_line(body)
                if line:
                    general_points.append(line)
            elif any(keyword in title for keyword in ["생활", "주의", "복약"]):
                line = _first_clean_line(body)
                if line:
                    general_points.append(line)
            if len(general_points) >= 3:
                break

    next_points.extend(_build_adherence_guidance_points(adherence_summary=adherence_summary))

    if _contains_any(normalized, ["잠", "수면", "못 자", "잠을 못", "잠이 안"]):
        next_points.append("최근 복용약 중 졸림이나 각성에 영향을 줄 수 있는 약이 있는지도 함께 보는 것이 좋습니다.")
        if profile and getattr(profile, "avg_sleep_hours_per_day", None) is not None:
            next_points.append(
                "기록상 수면 시간이 충분해 보여도 실제로는 자주 깨는지, 자고 일어나도 피곤한지 같은 체감 변화를 함께 확인하는 것이 좋습니다."
            )
    if _contains_any(normalized, ["술", "음주"]):
        next_points.append("음주와 현재 복용약의 조합은 따로 확인하는 것이 안전합니다.")
    if _contains_any(normalized, ["담배", "흡연"]):
        next_points.append("흡연 여부는 호흡기 증상이나 일부 약 복용 시 주의점과 함께 보는 것이 좋습니다.")

    if not general_points:
        general_points.extend(_build_profile_guidance_points(profile=profile, guide=guide)[:2])

    if not next_points:
        next_points.append(
            "현재 기록에서 가장 먼저는 생활 습관 변화와 복약 흐름이 함께 흔들리고 있지 않은지부터 확인하는 것이 좋습니다."
        )

    return (
        _dedupe_lines(current_points, limit=3),
        _dedupe_lines(general_points, limit=3),
        _dedupe_lines(next_points, limit=3),
    )


def _build_med_adherence_points(*, med_name: str, adherence_summary: dict[str, Any] | None) -> list[str]:
    if not adherence_summary:
        return []

    compact_med = _compact_text(med_name).lower()
    recent_lines = adherence_summary.get("recent_lines") or []
    recent_missed_names = adherence_summary.get("recent_missed_names") or []
    points: list[str] = []

    if any(compact_med and compact_med in _compact_text(str(name)).lower() for name in recent_missed_names):
        points.append(f"{med_name}은 최근 복약 기록에서 놓친 이력이 있어 다음 복용 전 일정 재확인이 필요합니다.")

    for line in recent_lines:
        clean = str(line).strip()
        if compact_med and compact_med in _compact_text(clean).lower():
            points.append("최근 복약 상태: " + clean)
            if len(points) >= 2:
                break

    return _dedupe_lines(points, limit=2)


def _extract_dur_alert_points(
    *,
    dur_alerts: list[dict[str, Any]],
    med_name: str | None = None,
    limit: int = 3,
) -> list[str]:
    if not dur_alerts:
        return []

    points: list[str] = []
    compact_med = _compact_text(med_name).lower() if med_name else ""
    for alert in dur_alerts:
        patient_med_name = str(alert.get("patient_med_name") or "").strip()
        related_med_name = str(alert.get("related_patient_med_name") or "").strip()
        if compact_med:
            candidates = [_compact_text(patient_med_name).lower(), _compact_text(related_med_name).lower()]
            if compact_med not in candidates and all(compact_med not in item for item in candidates if item):
                continue

        level = str(alert.get("level") or "").strip()
        message = str(alert.get("message") or "").strip()
        alert_type = str(alert.get("alert_type") or "").strip()
        if message:
            if level:
                points.append(f"DUR {level}: {message}")
            else:
                points.append(f"DUR {message}")
        elif alert_type:
            parts = [part for part in [patient_med_name, related_med_name] if part]
            joined = " / ".join(parts)
            if joined:
                points.append(f"DUR {alert_type}: {joined}")
            else:
                points.append(f"DUR {alert_type}")

    return _dedupe_lines(points, limit=limit)


def _build_med_guidance_points(*, guide: Guide | None, med_name: str) -> list[str]:
    if not guide or not isinstance(guide.content_json, dict):
        return []

    compact_med = _compact_text(med_name).lower()
    points: list[str] = []
    for section in guide.content_json.get("sections") or []:
        title = str(section.get("title") or "").strip()
        body = str(section.get("body") or "").strip()
        full_text = f"{title}\n{body}".strip()
        if compact_med and compact_med in _compact_text(full_text).lower():
            first_line = _first_clean_line(body)
            if first_line:
                points.append(first_line)
        elif any(keyword in title for keyword in ["주의", "복약", "생활"]):
            first_line = _first_clean_line(body)
            if first_line:
                points.append(first_line)
        if len(points) >= 2:
            break
    return _dedupe_lines(points, limit=2)


# 약 정보 텍스트 구성
def _build_meds_text(meds: list[dict[str, Any]]) -> str:
    if not meds:
        return "현재 복용 약 정보 없음"

    lines: list[str] = []
    for med in meds:
        display_name = med.get("display_name") or "약 이름 없음"
        dosage = med.get("dosage")
        route = med.get("route")

        chunks = [display_name]
        if dosage:
            chunks.append(f"용량={dosage}")
        if route:
            chunks.append(f"경로={route}")

        lines.append("- " + " / ".join(chunks))

    return "\n".join(lines)


# 시간 문구 변환
def _humanize_time(time_text: str | None) -> str:
    if not time_text:
        return "시간 미설정"

    raw = str(time_text).strip()
    hour = None
    minute = 0

    try:
        parts = raw.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        return raw

    if hour == 0 and minute == 0:
        return "자정"
    if hour < 12:
        prefix = "오전"
        shown_hour = 12 if hour == 0 else hour
    elif hour == 12:
        prefix = "정오"
        shown_hour = 12
    else:
        prefix = "오후"
        shown_hour = hour - 12

    if prefix == "정오":
        return "정오" if minute == 0 else f"정오 {minute}분"

    if minute == 0:
        return f"{prefix} {shown_hour}시"
    return f"{prefix} {shown_hour}시 {minute}분"


# 요일 문구 변환
def _humanize_days(days_text: str | None) -> str:
    if not days_text:
        return "요일 정보 없음"

    normalized = str(days_text).replace(" ", "")
    upper_normalized = normalized.upper()
    if normalized in {"1,2,3,4,5,6,7", "1,2,3,4,5,6,7,"} or upper_normalized in {
        "MON,TUE,WED,THU,FRI,SAT,SUN",
        "MON,TUE,WED,THU,FRI,SAT,SUN,",
    }:
        return "매일"

    day_map = {
        "1": "월",
        "2": "화",
        "3": "수",
        "4": "목",
        "5": "금",
        "6": "토",
        "7": "일",
        "MON": "월",
        "TUE": "화",
        "WED": "수",
        "THU": "목",
        "FRI": "금",
        "SAT": "토",
        "SUN": "일",
        "월": "월",
        "화": "화",
        "수": "수",
        "목": "목",
        "금": "금",
        "토": "토",
        "일": "일",
    }
    items = [day_map.get(x.upper(), day_map.get(x, x)) for x in normalized.split(",") if x]
    return ",".join(items) if items else "요일 정보 없음"


def _format_datetime_korean(value: Any) -> str:
    if value is None:
        return "일정 시간 미정"
    try:
        hour = int(value.strftime("%H"))
        minute = int(value.strftime("%M"))
        date_part = value.strftime("%Y-%m-%d")
    except Exception:
        return str(value)

    if hour == 0 and minute == 0:
        time_part = "자정"
    elif hour < 12:
        time_part = f"오전 {12 if hour == 0 else hour}시"
    elif hour == 12:
        time_part = "정오" if minute == 0 else f"정오 {minute}분"
    else:
        time_part = f"오후 {hour - 12}시"

    if minute and hour != 12:
        time_part += f" {minute}분"

    return f"{date_part} {time_part}"


# 일정 텍스트 구성
def _build_schedule_text(schedules: list[dict[str, Any]], meds: list[dict[str, Any]]) -> str:
    if not schedules:
        return "등록된 복약 일정 없음"

    med_name_map: dict[int, str] = {}
    for med in meds:
        patient_med_id = med.get("patient_med_id")
        display_name = med.get("display_name")
        if patient_med_id is not None and display_name:
            med_name_map[int(patient_med_id)] = str(display_name)

    lines: list[str] = []
    for schedule in schedules:
        patient_med_id = int(schedule.get("patient_med_id"))
        med_name = med_name_map.get(patient_med_id, f"patient_med_id={patient_med_id}")
        times = schedule.get("times") or []

        if not times:
            lines.append(f"- {med_name}: 시간 정보 없음")
            continue

        for item in times:
            time_label = _humanize_time(item.get("time_of_day"))
            days_label = _humanize_days(item.get("days_of_week"))

            if days_label == "요일 정보 없음" and time_label == "시간 미설정":
                lines.append(f"- {med_name}: 복용 시간 정보가 등록되어 있지 않습니다.")
            elif days_label == "요일 정보 없음":
                lines.append(f"- {med_name}: {time_label}에 복용하도록 기록되어 있습니다.")
            elif time_label == "시간 미설정":
                lines.append(f"- {med_name}: {days_label} 복용으로 기록되어 있으나 시간 정보는 없습니다.")
            elif days_label == "매일":
                lines.append(f"- {med_name}: 매일 {time_label}")
            else:
                lines.append(f"- {med_name}: {days_label} {time_label}")

    return "\n".join(lines) if lines else "등록된 복약 일정 없음"


def _build_hospital_schedule_text(hospital_schedules: list[HospitalSchedule]) -> str:
    if not hospital_schedules:
        return "등록된 병원 일정 없음"

    lines: list[str] = []
    for item in hospital_schedules:
        title = str(getattr(item, "title", "") or "병원 일정").strip()
        hospital_name = str(getattr(item, "hospital_name", "") or "").strip()
        location = str(getattr(item, "location", "") or "").strip()
        scheduled_at = _format_datetime_korean(getattr(item, "scheduled_at", None))
        line = f"- {scheduled_at}: {title}"
        if hospital_name:
            line += f" / {hospital_name}"
        if location:
            line += f" / {location}"
        lines.append(line)
    return "\n".join(lines)


def _build_hospital_schedule_brief(hospital_schedules: list[HospitalSchedule]) -> str:
    if not hospital_schedules:
        return "병원 일정 없음"
    lines: list[str] = []
    for item in hospital_schedules[:3]:
        title = str(getattr(item, "title", "") or "병원 일정").strip()
        scheduled_at = _format_datetime_korean(getattr(item, "scheduled_at", None))
        hospital_name = str(getattr(item, "hospital_name", "") or "").strip()
        chunk = f"{scheduled_at} {title}"
        if hospital_name:
            chunk += f" / {hospital_name}"
        lines.append(chunk)
    return " ; ".join(lines)


# 최신 guide 텍스트 구성
def _build_guide_text(guide: Guide | None) -> str:
    if not guide:
        return "최신 guide 없음"

    sections: list[str] = []
    if guide.content_text:
        sections.append(f"[guide 본문]\n{guide.content_text}")
    if isinstance(guide.content_json, dict):
        sections.append(f"[guide 구조화]\n{json.dumps(guide.content_json, ensure_ascii=False)}")
    if isinstance(guide.caregiver_summary, dict):
        sections.append(f"[caregiver summary]\n{json.dumps(guide.caregiver_summary, ensure_ascii=False)}")

    return "\n\n".join(sections) if sections else "최신 guide 없음"


# 최근 대화 텍스트 구성
def _build_history_text(messages: list[ChatMessage]) -> str:
    if not messages:
        return "이전 대화 없음"

    lines: list[str] = []
    for msg in messages:
        lines.append(f"- {msg.role}: {msg.content}")
    return "\n".join(lines)


def _build_recent_history_for_planner(messages: list[ChatMessage]) -> str:
    if not messages:
        return "이전 대화 없음"

    recent = messages[-6:]
    lines: list[str] = []
    for msg in recent:
        role = "user" if msg.role == "user" else "assistant"
        lines.append(f"- {role}: {msg.content}")
    return "\n".join(lines)


def _build_session_memory_text(memory: ChatSessionMemory | None) -> str:
    if not memory:
        return "구조화 메모리 없음"

    lines: list[str] = []
    if getattr(memory, "recent_topic", None):
        lines.append(f"- 최근 주제: {memory.recent_topic}")
    if getattr(memory, "recent_drug_name", None):
        lines.append(f"- 최근 현재 약: {memory.recent_drug_name}")
    if getattr(memory, "recent_external_drug_name", None):
        lines.append(f"- 최근 외부 약: {memory.recent_external_drug_name}")
    if getattr(memory, "recent_profile_focus", None):
        lines.append(f"- 최근 프로필 초점: {memory.recent_profile_focus}")
    if getattr(memory, "recent_hospital_focus", None):
        lines.append(f"- 최근 병원 일정 초점: {memory.recent_hospital_focus}")
    if getattr(memory, "pending_clarification", None):
        lines.append(f"- 대기 중 명확화: {memory.pending_clarification}")
    if getattr(memory, "clarification_question", None):
        lines.append(f"- 직전 확인 질문: {memory.clarification_question}")
    return "\n".join(lines) if lines else "구조화 메모리 없음"


async def _update_session_memory(
    *,
    session_id: int,
    analysis: QuestionAnalysis,
    plan: ChatPlan | None,
    assistant_content: str,
    context: PatientChatContext,
) -> None:
    memory = context.session_memory or await ChatSessionMemory.get_or_none(session_id=session_id)
    if not memory:
        memory = await ChatSessionMemory.create(session_id=session_id)

    topic = plan.topic if plan and plan.topic else analysis.primary_intent
    memory.recent_topic = str(topic or "")[:50] or None

    target_med_name = None
    if analysis.target_med:
        target_med_name = str(analysis.target_med.get("display_name") or "").strip() or None
    if not target_med_name and analysis.primary_intent in {
        "tonight_check",
        "schedule_order",
        "adherence_priority",
        "schedule",
    }:
        for med in context.meds:
            name = str(med.get("display_name") or "").strip()
            if name and name in assistant_content:
                target_med_name = name
                break
    if target_med_name:
        memory.recent_drug_name = target_med_name

    external_name = analysis.external_drug_name or (plan.referenced_drug_name if plan else None)
    if external_name:
        memory.recent_external_drug_name = str(external_name).strip()[:255] or None

    if analysis.primary_intent.startswith("profile") or (plan and plan.topic == "profile"):
        focus = plan.requested_fields if plan and plan.requested_fields else analysis.intents
        memory.recent_profile_focus = ", ".join(focus[:5])[:255] or None

    if analysis.primary_intent == "hospital_schedule" or (plan and plan.topic == "hospital_schedule"):
        normalized = str(analysis.raw_message or "").strip()
        if _contains_any(normalized, ["검사"]):
            memory.recent_hospital_focus = "검사 일정"
        elif _contains_any(normalized, ["외래", "진료"]):
            memory.recent_hospital_focus = "외래/진료 일정"
        else:
            memory.recent_hospital_focus = "가장 가까운 병원 일정"

    pending_clarification = None
    clarification_question = None
    if plan and plan.needs_clarification and plan.clarification_question:
        clarification_question = plan.clarification_question
        if plan.topic == "drug_interaction":
            pending_clarification = "interaction_scope"
        else:
            pending_clarification = f"{plan.topic}_clarification"
    elif "현재 복용약끼리 비교할지, 새로 받은 약까지 포함할지" in assistant_content:
        pending_clarification = "interaction_scope"
        clarification_question = "현재 복용약끼리 비교할지, 새로 받은 약까지 포함할지 먼저 알려 주세요."

    memory.pending_clarification = pending_clarification
    memory.clarification_question = clarification_question
    await memory.save()
    context.session_memory = memory


# KIDS evidence 텍스트 구성
def _build_kids_text(items: list[dict[str, Any]]) -> str:
    if not items:
        return "KIDS 안전성 근거 없음"
    return json.dumps(items, ensure_ascii=False)


# RAG context 텍스트 구성
def _build_rag_text(items: list[dict[str, Any]]) -> str:
    if not items:
        return "RAG 참고 근거 없음"
    return json.dumps(items, ensure_ascii=False)


# 최신 guide 조회
async def _get_latest_done_guide(patient_id: int) -> Guide | None:
    return await Guide.filter(patient_id=patient_id, status=GuideStatus.DONE).order_by("-created_at", "-id").first()


# 현재 복용 약 조회
async def _get_active_meds(patient_id: int) -> list[dict[str, Any]]:
    rows = (
        await PatientMed.filter(
            patient_id=patient_id,
            is_active=True,
            confirmed_at__not_isnull=True,
        )
        .prefetch_related("drug_info_cache", "drug_catalog")
        .order_by("id")
        .all()
    )
    if not rows:
        rows = (
            await PatientMed.filter(
                patient_id=patient_id,
                is_active=True,
            )
            .prefetch_related("drug_info_cache", "drug_catalog")
            .order_by("id")
            .all()
        )

    results: list[dict[str, Any]] = []
    for row in rows:
        cache = getattr(row, "drug_info_cache", None)
        catalog = getattr(row, "drug_catalog", None)
        results.append(
            {
                "patient_med_id": int(row.id),
                "display_name": row.display_name,
                "dosage": row.dosage,
                "route": row.route,
                "notes": row.notes,
                "source_document_id": getattr(row, "source_document_id", None),
                "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
                "drug_info": {
                    "drug_name_display": getattr(cache, "drug_name_display", None),
                    "manufacturer": getattr(cache, "manufacturer", None),
                    "efficacy": getattr(cache, "efficacy", None),
                    "dosage_info": getattr(cache, "dosage_info", None),
                    "precautions": getattr(cache, "precautions", None),
                    "interactions": getattr(cache, "interactions", None),
                    "side_effects": getattr(cache, "side_effects", None),
                    "storage_method": getattr(cache, "storage_method", None),
                },
                "drug_catalog": {
                    "name": getattr(catalog, "name", None),
                    "ingredients": getattr(catalog, "ingredients", None),
                    "warnings": getattr(catalog, "warnings", None),
                    "manufacturer": getattr(catalog, "manufacturer", None),
                },
            }
        )
    return results

# 현재 복약 일정 조회
async def _get_active_schedules(patient_id: int) -> list[dict[str, Any]]:
    schedules = await MedSchedule.filter(
        patient_id=patient_id,
        status="active",
    ).all()

    if not schedules:
        return []

    schedule_ids = [int(s.id) for s in schedules]
    schedule_times = await MedScheduleTime.filter(
        schedule_id__in=schedule_ids,
        is_active=True,
    ).all()

    time_map: dict[int, list[dict[str, Any]]] = {}
    for item in schedule_times:
        schedule_id = int(item.schedule_id)
        time_map.setdefault(schedule_id, []).append(
            {
                "time_of_day": str(item.time_of_day) if item.time_of_day else None,
                "days_of_week": item.days_of_week,
            }
        )

    results: list[dict[str, Any]] = []
    for schedule in schedules:
        results.append(
            {
                "schedule_id": int(schedule.id),
                "patient_med_id": int(schedule.patient_med_id),
                "times": time_map.get(int(schedule.id), []),
            }
        )

    return results


# 건강 프로필 조회
async def _get_profile(patient_id: int) -> PatientProfile | None:
    return await PatientProfile.get_or_none(patient_id=patient_id, is_deleted=False)


async def _get_hospital_schedules(patient_id: int) -> list[HospitalSchedule]:
    return await HospitalSchedule.filter(patient_id=patient_id).order_by("scheduled_at", "id").all()


async def _get_active_dur_alerts(patient_id: int) -> list[dict[str, Any]]:
    rows = (
        await DurAlert.filter(patient_id=patient_id, is_active=True)
        .prefetch_related("patient_med", "related_patient_med")
        .order_by("-created_at", "-id")
        .all()
    )

    results: list[dict[str, Any]] = []
    for row in rows:
        patient_med = getattr(row, "patient_med", None)
        related_med = getattr(row, "related_patient_med", None)
        results.append(
            {
                "alert_type": str(getattr(row, "alert_type", "") or "").strip(),
                "level": str(getattr(row, "level", "") or "").strip(),
                "message": str(getattr(row, "message", "") or "").strip(),
                "basis_json": str(getattr(row, "basis_json", "") or "").strip(),
                "patient_med_name": str(getattr(patient_med, "display_name", "") or "").strip(),
                "related_patient_med_name": str(getattr(related_med, "display_name", "") or "").strip(),
            }
        )
    return results


async def _get_recent_adherence_summary(patient_id: int, meds: list[dict[str, Any]]) -> dict[str, Any]:
    med_name_map = {
        int(med.get("patient_med_id")): str(med.get("display_name") or "").strip()
        for med in meds
        if med.get("patient_med_id") is not None
    }
    rows = await IntakeLog.filter(patient_id=patient_id).order_by("-scheduled_at", "-id").limit(20).all()

    if not rows:
        return {
            "total": 0,
            "taken": 0,
            "missed": 0,
            "pending": 0,
            "skipped": 0,
            "recent_missed_names": [],
            "recent_lines": [],
        }

    counts = {"taken": 0, "missed": 0, "pending": 0, "skipped": 0}
    recent_missed_names: list[str] = []
    recent_lines: list[str] = []
    for row in rows:
        status = str(getattr(row, "status", "") or "").strip().lower()
        if status in counts:
            counts[status] += 1
        med_name = med_name_map.get(
            int(getattr(row, "patient_med_id", 0) or 0),
            f"약 #{getattr(row, 'patient_med_id', '')}",
        )
        scheduled_at = _format_datetime_korean(getattr(row, "scheduled_at", None))
        if status == "missed" and med_name:
            recent_missed_names.append(med_name)
        status_label = {
            "taken": "복용 완료",
            "missed": "놓침",
            "pending": "대기",
            "skipped": "건너뜀",
        }.get(status, status or "기록")
        recent_lines.append(f"{scheduled_at} {med_name} - {status_label}")

    return {
        "total": len(rows),
        "taken": counts["taken"],
        "missed": counts["missed"],
        "pending": counts["pending"],
        "skipped": counts["skipped"],
        "recent_missed_names": _dedupe_lines(recent_missed_names, limit=4),
        "recent_lines": _dedupe_lines(recent_lines, limit=4),
    }


async def _get_session_memory(session_id: int) -> ChatSessionMemory | None:
    return await ChatSessionMemory.get_or_none(session_id=session_id)


# KIDS
async def _build_kids_evidence(*, meds: list[dict[str, Any]], profile: PatientProfile | None) -> list[dict[str, Any]]:
    del profile

    client = KIDSClient()
    if not client.is_enabled():
        return []

    evidence: list[dict[str, Any]] = []
    for med in meds[:5]:
        drug_name = str(med.get("display_name") or "").strip()
        if not drug_name:
            continue
        items = await client.search_safety_evidence(drug_name)
        evidence.extend(items)

    return evidence[:10]


# RAG용 텍스트 블록 추가 헬퍼
def _append_rag_block(blocks: list[dict[str, Any]], *, source: str, title: str, content: str) -> None:
    text = (content or "").strip()
    if not text:
        return
    blocks.append(
        {
            "source": source,
            "title": title,
            "content": text,
        }
    )


# 최신 guide에서 RAG 블록 추출
def _extract_guide_rag_blocks(guide: Guide | None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if not guide:
        return blocks

    if guide.content_text:
        _append_rag_block(
            blocks,
            source="guide_text",
            title="최신 가이드 본문",
            content=guide.content_text,
        )

    if isinstance(guide.content_json, dict):
        sections = guide.content_json.get("sections") or []
        for section in sections:
            title = str(section.get("title") or "가이드 섹션")
            body = str(section.get("body") or "")
            _append_rag_block(
                blocks,
                source="guide_section",
                title=title,
                content=body,
            )

    if isinstance(guide.caregiver_summary, dict):
        _append_rag_block(
            blocks,
            source="guide_caregiver_summary",
            title="보호자 요약",
            content=json.dumps(guide.caregiver_summary, ensure_ascii=False),
        )

    return blocks


# 프로필에서 RAG 블록 추출
def _extract_profile_rag_blocks(profile: PatientProfile | None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if not profile:
        return blocks

    profile_map = {
        "흡연 정보": getattr(profile, "avg_cig_packs_per_week", None),
        "음주 정보": getattr(profile, "avg_alcohol_bottles_per_week", None),
        "수면 정보": getattr(profile, "avg_sleep_hours_per_day", None),
        "운동 정보": getattr(profile, "avg_exercise_minutes_per_day", None),
        "기저질환": getattr(profile, "conditions", None),
        "알레르기": getattr(profile, "allergies", None),
        "메모": getattr(profile, "notes", None),
    }

    for title, value in profile_map.items():
        if value is not None and str(value).strip():
            _append_rag_block(
                blocks,
                source="profile",
                title=title,
                content=str(value),
            )

    return blocks


# 스케줄에서 RAG 블록 추출
def _extract_schedule_rag_blocks(meds: list[dict[str, Any]], schedules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    schedule_text = _build_schedule_text(schedules, meds)
    if schedule_text != "등록된 복약 일정 없음":
        _append_rag_block(
            blocks,
            source="schedule",
            title="복약 일정",
            content=schedule_text,
        )
    return blocks


# 약 정보에서 RAG 블록 추출
def _extract_meds_rag_blocks(meds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    meds_text = _build_meds_text(meds)
    if meds_text != "현재 복용 약 정보 없음":
        _append_rag_block(
            blocks,
            source="meds",
            title="현재 복용 약",
            content=meds_text,
        )
    return blocks


# RAG hook (MVP)
async def _build_rag_context(
    *,
    intent: str,
    latest_guide: Guide | None,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    profile: PatientProfile | None,
    kids_evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    guide_blocks = extract_guide_blocks(latest_guide)
    profile_blocks = extract_profile_blocks(profile)
    schedule_blocks = extract_schedule_blocks(_build_schedule_text(schedules, meds))
    meds_blocks = extract_meds_blocks(_build_meds_text(meds))
    external_blocks = extract_external_blocks(
        mfds_evidence=[],
        kids_evidence=kids_evidence,
    )

    return build_rag_context(
        intent=intent,
        guide_blocks=guide_blocks,
        profile_blocks=profile_blocks,
        schedule_blocks=schedule_blocks,
        meds_blocks=meds_blocks,
        external_blocks=external_blocks,
        limit=8,
    )


# 컨텍스트 구성
async def _build_patient_chat_context(
    *,
    session_id: int,
    patient_id: int,
    include_kids_evidence: bool = True,
) -> PatientChatContext:
    profile = await _get_profile(patient_id)
    latest_guide = await _get_latest_done_guide(patient_id)
    meds = await _get_active_meds(patient_id)
    schedules = await _get_active_schedules(patient_id)
    hospital_schedules = await _get_hospital_schedules(patient_id)
    dur_alerts = await _get_active_dur_alerts(patient_id)
    adherence_summary = await _get_recent_adherence_summary(patient_id, meds)
    session_memory = await _get_session_memory(session_id)
    recent_messages = (
        await ChatMessage.filter(session_id=session_id).order_by("-created_at", "-id").limit(CHAT_HISTORY_TURNS).all()
    )
    recent_messages = list(reversed(recent_messages))

    kids_evidence = await _build_kids_evidence(meds=meds, profile=profile) if include_kids_evidence else []
    rag_context: list[dict[str, Any]] = []

    return PatientChatContext(
        patient_id=patient_id,
        profile=profile,
        latest_guide=latest_guide,
        meds=meds,
        schedules=schedules,
        hospital_schedules=hospital_schedules,
        dur_alerts=dur_alerts,
        adherence_summary=adherence_summary,
        recent_messages=recent_messages,
        session_memory=session_memory,
        kids_evidence=kids_evidence,
        rag_context=rag_context,
    )


# 질문 의도 판별
def _detect_intent(message: str) -> str:
    return _analyze_intents(message)[0]


def _analyze_intents(message: str) -> list[str]:
    normalized = (message or "").strip()
    intents: list[str] = []
    external_drug_name = _extract_external_drug_name(normalized, None)

    if _contains_any(normalized, _DAILY_CHAT_KEYWORDS):
        _append_unique(intents, "daily")
    if _contains_any(normalized, _BOT_CAPABILITY_KEYWORDS):
        _append_unique(intents, "daily")
    if _contains_any(normalized, ["두드러기", "발진"]) and _contains_any(normalized, ["약 먹고", "복용", "약 먹은 뒤"]):
        _append_unique(intents, "rash")
    if _contains_any(normalized, _RASH_KEYWORDS):
        _append_unique(intents, "rash")
    if _contains_any(normalized, _MED_DETAIL_KEYWORDS) and _contains_any(
        normalized, ["언제 먹", "언제 복용", "몇 시", "시간"]
    ):
        _append_unique(intents, "med_detail")
    if _contains_any(normalized, _PROFILE_SMOKING_KEYWORDS):
        _append_unique(intents, "profile_smoking")
    if _contains_any(normalized, _PROFILE_ALCOHOL_KEYWORDS):
        _append_unique(intents, "profile_alcohol")
    if _contains_any(normalized, _PROFILE_SLEEP_KEYWORDS):
        _append_unique(intents, "profile_sleep")
    if _contains_any(normalized, _PROFILE_EXERCISE_KEYWORDS):
        _append_unique(intents, "profile_exercise")
    if _contains_any(normalized, _PROFILE_CONDITION_KEYWORDS):
        _append_unique(intents, "profile_conditions")
    if _contains_any(normalized, _PROFILE_ALLERGY_KEYWORDS):
        _append_unique(intents, "profile_allergies")
    if _contains_any(normalized, _PROFILE_HOSPITALIZATION_KEYWORDS):
        _append_unique(intents, "profile_hospitalization")
    if _is_profile_body_query(normalized):
        _append_unique(intents, "profile_body")
    if _is_profile_summary_query(normalized):
        _append_unique(intents, "profile_summary")
    if (
        _contains_any(normalized, ["아침", "오전"])
        and _contains_any(normalized, ["저녁", "오후", "취침 전"])
        and _contains_any(normalized, ["나눠", "구분"])
    ):
        _append_unique(intents, "med_time_split")
    if _contains_any(normalized, _MED_TIME_SPLIT_KEYWORDS):
        _append_unique(intents, "med_time_split")
    if _contains_any(normalized, _MED_REGULARITY_KEYWORDS):
        _append_unique(intents, "med_regularity")
    if _contains_any(normalized, _PRN_KEYWORDS):
        _append_unique(intents, "med_prn")
    if _contains_any(normalized, _MED_DETAIL_KEYWORDS):
        _append_unique(intents, "med_detail")
    if _contains_any(normalized, _CONDITION_TREATMENT_KEYWORDS) and "external_med" not in intents:
        _append_unique(intents, "condition_general")
    if external_drug_name or _contains_any(
        normalized, ["약에 대해서 궁금", "라는 약", "라고 알아", "약 알아", "약이 궁금"]
    ):
        _append_unique(intents, "external_med")
    if _contains_any(normalized, ["같이", "상호작용", "함께"]) and _contains_any(
        normalized, _MEDICATION_CAUTION_KEYWORDS
    ):
        _append_unique(intents, "medication_caution")
    if _contains_any(normalized, ["음식", "알레르기"]) and _contains_any(normalized, ["조심", "주의"]):
        _append_unique(intents, "allergy_food")
    if _contains_any(normalized, _MED_LIST_KEYWORDS):
        _append_unique(intents, "med_list")
    if _contains_any(normalized, _HOSPITAL_SCHEDULE_KEYWORDS):
        _append_unique(intents, "hospital_schedule")
    if _contains_any(normalized, _SCHEDULE_KEYWORDS):
        _append_unique(intents, "schedule")
    if _contains_any(normalized, _CAREGIVER_CHECK_KEYWORDS):
        _append_unique(intents, "caregiver_check")
    if _contains_any(normalized, _ALLERGY_FOOD_KEYWORDS):
        _append_unique(intents, "allergy_food")
    if _contains_any(normalized, _MISSED_DOSE_KEYWORDS):
        _append_unique(intents, "missed_dose")
    if _contains_any(normalized, _EMERGENCY_GUIDANCE_KEYWORDS):
        _append_unique(intents, "emergency_guidance")
    if _contains_any(normalized, ["3가지만", "세 가지만"]) and _contains_any(normalized, ["생활"]):
        _append_unique(intents, "lifestyle_top")
    if _contains_any(normalized, _LIFESTYLE_TOP_KEYWORDS):
        _append_unique(intents, "lifestyle_top")
    if _contains_any(normalized, _SESSION_SUMMARY_KEYWORDS):
        _append_unique(intents, "session_summary")
    if _contains_any(normalized, _MEDICATION_CAUTION_KEYWORDS):
        _append_unique(intents, "medication_caution")
    if _contains_any(normalized, ["주의"]) and _contains_any(normalized, ["약"]):
        _append_unique(intents, "medication_caution")
    if _contains_any(normalized, _GENERAL_CAUTION_KEYWORDS):
        _append_unique(intents, "general_caution")
    if _contains_any(normalized, _GUIDE_SUMMARY_KEYWORDS):
        _append_unique(intents, "guide")

    return intents or ["general"]


def _resolve_answer_mode(*, intents: list[str], is_emergency: bool) -> str:
    if is_emergency:
        return "emergency"
    if "external_med" in intents:
        return "external_drug_counseling"
    if "condition_general" in intents:
        return "condition_counseling"
    if "daily" in intents:
        return "daily_chat"
    if any(intent in intents for intent in {"missed_dose", "emergency_guidance", "rash"}):
        return "safety_guidance"
    if len(intents) == 1 and intents[0] in {
        "profile_body",
        "profile_summary",
        "profile_guidance",
        "profile_smoking",
        "profile_alcohol",
        "profile_sleep",
        "profile_exercise",
        "profile_conditions",
        "profile_allergies",
        "profile_hospitalization",
        "med_list",
        "med_time_split",
        "med_regularity",
        "schedule",
        "session_summary",
        "tonight_check",
        "schedule_order",
        "adherence_priority",
        "symptom_cause",
        "observation_check",
        "school_observation",
        "cold_med_caution",
        "hospital_schedule",
    }:
        return "direct_fact"
    if any(
        intent in intents
        for intent in {"caregiver_check", "self_check", "lifestyle_top", "general_caution", "guide", "profile_guidance"}
    ):
        return "record_counseling"
    return "general_counseling"


def _extract_condition_name(message: str, profile: PatientProfile | None) -> str | None:
    normalized = (message or "").strip()
    profile_conditions = _split_text_items(getattr(profile, "conditions", None) if profile else None)
    generic_conditions = [
        "골다공증",
        "고혈압",
        "당뇨",
        "제2형 당뇨",
        "고지혈증",
        "빈혈",
        "천식",
        "알레르기 비염",
        "비염",
        "심부전",
        "역류성식도염",
        "위식도역류질환",
        "갑상선기능저하증",
    ]
    for condition in profile_conditions + generic_conditions:
        if condition and _contains_keyword(normalized, condition):
            return condition
    return None


def _is_profile_caution_query(message: str) -> bool:
    normalized = (message or "").strip()
    return _contains_any(
        normalized,
        [
            "내 기록 기준",
            "지금 내 기록 기준",
            "건강기록 기준",
            "기록 기준",
            "주의할 점",
            "조심할 점",
            "내가 주의",
            "내 기록으로",
            "건강프로필 기준으로",
            "건강 프로필 기준으로",
        ],
    )


def _is_guidance_query(message: str) -> bool:
    normalized = (message or "").strip()
    return _contains_any(
        normalized,
        [
            "먼저 뭐 봐야",
            "먼저 봐야",
            "먼저 봐야 할",
            "먼저 무엇을 봐야",
            "먼저 확인해야",
            "어떻게 관리",
            "관리해야",
            "전반적으로 조언",
            "조언해줘",
            "생활관리에서",
            "생활 관리에서",
            "중요한 점",
            "제일 중요한 점",
            "무엇이 중요",
        ],
    )


def _is_profile_body_query(message: str) -> bool:
    normalized = (message or "").strip()
    return _contains_any(normalized, _PROFILE_BODY_KEYWORDS)


def _is_profile_summary_query(message: str) -> bool:
    normalized = (message or "").strip()
    return _contains_any(normalized, _PROFILE_SUMMARY_KEYWORDS) or (
        _contains_any(normalized, ["전반적으로", "전반적", "요약"])
        and _contains_any(normalized, ["건강프로필", "건강 프로필", "내 프로필"])
    )


def _is_profile_related_query(message: str) -> bool:
    normalized = _normalize_user_message(message)
    return (
        _is_profile_body_query(normalized)
        or _is_profile_summary_query(normalized)
        or _contains_any(
            normalized,
            _PROFILE_SMOKING_KEYWORDS
            + _PROFILE_ALCOHOL_KEYWORDS
            + _PROFILE_SLEEP_KEYWORDS
            + _PROFILE_EXERCISE_KEYWORDS
            + _PROFILE_CONDITION_KEYWORDS
            + _PROFILE_ALLERGY_KEYWORDS
            + _PROFILE_HOSPITALIZATION_KEYWORDS,
        )
    )


def _detect_time_period(message: str) -> str | None:
    normalized = (message or "").strip()
    if _contains_any(normalized, ["오늘 밤", "오늘 저녁", "자기 전", "취침 전", "밤에"]):
        return "night"
    if _contains_any(normalized, ["저녁", "저녁 먹고", "저녁에"]):
        return "evening"
    if _contains_any(normalized, ["아침", "아침에", "아침 먹고"]):
        return "morning"
    return None


def _was_waiting_for_interaction_scope(
    recent_messages: list[ChatMessage],
    session_memory: ChatSessionMemory | None = None,
) -> bool:
    if session_memory and getattr(session_memory, "pending_clarification", None) == "interaction_scope":
        return True
    for recent in reversed(recent_messages):
        role = str(getattr(recent, "role", "") or "")
        content = str(getattr(recent, "content", "") or "")
        if role == "assistant" and "현재 복용약끼리 비교할지, 새로 받은 약까지 포함할지" in content:
            return True
        if role == "user" and content.strip():
            break
    return False


def _is_hospital_followup_query(message: str, session_memory: ChatSessionMemory | None) -> bool:
    normalized = (message or "").strip()
    if not normalized or not session_memory:
        return False
    recent_topic = str(getattr(session_memory, "recent_topic", "") or "").strip()
    pending = str(getattr(session_memory, "pending_clarification", "") or "").strip()
    if recent_topic != "hospital_schedule" and pending != "hospital_schedule_clarification":
        return False
    if normalized in _AFFIRMATIVE_SHORT_REPLIES:
        return True
    if _contains_any(
        normalized,
        ["그 다음", "그다음", "다다음", "다음 외래", "다음 진료", "다음 검사", "다음 일정", "그 일정", "그거"],
    ):
        return True
    return False


def _should_reset_pending_clarification(message: str) -> bool:
    normalized = _normalize_user_message(message)
    if not normalized:
        return False
    if _contains_any(normalized, _CLARIFICATION_RESET_PREFIXES):
        return True
    if _contains_any(normalized, _SYMPTOM_WORDS) and not _contains_any(
        normalized,
        _MEDICATION_CAUTION_KEYWORDS
        + ["같이 먹", "함께 먹", "추가로 먹", "먹어도 돼", "복용해도 돼", "상호작용", "조합"],
    ):
        return True
    return False


def _analyze_question(
    *,
    message: str,
    meds: list[dict[str, Any]],
    recent_messages: list[ChatMessage],
    requester_role: RequesterRole,
    profile: PatientProfile | None,
    session_memory: ChatSessionMemory | None,
) -> QuestionAnalysis:
    normalized = _normalize_user_message(message)
    reset_pending_clarification = _should_reset_pending_clarification(normalized)
    profile_query = _is_profile_related_query(normalized)
    hospital_query = _contains_any(normalized, _HOSPITAL_SCHEDULE_KEYWORDS)
    hospital_followup_query = _is_hospital_followup_query(normalized, session_memory)
    med_list_query = _contains_any(normalized, _MED_LIST_KEYWORDS)
    current_meds_interaction_query = _contains_any(
        normalized,
        _MED_LIST_KEYWORDS
        + ["오늘 약", "오늘 먹는 약", "오늘 복용약", "지금 먹는 약", "현재 먹는 약", "현재 약", "복용약"],
    ) and _contains_any(normalized, ["같이", "상호작용", "함께", "조합", "조심", "주의", "같이 먹", "함께 먹"])
    target_med = _extract_target_med(
        message=normalized,
        meds=meds,
        recent_messages=recent_messages,
        session_memory=session_memory,
    )
    external_drug_name = None
    if (
        not profile_query
        and not hospital_query
        and not hospital_followup_query
        and not med_list_query
        and not current_meds_interaction_query
    ):
        external_drug_name = (
            None
            if target_med
            else _extract_external_drug_name(
                normalized,
                recent_messages,
                session_memory=session_memory,
            )
        )
    explicit_external_caution_query = bool(
        external_drug_name
        and _contains_any(normalized, ["주의사항", "주의할 점", "부작용", "용도", "무슨 약", "어떤 약", "뭐야"])
        and not _contains_any(
            normalized, ["같이 먹", "함께 먹", "추가로 먹", "먹어도 돼", "복용해도 돼", "조합", "상호작용"]
        )
    )
    explicit_new_drug_interaction_query = bool(
        _contains_any(
            normalized, ["같이 먹", "함께 먹", "추가로 먹", "먹어도 돼", "복용해도 돼", "괜찮아", "조합", "상호작용"]
        )
        and (external_drug_name or _contains_any(normalized, ["새 감기약", "새 약", "감기약"]))
    )
    target_condition = _extract_condition_name(normalized, profile)
    time_period = _detect_time_period(normalized)
    bracketed_drug_name = _extract_bracketed_drug_name(normalized)
    if (
        target_condition
        and external_drug_name
        and not any(str(external_drug_name).endswith(suffix) for suffix in _EXTERNAL_DRUG_SUFFIXES)
    ):
        external_drug_name = None
    is_emergency, emergency_message = _detect_emergency(normalized)
    if (
        not reset_pending_clarification
        and _was_waiting_for_interaction_scope(recent_messages, session_memory)
        and _contains_any(normalized, ["현재 복용약끼리", "현재 약끼리", "복용약끼리", "현재 먹는 약끼리"])
    ):
        return QuestionAnalysis(
            raw_message=normalized,
            intents=["medication_caution"],
            primary_intent="medication_caution",
            target_med=None,
            external_drug_name=None,
            target_condition=target_condition,
            time_period=time_period,
            is_emergency=is_emergency,
            emergency_message=emergency_message,
            answer_mode="record_counseling",
        )

    raw_intents: list[str]
    if is_emergency:
        raw_intents = ["emergency"]
    elif _contains_any(normalized, _DAILY_CHAT_KEYWORDS + _BOT_CAPABILITY_KEYWORDS):
        raw_intents = ["daily"]
    elif _contains_any(normalized, _MISSED_DOSE_KEYWORDS):
        raw_intents = (
            ["missed_dose", "emergency_guidance"]
            if _contains_any(normalized, _EMERGENCY_GUIDANCE_KEYWORDS)
            else ["missed_dose"]
        )
    elif _contains_any(normalized, _RASH_KEYWORDS):
        raw_intents = ["rash"]
    elif bracketed_drug_name:
        recent_topic = str(getattr(session_memory, "recent_topic", "") or "").strip()
        pending = str(getattr(session_memory, "pending_clarification", "") or "").strip()
        if target_med and recent_topic == "med_schedule":
            raw_intents = ["med_detail", "schedule"]
        elif target_med and pending == "interaction_scope":
            raw_intents = ["medication_caution", "med_detail"]
        elif pending == "interaction_scope":
            raw_intents = ["medication_caution", "external_med"]
        elif target_med:
            raw_intents = ["med_detail"]
        else:
            raw_intents = ["external_med"]
    elif current_meds_interaction_query:
        raw_intents = ["medication_caution", "med_list"]
    elif explicit_new_drug_interaction_query:
        raw_intents = ["medication_caution", "external_med"]
    elif explicit_external_caution_query:
        raw_intents = ["external_med"]
    elif _is_guidance_query(normalized):
        raw_intents = ["profile_guidance"]
    elif _is_profile_summary_query(normalized):
        raw_intents = ["profile_summary"]
        if _contains_any(normalized, _PROFILE_SLEEP_KEYWORDS):
            raw_intents.append("profile_sleep")
        if _contains_any(normalized, _PROFILE_EXERCISE_KEYWORDS):
            raw_intents.append("profile_exercise")
    elif hospital_query or hospital_followup_query:
        raw_intents = ["hospital_schedule"]
    elif _is_profile_body_query(normalized):
        raw_intents = ["profile_body"]
        if _contains_any(normalized, _PROFILE_SLEEP_KEYWORDS):
            raw_intents.append("profile_sleep")
        if _contains_any(normalized, _PROFILE_EXERCISE_KEYWORDS):
            raw_intents.append("profile_exercise")
    elif external_drug_name:
        if _contains_any(
            normalized,
            _MEDICATION_CAUTION_KEYWORDS
            + _COLD_MED_CAUTION_KEYWORDS
            + ["같이 먹", "함께 먹", "추가로 먹", "먹어도 돼", "복용해도 돼", "괜찮아", "같이 복용"],
        ):
            raw_intents = ["medication_caution", "external_med"]
        else:
            raw_intents = ["external_med"]
    elif target_condition and _contains_any(normalized, _CONDITION_TREATMENT_KEYWORDS + _MED_DETAIL_KEYWORDS):
        raw_intents = ["condition_general"]
    elif _is_profile_caution_query(normalized):
        raw_intents = ["general_caution"]
    elif _contains_any(
        normalized, _TONIGHT_CHECK_KEYWORDS + ["오늘 약", "오늘 먹을 약", "오늘 복용할 약", "오늘 내가 먹어야 할 약"]
    ):
        raw_intents = ["tonight_check"]
    elif _contains_any(normalized, _SCHEDULE_ORDER_KEYWORDS):
        raw_intents = ["schedule_order"]
    elif _contains_any(
        normalized,
        _ADHERENCE_PRIORITY_KEYWORDS
        + ["안 빼먹어야", "꼭 안 빼먹어야", "꼭 챙겨야", "자주 놓치는 약", "자주 놓치", "놓치는 약"],
    ):
        raw_intents = ["adherence_priority"]
    elif _contains_any(normalized, _SCHOOL_OBSERVATION_KEYWORDS):
        raw_intents = ["school_observation"]
    elif _contains_any(normalized, _COLD_MED_CAUTION_KEYWORDS):
        raw_intents = ["cold_med_caution"]
    elif target_med and _contains_any(normalized, _OBSERVATION_CHECK_KEYWORDS + _SYMPTOM_WORDS):
        raw_intents = ["observation_check"]
    elif _contains_any(normalized, _SYMPTOM_WORDS) and _contains_any(normalized, _SYMPTOM_GUIDANCE_KEYWORDS):
        raw_intents = ["symptom_cause"]
    elif _contains_any(normalized, _SYMPTOM_WORDS) and _contains_any(
        normalized, _SYMPTOM_CAUSE_KEYWORDS + _FIRST_CHECK_KEYWORDS
    ):
        raw_intents = ["symptom_cause"]
    elif _contains_any(normalized, _FOLLOWUP_MED_REFERENCES) and _contains_any(
        normalized, _SCHEDULE_KEYWORDS + _MED_TIME_SPLIT_KEYWORDS
    ):
        raw_intents = ["med_detail", "schedule"]
    elif target_med and _contains_any(normalized, _SCHEDULE_KEYWORDS + _MED_TIME_SPLIT_KEYWORDS):
        raw_intents = ["med_detail", "schedule"]
    elif target_med:
        raw_intents = ["med_detail"]
        if _contains_any(normalized, _MEDICATION_CAUTION_KEYWORDS):
            raw_intents.append("medication_caution")
        if _contains_any(normalized, _PRN_KEYWORDS + _MED_REGULARITY_KEYWORDS):
            raw_intents.append("med_prn")
    elif med_list_query:
        raw_intents = ["med_list"]
        if _contains_any(normalized, _MED_TIME_SPLIT_KEYWORDS):
            raw_intents.append("med_time_split")
        if _contains_any(normalized, _MED_REGULARITY_KEYWORDS):
            raw_intents.append("med_regularity")
    elif _contains_any(normalized, _LIFESTYLE_TOP_KEYWORDS):
        raw_intents = ["lifestyle_top"]
    elif _is_guidance_query(normalized) and _contains_any(
        normalized, _PROFILE_SLEEP_KEYWORDS + _PROFILE_EXERCISE_KEYWORDS + ["건강프로필", "건강 프로필"]
    ):
        raw_intents = ["profile_guidance"]
    elif _contains_any(normalized, _PROFILE_SLEEP_KEYWORDS) and _contains_any(normalized, _PROFILE_EXERCISE_KEYWORDS):
        raw_intents = ["profile_sleep", "profile_exercise"]
    elif _contains_any(normalized, _PROFILE_SLEEP_KEYWORDS):
        raw_intents = ["profile_sleep"]
    elif _contains_any(normalized, _PROFILE_EXERCISE_KEYWORDS):
        raw_intents = ["profile_exercise"]
    elif _contains_any(normalized, _PROFILE_ALCOHOL_KEYWORDS):
        raw_intents = ["profile_alcohol"]
    elif _contains_any(normalized, _PROFILE_SMOKING_KEYWORDS):
        raw_intents = ["profile_smoking"]
    elif _contains_any(normalized, _CAREGIVER_CHECK_KEYWORDS):
        raw_intents = ["caregiver_check"]
    elif _contains_any(normalized, _ALLERGY_FOOD_KEYWORDS):
        raw_intents = ["allergy_food"]
    elif _contains_any(normalized, _SCHEDULE_KEYWORDS):
        raw_intents = ["schedule"]
    elif _contains_any(normalized, _SESSION_SUMMARY_KEYWORDS):
        raw_intents = ["session_summary"]
    elif _contains_any(normalized, _GUIDE_SUMMARY_KEYWORDS) and not target_med and not external_drug_name:
        raw_intents = ["guide"]
    else:
        raw_intents = ["general"]

    intents = _normalize_intent_order(raw_intents, requester_role)
    answer_mode = _resolve_answer_mode(intents=intents, is_emergency=is_emergency)

    return QuestionAnalysis(
        raw_message=normalized,
        intents=intents,
        primary_intent=intents[0],
        target_med=target_med,
        external_drug_name=external_drug_name,
        target_condition=target_condition,
        time_period=time_period,
        is_emergency=is_emergency,
        emergency_message=emergency_message,
        answer_mode=answer_mode,
    )


# 보호자용 관리형 응답 변환
def _to_caregiver_style(*, answer: str, audience: str) -> str:
    text = str(answer or "").strip()
    if audience == "senior" and "낙상" not in text and ("어지러" in text or "혈압" in text or "보행" in text):
        text += "\n어지러움이나 보행 불안정이 있으면 낙상 위험도 함께 확인해 주세요."
    return text


# 프로필 기반 직접 응답
def _answer_profile_intent(
    *,
    intent: str,
    profile: PatientProfile | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    if not profile:
        base = f"{target_label} 기준으로 등록된 건강 프로필이 없습니다."
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    if intent == "profile_smoking":
        smoker = getattr(profile, "is_smoker", None)
        value = getattr(profile, "avg_cig_packs_per_week", None)
        if value is None and smoker is None:
            base = f"{target_label} 기준으로 흡연 정보가 등록되어 있지 않습니다."
        elif value is None and smoker is False:
            base = f"{target_label} 기준으로 비흡연으로 기록되어 있습니다."
        elif value is None:
            base = f"{target_label} 기준으로 흡연 중으로 보이지만 주간 흡연량은 등록되어 있지 않습니다."
        else:
            prefix = "흡연 중이며 " if smoker is not False else "현재 비흡연으로 기록되어 있으나, "
            base = f"{target_label} 기준으로 {prefix}주에 평균 {value}갑 정도 흡연하는 것으로 기록되어 있습니다."
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    if intent == "profile_alcohol":
        value = getattr(profile, "avg_alcohol_bottles_per_week", None)
        if value is None:
            base = f"{target_label} 기준으로 주간 음주량 정보가 등록되어 있지 않습니다."
        else:
            base = f"{target_label} 기준으로 주에 평균 {value}병 정도 음주하는 것으로 기록되어 있습니다."
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    if intent == "profile_sleep":
        value = getattr(profile, "avg_sleep_hours_per_day", None)
        if value is None:
            base = f"{target_label} 기준으로 평균 수면 시간 정보가 등록되어 있지 않습니다."
        else:
            base = f"{target_label} 기준으로 하루 평균 {value}시간 정도 수면하는 것으로 기록되어 있습니다."
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    if intent == "profile_exercise":
        value = getattr(profile, "avg_exercise_minutes_per_day", None)
        if value is None:
            base = f"{target_label} 기준으로 평균 운동 시간 정보가 등록되어 있지 않습니다."
        else:
            base = f"{target_label} 기준으로 하루 평균 {value}분 정도 운동하는 것으로 기록되어 있습니다."
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    if intent == "profile_body":
        height_cm = getattr(profile, "height_cm", None)
        weight_kg = getattr(profile, "weight_kg", None)
        bmi = getattr(profile, "bmi", None)
        points: list[str] = []
        if height_cm is not None:
            points.append(f"키는 {height_cm}cm입니다.")
        if weight_kg is not None:
            points.append(f"몸무게는 {weight_kg}kg입니다.")
        if bmi is not None:
            bmi_category = _bmi_category_text(bmi)
            if bmi_category:
                points.append(f"BMI는 {bmi}이며 {bmi_category}입니다.")
            else:
                points.append(f"BMI는 {bmi}입니다.")
        if not points:
            base = f"{target_label} 기준으로 키, 몸무게, BMI 정보가 등록되어 있지 않습니다."
        else:
            base = f"{target_label} 기준 건강 프로필 수치는 다음과 같습니다.\n" + "\n".join(
                f"- {point}" for point in points
            )
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    if intent == "profile_summary":
        lines = _build_profile_summary_lines(profile)
        if not lines:
            base = f"{target_label} 기준으로 요약할 건강 프로필 정보가 아직 충분하지 않습니다."
        else:
            base = f"{target_label} 기준 건강 프로필을 요약하면 다음과 같습니다.\n" + "\n".join(
                f"- {line}" for line in lines[:6]
            )
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    if intent == "profile_conditions":
        conditions = _split_text_items(getattr(profile, "conditions", None))
        if not conditions:
            base = f"{target_label} 기준으로 등록된 기저질환이나 건강 상태 정보가 없습니다."
        else:
            base = f"{target_label} 기준 건강 상태는 다음과 같이 기록되어 있습니다.\n" + "\n".join(
                f"- {condition}" for condition in conditions[:5]
            )
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    if intent == "profile_allergies":
        allergies = _split_text_items(getattr(profile, "allergies", None))
        if not allergies:
            base = f"{target_label} 기준으로 등록된 알레르기 정보가 없습니다."
        else:
            base = f"{target_label} 기준 알레르기 정보는 다음과 같습니다.\n" + "\n".join(
                f"- {allergy}" for allergy in allergies[:5]
            )
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    if intent == "profile_hospitalization":
        is_hospitalized = getattr(profile, "is_hospitalized", None)
        discharge_date = getattr(profile, "discharge_date", None)
        if is_hospitalized is None and discharge_date is None:
            base = f"{target_label} 기준으로 입원/퇴원 정보가 등록되어 있지 않습니다."
        elif is_hospitalized is True:
            base = f"{target_label} 기준으로 현재 입원 중으로 기록되어 있습니다."
            if discharge_date:
                base += f"\n- 퇴원 예정 또는 기록된 퇴원일: {discharge_date}"
        else:
            base = f"{target_label} 기준으로 현재 입원 중은 아닌 것으로 기록되어 있습니다."
            if discharge_date:
                base += f"\n- 기록된 퇴원일: {discharge_date}"
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    return None


def _answer_profile_guidance_intent(
    *,
    message: str,
    profile: PatientProfile | None,
    guide: Guide | None,
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    if not profile and not guide:
        return None

    current_points, general_points, next_points = _build_profile_guidance_sections(
        message=message,
        profile=profile,
        guide=guide,
        adherence_summary=adherence_summary,
    )

    if not current_points and not general_points and not next_points:
        return None

    base = _compose_medical_sections(
        current_record_points=current_points,
        general_info_points=general_points,
        next_check_points=next_points,
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


# 현재 복용 약 목록 직접 응답
def _answer_med_list_intent(
    *,
    meds: list[dict[str, Any]],
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    if not meds:
        base = f"{target_label} 기준으로 현재 확인되는 복용 약 정보가 없습니다."
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    med_lines: list[str] = []
    for med in meds:
        name = med.get("display_name") or "약 이름 없음"
        dosage = med.get("dosage")
        notes = med.get("notes")
        chunk = name
        if dosage:
            chunk += f" {dosage}"
        if notes:
            chunk += f" ({notes})"
        med_lines.append(f"- {chunk}")

    base = f"{target_label} 기준으로 현재 복용 중인 약은 다음과 같습니다.\n" + "\n".join(med_lines)
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _extract_target_med(
    *,
    message: str,
    meds: list[dict[str, Any]],
    recent_messages: list[ChatMessage] | None = None,
    session_memory: ChatSessionMemory | None = None,
) -> dict[str, Any] | None:
    normalized = _normalize_user_message(message)
    bracketed_name = _extract_bracketed_drug_name(normalized)
    if bracketed_name:
        for med in meds:
            name = str(med.get("display_name") or "").strip()
            if name and (_contains_keyword(bracketed_name, name) or _contains_keyword(name, bracketed_name)):
                return med

    for med in meds:
        name = str(med.get("display_name") or "").strip()
        if name and _contains_keyword(normalized, name):
            return med

    fuzzy_matched = _find_best_med_match(query=normalized, meds=meds)
    if fuzzy_matched:
        return fuzzy_matched

    if recent_messages and _contains_any(normalized, _FOLLOWUP_MED_REFERENCES):
        for recent in reversed(recent_messages):
            recent_content = str(getattr(recent, "content", "") or "")
            for med in meds:
                name = str(med.get("display_name") or "").strip()
                if name and _contains_keyword(recent_content, name):
                    return med

    if session_memory and _contains_any(normalized, _FOLLOWUP_MED_REFERENCES):
        remembered_name = str(getattr(session_memory, "recent_drug_name", "") or "").strip()
        if remembered_name:
            for med in meds:
                name = str(med.get("display_name") or "").strip()
                if name and name == remembered_name:
                    return med

    return None


def _has_record_context(context: PatientChatContext) -> bool:
    return bool(
        context.profile or context.meds or context.schedules or context.hospital_schedules or context.latest_guide
    )


def _has_required_context_for_request(
    *,
    analysis: QuestionAnalysis,
    plan: ChatPlan | None,
    context: PatientChatContext,
) -> bool:
    primary = analysis.primary_intent
    topic = plan.topic if plan else ""

    if primary in {"daily", "general", "external_med", "condition_general", "guide"}:
        return True

    if primary in {
        "profile_body",
        "profile_summary",
        "profile_smoking",
        "profile_alcohol",
        "profile_sleep",
        "profile_exercise",
        "profile_conditions",
        "profile_allergies",
        "profile_hospitalization",
    }:
        return context.profile is not None

    if primary == "profile_guidance":
        return bool(context.profile or context.latest_guide or context.adherence_summary.get("total"))

    if primary in {
        "med_list",
        "med_detail",
        "med_time_split",
        "med_regularity",
        "med_prn",
        "schedule",
        "tonight_check",
        "schedule_order",
        "adherence_priority",
        "missed_dose",
        "self_check",
        "caregiver_check",
    }:
        return bool(context.meds or context.schedules or context.adherence_summary.get("total"))

    if primary == "medication_caution":
        return bool(context.meds or analysis.external_drug_name)

    if primary == "general_caution":
        return bool(
            context.profile
            or context.latest_guide
            or context.meds
            or context.schedules
            or context.adherence_summary.get("total")
        )

    if primary == "hospital_schedule":
        return bool(context.hospital_schedules)

    if primary in {"session_summary", "lifestyle_top"}:
        return _has_record_context(context)

    if topic == "profile":
        return bool(context.profile or context.latest_guide or context.adherence_summary.get("total"))
    if topic in {"current_meds", "med_schedule", "drug_interaction"}:
        return bool(context.meds or context.schedules or context.adherence_summary.get("total"))
    if topic == "hospital_schedule":
        return bool(context.hospital_schedules)

    return _has_record_context(context)


def _resolve_data_readiness(context: PatientChatContext) -> str:
    has_profile = context.profile is not None
    has_meds = bool(context.meds)
    has_schedules = bool(context.schedules)
    has_hospital = bool(context.hospital_schedules)
    has_guide = context.latest_guide is not None
    has_adherence = bool(context.adherence_summary.get("total"))

    score = sum([has_profile, has_meds, has_schedules, has_hospital, has_guide, has_adherence])
    if score == 0:
        return "empty"
    if score <= 2:
        return "partial"
    return "rich"


def _is_personalized_request(*, analysis: QuestionAnalysis, plan: ChatPlan | None) -> bool:
    if analysis.primary_intent in _PERSONALIZED_INTENTS:
        return True
    if analysis.primary_intent in {"daily", "general", "external_med", "condition_general"}:
        return False
    if plan and plan.topic in {"profile", "hospital_schedule", "current_meds", "med_schedule", "drug_interaction"}:
        return True
    return False


def _build_record_required_reply(
    *,
    analysis: QuestionAnalysis,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    if analysis.primary_intent in {"daily", "general", "external_med", "condition_general"}:
        base = (
            "현재 기록이 충분하지 않아도 일반적인 기준으로는 안내드릴 수 있습니다. "
            "맞춤형 설명이 필요하면 건강 프로필이나 복약 정보를 더 등록해 주세요."
        )
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    if analysis.primary_intent in {
        "med_list",
        "schedule",
        "med_detail",
        "medication_caution",
        "tonight_check",
        "schedule_order",
    }:
        base = (
            "현재 등록된 복약 정보가 없어 맞춤 복약 답변은 아직 어렵습니다. "
            "대신 일반적인 약 정보나 복용 시 주의점은 안내할 수 있습니다. 정확한 복약 상담을 원하시면 처방 문서나 복약 정보를 먼저 등록해 주세요."
        )
    elif analysis.primary_intent in {
        "profile_body",
        "profile_summary",
        "profile_guidance",
        "profile_sleep",
        "profile_exercise",
        "profile_conditions",
        "profile_allergies",
    }:
        base = (
            "현재 등록된 건강 프로필이 충분하지 않아 맞춤 건강 답변은 제한됩니다. "
            "건강 프로필을 입력하면 BMI, 수면, 운동, 알레르기, 기저질환 기준으로 더 정확히 안내드릴 수 있습니다."
        )
    elif analysis.primary_intent == "hospital_schedule":
        base = (
            "현재 연결된 병원 일정이 없어 맞춤 예약 확인은 어렵습니다. "
            "일정이 등록되면 다음 외래나 검사 일정을 바로 안내드릴 수 있습니다."
        )
    else:
        base = (
            f"{target_label} 기준 기록이 아직 충분하지 않아 개인화 답변은 제한됩니다. "
            "일반적인 약 정보나 건강 정보는 안내할 수 있고, 건강 프로필이나 처방 문서를 등록하면 더 정확히 도와드릴 수 있습니다."
        )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _extract_external_drug_name(
    message: str,
    recent_messages: list[ChatMessage] | None = None,
    *,
    session_memory: ChatSessionMemory | None = None,
) -> str | None:
    normalized = _normalize_user_message(message)
    bracketed_name = _extract_bracketed_drug_name(normalized)
    if bracketed_name:
        return bracketed_name
    if _contains_any(
        normalized,
        _MED_LIST_KEYWORDS
        + ["현재 약", "지금 먹는 약", "복용약", "현재 복용약", "같이 먹", "함께 먹", "조합", "상호작용"],
    ):
        return None
    patterns = [
        r"([가-힣A-Za-z0-9]+)라고\s*알아",
        r"([가-힣A-Za-z0-9]+)라는\s*약",
        r"([가-힣A-Za-z0-9]+)은\s*어떤\s*약",
        r"([가-힣A-Za-z0-9]+)[이가은는]\s*무슨\s*약",
        r"([가-힣A-Za-z0-9]+)[이가은는]\s*어떤\s*약",
        r"([가-힣A-Za-z0-9]+)[이가은는]\s*뭐야",
        r"([가-힣A-Za-z0-9]+)에\s*대해서\s*알려",
        r"([가-힣A-Za-z0-9]+)에대해서\s*알려",
        r"([가-힣A-Za-z0-9]+)\s*알려줘",
        r"([가-힣A-Za-z0-9]+)\s*설명해줘",
        r"([가-힣A-Za-z0-9]+)의\s*(용도|주의사항|부작용)",
        r"([가-힣A-Za-z0-9]+)[를을은는이가]\s*(새로\s*처방|처방받|먹는\s*약|용도|부작용|주의사항)",
        r"([가-힣A-Za-z0-9]+)\s*정보좀",
        r"([가-힣A-Za-z0-9]+)\s*정보\s*좀",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            candidate = match.group(1).strip()
            if len(candidate) >= 2 and candidate not in _EXTERNAL_DRUG_STOPWORDS:
                return candidate

    if _contains_any(normalized, _EXTERNAL_DRUG_CONTEXT_KEYWORDS + _EXTERNAL_DRUG_QUERY_KEYWORDS):
        tokens = [token.strip() for token in re.split(r"[\s,./()]+", normalized) if token.strip()]
        preferred: list[str] = []
        for token in tokens:
            if token in _EXTERNAL_DRUG_STOPWORDS:
                continue
            if len(token) < 2:
                continue
            if _contains_any(token, _EXTERNAL_DRUG_CONTEXT_KEYWORDS):
                continue
            if any(ch.isdigit() for ch in token):
                continue
            if any(token.endswith(suffix) for suffix in _EXTERNAL_DRUG_SUFFIXES):
                preferred.append(token)
        if preferred:
            return preferred[0]

    if recent_messages and _contains_any(normalized, _EXTERNAL_MED_FOLLOWUP_KEYWORDS):
        for recent in reversed(recent_messages):
            recent_content = str(getattr(recent, "content", "") or "").strip()
            for pattern in patterns:
                match = re.search(pattern, recent_content)
                if match:
                    candidate = match.group(1).strip()
                    if len(candidate) >= 2 and candidate not in _EXTERNAL_DRUG_STOPWORDS:
                        return candidate
            if _contains_any(recent_content, _EXTERNAL_DRUG_CONTEXT_KEYWORDS):
                tokens = [token.strip() for token in re.split(r"[\s,./()]+", recent_content) if token.strip()]
                preferred: list[str] = []
                for token in tokens:
                    if token in _EXTERNAL_DRUG_STOPWORDS or len(token) < 2 or any(ch.isdigit() for ch in token):
                        continue
                    if _contains_any(token, _EXTERNAL_DRUG_CONTEXT_KEYWORDS):
                        continue
                    if any(token.endswith(suffix) for suffix in _EXTERNAL_DRUG_SUFFIXES):
                        preferred.append(token)
                if preferred:
                    return preferred[0]
    if session_memory and _contains_any(normalized, _FOLLOWUP_MED_REFERENCES + _EXTERNAL_MED_FOLLOWUP_KEYWORDS):
        remembered_name = str(getattr(session_memory, "recent_external_drug_name", "") or "").strip()
        if remembered_name:
            return remembered_name
    return None


async def _lookup_external_med_info(drug_name: str) -> dict[str, Any]:
    result: dict[str, Any] = {"mfds": None, "kids": []}
    mfds_service = MfdsService()
    kids_client = KIDSClient()
    normalized_query = _compact_text(drug_name).lower()

    try:
        mfds_response = await mfds_service.search_easy_drug_info(drug_name=drug_name, num_of_rows=1)
        if mfds_response.items:
            for item in mfds_response.items:
                item_name = _compact_text(getattr(item, "item_name", "")).lower()
                if normalized_query and item_name and (normalized_query in item_name or item_name in normalized_query):
                    result["mfds"] = item
                    break
    except Exception:
        logger.exception("external med mfds lookup failed drug=%s", _mask_log_value(drug_name))

    try:
        if kids_client.is_enabled():
            kids_items = await kids_client.search_safety_evidence(drug_name)
            filtered_kids: list[dict[str, Any]] = []
            for item in kids_items:
                content = _compact_text(str(item.get("content") or "")).lower()
                if normalized_query and content and normalized_query in content:
                    filtered_kids.append(item)
            result["kids"] = filtered_kids[:5]
    except Exception:
        logger.exception("external med kids lookup failed drug=%s", _mask_log_value(drug_name))

    return result


def _build_external_drug_text(*, drug_name: str | None, lookup: dict[str, Any] | None) -> str:
    clean_name = str(drug_name or "").strip()
    if not clean_name:
        return "질문 관련 외부 약 정보 없음"

    if not lookup:
        return f"- 질문한 외부 약 이름: {clean_name}"

    mfds_item = lookup.get("mfds")
    kids_items = lookup.get("kids") or []
    parts = [f"- 질문한 외부 약 이름: {clean_name}"]

    if mfds_item:
        item_name = str(getattr(mfds_item, "item_name", "") or clean_name).strip()
        efficacy = _first_clean_line(getattr(mfds_item, "efficacy", None))
        precautions = _first_clean_line(getattr(mfds_item, "precautions", None))
        dosage_info = _first_clean_line(getattr(mfds_item, "dosage_info", None))
        if item_name:
            parts.append(f"- MFDS 약 이름: {item_name}")
        if efficacy:
            parts.append(f"- MFDS 용도: {efficacy}")
        if precautions:
            parts.append(f"- MFDS 주의사항: {precautions}")
        if dosage_info:
            parts.append(f"- MFDS 복용 참고: {dosage_info}")

    if kids_items:
        first_kids = _first_clean_line(kids_items[0].get("content"))
        if first_kids:
            parts.append(f"- KIDS 안전 근거: {first_kids}")

    if len(parts) == 1:
        parts.append("- 외부 의약 정보 근거는 아직 직접 확인되지 않았습니다.")

    return "\n".join(parts)


def _should_prefer_llm(*, analysis: QuestionAnalysis) -> bool:
    return analysis.answer_mode in {"record_counseling", "general_counseling", "condition_counseling"}


def _answer_med_time_split_intent(
    *,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    med_name_map = {int(med.get("patient_med_id")): med for med in meds if med.get("patient_med_id") is not None}
    morning: list[str] = []
    evening: list[str] = []
    other: list[str] = []

    for schedule in schedules:
        patient_med_id = int(schedule.get("patient_med_id"))
        med = med_name_map.get(patient_med_id, {})
        label = med.get("display_name") or f"약 #{patient_med_id}"
        dosage = med.get("dosage")
        notes = str(med.get("notes") or "").strip()
        shown = f"{label} {dosage}".strip()
        if any(keyword in notes for keyword in ["필요", "열날", "증상", "통증 시"]):
            other.append(f"{shown} (필요 시 복용)")
            continue
        times = schedule.get("times") or []
        if not times:
            other.append(shown)
            continue
        for item in times:
            time_of_day = str(item.get("time_of_day") or "")
            hour = int(time_of_day.split(":")[0]) if ":" in time_of_day else -1
            if 4 <= hour < 12:
                morning.append(shown)
            elif 17 <= hour <= 23:
                evening.append(shown)
            else:
                other.append(f"{shown} ({_humanize_time(time_of_day)})")

    parts = [f"{target_label} 기준으로 복약 시간을 나누면 다음과 같습니다."]
    if morning:
        parts.append("아침:")
        parts.extend(f"- {item}" for item in list(dict.fromkeys(morning)))
    if evening:
        parts.append("저녁:")
        parts.extend(f"- {item}" for item in list(dict.fromkeys(evening)))
    if other:
        parts.append("기타 시간:")
        parts.extend(f"- {item}" for item in list(dict.fromkeys(other)))
    if len(parts) == 1:
        parts.append("- 등록된 복약 일정 정보가 충분하지 않습니다.")

    base = "\n".join(parts)
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_med_regularity_intent(
    *,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    schedule_med_ids = {schedule.get("patient_med_id") for schedule in schedules}
    lines: list[str] = []
    for med in meds:
        name = str(med.get("display_name") or "해당 약").strip()
        notes = str(med.get("notes") or "").strip()
        patient_med_id = med.get("patient_med_id")
        if any(keyword in notes for keyword in ["필요", "열날", "증상", "통증 시"]):
            lines.append(f"- {name}: 필요 시 복용으로 보는 것이 자연스럽습니다.")
        elif patient_med_id in schedule_med_ids or any(
            keyword in notes for keyword in ["식후 복용", "취침 전", "기상 직후", "아침", "저녁"]
        ):
            lines.append(f"- {name}: 기록상 매일 정해진 시점에 복용하는 약으로 보입니다.")
        else:
            lines.append(f"- {name}: 현재 정보만으로 매일 복용 여부를 단정하기는 어렵습니다.")

    base = f"{target_label} 기준으로 매일 복용 여부를 보면 다음과 같습니다.\n" + "\n".join(lines)
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_med_prn_intent(
    *,
    message: str,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    recent_messages: list[ChatMessage] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    matched = _extract_target_med(message=message, meds=meds, recent_messages=recent_messages)

    if not matched:
        return None

    notes = str(matched.get("notes") or "").strip()
    name = matched.get("display_name") or "이 약"
    patient_med_id = matched.get("patient_med_id")
    matched_schedules = [schedule for schedule in schedules if schedule.get("patient_med_id") == patient_med_id]

    if any(keyword in notes for keyword in ["필요", "열날", "증상", "통증 시"]):
        base = f"{target_label} 기준으로 {name}은 매일 정해진 시간에 먹는 약이라기보다 증상이 있을 때 복용하는 약으로 보는 것이 더 자연스럽습니다."
    elif matched_schedules or any(
        keyword in notes for keyword in ["식후 복용", "취침 전", "기상 직후", "아침", "저녁"]
    ):
        times: list[str] = []
        for schedule in matched_schedules:
            for item in schedule.get("times") or []:
                time_label = _humanize_time(item.get("time_of_day"))
                if time_label not in times:
                    times.append(time_label)
        if times:
            base = f"{target_label} 기준으로 {name}은 기록상 매일 복용하는 약으로 보는 것이 자연스럽습니다. 현재 등록된 시간은 {', '.join(times[:3])}입니다."
        else:
            base = f"{target_label} 기준으로 {name}은 메모와 일정상 매일 정해진 시점에 복용하는 약으로 보는 것이 자연스럽습니다."
    elif notes:
        base = f"{target_label} 기준으로 {name}은 메모상 `{notes}`로 기록되어 있습니다. 정시 복용 여부는 처방 의도와 문서 내용을 함께 확인하는 것이 좋습니다."
    else:
        base = f"{target_label} 기준으로 {name}의 매일 복용 여부를 단정할 근거는 부족합니다. 확정 문서와 처방 지시를 함께 확인해 주세요."

    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


async def _answer_med_detail_intent(
    *,
    message: str,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    recent_messages: list[ChatMessage] | None,
    session_memory: ChatSessionMemory | None = None,
    matched_med: dict[str, Any] | None = None,
    dur_alerts: list[dict[str, Any]] | None = None,
    adherence_summary: dict[str, Any] | None = None,
    guide: Guide | None = None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    matched = matched_med or _extract_target_med(
        message=message,
        meds=meds,
        recent_messages=recent_messages,
        session_memory=session_memory,
    )
    if not matched:
        return None

    name = str(matched.get("display_name") or "해당 약").strip()
    dosage = str(matched.get("dosage") or "").strip()
    notes = str(matched.get("notes") or "").strip()
    patient_med_id = matched.get("patient_med_id")

    schedule_lines: list[str] = []
    for schedule in schedules:
        if schedule.get("patient_med_id") != patient_med_id:
            continue
        for item in schedule.get("times") or []:
            time_label = _humanize_time(item.get("time_of_day"))
            days_label = _humanize_days(item.get("days_of_week"))
            schedule_lines.append(f"{days_label} {time_label}".strip())

    lookup = await _lookup_external_med_info(name)
    mfds_item = lookup.get("mfds")
    kids_items = lookup.get("kids") or []
    med_info = matched.get("drug_info") or {}
    catalog_info = matched.get("drug_catalog") or {}

    record_points: list[str] = []
    general_points: list[str] = []
    next_points: list[str] = []
    efficacy = _first_clean_line(getattr(mfds_item, "efficacy", None)) if mfds_item else ""
    if not efficacy:
        efficacy = _summarize_text(med_info.get("efficacy"), max_sentences=1)
    if dosage:
        record_points.append(f"{name} 용량은 {dosage}로 기록되어 있습니다.")
    if efficacy:
        general_points.append(f"{name}은 보통 {efficacy}")
    if schedule_lines:
        record_points.append("복용 시간은 " + ", ".join(schedule_lines[:3]) + "입니다.")
    if notes:
        record_points.append(f"복용 메모에는 `{notes}`로 남아 있습니다.")
    precautions = _summarize_text(getattr(mfds_item, "precautions", None), max_sentences=1) if mfds_item else ""
    if not precautions:
        precautions = _summarize_text(med_info.get("precautions"), max_sentences=1)
    if precautions:
        general_points.append(f"주의사항으로는 {precautions}")
    if med_info.get("storage_method"):
        general_points.append(f"보관 방법은 {_first_clean_line(str(med_info.get('storage_method') or ''))}")
    ingredients = _first_clean_line(str(catalog_info.get("ingredients") or ""))
    if ingredients:
        general_points.append(f"성분 참고로는 {ingredients}")
    if kids_items:
        kids_summary = _first_clean_line(kids_items[0].get("content"))
        if kids_summary:
            general_points.append(f"추가 안전 근거로는 {kids_summary}")
    dur_points = _extract_dur_alert_points(dur_alerts=dur_alerts or [], med_name=name, limit=2)
    if dur_points:
        next_points.extend(dur_points)
    med_adherence_points = _build_med_adherence_points(med_name=name, adherence_summary=adherence_summary)
    if med_adherence_points:
        record_points.extend(med_adherence_points)
    guide_points = _build_med_guidance_points(guide=guide, med_name=name)
    if guide_points:
        next_points.extend(guide_points[:2])
    if not next_points:
        next_points.append("복용 시간과 추가 복용 여부를 임의로 바꾸기보다 현재 일정과 처방 지시를 먼저 확인해 주세요.")

    base = _compose_medical_sections(
        current_record_points=record_points,
        general_info_points=general_points,
        next_check_points=next_points,
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


# 보호자 체크포인트 직접 응답
def _answer_caregiver_check_intent(
    *,
    guide: Guide | None,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    points: list[str] = []

    if guide and isinstance(guide.caregiver_summary, dict):
        for key in ("today_checklist", "care_points", "warning_signs"):
            value = guide.caregiver_summary.get(key) or []
            if isinstance(value, list):
                points.extend(str(item).strip() for item in value if str(item).strip())

    if not points and schedules:
        schedule_text = _build_schedule_text(schedules, meds)
        points.append(f"오늘 복약 일정 확인: {schedule_text}")

    if not points:
        base = f"{target_label} 기준으로 오늘 보호자가 확인할 체크포인트 정보가 아직 충분하지 않습니다."
    else:
        deduped: list[str] = []
        for point in points:
            if point not in deduped:
                deduped.append(point)
        base = f"{target_label} 기준으로 오늘 보호자가 확인해야 할 내용은 다음과 같습니다.\n" + "\n".join(
            f"- {point}" for point in deduped[:5]
        )

    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_self_check_intent(
    *,
    guide: Guide | None,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    points: list[str] = []

    if schedules:
        schedule_text = _build_schedule_text(schedules, meds)
        for line in schedule_text.splitlines():
            clean = line.strip().lstrip("-").strip()
            if clean:
                points.append(clean)

    if guide and isinstance(guide.content_json, dict):
        for section in guide.content_json.get("sections") or []:
            title = str(section.get("title") or "")
            body = str(section.get("body") or "").strip()
            if "주의" in title or "생활" in title:
                for line in body.splitlines():
                    clean = line.strip().lstrip("-").strip()
                    if clean:
                        points.append(clean)

    deduped: list[str] = []
    for point in points:
        if point not in deduped:
            deduped.append(point)

    if deduped:
        base = f"{target_label} 기준으로 오늘 본인이 확인하면 좋은 체크리스트는 다음과 같습니다.\n" + "\n".join(
            f"- {point}" for point in deduped[:4]
        )
    else:
        base = f"{target_label} 기준으로 오늘 확인할 체크리스트 정보가 아직 충분하지 않습니다."

    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_allergy_food_intent(
    *,
    profile: PatientProfile | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    allergies = _split_text_items(getattr(profile, "allergies", None) if profile else None)

    if allergies:
        base = f"{target_label} 기준으로 특히 조심해야 할 알레르기/음식 정보는 다음과 같습니다.\n" + "\n".join(
            f"- {item}" for item in allergies
        )
    else:
        base = f"{target_label} 기준으로 등록된 알레르기나 음식 주의 정보는 아직 없습니다."

    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_missed_dose_intent(
    *,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    base = (
        f"{target_label} 기준으로 복약을 놓쳤을 때는 바로 추가 복용을 단정하기보다, 처방 지시나 약 봉투 안내를 먼저 확인하는 것이 안전합니다.\n"
        "- 다음 복용 시간이 매우 가까우면 임의로 두 번 먹이지 말고\n"
        "- 현재 증상이나 이상 반응이 있으면 의료진이나 약사와 상담해 주세요."
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_emergency_guidance_intent(
    *,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    base = (
        f"{target_label} 기준으로 바로 병원이나 119를 생각해야 하는 신호는 다음과 같습니다.\n"
        "- 숨쉬기 힘들어지거나 호흡이 가빠질 때\n"
        "- 입술이 파래지거나 의식이 처지거나 깨우기 어려울 때\n"
        "- 심한 발진, 얼굴 붓기, 전신 두드러기처럼 급격한 이상 반응이 함께 있을 때\n"
        "- 어지러움이 심해져 걷기 어렵거나 쓰러질 것 같을 때"
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_lifestyle_top_intent(
    *,
    guide: Guide | None,
    profile: PatientProfile | None,
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    record_points: list[str] = []
    general_points: list[str] = []
    next_points: list[str] = []
    if guide and isinstance(guide.content_json, dict):
        for section in guide.content_json.get("sections") or []:
            title = str(section.get("title") or "")
            body = str(section.get("body") or "").strip()
            if "생활" in title or "주의" in title:
                for line in body.split("\n"):
                    clean = line.strip().replace("- ", "")
                    if clean:
                        general_points.append(clean)
    if not general_points and guide and guide.content_text:
        general_points.extend([line.strip() for line in guide.content_text.split(".") if line.strip()])

    if profile:
        sleep_hours = getattr(profile, "avg_sleep_hours_per_day", None)
        exercise_minutes = getattr(profile, "avg_exercise_minutes_per_day", None)
        allergies = _split_text_items(getattr(profile, "allergies", None))
        smoker = getattr(profile, "is_smoker", None)
        alcohol = getattr(profile, "avg_alcohol_bottles_per_week", None)

        if allergies:
            record_points.append(f"알레르기 주의 정보는 {', '.join(allergies[:2])}입니다.")
        if sleep_hours is not None:
            record_points.append(f"수면은 하루 평균 {sleep_hours}시간으로 기록되어 있습니다.")
        if exercise_minutes is not None:
            record_points.append(f"운동은 하루 평균 {exercise_minutes}분 정도로 기록되어 있습니다.")
        if smoker is True:
            record_points.append(
                "흡연 중으로 기록되어 있어 호흡기 증상이나 약 복용 시 주의점을 함께 보는 것이 좋습니다."
            )
        if alcohol is not None:
            record_points.append(f"주간 음주량은 {alcohol}병으로 기록되어 있습니다.")
        if sleep_hours is not None and float(sleep_hours) < 6:
            next_points.append("수면 시간이 짧은 편이라 먼저 수면 리듬과 최근 복용약 영향을 함께 보는 것이 좋습니다.")
        if exercise_minutes is not None and int(exercise_minutes) < 20:
            next_points.append(
                "활동량이 적은 편이라 무리 없는 범위에서 가벼운 활동을 유지하는지 확인하는 것이 좋습니다."
            )

    next_points.extend(_build_adherence_guidance_points(adherence_summary=adherence_summary))

    if not next_points:
        if profile and getattr(profile, "is_smoker", None) is True:
            next_points.append(
                "생활관리에서는 흡연과 음주가 현재 증상이나 약 복용에 영향을 주지 않는지 먼저 같이 보는 것이 좋습니다."
            )
        elif profile and getattr(profile, "avg_sleep_hours_per_day", None) is not None:
            next_points.append(
                "기록상 수면 시간은 유지되고 있어도 실제 피로감, 중간 각성, 복용 후 졸림 같은 체감 변화가 있는지 함께 확인하는 것이 좋습니다."
            )
        else:
            next_points.append(
                "생활관리에서는 현재 복약 일정과 생활 습관이 서로 영향을 주는 부분부터 먼저 확인하는 것이 좋습니다."
            )

    if not record_points and not general_points and not next_points:
        base = f"{target_label} 기준 생활관리 요약 정보가 아직 충분하지 않습니다."
    else:
        base = _compose_medical_sections(
            current_record_points=record_points,
            general_info_points=general_points,
            next_check_points=next_points,
        )

    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_condition_general_intent(
    *,
    condition_name: str | None,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    profile: PatientProfile | None,
    message: str,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    condition = str(condition_name or "해당 질환").strip()
    profile_points: list[str] = []
    if profile:
        allergies = _split_text_items(getattr(profile, "allergies", None))
        other_conditions = [
            item for item in _split_text_items(getattr(profile, "conditions", None)) if item != condition
        ]
        if allergies:
            profile_points.append("알레르기: " + ", ".join(allergies[:2]))
        if other_conditions:
            profile_points.append("함께 관리 중인 상태: " + ", ".join(other_conditions[:2]))

    related_keywords = _CONDITION_MED_KEYWORDS.get(condition, [])
    related_meds: list[str] = []
    for med in meds:
        name = str(med.get("display_name") or "").strip()
        if not name:
            continue
        if any(keyword in name for keyword in related_keywords):
            related_meds.append(name)

    if condition == "골다공증":
        lead = "골다공증은 보통 칼슘·비타민D 보충과 함께 골흡수 억제제 같은 치료약을 사용합니다."
    elif condition in {"당뇨", "제2형 당뇨"}:
        lead = "당뇨는 혈당 조절 약과 식사·운동 관리가 함께 가는 경우가 많습니다."
    elif condition == "고혈압":
        lead = "고혈압은 혈압약을 꾸준히 복용하면서 어지러움이나 저혈압 증상을 함께 확인하는 것이 중요합니다."
    elif condition == "고지혈증":
        lead = "고지혈증은 지질강하제 복용과 식습관, 운동 관리가 함께 중요합니다."
    elif condition == "빈혈":
        lead = "빈혈은 원인에 따라 철분제나 원인 교정 치료를 함께 보는 경우가 많습니다."
    else:
        lead = f"{condition}은 진단 상태와 현재 복용약을 함께 보고 치료 방향을 정하는 것이 중요합니다."

    lines = [lead]
    if related_meds:
        related_text = ", ".join(_dedupe_lines(related_meds, limit=3))
        lines.append(f"현재 기록에서는 {_with_particle(related_text, ('이', '가'))} 관련 약으로 보입니다.")
        if _contains_any(message, ["매일", "주 1회", "나눠", "구분"]) and schedules:
            med_id_map = {int(med.get("patient_med_id")): med for med in meds if med.get("patient_med_id") is not None}
            daily: list[str] = []
            weekly: list[str] = []
            for schedule in schedules:
                med = med_id_map.get(int(schedule.get("patient_med_id")))
                if not med:
                    continue
                name = str(med.get("display_name") or "").strip()
                if not any(keyword in name for keyword in related_keywords):
                    continue
                for item in schedule.get("times") or []:
                    days = str(item.get("days_of_week") or "").strip().upper()
                    if (
                        days in {"SAT", "SUN", "MON"}
                        and len(schedule.get("times") or []) == 1
                        and ("알렌드론" in name or "리세드론" in name)
                    ):
                        weekly.append(name)
                    elif "MON,TUE,WED,THU,FRI,SAT,SUN" in days or _humanize_days(days) == "매일":
                        daily.append(name)
            daily = _dedupe_lines(daily, limit=3)
            weekly = _dedupe_lines(weekly, limit=3)
            if daily or weekly:
                parts: list[str] = []
                if daily:
                    parts.append("매일 챙길 약: " + ", ".join(daily))
                if weekly:
                    parts.append("주 1회 확인할 약: " + ", ".join(weekly))
                lines.append(" / ".join(parts))
    if profile_points:
        lines.append("현재 기록 기준으로는 " + " / ".join(profile_points[:2]) + "도 함께 확인하는 것이 좋습니다.")
    lines.append("새 약을 추가하거나 바꾸는 판단은 현재 복용약과 병력 확인 후 의료진과 상의하는 것이 안전합니다.")

    base = " ".join(lines)
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_session_summary_intent(
    *,
    meds: list[dict[str, Any]],
    profile: PatientProfile | None,
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    med_names = [str(med.get("display_name")).strip() for med in meds if str(med.get("display_name") or "").strip()]
    conditions = _split_text_items(getattr(profile, "conditions", None) if profile else None)
    allergies = _split_text_items(getattr(profile, "allergies", None) if profile else None)
    current_points: list[str] = []
    general_points: list[str] = []
    next_points: list[str] = []

    if conditions:
        current_points.append("현재 건강 상태로는 " + ", ".join(conditions[:2]) + "가 기록되어 있습니다.")
    if allergies:
        current_points.append("알레르기 정보는 " + ", ".join(allergies[:2]) + "입니다.")
    if med_names:
        current_points.append("현재 복약 관리는 " + ", ".join(_dedupe_lines(med_names, limit=4)) + " 중심입니다.")
    else:
        current_points.append("현재 복용 약 정보는 아직 충분하지 않습니다.")

    general_points.append(
        "기록된 건강 상태와 복약 일정, 최근 복약 흐름을 같이 보면서 관리 우선순위를 정리하는 것이 좋습니다."
    )

    if adherence_summary and int(adherence_summary.get("total", 0) or 0) > 0:
        taken = int(adherence_summary.get("taken", 0) or 0)
        missed = int(adherence_summary.get("missed", 0) or 0)
        pending = int(adherence_summary.get("pending", 0) or 0)
        current_points.append(f"최근 복약 기록은 완료 {taken}건, 놓침 {missed}건, 대기 {pending}건입니다.")
        if missed > 0:
            next_points.append("최근 놓친 약부터 오늘 일정에 다시 들어 있는지 먼저 확인하는 것이 좋습니다.")
        elif pending > 0:
            next_points.append("아직 복용 대기 상태인 일정이 남아 있는지 함께 확인하는 것이 좋습니다.")
    else:
        next_points.append("복약 기록이 충분하지 않다면 오늘 일정과 실제 복용 여부를 먼저 맞춰 보는 것이 좋습니다.")

    base = _compose_medical_sections(
        current_record_points=current_points,
        general_info_points=general_points,
        next_check_points=next_points,
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _collect_schedule_lines_for_period(
    *,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    period: str,
) -> list[str]:
    med_name_map = {int(med.get("patient_med_id")): med for med in meds if med.get("patient_med_id") is not None}
    lines: list[str] = []
    for schedule in schedules:
        med = med_name_map.get(int(schedule.get("patient_med_id")), {})
        med_name = str(med.get("display_name") or "").strip()
        dosage = str(med.get("dosage") or "").strip()
        notes = str(med.get("notes") or "").strip()
        if not med_name:
            continue
        if any(keyword in notes for keyword in ["필요", "열날", "증상"]) and period == "night":
            continue
        for item in schedule.get("times") or []:
            time_label = _humanize_time(item.get("time_of_day"))
            hour_raw = str(item.get("time_of_day") or "00:00:00").split(":")[0]
            try:
                hour = int(hour_raw)
            except Exception:
                hour = -1
            if period == "night" and hour < 20:
                continue
            if period == "evening" and not (17 <= hour <= 23):
                continue
            if period == "morning" and not (4 <= hour < 12):
                continue
            label = med_name
            if dosage:
                label += f" {dosage}"
            label += f" ({time_label})"
            lines.append(label)
    return _dedupe_lines(lines, limit=5)


def _answer_tonight_check_intent(
    *,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    if not meds and not schedules:
        base = f"{target_label} 기준으로 등록된 복용약이나 복약 일정이 아직 없습니다."
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    tonight_lines = _collect_schedule_lines_for_period(meds=meds, schedules=schedules, period="night")
    extra_points: list[str] = []
    for med in meds:
        notes = str(med.get("notes") or "").strip()
        name = str(med.get("display_name") or "").strip()
        if name and any(keyword in notes for keyword in ["필요", "열날", "증상"]):
            extra_points.append(f"{name}은 증상이 있을 때만 복용하는 약인지 함께 확인해 주세요.")
    if tonight_lines:
        base = f"{target_label} 기준 오늘 복약 일정에서 밤에 챙겨야 할 약은 다음과 같습니다.\n" + "\n".join(
            f"- {line}" for line in tonight_lines
        )
        if extra_points:
            base += "\n" + "\n".join(f"- {line}" for line in _dedupe_lines(extra_points, limit=2))
        if adherence_summary and int(adherence_summary.get("missed", 0) or 0) > 0:
            recent_missed_names = adherence_summary.get("recent_missed_names") or []
            if recent_missed_names:
                base += "\n- 최근 놓친 기록이 있는 약: " + ", ".join(recent_missed_names[:2])
    else:
        base = f"{target_label} 기준으로 오늘 밤에 해당하는 복약 일정은 현재 뚜렷하게 확인되지 않습니다."
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_schedule_order_intent(
    *,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    time_period: str | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    period = time_period or "morning"
    label = {"morning": "아침", "evening": "저녁", "night": "밤"}.get(period, "복약")
    lines = _collect_schedule_lines_for_period(meds=meds, schedules=schedules, period=period)
    if lines:
        base = f"{target_label} 기준으로 {label} 약은 다음 순서로 정리해 볼 수 있습니다.\n" + "\n".join(
            f"- {idx + 1}. {line}" for idx, line in enumerate(lines)
        )
    else:
        base = f"{target_label} 기준으로 {label} 복약 순서를 정리할 일정 정보가 아직 충분하지 않습니다."
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_adherence_priority_intent(
    *,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    missed_names = []
    if adherence_summary:
        missed_names = [
            str(name).strip() for name in adherence_summary.get("recent_missed_names") or [] if str(name).strip()
        ]
    if missed_names:
        base = (
            f"{target_label} 기준 최근 복약 기록에서 자주 놓친 약으로는 "
            f"{', '.join(_dedupe_lines(missed_names, limit=3))}이 보입니다.\n"
            "복용 우선순위를 임의로 바꾸기보다, 최근 놓친 약이 오늘 일정에도 있는지 먼저 확인해 빠뜨리지 않는 것이 좋습니다."
        )
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    evening_lines = _collect_schedule_lines_for_period(meds=meds, schedules=schedules, period="evening")
    if evening_lines:
        base = (
            f"{target_label} 기준으로 자주 놓친다면 먼저 챙겨야 할 저녁 약은 다음과 같습니다.\n"
            + "\n".join(f"- {line}" for line in evening_lines[:3])
            + "\n복용 우선순위를 임의로 바꾸기보다, 실제 저녁 일정에 잡힌 약부터 빠뜨리지 않게 확인하는 것이 좋습니다."
        )
    else:
        med_names = [
            str(med.get("display_name") or "").strip() for med in meds if str(med.get("display_name") or "").strip()
        ]
        base = f"{target_label} 기준으로 특정 약 하나를 제일 중요하다고 단정하기보다, 현재 처방된 약을 일정대로 빠뜨리지 않는 것이 더 중요합니다."
        if med_names:
            base += "\n현재 확인되는 약: " + ", ".join(med_names[:4])
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_symptom_cause_intent(
    *,
    message: str,
    meds: list[dict[str, Any]],
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    normalized = (message or "").strip()
    points: list[str] = []
    urgency_points: list[str] = []
    med_names = [
        str(med.get("display_name") or "").strip() for med in meds if str(med.get("display_name") or "").strip()
    ]

    has_gi_symptom = _contains_any(
        normalized,
        [
            "복통",
            "배 아",
            "배아",
            "속쓰림",
            "속 쓰림",
            "속이 쓰",
            "속이 안 좋",
            "속이 안좋",
            "메스껍",
            "울렁",
            "구역",
            "구토",
        ],
    )
    if has_gi_symptom:
        points.append("물을 조금씩 자주 마시고, 자극적인 음식이나 과식은 잠시 피하는 것이 좋습니다.")
        points.append("언제부터 아픈지와 마지막 복용 약 시간이 언제였는지 같이 확인해 보세요.")
        if any("아세트아미노펜" in name for name in med_names):
            points.append(
                "현재 기록에 삼남아세트아미노펜이 있어도, 복통 때문에 임의로 진통제를 더 추가하기 전에는 성분 중복을 먼저 확인하는 것이 안전합니다."
            )
        elif med_names:
            points.append(
                "현재 복용 중인 약 외에 진통제나 감기약을 임의로 더 먹기 전에는 성분을 먼저 확인하는 것이 좋습니다."
            )
        urgency_points.append(
            "통증이 점점 심해지거나, 계속 토하거나, 피가 섞이거나, 열이 함께 나면 바로 진료를 받는 것이 안전합니다."
        )

    if "어지러" in normalized:
        for med in meds:
            name = str(med.get("display_name") or "").strip()
            if any(keyword in name for keyword in ["암로디핀", "텔미사르탄", "비소프롤롤", "푸로세미드"]):
                points.append(f"{name}은 어지러움과 관련해 함께 확인해 볼 수 있는 약입니다.")
    if "식은땀" in normalized:
        for med in meds:
            name = str(med.get("display_name") or "").strip()
            if any(keyword in name for keyword in ["메트포르민", "글리메피리드"]):
                points.append(f"{name} 복용 중 식은땀이나 떨림이 있으면 저혈당 여부도 먼저 확인하는 것이 좋습니다.")
    if "멍" in normalized or "출혈" in normalized:
        for med in meds:
            name = str(med.get("display_name") or "").strip()
            if any(keyword in name for keyword in ["아스피린", "클로피도그렐"]):
                points.append(f"{name}은 멍이나 출혈 경향과 함께 확인할 수 있는 약입니다.")

    if not points:
        base = f"{target_label} 기준으로 증상과 약의 관련성을 단정할 수는 없지만, 복용 중인 약과 증상이 시작된 시점을 함께 확인하는 것이 좋습니다."
    else:
        heading = (
            f"{target_label} 기준으로 현재 증상에서 먼저 확인할 점은 다음과 같습니다."
            if has_gi_symptom
            else f"{target_label} 기준으로 현재 증상과 관련해 먼저 확인해 볼 약은 다음과 같습니다."
        )
        base = heading + "\n" + "\n".join(f"- {point}" for point in _dedupe_lines(points, limit=4))
        if urgency_points:
            base += "\n" + "\n".join(f"- {item}" for item in _dedupe_lines(urgency_points, limit=2))
        else:
            base += "\n증상이 심해지거나 새로 시작된 경우에는 복용 시점과 함께 의료진에게 알려 주세요."

    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_observation_check_intent(
    *,
    message: str,
    matched_med: dict[str, Any] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    if not matched_med:
        return None

    med_name = str(matched_med.get("display_name") or "해당 약").strip()
    normalized = (message or "").strip()
    points: list[str] = []
    if "기침" in normalized or "숨" in normalized or "호흡" in normalized:
        points.append("기침이 더 심해지거나 숨쉬기 힘들어지지 않는지 먼저 확인해 주세요.")
        points.append("말하기 힘들 정도의 호흡곤란, 입술이 파래짐, 처짐이 보이면 즉시 응급진료가 우선입니다.")
    if "열" in normalized:
        points.append("해열제 복용 뒤에도 열이 계속 오르거나 처짐이 심해지는지 함께 보세요.")
    if "발진" in normalized or "두드러기" in normalized:
        points.append("발진, 얼굴 붓기, 전신 두드러기가 생기면 추가 복용 전에 바로 상태를 확인해야 합니다.")

    if not points:
        points.append("복용 뒤 증상이 더 심해지지 않는지와 새로 생긴 이상 반응이 없는지를 먼저 확인해 주세요.")

    base = f"{target_label} 기준으로 {med_name} 복용 뒤에는 다음 상태를 먼저 보면 좋습니다.\n" + "\n".join(
        f"- {item}" for item in _dedupe_lines(points, limit=3)
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_school_observation_intent(
    *,
    profile: PatientProfile | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    conditions = _split_text_items(getattr(profile, "conditions", None) if profile else None)
    points: list[str] = []
    if any("천식" in item for item in conditions):
        points.append("기침이 평소보다 심해지거나 숨쉬기 힘들어하는지 봐 달라고 전해 주세요.")
        points.append(
            "말을 하기 힘들 정도로 숨이 차거나 처지는 모습이 보이면 바로 보호자에게 연락해 달라고 하는 것이 좋습니다."
        )
    if any("비염" in item for item in conditions):
        points.append("콧물, 코막힘이 심해지면서 수업에 집중하기 어려워하는지도 함께 봐 달라고 할 수 있습니다.")
    if not points:
        points.append("복용 뒤 졸림, 발진, 호흡 불편 같은 새로운 증상이 없는지 봐 달라고 전하는 것이 좋습니다.")
    base = f"{target_label} 기준으로 학교에서는 다음 증상을 특히 봐 달라고 전달하면 좋습니다.\n" + "\n".join(
        f"- {item}" for item in _dedupe_lines(points, limit=3)
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_cold_med_caution_intent(
    *,
    profile: PatientProfile | None,
    meds: list[dict[str, Any]],
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    points: list[str] = []
    allergies = _split_text_items(getattr(profile, "allergies", None) if profile else None)
    conditions = _split_text_items(getattr(profile, "conditions", None) if profile else None)
    if allergies:
        points.append("알레르기 성분이 겹치지 않는지 먼저 성분표를 확인하는 것이 좋습니다.")
    if any("고혈압" in item for item in conditions):
        points.append("코감기약 성분 중 혈압을 올릴 수 있는 성분은 없는지 확인하는 것이 좋습니다.")
    if any("골다공증" in item for item in conditions):
        points.append("골다공증 약 복용 시간과 겹치지 않게 공복약/식후약 순서를 함께 확인하세요.")
    if any("고지혈증" in item for item in conditions):
        points.append("현재 복용 중인 지질강하제와 함께 먹어도 되는지 약사나 의료진에게 확인하는 것이 안전합니다.")
    if meds:
        med_names = [
            str(med.get("display_name") or "").strip() for med in meds if str(med.get("display_name") or "").strip()
        ]
        if med_names:
            points.append("현재 복용약: " + ", ".join(med_names[:4]))

    base = f"{target_label} 기준으로 감기약을 새로 먹게 되면 다음 점을 먼저 확인하는 것이 좋습니다.\n" + "\n".join(
        f"- {item}" for item in _dedupe_lines(points, limit=4)
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_rash_intent(
    *,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    base = (
        f"{target_label} 기준으로 약 복용 후 두드러기나 발진이 생기면 추가 복용 전에 상태를 먼저 확인하는 것이 안전합니다.\n"
        "- 숨쉬기 힘듦, 얼굴 붓기, 전신 두드러기가 함께 있으면 즉시 응급진료가 우선이고\n"
        "- 가벼운 피부 발진이라도 복용 약 이름과 발생 시간을 기록해 의료진과 상담해 주세요."
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


# 스케줄 기반 직접 응답
def _answer_schedule_intent(
    *,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    schedule_text = _build_schedule_text(schedules, meds)
    if schedule_text == "등록된 복약 일정 없음":
        base = f"{target_label} 기준으로 등록된 복약 일정이 없습니다."
    else:
        base = f"{target_label} 기준 복약 일정은 다음과 같습니다.\n{schedule_text}"

    if audience == "senior":
        base += "\n어지러움이나 복약 시간 혼동이 생기지 않도록 복용 전 다시 확인하는 것이 좋습니다."

    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_hospital_schedule_intent(
    *,
    hospital_schedules: list[HospitalSchedule],
    message: str,
    session_memory: ChatSessionMemory | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    if not hospital_schedules:
        base = f"{target_label} 기준으로 등록된 병원 예약이나 검사 일정이 없습니다."
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    normalized = (message or "").strip()
    upcoming = [item for item in hospital_schedules if getattr(item, "scheduled_at", None) is not None]
    focus = str(getattr(session_memory, "recent_hospital_focus", "") or "").strip()

    filtered = upcoming or hospital_schedules
    if _contains_any(normalized, ["외래", "진료"]) or "외래/진료" in focus:
        filtered = [
            item for item in filtered if _contains_any(str(getattr(item, "title", "") or ""), ["외래", "진료"])
        ] or filtered
    elif _contains_any(normalized, ["검사"]) or "검사" in focus:
        filtered = [
            item for item in filtered if _contains_any(str(getattr(item, "title", "") or ""), ["검사"])
        ] or filtered

    schedule_index = 0
    if _contains_any(normalized, ["그 다음", "다다음"]) or normalized in _AFFIRMATIVE_SHORT_REPLIES:
        schedule_index = 1

    target_schedules = filtered or hospital_schedules
    has_followup_request = schedule_index == 1
    if has_followup_request and len(target_schedules) <= 1:
        title_hint = (
            "외래/진료 일정"
            if (_contains_any(normalized, ["외래", "진료"]) or "외래/진료" in focus)
            else ("검사 일정" if (_contains_any(normalized, ["검사"]) or "검사" in focus) else "병원 일정")
        )
        first_schedule = target_schedules[0]
        first_title = str(getattr(first_schedule, "title", "") or "병원 일정").strip()
        first_time = _format_datetime_korean(getattr(first_schedule, "scheduled_at", None))
        base = (
            f"{target_label} 기준 그 다음 {title_hint}은 아직 등록되어 있지 않습니다.\n"
            f"현재 확인되는 가장 가까운 일정은 {first_time}의 {first_title}입니다."
        )
        hospital_name = str(getattr(first_schedule, "hospital_name", "") or "").strip()
        location = str(getattr(first_schedule, "location", "") or "").strip()
        if hospital_name:
            base += f"\n병원: {hospital_name}"
        if location:
            base += f"\n장소: {location}"
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    target_schedule = (
        target_schedules[schedule_index] if len(target_schedules) > schedule_index else target_schedules[0]
    )

    if _contains_any(normalized, ["언제", "다음", "가장 가까운", "최근", "예약 언제였지"]):
        title = str(getattr(target_schedule, "title", "") or "병원 일정").strip()
        hospital_name = str(getattr(target_schedule, "hospital_name", "") or "").strip()
        location = str(getattr(target_schedule, "location", "") or "").strip()
        scheduled_at = _format_datetime_korean(getattr(target_schedule, "scheduled_at", None))
        parts = [
            (
                f"{target_label} 기준 그 다음 병원 일정은 {scheduled_at}의 {title}입니다."
                if schedule_index == 1 and len(target_schedules) > 1
                else f"{target_label} 기준 가장 가까운 병원 일정은 {scheduled_at}의 {title}입니다."
            )
        ]
        if hospital_name:
            parts.append(f"병원: {hospital_name}")
        if location:
            parts.append(f"장소: {location}")
        base = "\n".join(parts)
    else:
        base = f"{target_label} 기준 등록된 병원 일정은 다음과 같습니다.\n{_build_hospital_schedule_text(hospital_schedules[:3])}"

    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _med_category_flags(name: str) -> set[str]:
    normalized = _compact_text(name).lower()
    flags: set[str] = set()
    if any(token in normalized for token in ["아세트아미노펜", "타이레놀", "게보린"]):
        flags.add("acetaminophen")
    if any(token in normalized for token in ["탁센", "이부프로펜", "나프록센", "덱시", "록소", "아스피린"]):
        flags.add("nsaid")
    if any(token in normalized for token in ["비염", "항히스타민", "세티리진", "로라타딘", "펙소"]):
        flags.add("antihistamine")
    return flags


def _build_interaction_focus_points(
    *, med_names: list[str], adherence_summary: dict[str, Any] | None
) -> tuple[list[str], list[str], list[str]]:
    record_points: list[str] = []
    general_points: list[str] = []
    next_points: list[str] = []

    if med_names:
        record_points.append("현재 확인되는 복용약은 " + ", ".join(_dedupe_lines(med_names, limit=4)) + "입니다.")

    if adherence_summary and int(adherence_summary.get("missed", 0) or 0) > 0:
        missed_names = adherence_summary.get("recent_missed_names") or []
        if missed_names:
            record_points.append(
                "최근 놓친 기록이 있는 약은 " + ", ".join(_dedupe_lines(missed_names, limit=3)) + "입니다."
            )

    flags_by_med = {name: _med_category_flags(name) for name in med_names}
    nsaid_meds = [name for name, flags in flags_by_med.items() if "nsaid" in flags]
    acet_meds = [name for name, flags in flags_by_med.items() if "acetaminophen" in flags]
    antihistamine_meds = [name for name, flags in flags_by_med.items() if "antihistamine" in flags]

    if len(nsaid_meds) >= 2:
        general_points.append(
            "진통소염제 계열이 겹칠 수 있어 위장 증상, 신장 부담, 출혈 위험을 특히 조심해 보는 것이 좋습니다."
        )
    if nsaid_meds and acet_meds:
        general_points.append(
            "해열진통제와 소염진통제를 함께 쓰는 형태일 수 있어 추가 복용을 임의로 늘리지 않는 것이 좋습니다."
        )
    if len(antihistamine_meds) >= 2:
        general_points.append("항히스타민 계열이 겹치면 졸림이나 집중력 저하를 더 주의해서 보는 것이 좋습니다.")
    if not general_points:
        general_points.append(
            "현재 약 이름만으로 중대한 상호작용을 단정하긴 어렵지만, 성분 중복 여부를 먼저 확인하는 것이 안전합니다."
        )

    next_points.append("처방 외 진통제나 감기약을 추가할 때는 성분표와 현재 복용약 이름을 같이 확인해 주세요.")
    if adherence_summary and int(adherence_summary.get("missed", 0) or 0) > 0:
        next_points.append("상호작용 확인과 함께 복약 누락이 반복되지 않는지도 같이 보는 것이 좋습니다.")

    return record_points, general_points, next_points


def _build_external_interaction_points(
    *,
    external_drug_name: str,
    meds: list[dict[str, Any]],
    profile: PatientProfile | None,
    adherence_summary: dict[str, Any] | None,
    lookup: dict[str, Any] | None,
) -> tuple[list[str], list[str], list[str]]:
    med_names = [
        str(med.get("display_name") or "").strip() for med in meds if str(med.get("display_name") or "").strip()
    ]
    record_points: list[str] = (
        [f"현재 복용약은 {', '.join(_dedupe_lines(med_names, limit=4))}입니다."] if med_names else []
    )
    general_points: list[str] = []
    next_points: list[str] = []

    external_flags = _med_category_flags(external_drug_name)
    current_flags = {name: _med_category_flags(name) for name in med_names}

    overlapping_nsaids = [
        name for name, flags in current_flags.items() if "nsaid" in flags and "nsaid" in external_flags
    ]
    overlapping_ace = [
        name for name, flags in current_flags.items() if "acetaminophen" in flags and "acetaminophen" in external_flags
    ]
    overlapping_antihistamine = [
        name for name, flags in current_flags.items() if "antihistamine" in flags and "antihistamine" in external_flags
    ]

    if overlapping_nsaids:
        general_points.append(
            f"{external_drug_name}은 진통소염제 계열로 보이며 현재 복용약 중 {', '.join(overlapping_nsaids[:3])}과 계열이 겹칠 수 있습니다."
        )
    if overlapping_ace:
        general_points.append(
            f"{external_drug_name}은 아세트아미노펜 계열로 보이며 현재 복용약 중 {', '.join(overlapping_ace[:3])}과 중복 여부를 먼저 확인하는 것이 좋습니다."
        )
    if overlapping_antihistamine:
        general_points.append(
            f"{external_drug_name}은 항히스타민 계열로 보이며 현재 복용약 중 {', '.join(overlapping_antihistamine[:3])}과 함께 복용 시 졸림을 더 주의해서 볼 수 있습니다."
        )

    if profile:
        allergies = _split_text_items(getattr(profile, "allergies", None))
        conditions = _split_text_items(getattr(profile, "conditions", None))
        if allergies:
            record_points.append("등록된 알레르기 정보는 " + ", ".join(allergies[:2]) + "입니다.")
        if conditions:
            record_points.append("현재 건강 상태로는 " + ", ".join(conditions[:2]) + "가 기록되어 있습니다.")

    if not general_points:
        general_points.append(
            f"{external_drug_name}을 현재 약과 같이 복용해도 되는지 판단하려면 성분 중복과 진통제/감기약 계열 중복 여부를 먼저 확인하는 것이 좋습니다."
        )

    mfds_item = lookup.get("mfds") if lookup else None
    kids_items = lookup.get("kids") or [] if lookup else []
    efficacy = _summarize_text(getattr(mfds_item, "efficacy", None), max_sentences=1) if mfds_item else ""
    precautions = _summarize_text(getattr(mfds_item, "precautions", None), max_sentences=1) if mfds_item else ""
    if efficacy:
        general_points.append(f"{external_drug_name}은 일반적으로 {efficacy}")
    if precautions:
        general_points.append(f"주의사항으로는 {precautions}")
    if kids_items:
        kids_summary = _summarize_text(kids_items[0].get("content"), max_sentences=1)
        if kids_summary:
            general_points.append(f"추가 안전 근거로는 {kids_summary}")

    if adherence_summary and int(adherence_summary.get("missed", 0) or 0) > 0:
        missed_names = _dedupe_lines(
            [str(name).strip() for name in (adherence_summary.get("recent_missed_names") or []) if str(name).strip()],
            limit=2,
        )
        if missed_names:
            record_points.append("최근 복용을 놓친 약은 " + ", ".join(missed_names) + "입니다.")
        next_points.append("새 약 비교와 함께 최근 놓친 약이 있다면 복용 간격이 겹치지 않는지도 같이 확인해 주세요.")

    next_points.append("새 약을 추가하기 전에는 제품명뿐 아니라 성분명도 함께 확인해 주세요.")
    next_points.append(
        "복용 후 발진, 호흡 불편, 심한 어지러움이 있으면 추가 복용 전에 상태를 다시 확인하는 것이 좋습니다."
    )

    return record_points, general_points, next_points


def _answer_drug_interaction_overview(
    *,
    meds: list[dict[str, Any]],
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    med_names = [
        str(med.get("display_name") or "").strip() for med in meds if str(med.get("display_name") or "").strip()
    ]
    if len(med_names) < 2:
        base = f"{target_label} 기준으로 비교할 복용약 정보가 아직 충분하지 않습니다."
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    record_points, general_points, next_points = _build_interaction_focus_points(
        med_names=med_names,
        adherence_summary=adherence_summary,
    )
    base = _compose_medical_sections(
        current_record_points=record_points,
        general_info_points=general_points,
        next_check_points=next_points,
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _build_clarification_reply(
    *,
    analysis: QuestionAnalysis,
    context: PatientChatContext,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    message = _normalize_user_message(analysis.raw_message)

    if analysis.primary_intent == "general":
        if _contains_any(message, ["예약", "병원", "외래", "검사", "진료"]):
            if context.hospital_schedules:
                return _answer_hospital_schedule_intent(
                    hospital_schedules=context.hospital_schedules,
                    message=message,
                    session_memory=context.session_memory,
                    target_label=target_label,
                    requester_role=requester_role,
                    audience=audience,
                )
            base = (
                f"{target_label} 기준으로 병원 일정 질문으로 보입니다. "
                "외래 예약인지, 검사 일정인지, 가장 가까운 방문 일정인지 한 가지로 적어 주시면 바로 확인해 드리겠습니다."
            )
            return (
                _to_caregiver_style(answer=base, audience=audience)
                if requester_role == RequesterRole.CAREGIVER
                else base
            )

        if _contains_any(message, ["같이 먹", "같이 복용", "조합", "상호작용"]):
            base = (
                "현재 복용약끼리 비교할지, 새로 받은 약까지 포함할지 먼저 알려 주세요. "
                "약 이름이 있으면 주의 조합을 바로 정리해 드릴 수 있습니다."
            )
            return (
                _to_caregiver_style(answer=base, audience=audience)
                if requester_role == RequesterRole.CAREGIVER
                else base
            )

        if _contains_any(message, _FOLLOWUP_MED_REFERENCES):
            base = (
                "약 이름만 괄호로 다시 보내 주세요. 예: (푸마티펜정케토티펜)\n"
                "이렇게 보내 주시면 그 약 기준으로 복용 시간이나 설명을 바로 이어서 안내해 드리겠습니다."
            )
            return (
                _to_caregiver_style(answer=base, audience=audience)
                if requester_role == RequesterRole.CAREGIVER
                else base
            )

    if analysis.primary_intent == "medication_caution" and not analysis.target_med and not analysis.external_drug_name:
        if context.meds:
            return _answer_drug_interaction_overview(
                meds=context.meds,
                adherence_summary=context.adherence_summary,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        else:
            base = "상호작용을 보려면 비교할 약 이름이 필요합니다. 현재 복용약끼리 볼지, 특정 약을 새로 추가해 볼지 알려 주세요."
            return (
                _to_caregiver_style(answer=base, audience=audience)
                if requester_role == RequesterRole.CAREGIVER
                else base
            )

    return None


async def _render_planned_reply(
    *,
    plan: ChatPlan | None,
    message: str,
    context: PatientChatContext,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    if not plan:
        return None

    if (
        plan.topic == "drug_interaction"
        and plan.needs_clarification
        and not plan.referenced_drug_name
        and len(
            [
                str(med.get("display_name") or "").strip()
                for med in context.meds
                if str(med.get("display_name") or "").strip()
            ]
        )
        >= 2
    ):
        plan = ChatPlan(
            topic=plan.topic,
            requested_fields=plan.requested_fields,
            referenced_drug_name=plan.referenced_drug_name,
            needs_clarification=False,
            clarification_question=None,
            use_record_data=plan.use_record_data,
            answer_style=plan.answer_style,
        )

    if plan.topic == "med_schedule" and plan.needs_clarification and context.schedules:
        plan = ChatPlan(
            topic=plan.topic,
            requested_fields=plan.requested_fields,
            referenced_drug_name=plan.referenced_drug_name,
            needs_clarification=False,
            clarification_question=None,
            use_record_data=plan.use_record_data,
            answer_style=plan.answer_style,
        )

    if plan.needs_clarification and plan.clarification_question:
        return (
            _to_caregiver_style(answer=plan.clarification_question, audience=audience)
            if requester_role == RequesterRole.CAREGIVER
            else plan.clarification_question
        )

    topic = plan.topic

    if topic == "profile":
        requested = set(plan.requested_fields)
        answers: list[str] = []
        if "summary" in requested and "guidance" not in requested:
            summary = _answer_profile_intent(
                intent="profile_summary",
                profile=context.profile,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
            if summary:
                answers.append(summary)
        else:
            if requested & {"bmi", "height", "weight", "body_metrics"}:
                body = _answer_profile_intent(
                    intent="profile_body",
                    profile=context.profile,
                    target_label=target_label,
                    requester_role=requester_role,
                    audience=audience,
                )
                if body:
                    answers.append(body)
            if "sleep" in requested:
                sleep = _answer_profile_intent(
                    intent="profile_sleep",
                    profile=context.profile,
                    target_label=target_label,
                    requester_role=requester_role,
                    audience=audience,
                )
                if sleep:
                    answers.append(sleep)
            if "exercise" in requested:
                exercise = _answer_profile_intent(
                    intent="profile_exercise",
                    profile=context.profile,
                    target_label=target_label,
                    requester_role=requester_role,
                    audience=audience,
                )
                if exercise:
                    answers.append(exercise)
            if "smoking" in requested:
                smoking = _answer_profile_intent(
                    intent="profile_smoking",
                    profile=context.profile,
                    target_label=target_label,
                    requester_role=requester_role,
                    audience=audience,
                )
                if smoking:
                    answers.append(smoking)
            if "alcohol" in requested:
                alcohol = _answer_profile_intent(
                    intent="profile_alcohol",
                    profile=context.profile,
                    target_label=target_label,
                    requester_role=requester_role,
                    audience=audience,
                )
                if alcohol:
                    answers.append(alcohol)
            if "conditions" in requested:
                conditions = _answer_profile_intent(
                    intent="profile_conditions",
                    profile=context.profile,
                    target_label=target_label,
                    requester_role=requester_role,
                    audience=audience,
                )
                if conditions:
                    answers.append(conditions)
            if "allergies" in requested:
                allergies = _answer_profile_intent(
                    intent="profile_allergies",
                    profile=context.profile,
                    target_label=target_label,
                    requester_role=requester_role,
                    audience=audience,
                )
                if allergies:
                    answers.append(allergies)
            if "hospitalization" in requested:
                hospitalization = _answer_profile_intent(
                    intent="profile_hospitalization",
                    profile=context.profile,
                    target_label=target_label,
                    requester_role=requester_role,
                    audience=audience,
                )
                if hospitalization:
                    answers.append(hospitalization)
            if requested & {"guidance", "lifestyle", "risk"} or plan.answer_style in {"guidance", "advice"}:
                guidance = _answer_profile_guidance_intent(
                    message=message,
                    profile=context.profile,
                    guide=context.latest_guide,
                    adherence_summary=context.adherence_summary,
                    target_label=target_label,
                    requester_role=requester_role,
                    audience=audience,
                )
                if guidance:
                    answers.append(guidance)
        return _compose_answers(answers=answers, requester_role=requester_role, audience=audience)

    if topic == "condition_general":
        return _answer_condition_general_intent(
            condition_name=plan.referenced_drug_name or None,
            meds=context.meds,
            schedules=context.schedules,
            profile=context.profile,
            message=message,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )

    if topic == "hospital_schedule":
        return _answer_hospital_schedule_intent(
            hospital_schedules=context.hospital_schedules,
            message=message,
            session_memory=context.session_memory,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )

    if topic == "current_meds":
        matched_med = None
        if plan.referenced_drug_name:
            matched_med = _extract_target_med(
                message=plan.referenced_drug_name,
                meds=context.meds,
                recent_messages=context.recent_messages,
                session_memory=context.session_memory,
            )
        if matched_med:
            return await _answer_med_detail_intent(
                message=plan.referenced_drug_name,
                meds=context.meds,
                schedules=context.schedules,
                recent_messages=context.recent_messages,
                session_memory=context.session_memory,
                matched_med=matched_med,
                dur_alerts=context.dur_alerts,
                adherence_summary=context.adherence_summary,
                guide=context.latest_guide,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        return _answer_med_list_intent(
            meds=context.meds,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )

    if topic == "med_schedule":
        if plan.referenced_drug_name:
            matched_med = _extract_target_med(
                message=plan.referenced_drug_name,
                meds=context.meds,
                recent_messages=context.recent_messages,
                session_memory=context.session_memory,
            )
            if matched_med:
                return await _answer_med_detail_intent(
                    message=plan.referenced_drug_name,
                    meds=context.meds,
                    schedules=context.schedules,
                    recent_messages=context.recent_messages,
                    session_memory=context.session_memory,
                    matched_med=matched_med,
                    dur_alerts=context.dur_alerts,
                    adherence_summary=context.adherence_summary,
                    guide=context.latest_guide,
                    target_label=target_label,
                    requester_role=requester_role,
                    audience=audience,
                )
        return _answer_schedule_intent(
            meds=context.meds,
            schedules=context.schedules,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )

    if topic == "external_drug":
        return await _answer_external_med_intent(
            message=message,
            meds=context.meds,
            schedules=context.schedules,
            recent_messages=context.recent_messages,
            profile=context.profile,
            external_drug_name=plan.referenced_drug_name,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )

    if topic == "drug_interaction":
        if plan.referenced_drug_name:
            return await _answer_external_interaction_intent(
                external_drug_name=plan.referenced_drug_name,
                meds=context.meds,
                profile=context.profile,
                adherence_summary=context.adherence_summary,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        return _answer_drug_interaction_overview(
            meds=context.meds,
            adherence_summary=context.adherence_summary,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )

    return None


# guide 기반 직접 응답
def _answer_guide_intent(
    *,
    guide: Guide | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    if not guide or not guide.content_text:
        return None

    base = f"{target_label} 기준 최신 가이드를 요약하면 다음과 같습니다.\n{guide.content_text}"

    if audience == "child":
        base += "\n어려운 부분은 보호자와 같이 확인하면 좋습니다."
    elif audience == "senior":
        base += "\n어지러움이나 낙상 위험이 있으면 복용 후 상태를 더 주의 깊게 살펴주세요."

    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


async def _answer_medication_caution_intent(
    *,
    message: str,
    guide: Guide | None,
    meds: list[dict[str, Any]],
    profile: PatientProfile | None,
    dur_alerts: list[dict[str, Any]],
    adherence_summary: dict[str, Any] | None,
    recent_messages: list[ChatMessage] | None,
    matched_med: dict[str, Any] | None = None,
    external_drug_name: str | None = None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    interaction_drug_name = external_drug_name or _extract_external_drug_name(message, recent_messages)
    if interaction_drug_name:
        return await _answer_external_interaction_intent(
            external_drug_name=interaction_drug_name,
            meds=meds,
            profile=profile,
            adherence_summary=adherence_summary,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )

    if _contains_any(message, ["새 감기약", "새 약", "감기약 추가", "감기약"]) and meds:
        record_points, general_points, next_points = _build_interaction_focus_points(
            med_names=[
                str(med.get("display_name") or "").strip() for med in meds if str(med.get("display_name") or "").strip()
            ],
            adherence_summary=adherence_summary,
        )
        general_points.insert(
            0,
            "새 감기약을 추가할 때는 해열진통제, 항히스타민, 진해거담 성분이 현재 복용약과 겹치지 않는지 먼저 확인하는 것이 좋습니다.",
        )
        base = _compose_medical_sections(
            current_record_points=record_points,
            general_info_points=general_points,
            next_check_points=next_points
            or ["새로 추가할 감기약의 제품명이나 성분명을 알려 주시면 현재 약과 비교해 드릴 수 있습니다."],
        )
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    matched_med = matched_med or _extract_target_med(message=message, meds=meds, recent_messages=recent_messages)
    record_points: list[str] = []
    general_points: list[str] = []
    next_points: list[str] = []

    if matched_med:
        med_name = str(matched_med.get("display_name") or "해당 약").strip()
        med_notes = str(matched_med.get("notes") or "").strip()
        med_info = matched_med.get("drug_info") or {}
        if med_notes:
            record_points.append(f"{med_name} 메모에는 `{med_notes}`로 기록되어 있습니다.")
        lookup = await _lookup_external_med_info(med_name)
        mfds_item = lookup.get("mfds")
        kids_items = lookup.get("kids") or []
        precautions = _first_clean_line(getattr(mfds_item, "precautions", None)) if mfds_item else ""
        if not precautions:
            precautions = _first_clean_line(str(med_info.get("precautions") or ""))
        if precautions:
            general_points.append(f"{med_name} 주의사항으로는 {precautions}")
        if "같이" in message or "상호작용" in message or "조심" in message:
            next_points.append(
                f"{med_name} 복용 후 두통, 발진, 호흡 불편 같은 이상 반응이 있으면 추가 복용 전에 상태를 확인해 주세요."
            )
        if kids_items:
            kids_summary = _first_clean_line(kids_items[0].get("content"))
            if kids_summary:
                general_points.append(f"추가 안전 근거로는 {kids_summary}")
        next_points.extend(_extract_dur_alert_points(dur_alerts=dur_alerts, med_name=med_name, limit=2))

    if profile and getattr(profile, "allergies", None):
        raw_allergies = str(profile.allergies).strip()
        if raw_allergies and ("음식" in message or "알레르기" in message):
            record_points.append(f"등록된 알레르기 정보는 {raw_allergies}입니다.")

    caution_body = ""
    if guide and isinstance(guide.content_json, dict):
        sections = guide.content_json.get("sections") or []
        for section in sections:
            title = str(section.get("title") or "")
            body = str(section.get("body") or "")
            if "주의" in title or "주의" in body or "신호" in title:
                caution_body = body
                break

    if caution_body:
        for line in caution_body.split("\n"):
            clean = line.strip().lstrip("-").strip()
            if clean and clean not in next_points and not any(keyword in clean for keyword in ["운동", "수면", "생활"]):
                next_points.append(clean)

    if not record_points and not general_points and not next_points:
        return None

    if not next_points:
        next_points.append("새 약을 추가하거나 함께 복용하기 전에는 현재 복용약과 성분 중복 여부를 먼저 확인해 주세요.")

    base = _compose_medical_sections(
        current_record_points=record_points,
        general_info_points=general_points,
        next_check_points=next_points,
    )

    if audience == "senior":
        base += "\n어지러움이 있으면 낙상 위험도 함께 조심해 주세요."

    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_general_caution_intent(
    *,
    profile: PatientProfile | None,
    guide: Guide | None,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    points: list[str] = []

    if profile:
        allergies = _split_text_items(getattr(profile, "allergies", None))
        conditions = _split_text_items(getattr(profile, "conditions", None))
        if allergies:
            points.append("알레르기: " + ", ".join(allergies))
        if conditions:
            points.append("건강 상태: " + ", ".join(conditions))
        sleep_hours = getattr(profile, "avg_sleep_hours_per_day", None)
        if sleep_hours is not None:
            points.append(
                f"수면은 하루 평균 {sleep_hours}시간으로 기록되어 있어, 수면 리듬을 일정하게 유지하는 것이 좋습니다."
            )
        exercise_minutes = getattr(profile, "avg_exercise_minutes_per_day", None)
        if exercise_minutes is not None:
            points.append(
                f"운동은 하루 평균 {exercise_minutes}분으로 기록되어 있어 무리하지 않는 범위에서 꾸준히 유지하는 것이 좋습니다."
            )

    if guide and isinstance(guide.content_json, dict):
        for section in guide.content_json.get("sections") or []:
            title = str(section.get("title") or "")
            body = str(section.get("body") or "").strip()
            if ("주의" in title or "생활" in title) and body:
                first_line = body.splitlines()[0].strip().lstrip("-").strip()
                if first_line and first_line not in points:
                    points.append(first_line)
            if len(points) >= 3:
                break

    if not points and meds:
        for med in meds[:2]:
            med_name = str(med.get("display_name") or "").strip()
            med_notes = str(med.get("notes") or "").strip()
            if med_name and med_notes:
                points.append(f"{med_name}: {med_notes}")

    if not points and schedules:
        schedule_text = _build_schedule_text(schedules, meds)
        first_line = _first_clean_line(schedule_text)
        if first_line and first_line != "등록된 복약 일정 없음":
            points.append(f"복약 일정: {first_line}")

    points.extend(_build_adherence_guidance_points(adherence_summary=adherence_summary))

    if not points:
        return None

    base = f"{target_label} 기준으로 지금 특히 주의해서 볼 점은 다음과 같습니다.\n" + "\n".join(
        f"- {point}" for point in _dedupe_lines(points, limit=3)
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


async def _answer_external_med_intent(
    *,
    message: str,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    recent_messages: list[ChatMessage] | None,
    profile: PatientProfile | None,
    external_drug_name: str | None = None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    drug_name = external_drug_name or _extract_external_drug_name(message, recent_messages)
    current_med_match = _find_best_med_match(query=drug_name or message, meds=meds)
    if current_med_match:
        current_med_answer = await _answer_med_detail_intent(
            message=str(drug_name or message),
            meds=meds,
            schedules=schedules,
            recent_messages=recent_messages,
            session_memory=None,
            matched_med=current_med_match,
            adherence_summary=None,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )
        if current_med_answer:
            return current_med_answer

    if not drug_name:
        base = (
            f"{target_label} 기준 현재 기록에 없는 약에 대해선 복용 여부를 바로 단정하기 어렵습니다. "
            "약 이름이나 처방 상황을 조금 더 알려주시면 확인 범위를 안내드릴 수 있습니다."
        )
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    topic_particle = _choose_korean_particle(drug_name, ("은", "는"))

    lookup = await _lookup_external_med_info(drug_name)
    mfds_item = lookup.get("mfds")
    kids_items = lookup.get("kids") or []

    profile_points: list[str] = []
    if profile:
        allergies = _split_text_items(getattr(profile, "allergies", None))
        conditions = _split_text_items(getattr(profile, "conditions", None))
        sleep_hours = getattr(profile, "avg_sleep_hours_per_day", None)
        exercise_minutes = getattr(profile, "avg_exercise_minutes_per_day", None)
        if allergies:
            profile_points.append("알레르기: " + ", ".join(allergies[:3]))
        if conditions:
            profile_points.append("건강 상태: " + ", ".join(conditions[:3]))
        if sleep_hours is not None:
            profile_points.append(f"수면: 하루 평균 {sleep_hours}시간")
        if exercise_minutes is not None:
            profile_points.append(f"운동: 하루 평균 {exercise_minutes}분")

    if mfds_item:
        record_points = [f"{drug_name}{topic_particle} 현재 복용 중인 약으로 기록되어 있지는 않습니다."]
        general_points: list[str] = []
        next_points: list[str] = []
        item_name = str(getattr(mfds_item, "item_name", "") or drug_name).strip()
        efficacy = _summarize_text(getattr(mfds_item, "efficacy", None), max_sentences=1)
        precautions = _summarize_text(getattr(mfds_item, "precautions", None), max_sentences=2)
        dosage_info = _summarize_text(getattr(mfds_item, "dosage_info", None), max_sentences=1)
        if item_name:
            general_points.append(f"약 정보명은 {item_name}입니다.")
        if efficacy:
            general_points.append(f"일반적으로는 {efficacy}")
        if precautions:
            general_points.append(f"주의할 점으로는 {precautions}")
        if dosage_info:
            next_points.append(f"복용 참고로는 {dosage_info}")
        if kids_items:
            first_kids = _summarize_text(kids_items[0].get("content"), max_sentences=1)
            if first_kids:
                general_points.append(f"추가 안전 근거로는 {first_kids}")
        if profile_points:
            record_points.append(
                "현재 건강기록 기준으로는 " + " / ".join(profile_points[:2]) + "를 함께 보는 것이 좋습니다."
            )
        next_points.append(
            "실제 복용 전에는 처방 여부와 성분을 다시 확인하고, 복용 판단은 의료진이나 약사와 상의하는 것이 좋습니다."
        )
        base = _compose_medical_sections(
            current_record_points=record_points,
            general_info_points=general_points,
            next_check_points=next_points,
        )
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    base = _compose_medical_sections(
        current_record_points=[
            f"{drug_name}{topic_particle} 현재 복용 중인 약으로 기록되어 있지는 않습니다.",
            *(
                [f"현재 건강기록 기준으로는 {' / '.join(profile_points[:2])}를 함께 볼 수 있습니다."]
                if profile_points
                else []
            ),
        ],
        general_info_points=[],
        next_check_points=["제품명이나 성분명이 더 정확하면 안내 범위를 더 좁힐 수 있습니다."],
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


async def _answer_external_interaction_intent(
    *,
    external_drug_name: str,
    meds: list[dict[str, Any]],
    profile: PatientProfile | None,
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    lookup = await _lookup_external_med_info(external_drug_name)
    record_points, general_points, next_points = _build_external_interaction_points(
        external_drug_name=external_drug_name,
        meds=meds,
        profile=profile,
        adherence_summary=adherence_summary,
        lookup=lookup,
    )
    base = _compose_medical_sections(
        current_record_points=record_points,
        general_info_points=general_points,
        next_check_points=next_points,
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


# 일상 대화 응답
def _answer_daily_chat(
    *,
    message: str,
    requester_role: RequesterRole,
    target_label: str,
    data_readiness: str = "partial",
) -> str:
    normalized = (message or "").strip()

    if _contains_any(normalized, ["이름이 뭐", "너 이름", "누구야"]):
        return "저는 복약과 건강 정보를 도와드리는 의료 챗봇입니다."

    if _contains_any(normalized, _BOT_CAPABILITY_KEYWORDS):
        if data_readiness == "empty":
            return (
                "저는 약 정보, 복용 시 주의사항, 병원 일정, 건강프로필 입력 방법, 생활관리 질문을 도와드릴 수 있습니다. "
                "아직 기록이 적다면 일반적인 기준으로 먼저 설명드리고, 맞춤 답변이 필요한 경우에만 건강프로필이나 복약 정보를 더 요청드릴게요."
            )
        return (
            "저는 복용 중인 약, 복약 시간, 주의사항, 놓친 복약, 병원 일정, 건강프로필, 생활관리, 보호자 체크포인트를 "
            "안내해 드릴 수 있습니다. 기록이 부족한 부분은 일반적인 기준으로 먼저 설명드리고, 맞춤 답변이 필요할 때만 추가 정보를 부탁드립니다."
        )

    if _contains_any(normalized, ["너 뭐해", "뭘 하는", "뭐 하는 애", "뭐하는 애", "뭐하는 애니"]):
        if data_readiness == "empty":
            return "저는 약 정보와 건강 질문을 기본적으로 안내하고, 기록이 쌓이면 복약 일정과 건강 기록까지 연결해 설명하는 의료 챗봇입니다."
        return "저는 복약 일정, 복용 중인 약, 주의사항, 건강 기록을 기준으로 안내를 도와드리는 의료 챗봇입니다."

    if _contains_any(normalized, ["오늘 어때", "오늘 하루", "기분 어때"]):
        return "저는 괜찮습니다. 오늘도 복약과 건강 관련 질문을 도와드릴 준비가 되어 있습니다."

    if _contains_any(normalized, ["고마워", "감사"]):
        return "도움이 되었다면 다행입니다. 필요한 내용이 있으면 이어서 말씀해 주세요."

    if _contains_any(normalized, ["안녕", "반가워"]):
        if data_readiness == "empty":
            return (
                "안녕하세요. 복약과 건강 정보를 도와드릴게요. "
                "지금은 일반적인 약 정보나 건강 질문부터 안내드릴 수 있고, 건강프로필이나 복약 정보가 쌓이면 맞춤 답변까지 더 정확하게 이어드릴게요."
            )
        if data_readiness == "rich":
            return (
                f"안녕하세요. {target_label} 기준 기록을 참고해서 복약과 건강 정보를 도와드릴게요. "
                "약 정보, 복용 시간, 병원 일정, 건강프로필 중 궁금한 것을 편하게 물어보세요."
            )
        return (
            f"안녕하세요. {target_label} 기준으로 확인 가능한 기록을 참고해 복약과 건강 정보를 도와드릴게요. "
            "부족한 정보가 있으면 일반적인 기준으로 먼저 설명드리겠습니다."
        )

    if _contains_any(normalized, ["잘 자"]):
        return "편안한 밤 보내세요. 복약 일정이 있다면 잊지 않도록 한 번 더 확인해 주세요."

    return (
        "일상적인 대화도 자연스럽게 이어갈 수 있습니다. 의료 관련 내용은 현재 기록이 있으면 맞춤형으로, 부족하면 일반적인 기준으로 먼저 안내드릴게요."
        if requester_role != RequesterRole.CAREGIVER
        else "일상적인 대화도 가능하지만, 보호자 관점에서는 복약과 상태 확인 중심으로 우선 안내드릴 수 있습니다."
    )


def _extract_core_answer(answer: str, requester_role: RequesterRole) -> str:
    text = str(answer or "").replace(CHAT_DISCLAIMER, "").strip()
    return text


def _compose_answers(
    *,
    answers: list[str],
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    parts: list[str] = []
    seen: set[str] = set()
    for answer in answers:
        core = _extract_core_answer(answer, requester_role)
        if core and core not in seen:
            seen.add(core)
            parts.append(core)

    if not parts:
        return None

    combined = "\n\n".join(parts[:3])
    combined = re.sub(r"(회원님 기록 기준으로|선택한 복약자 기준으로)\s*", "", combined)
    combined = combined.strip()
    if requester_role == RequesterRole.CAREGIVER:
        return _to_caregiver_style(answer=combined, audience=audience)
    return combined


def _compose_medical_sections(
    *,
    current_record_points: list[str],
    general_info_points: list[str],
    next_check_points: list[str],
) -> str:
    sections: list[str] = []

    current_points = _dedupe_lines(current_record_points, limit=4)
    general_points = _dedupe_lines(general_info_points, limit=3)
    next_points = _dedupe_lines(next_check_points, limit=3)

    if current_points:
        sections.append("현재 기록 기준\n" + "\n".join(f"- {item}" for item in current_points))
    if general_points:
        sections.append("일반적으로 보면\n" + "\n".join(f"- {item}" for item in general_points))
    if next_points:
        sections.append("지금 확인할 포인트\n" + "\n".join(f"- {item}" for item in next_points))

    return "\n\n".join(sections).strip()


def _should_finalize_with_rules(
    *,
    analysis: QuestionAnalysis,
    composed_answer: str | None,
    clarification_reply: str | None,
) -> bool:
    if clarification_reply:
        return True
    if not composed_answer:
        return False
    if analysis.answer_mode in {"daily_chat", "direct_fact", "safety_guidance", "external_drug_counseling"}:
        return True
    if analysis.primary_intent in {
        "daily",
        "external_med",
        "condition_general",
        "medication_caution",
        "med_detail",
        "med_list",
        "schedule",
        "hospital_schedule",
        "profile_body",
        "profile_summary",
        "profile_guidance",
        "general_caution",
        "tonight_check",
        "adherence_priority",
        "session_summary",
        "lifestyle_top",
    }:
        return True
    return False


def _build_fact_summary(
    *,
    analysis: QuestionAnalysis,
    context: PatientChatContext,
    target_label: str,
) -> str:
    points: list[str] = []

    if analysis.target_med:
        med_name = str(analysis.target_med.get("display_name") or "").strip()
        dosage = str(analysis.target_med.get("dosage") or "").strip()
        notes = str(analysis.target_med.get("notes") or "").strip()
        source_document_id = analysis.target_med.get("source_document_id")
        if med_name:
            line = med_name
            if dosage:
                line += f" {dosage}"
            if notes:
                line += f" / {notes}"
            points.append("현재 기록 약 정보: " + line)
        if source_document_id:
            points.append(f"확정 약 출처 문서: #{source_document_id}")
        patient_med_id = analysis.target_med.get("patient_med_id")
        schedule_lines: list[str] = []
        for schedule in context.schedules:
            if schedule.get("patient_med_id") != patient_med_id:
                continue
            for item in schedule.get("times") or []:
                schedule_lines.append(
                    f"{_humanize_days(item.get('days_of_week'))} {_humanize_time(item.get('time_of_day'))}".strip()
                )
        if schedule_lines:
            points.append("복용 시간: " + ", ".join(schedule_lines[:3]))
        points.extend(_extract_dur_alert_points(dur_alerts=context.dur_alerts, med_name=med_name, limit=2))
        points.extend(_build_med_adherence_points(med_name=med_name, adherence_summary=context.adherence_summary))

    if analysis.external_drug_name:
        points.append(f"질문 약 이름: {analysis.external_drug_name}")
        if not any(
            _contains_keyword(str(med.get("display_name") or ""), analysis.external_drug_name) for med in context.meds
        ):
            points.append("현재 복용약 목록에는 없음")

    if analysis.target_condition:
        points.append(f"질문 질환: {analysis.target_condition}")

    if analysis.primary_intent in {"profile_body", "profile_summary"} and context.profile:
        if getattr(context.profile, "height_cm", None) is not None:
            points.append(f"키: {context.profile.height_cm}cm")
        if getattr(context.profile, "weight_kg", None) is not None:
            points.append(f"몸무게: {context.profile.weight_kg}kg")
        if getattr(context.profile, "bmi", None) is not None:
            points.append(f"BMI: {context.profile.bmi}")

    if analysis.primary_intent == "hospital_schedule" and context.hospital_schedules:
        next_schedule = context.hospital_schedules[0]
        title = str(getattr(next_schedule, "title", "") or "병원 일정").strip()
        scheduled_at = _format_datetime_korean(getattr(next_schedule, "scheduled_at", None))
        hospital_name = str(getattr(next_schedule, "hospital_name", "") or "").strip()
        line = f"다음 병원 일정: {scheduled_at} / {title}"
        if hospital_name:
            line += f" / {hospital_name}"
        points.append(line)

    conditions = _split_text_items(getattr(context.profile, "conditions", None) if context.profile else None)
    allergies = _split_text_items(getattr(context.profile, "allergies", None) if context.profile else None)
    if conditions:
        points.append("건강 상태: " + ", ".join(conditions[:3]))
    if allergies:
        points.append("알레르기: " + ", ".join(allergies[:3]))

    if analysis.primary_intent in {"med_list", "schedule", "med_time_split"} and context.meds:
        med_names = [
            str(med.get("display_name") or "").strip()
            for med in context.meds
            if str(med.get("display_name") or "").strip()
        ]
        if med_names:
            points.append(f"{target_label} 현재 복용약: " + ", ".join(med_names[:4]))

    if (
        analysis.primary_intent == "general_caution"
        and context.latest_guide
        and isinstance(context.latest_guide.content_json, dict)
    ):
        for section in context.latest_guide.content_json.get("sections") or []:
            title = str(section.get("title") or "").strip()
            body = str(section.get("body") or "").strip()
            if ("주의" in title or "생활" in title or "신호" in title) and body:
                points.append(f"{title}: {_first_clean_line(body)}")
            if len(points) >= 5:
                break

    if analysis.primary_intent in {"general_caution", "profile_guidance", "adherence_priority", "tonight_check"}:
        points.extend(_build_adherence_guidance_points(adherence_summary=context.adherence_summary))

    deduped = _dedupe_lines(points, limit=6)
    return "\n".join(f"- {item}" for item in deduped) if deduped else "질문 관련 결정적 사실이 아직 충분하지 않습니다."


def _normalize_intent_order(intents: list[str], requester_role: RequesterRole) -> list[str]:
    ordered: list[str] = []
    skip = set()

    if "external_med" in intents:
        skip.update({"med_detail", "general_caution", "allergy_food", "guide"})
    if "lifestyle_top" in intents:
        skip.update({"profile_sleep", "profile_exercise", "allergy_food"})
    if "profile_summary" in intents:
        skip.update({"guide", "session_summary"})
    if "med_time_split" in intents:
        skip.add("med_list")
    if "med_detail" in intents:
        skip.add("schedule")
    if requester_role != RequesterRole.CAREGIVER and "caregiver_check" in intents:
        # 본인 질문에서는 caregiver_check를 self_check로 대체
        intents = [intent for intent in intents if intent != "caregiver_check"] + ["self_check"]

    priority = [
        "rash",
        "missed_dose",
        "emergency_guidance",
        "self_check",
        "caregiver_check",
        "school_observation",
        "cold_med_caution",
        "external_med",
        "condition_general",
        "adherence_priority",
        "tonight_check",
        "schedule_order",
        "symptom_cause",
        "observation_check",
        "med_detail",
        "medication_caution",
        "general_caution",
        "profile_summary",
        "profile_body",
        "profile_guidance",
        "med_time_split",
        "med_regularity",
        "med_list",
        "hospital_schedule",
        "schedule",
        "allergy_food",
        "lifestyle_top",
        "session_summary",
        "profile_smoking",
        "profile_alcohol",
        "profile_sleep",
        "profile_exercise",
        "guide",
        "daily",
        "general",
    ]

    for key in priority:
        if key in intents and key not in skip and key not in ordered:
            ordered.append(key)

    for intent in intents:
        if intent not in skip and intent not in ordered:
            ordered.append(intent)

    return ordered


# LLM 호출
async def _call_chat_model(*, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    api_key = (os.getenv("OPENAI_API_KEY", "") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY missing")

    model = (os.getenv("OPENAI_MODEL", "gpt-4o-mini") or "").strip()

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(timeout=40) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    content = data["choices"][0]["message"]["content"].strip()
    if not content:
        raise RuntimeError("empty llm content")

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

    return {
        "content": content,
        "is_emergency": False,
        "emergency_message": None,
        "disclaimer": CHAT_DISCLAIMER,
    }


async def _plan_chat_question(
    *,
    message: str,
    context: PatientChatContext,
    requester_role: RequesterRole,
    audience: str,
    target_label: str,
) -> ChatPlan | None:
    if not _has_openai_api_key():
        return None

    try:
        system_prompt = _read_prompt_template("chat_planner_system_prompt.txt").format(
            requester_role=requester_role.value,
            target_label=target_label,
            audience_label=_audience_label(audience),
        )
        user_prompt = _read_prompt_template("chat_planner_user_prompt.txt").format(
            user_message=message,
            meds_text=_build_meds_text(context.meds),
            schedule_text=_build_schedule_text(context.schedules, context.meds),
            hospital_schedule_text=_build_hospital_schedule_brief(context.hospital_schedules),
            profile_text=_build_profile_text(context.profile),
            history_text=_build_recent_history_for_planner(context.recent_messages),
            session_memory_text=_build_session_memory_text(context.session_memory),
        )
    except RuntimeError:
        logger.warning("chat planner prompts missing; planner disabled")
        return None

    try:
        result = await _call_chat_model(system_prompt=system_prompt, user_prompt=user_prompt)
    except Exception:
        logger.exception("chat planner failed")
        return None

    topic = str(result.get("topic") or "").strip()
    if not topic:
        return None

    requested_fields = result.get("requested_fields") or []
    if not isinstance(requested_fields, list):
        requested_fields = []
    use_record_data = result.get("use_record_data") or []
    if not isinstance(use_record_data, list):
        use_record_data = []

    referenced_drug_name = str(result.get("referenced_drug_name") or "").strip() or None
    clarification_question = str(result.get("clarification_question") or "").strip() or None

    return ChatPlan(
        topic=topic,
        requested_fields=[str(item).strip() for item in requested_fields if str(item).strip()],
        referenced_drug_name=referenced_drug_name,
        needs_clarification=bool(result.get("needs_clarification", False)),
        clarification_question=clarification_question,
        use_record_data=[str(item).strip() for item in use_record_data if str(item).strip()],
        answer_style=str(result.get("answer_style") or "direct").strip() or "direct",
    )


# 일반 fallback 답변
def _fallback_reply(
    *,
    intent: str,
    latest_guide: Guide | None,
    meds: list[dict[str, Any]],
    profile: PatientProfile | None,
    meds_text: str,
    schedule_text: str,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    data_readiness = (
        "rich" if (meds or schedule_text != "등록된 복약 일정 없음" or latest_guide or profile) else "empty"
    )
    short_profile: list[str] = []
    allergies = _split_text_items(getattr(profile, "allergies", None) if profile else None)
    conditions = _split_text_items(getattr(profile, "conditions", None) if profile else None)
    if conditions:
        short_profile.append("건강 상태: " + ", ".join(conditions[:2]))
    if allergies:
        short_profile.append("알레르기: " + ", ".join(allergies[:2]))

    if intent == "external_med":
        base = (
            "현재 복용약과는 별도로 일반적인 약 정보를 설명해 드릴 수 있습니다. "
            "약 이름이나 성분명을 한 번 더 정확히 적어 주시면 용도, 주의사항, 현재 기록 기준 주의점을 나눠 안내드리겠습니다."
        )
    elif intent == "hospital_schedule":
        base = "병원 일정은 외래 예약인지 검사 일정인지에 따라 다르게 확인해야 합니다. 가장 가까운 예약인지, 특정 일정인지 함께 적어 주세요."
    elif intent == "condition_general":
        tail = f" 현재 기록에서 {' / '.join(short_profile)}도 함께 보입니다." if short_profile else ""
        base = (
            "질환에 대한 일반적인 치료 방향은 설명할 수 있지만, 특정 약 추천은 현재 진단과 복용약을 함께 봐야 합니다."
            + tail
        )
    elif intent == "general":
        if data_readiness == "empty":
            base = (
                "현재 기록이 많지 않아 맞춤 답변은 제한되지만, 일반적인 약 정보와 서비스 안내는 바로 도와드릴 수 있습니다. "
                "예를 들어 `게보린이 뭐야?`, `너는 뭘 도와줘?`, `건강프로필에 뭐를 입력하면 돼?`처럼 물어보시면 자연스럽게 이어서 설명드릴게요."
            )
        elif not meds and schedule_text == "등록된 복약 일정 없음":
            if latest_guide or profile:
                base = (
                    "현재 복용약이나 복약 일정 정보는 부족하지만, 건강 프로필과 가이드 범위 안에서는 안내할 수 있습니다. "
                    "예를 들어 건강프로필 요약, 수면/운동/흡연/음주 기록, 생활관리 포인트를 물어보시면 바로 이어서 설명드릴 수 있습니다."
                )
            else:
                base = (
                    "현재 기록에는 복용약이나 복약 일정이 아직 없어 맞춤 답변은 제한됩니다. "
                    "그래도 일반적인 약 정보, 서비스 사용 방법, 병원 일정 확인, 건강프로필 등록 전 안내는 도와드릴 수 있습니다."
                )
        else:
            base = (
                "지금 질문은 범위가 조금 넓어 보여서, 확인하려는 기준을 한 가지만 먼저 잡으면 더 정확히 이어갈 수 있습니다. "
                "예를 들어 약 이름, 복용 시간, 병원 예약, 건강프로필 중 어느 쪽인지 먼저 적어 주세요."
            )
    else:
        base = (
            "현재 질문에 바로 연결할 근거가 충분하지 않습니다. "
            "약 이름, 복용 상황, 병원 일정, 건강 기록 중 어느 쪽인지 한 줄만 더 알려주시면 맞는 방향으로 이어서 설명드리겠습니다."
        )

    if audience == "senior":
        base += "\n어지러움이나 낙상 위험이 있는 경우 복용 후 상태를 함께 확인해 주세요."

    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


# assistant 응급 플래그 재구성
def _reconstruct_emergency_fields(*, current: ChatMessage, previous: ChatMessage | None) -> tuple[bool, str | None]:
    if current.role != "assistant":
        return False, None

    if previous and previous.role == "user":
        is_emergency, emergency_message = _detect_emergency(previous.content)
        if is_emergency:
            return True, emergency_message

    if "응급 상황이 의심됩니다" in current.content:
        return True, "응급 상황이 의심됩니다. 즉시 119 또는 가까운 응급실/의료기관에 연락해 주세요."

    return False, None


async def _build_deterministic_answer_parts(
    *,
    analysis: QuestionAnalysis,
    context: PatientChatContext,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> list[str]:
    deterministic_parts: list[str] = []

    for current_intent in analysis.intents:
        deterministic_answer: str | None = None

        if current_intent in {
            "profile_body",
            "profile_summary",
            "profile_guidance",
            "profile_smoking",
            "profile_alcohol",
            "profile_sleep",
            "profile_exercise",
            "profile_conditions",
            "profile_allergies",
            "profile_hospitalization",
        }:
            if current_intent == "profile_guidance":
                deterministic_answer = _answer_profile_guidance_intent(
                    message=analysis.raw_message,
                    profile=context.profile,
                    guide=context.latest_guide,
                    adherence_summary=context.adherence_summary,
                    target_label=target_label,
                    requester_role=requester_role,
                    audience=audience,
                )
            else:
                deterministic_answer = _answer_profile_intent(
                    intent=current_intent,
                    profile=context.profile,
                    target_label=target_label,
                    requester_role=requester_role,
                    audience=audience,
                )
        elif current_intent == "med_time_split":
            deterministic_answer = _answer_med_time_split_intent(
                meds=context.meds,
                schedules=context.schedules,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "med_regularity":
            deterministic_answer = _answer_med_regularity_intent(
                meds=context.meds,
                schedules=context.schedules,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "med_prn":
            deterministic_answer = _answer_med_prn_intent(
                message=analysis.raw_message,
                meds=context.meds,
                schedules=context.schedules,
                recent_messages=context.recent_messages,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "med_detail":
            deterministic_answer = await _answer_med_detail_intent(
                message=analysis.raw_message,
                meds=context.meds,
                schedules=context.schedules,
                recent_messages=context.recent_messages,
                session_memory=context.session_memory,
                matched_med=analysis.target_med,
                dur_alerts=context.dur_alerts,
                adherence_summary=context.adherence_summary,
                guide=context.latest_guide,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "med_list":
            deterministic_answer = _answer_med_list_intent(
                meds=context.meds,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "caregiver_check":
            deterministic_answer = _answer_caregiver_check_intent(
                guide=context.latest_guide,
                meds=context.meds,
                schedules=context.schedules,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "self_check":
            deterministic_answer = _answer_self_check_intent(
                guide=context.latest_guide,
                meds=context.meds,
                schedules=context.schedules,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "allergy_food":
            deterministic_answer = _answer_allergy_food_intent(
                profile=context.profile,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "missed_dose":
            deterministic_answer = _answer_missed_dose_intent(
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "emergency_guidance":
            deterministic_answer = _answer_emergency_guidance_intent(
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "lifestyle_top":
            deterministic_answer = _answer_lifestyle_top_intent(
                guide=context.latest_guide,
                profile=context.profile,
                adherence_summary=context.adherence_summary,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "session_summary":
            deterministic_answer = _answer_session_summary_intent(
                meds=context.meds,
                profile=context.profile,
                adherence_summary=context.adherence_summary,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "tonight_check":
            deterministic_answer = _answer_tonight_check_intent(
                meds=context.meds,
                schedules=context.schedules,
                adherence_summary=context.adherence_summary,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "schedule_order":
            deterministic_answer = _answer_schedule_order_intent(
                meds=context.meds,
                schedules=context.schedules,
                time_period=analysis.time_period,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "adherence_priority":
            deterministic_answer = _answer_adherence_priority_intent(
                meds=context.meds,
                schedules=context.schedules,
                adherence_summary=context.adherence_summary,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "symptom_cause":
            deterministic_answer = _answer_symptom_cause_intent(
                message=analysis.raw_message,
                meds=context.meds,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "observation_check":
            deterministic_answer = _answer_observation_check_intent(
                message=analysis.raw_message,
                matched_med=analysis.target_med,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "school_observation":
            deterministic_answer = _answer_school_observation_intent(
                profile=context.profile,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "cold_med_caution":
            deterministic_answer = _answer_cold_med_caution_intent(
                profile=context.profile,
                meds=context.meds,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "rash":
            deterministic_answer = _answer_rash_intent(
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "schedule":
            deterministic_answer = _answer_schedule_intent(
                meds=context.meds,
                schedules=context.schedules,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "hospital_schedule":
            deterministic_answer = _answer_hospital_schedule_intent(
                hospital_schedules=context.hospital_schedules,
                message=analysis.raw_message,
                session_memory=context.session_memory,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "medication_caution":
            deterministic_answer = await _answer_medication_caution_intent(
                message=analysis.raw_message,
                guide=context.latest_guide,
                meds=context.meds,
                profile=context.profile,
                dur_alerts=context.dur_alerts,
                adherence_summary=context.adherence_summary,
                recent_messages=context.recent_messages,
                matched_med=analysis.target_med,
                external_drug_name=analysis.external_drug_name,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "general_caution":
            deterministic_answer = _answer_general_caution_intent(
                profile=context.profile,
                guide=context.latest_guide,
                meds=context.meds,
                schedules=context.schedules,
                adherence_summary=context.adherence_summary,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "external_med":
            deterministic_answer = await _answer_external_med_intent(
                message=analysis.raw_message,
                meds=context.meds,
                schedules=context.schedules,
                recent_messages=context.recent_messages,
                profile=context.profile,
                external_drug_name=analysis.external_drug_name,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "condition_general":
            deterministic_answer = _answer_condition_general_intent(
                condition_name=analysis.target_condition,
                meds=context.meds,
                schedules=context.schedules,
                profile=context.profile,
                message=analysis.raw_message,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "guide":
            deterministic_answer = _answer_guide_intent(
                guide=context.latest_guide,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        elif current_intent == "daily":
            deterministic_answer = _answer_daily_chat(
                message=analysis.raw_message,
                requester_role=requester_role,
                target_label=target_label,
                data_readiness=_resolve_data_readiness(context),
            )

        if deterministic_answer:
            deterministic_parts.append(deterministic_answer)

    return deterministic_parts


class ChatService:
    @staticmethod
    def _to_chat_message_item(*, row: ChatMessage, previous: ChatMessage | None = None) -> ChatMessageItem:
        is_emergency, emergency_message = _reconstruct_emergency_fields(
            current=row,
            previous=previous,
        )
        return ChatMessageItem(
            message_id=int(row.id),
            role=row.role,
            content=row.content,
            status=str(getattr(row, "status", "") or "completed"),
            error_message=getattr(row, "error_message", None),
            is_emergency=is_emergency,
            emergency_message=emergency_message,
            disclaimer=CHAT_DISCLAIMER if row.role == "assistant" else None,
            created_at=row.created_at,
        )

    @staticmethod
    async def _enqueue_chat_reply_task(*, session_id: int, user_message_id: int, assistant_message_id: int) -> None:
        payload = {
            "task": "generate_chat_reply",
            "session_id": session_id,
            "user_message_id": user_message_id,
            "assistant_message_id": assistant_message_id,
        }
        client = redis.from_url(REDIS_URL, decode_responses=True)
        try:
            await client.lpush(CHAT_WORKER_QUEUE, json.dumps(payload, ensure_ascii=False))
        finally:
            await client.aclose()

    @staticmethod
    async def _generate_assistant_content(
        *,
        session_id: int,
        patient_id: int,
        requester: User,
        stripped: str,
    ) -> tuple[str, QuestionAnalysis, ChatPlan | None, PatientChatContext]:
        requester_role = await _resolve_requester_role(int(requester.id))
        target_label = "선택한 복약자" if requester_role == RequesterRole.CAREGIVER else "회원님 기록"

        context = await _build_patient_chat_context(
            session_id=session_id,
            patient_id=patient_id,
            include_kids_evidence=False,
        )

        audience = _resolve_audience(context.profile)
        chat_plan = await _plan_chat_question(
            message=stripped,
            context=context,
            requester_role=requester_role,
            audience=audience,
            target_label=target_label,
        )
        analysis = _analyze_question(
            message=stripped,
            meds=context.meds,
            recent_messages=context.recent_messages,
            requester_role=requester_role,
            profile=context.profile,
            session_memory=context.session_memory,
        )
        chat_plan = _harmonize_chat_plan(analysis=analysis, plan=chat_plan)
        is_emergency = analysis.is_emergency
        emergency_message = analysis.emergency_message
        intent = analysis.primary_intent
        llm_preferred = _should_prefer_llm(analysis=analysis)
        record_context_available = _has_required_context_for_request(
            analysis=analysis,
            plan=chat_plan,
            context=context,
        )
        personalized_request = _is_personalized_request(analysis=analysis, plan=chat_plan)

        if analysis.primary_intent in EXTERNAL_EVIDENCE_INTENTS:
            context.kids_evidence = await _build_kids_evidence(meds=context.meds, profile=context.profile)

        context.rag_context = await _build_rag_context(
            intent=intent,
            latest_guide=context.latest_guide,
            meds=context.meds,
            schedules=context.schedules,
            profile=context.profile,
            kids_evidence=context.kids_evidence,
        )

        if is_emergency:
            assistant_content = f"{emergency_message} 현재 질문은 즉시 전문 의료진 확인이 우선입니다."
            return assistant_content, analysis, chat_plan, context

        if personalized_request and not record_context_available:
            assistant_content = _build_record_required_reply(
                analysis=analysis,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
            return assistant_content, analysis, chat_plan, context

        planned_reply = await _render_planned_reply(
            plan=chat_plan,
            message=stripped,
            context=context,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )
        if planned_reply:
            return planned_reply, analysis, chat_plan, context

        deterministic_parts = await _build_deterministic_answer_parts(
            analysis=analysis,
            context=context,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )

        composed_answer = _compose_answers(
            answers=deterministic_parts,
            requester_role=requester_role,
            audience=audience,
        )

        meds_text = _build_meds_text(context.meds)
        schedule_text = _build_schedule_text(context.schedules, context.meds)
        hospital_schedule_text = _build_hospital_schedule_text(context.hospital_schedules)
        profile_text = _build_profile_text(context.profile)
        guide_text = _build_guide_text(context.latest_guide)
        history_text = _build_history_text(context.recent_messages)
        session_memory_text = _build_session_memory_text(context.session_memory)
        kids_text = _build_kids_text(context.kids_evidence)
        rag_text = _build_rag_text(context.rag_context)
        deterministic_text = _build_fact_summary(
            analysis=analysis,
            context=context,
            target_label=target_label,
        )
        if composed_answer:
            deterministic_text = (
                deterministic_text + "\n- 현재 직접 답변 초안: " + _extract_core_answer(composed_answer, requester_role)
            )
        external_lookup = (
            await _lookup_external_med_info(analysis.external_drug_name) if analysis.external_drug_name else None
        )
        external_drug_text = _build_external_drug_text(
            drug_name=analysis.external_drug_name,
            lookup=external_lookup,
        )
        clarification_reply = _build_clarification_reply(
            analysis=analysis,
            context=context,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )

        if clarification_reply:
            return clarification_reply, analysis, chat_plan, context

        if _should_finalize_with_rules(
            analysis=analysis,
            composed_answer=composed_answer,
            clarification_reply=clarification_reply,
        ):
            assistant_content = composed_answer or _fallback_reply(
                intent=intent,
                latest_guide=context.latest_guide,
                meds=context.meds,
                profile=context.profile,
                meds_text=meds_text,
                schedule_text=schedule_text,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
            return assistant_content, analysis, chat_plan, context

        if llm_preferred:
            try:
                system_prompt = _read_prompt_template("chat_system_prompt.txt").format(
                    requester_role=requester_role.value,
                    target_label=target_label,
                    answer_mode=analysis.answer_mode,
                    audience_label=_audience_label(audience),
                    extra_safety=_extra_safety_text(audience),
                    kids_text=kids_text,
                    rag_text=rag_text,
                    external_drug_text=external_drug_text,
                    deterministic_text=deterministic_text,
                    disclaimer=CHAT_DISCLAIMER,
                )
                user_prompt = _read_prompt_template("chat_user_prompt.txt").format(
                    guide_text=guide_text,
                    meds_text=meds_text,
                    schedule_text=schedule_text,
                    hospital_schedule_text=hospital_schedule_text,
                    profile_text=profile_text,
                    external_drug_text=external_drug_text,
                    deterministic_text=deterministic_text,
                    history_text=history_text,
                    session_memory_text=session_memory_text,
                    user_message=stripped,
                )
                llm_result = await _call_chat_model(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
                assistant_content = (llm_result.get("content") or "").strip()
                if not assistant_content:
                    raise ValueError("empty assistant content")
                return assistant_content, analysis, chat_plan, context
            except Exception:
                logger.exception("chat fallback used session_id=%s", session_id)

        assistant_content = composed_answer or _fallback_reply(
            intent=intent,
            latest_guide=context.latest_guide,
            meds=context.meds,
            profile=context.profile,
            meds_text=meds_text,
            schedule_text=schedule_text,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )
        return assistant_content, analysis, chat_plan, context

    @staticmethod
    async def _generate_fast_assistant_content(
        *,
        session_id: int,
        patient_id: int,
        requester: User,
        stripped: str,
    ) -> tuple[str, QuestionAnalysis, PatientChatContext] | None:
        requester_role = await _resolve_requester_role(int(requester.id))
        context = await _build_patient_chat_context(
            session_id=session_id,
            patient_id=patient_id,
            include_kids_evidence=False,
        )
        analysis = _analyze_question(
            message=stripped,
            meds=context.meds,
            recent_messages=context.recent_messages,
            requester_role=requester_role,
            profile=context.profile,
            session_memory=context.session_memory,
        )
        if analysis.primary_intent not in FAST_SYNC_INTENTS:
            return None

        target_label = "선택한 복약자" if requester_role == RequesterRole.CAREGIVER else "회원님 기록"
        audience = _resolve_audience(context.profile)
        answers = await _build_deterministic_answer_parts(
            analysis=analysis,
            context=context,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )
        assistant_content = _compose_answers(
            answers=answers,
            requester_role=requester_role,
            audience=audience,
        )
        if not assistant_content:
            return None
        return assistant_content, analysis, context

    @staticmethod
    async def create_session(
        *,
        requester: User,
        patient_id: int,
        mode: str,
    ) -> ChatSessionCreateResponse:
        session = await ChatSession.create(
            user_id=int(requester.id),
            patient_id=patient_id,
            mode=mode,
        )
        await ChatSessionMemory.get_or_create(session_id=int(session.id))

        return ChatSessionCreateResponse(
            success=True,
            data=ChatSessionCreateData(
                session_id=int(session.id),
                patient_id=patient_id,
                mode=mode,
                created_at=session.created_at,
            ),
        )

    @staticmethod
    async def create_feedback(
        *,
        requester: User,
        session_id: int,
        assistant_message_id: int,
        helpful: bool,
        feedback_type: str | None,
        comment: str | None,
    ) -> ChatFeedbackCreateResponse:
        session = await ChatSession.get_or_none(id=session_id)
        if not session:
            raise ChatServiceError(
                status_code=404,
                code="CHAT_SESSION_NOT_FOUND",
                message="채팅 세션을 찾을 수 없습니다.",
            )

        assistant_message = await ChatMessage.get_or_none(
            id=assistant_message_id,
            session_id=session_id,
            role="assistant",
        )
        if not assistant_message:
            raise ChatServiceError(
                status_code=404,
                code="CHAT_MESSAGE_NOT_FOUND",
                message="피드백 대상 assistant 메시지를 찾을 수 없습니다.",
            )

        feedback = await ChatFeedback.create(
            session_id=session_id,
            assistant_message_id=assistant_message_id,
            user_id=int(requester.id),
            helpful=helpful,
            feedback_type=str(feedback_type or "").strip()[:50] or None,
            comment=str(comment or "").strip()[:1000] or None,
        )

        return ChatFeedbackCreateResponse(
            success=True,
            data=ChatFeedbackCreateData(
                feedback_id=int(feedback.id),
                session_id=session_id,
                assistant_message_id=assistant_message_id,
                helpful=feedback.helpful,
                feedback_type=feedback.feedback_type,
                comment=feedback.comment,
                created_at=feedback.created_at,
            ),
        )

    @staticmethod
    async def list_messages(*, session_id: int) -> ChatMessageListResponse:
        session = await ChatSession.get_or_none(id=session_id)
        if not session:
            raise ChatServiceError(
                status_code=404,
                code="CHAT_SESSION_NOT_FOUND",
                message="채팅 세션을 찾을 수 없습니다.",
            )

        rows = await ChatMessage.filter(session_id=session_id).order_by("created_at", "id").all()

        items: list[ChatMessageItem] = []
        for idx, row in enumerate(rows):
            prev_row = rows[idx - 1] if idx > 0 else None
            items.append(ChatService._to_chat_message_item(row=row, previous=prev_row))

        return ChatMessageListResponse(
            success=True,
            data=ChatMessageListData(
                session_id=int(session.id),
                items=items,
                total=len(items),
            ),
        )

    @staticmethod
    async def create_message(
        *,
        requester: User,
        session_id: int,
        content: str,
    ) -> ChatMessageCreateResponse:
        stripped = _normalize_user_message(content)
        if not stripped:
            raise ChatServiceError(
                status_code=422,
                code="MESSAGE_EMPTY",
                message="메시지를 입력해 주세요.",
            )
        if len(stripped) > CHAT_MAX_MESSAGE_CHARS:
            raise ChatServiceError(
                status_code=422,
                code="MESSAGE_TOO_LONG",
                message=f"메시지는 {CHAT_MAX_MESSAGE_CHARS}자 이하로 입력해 주세요.",
            )

        session = await ChatSession.get_or_none(id=session_id)
        if not session:
            raise ChatServiceError(
                status_code=404,
                code="CHAT_SESSION_NOT_FOUND",
                message="채팅 세션을 찾을 수 없습니다.",
            )

        patient_id = getattr(session, "patient_id", None)
        if patient_id is None:
            raise ChatServiceError(
                status_code=500,
                code="CHAT_SESSION_PATIENT_MISSING",
                message="세션에 연결된 환자 정보가 없습니다.",
            )

        user_msg = await ChatMessage.create(
            session_id=session_id,
            role="user",
            content=stripped,
            status="completed",
            completed_at=datetime.now(),
        )

        fast_result = await ChatService._generate_fast_assistant_content(
            session_id=int(session.id),
            patient_id=int(patient_id),
            requester=requester,
            stripped=stripped,
        )
        if fast_result:
            assistant_content, analysis, context = fast_result
            assistant_msg = await ChatMessage.create(
                session_id=session_id,
                role="assistant",
                content=assistant_content,
                status="completed",
                completed_at=datetime.now(),
            )
            await _update_session_memory(
                session_id=int(session.id),
                analysis=analysis,
                plan=None,
                assistant_content=assistant_content,
                context=context,
            )
            return ChatMessageCreateResponse(
                success=True,
                data=ChatMessageCreateData(
                    session_id=int(session.id),
                    user_message=ChatService._to_chat_message_item(row=user_msg),
                    assistant_message=ChatService._to_chat_message_item(row=assistant_msg, previous=user_msg),
                ),
            )

        assistant_msg = await ChatMessage.create(
            session_id=session_id,
            role="assistant",
            content="응답을 준비하고 있습니다.",
            status="queued",
        )

        await ChatService._enqueue_chat_reply_task(
            session_id=int(session.id),
            user_message_id=int(user_msg.id),
            assistant_message_id=int(assistant_msg.id),
        )

        return ChatMessageCreateResponse(
            success=True,
            data=ChatMessageCreateData(
                session_id=int(session.id),
                user_message=ChatService._to_chat_message_item(row=user_msg),
                assistant_message=ChatService._to_chat_message_item(row=assistant_msg, previous=user_msg),
            ),
        )

    @staticmethod
    async def generate_assistant_reply(
        *,
        session_id: int,
        user_message_id: int,
        assistant_message_id: int,
    ) -> None:
        started_monotonic = datetime.now()
        session = await ChatSession.get_or_none(id=session_id)
        if not session:
            raise ChatServiceError(
                status_code=404,
                code="CHAT_SESSION_NOT_FOUND",
                message="채팅 세션을 찾을 수 없습니다.",
            )

        patient_id = getattr(session, "patient_id", None)
        if patient_id is None:
            raise ChatServiceError(
                status_code=500,
                code="CHAT_SESSION_PATIENT_MISSING",
                message="세션에 연결된 환자 정보가 없습니다.",
            )

        user_msg = await ChatMessage.get_or_none(
            id=user_message_id,
            session_id=session_id,
            role="user",
        )
        assistant_msg = await ChatMessage.get_or_none(
            id=assistant_message_id,
            session_id=session_id,
            role="assistant",
        )
        if not user_msg or not assistant_msg:
            raise ChatServiceError(
                status_code=404,
                code="CHAT_MESSAGE_NOT_FOUND",
                message="채팅 메시지를 찾을 수 없습니다.",
            )

        assistant_status = str(getattr(assistant_msg, "status", "") or "")
        if (
            assistant_status == "completed"
            and assistant_msg.content
            and assistant_msg.content != "응답을 준비하고 있습니다."
        ):
            return

        assistant_msg.status = "processing"
        assistant_msg.error_message = None
        assistant_msg.started_at = datetime.now()
        await assistant_msg.save(update_fields=["status", "error_message", "started_at"])

        try:
            requester = await User.get(id=int(session.user_id))
            assistant_content, analysis, chat_plan, context = await ChatService._generate_assistant_content(
                session_id=session_id,
                patient_id=int(patient_id),
                requester=requester,
                stripped=_normalize_user_message(user_msg.content),
            )

            assistant_msg.content = assistant_content
            assistant_msg.status = "completed"
            assistant_msg.error_message = None
            assistant_msg.completed_at = datetime.now()
            await assistant_msg.save(update_fields=["content", "status", "error_message", "completed_at"])

            await _update_session_memory(
                session_id=session_id,
                analysis=analysis,
                plan=chat_plan,
                assistant_content=assistant_content,
                context=context,
            )
            elapsed = (datetime.now() - started_monotonic).total_seconds()
            if elapsed >= CHAT_SLOW_REPLY_SECONDS:
                logger.warning(
                    "chat slow reply session_id=%s assistant_message_id=%s intent=%s elapsed=%.2fs",
                    session_id,
                    assistant_message_id,
                    analysis.primary_intent,
                    elapsed,
                )
            else:
                logger.info(
                    "chat reply completed session_id=%s assistant_message_id=%s intent=%s elapsed=%.2fs",
                    session_id,
                    assistant_message_id,
                    analysis.primary_intent,
                    elapsed,
                )
        except Exception as exc:
            logger.exception(
                "chat async reply failed session_id=%s assistant_message_id=%s", session_id, assistant_message_id
            )
            assistant_msg.content = "일시적인 오류로 답변을 준비하지 못했습니다. 잠시 후 다시 시도해 주세요."
            assistant_msg.status = "failed"
            assistant_msg.error_message = str(exc)[:1000]
            assistant_msg.completed_at = datetime.now()
            await assistant_msg.save(update_fields=["content", "status", "error_message", "completed_at"])
