from __future__ import annotations

import json
import re
from typing import Any


async def call_chat_model(*, system_prompt: str, user_prompt: str, ops: dict[str, Any]) -> dict[str, Any]:
    api_key = (ops["getenv"]("OPENAI_API_KEY", "") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY missing")
    model = (ops["getenv"]("OPENAI_MODEL", "gpt-4o-mini") or "").strip()
    started = ops["perf_counter"]()
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    async with ops["httpx_client"](timeout=40) as client:
        response = await client.post(url, headers=headers, json=payload)
        elapsed_ms = int((ops["perf_counter"]() - started) * 1000)
        ops["log_metric"]("llm_call", model=model, status=response.status_code, elapsed_ms=elapsed_ms)
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
    return {"content": content, "is_emergency": False, "emergency_message": None, "disclaimer": ops["chat_disclaimer"]}


async def plan_chat_question(
    *,
    message: str,
    context: Any,
    requester_role: Any,
    audience: str,
    target_label: str,
    plan_factory: Any,
    ops: dict[str, Any],
) -> Any | None:
    if not ops["has_openai_api_key"]():
        return None
    try:
        system_prompt = ops["read_prompt_template"]("chat_planner_system_prompt.txt").format(
            requester_role=requester_role.value,
            target_label=target_label,
            audience_label=ops["audience_label"](audience),
        )
        user_prompt = ops["read_prompt_template"]("chat_planner_user_prompt.txt").format(
            user_message=message,
            meds_text=ops["build_meds_text"](context.meds),
            schedule_text=ops["build_schedule_text"](context.schedules, context.meds),
            hospital_schedule_text=ops["build_hospital_schedule_brief"](context.hospital_schedules),
            profile_text=ops["build_profile_text"](context.profile),
            history_text=ops["build_recent_history_for_planner"](context.recent_messages),
            session_memory_text=ops["build_session_memory_text"](context.session_memory),
        )
    except RuntimeError:
        ops["logger"].warning("chat planner prompts missing; planner disabled")
        return None
    try:
        result = await ops["call_chat_model"](system_prompt=system_prompt, user_prompt=user_prompt)
    except Exception:
        ops["logger"].exception("chat planner failed")
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
    return plan_factory(
        topic=topic,
        requested_fields=[str(item).strip() for item in requested_fields if str(item).strip()],
        referenced_drug_name=referenced_drug_name,
        needs_clarification=bool(result.get("needs_clarification", False)),
        clarification_question=clarification_question,
        use_record_data=[str(item).strip() for item in use_record_data if str(item).strip()],
        answer_style=str(result.get("answer_style") or "direct").strip() or "direct",
    )


def fallback_reply(
    *,
    intent: str,
    latest_guide: Any | None,
    meds: list[dict[str, Any]],
    profile: Any | None,
    schedule_text: str,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str:
    data_readiness = "rich" if (meds or schedule_text != "등록된 복약 일정 없음" or latest_guide or profile) else "empty"
    short_profile: list[str] = []
    allergies = ops["split_text_items"](getattr(profile, "allergies", None) if profile else None)
    conditions = ops["split_text_items"](getattr(profile, "conditions", None) if profile else None)
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
        base = "질환에 대한 일반적인 치료 방향은 설명할 수 있지만, 특정 약 추천은 현재 진단과 복용약을 함께 봐야 합니다." + tail
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
    return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base
