from app.services.chat import CHAT_DISCLAIMER, QuestionAnalysis, _apply_response_contract


def _analysis(*, is_emergency: bool, emergency_message: str | None = None) -> QuestionAnalysis:
    return QuestionAnalysis(
        raw_message="테스트",
        intents=["general"],
        primary_intent="general",
        target_med=None,
        external_drug_name=None,
        target_condition=None,
        time_period=None,
        is_emergency=is_emergency,
        emergency_message=emergency_message,
        answer_mode="deterministic",
    )


def test_response_contract_appends_disclaimer():
    result = _apply_response_contract(content="현재 복약 기록을 확인해볼게요.", analysis=_analysis(is_emergency=False))
    assert CHAT_DISCLAIMER in result


def test_response_contract_keeps_existing_disclaimer_single():
    base = f"답변입니다.\n\n{CHAT_DISCLAIMER}"
    result = _apply_response_contract(content=base, analysis=_analysis(is_emergency=False))
    assert result.count(CHAT_DISCLAIMER) == 1


def test_response_contract_adds_emergency_guidance():
    result = _apply_response_contract(
        content="지금은 바로 상태 확인이 필요해요.",
        analysis=_analysis(
            is_emergency=True,
            emergency_message="응급 상황이 의심됩니다. 즉시 119 또는 가까운 응급실에 연락해 주세요.",
        ),
    )
    assert "119" in result
    assert "응급실" in result
