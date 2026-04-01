from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import httpx

EVAL_PRESETS: dict[str, list[str]] = {
    # Cheapest loop for day-to-day regression checks.
    "focused_patient_rich": [
        "daily_001",
        "interaction_002",
        "interaction_004",
        "schedule_001",
        "schedule_002",
        "schedule_003",
    ],
    "focused_caregiver_rich": [
        "daily_001",
        "caregiver_002",
        "caregiver_003",
        "caregiver_004",
    ],
    "focused_empty_patient": [
        "daily_001",
        "empty_001",
        "empty_002",
    ],
    "focused_smoke": [
        "daily_001",
        "hospital_001",
        "profile_001",
        "med_current_001",
        "interaction_001",
        "external_drug_001",
    ],
}


def _env_list(name: str) -> list[str]:
    raw = str(os.getenv(name) or "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _load_cases() -> list[dict[str, object]]:
    cases_path = Path(__file__).with_name("chat_eval_cases.json")
    return json.loads(cases_path.read_text(encoding="utf-8"))


def _resolve_ids_from_preset() -> set[str]:
    preset = str(os.getenv("CHAT_EVAL_PRESET") or "").strip().lower()
    if not preset:
        return set()
    return set(EVAL_PRESETS.get(preset, []))


def _filter_cases(cases: list[dict[str, object]]) -> list[dict[str, object]]:
    stage = str(os.getenv("CHAT_EVAL_STAGE") or "core").strip().lower()
    allowed_stages = {
        "smoke": {"smoke"},
        "core": {"smoke", "core"},
        "full": {"smoke", "core", "full"},
    }.get(stage, {"smoke", "core"})

    categories = set(_env_list("CHAT_EVAL_CATEGORIES"))
    ids = _resolve_ids_from_preset() | set(_env_list("CHAT_EVAL_IDS"))
    data_state = str(os.getenv("CHAT_EVAL_DATA_STATE") or "").strip().lower()
    persona = str(os.getenv("CHAT_EVAL_PERSONA") or "").strip().lower()
    limit = int(os.getenv("CHAT_EVAL_LIMIT") or "0")

    filtered: list[dict[str, object]] = []
    for case in cases:
        if str(case.get("stage") or "").lower() not in allowed_stages:
            continue
        if categories and str(case.get("category")) not in categories:
            continue
        if ids and str(case.get("id")) not in ids:
            continue
        if data_state and str(case.get("data_state") or "any").lower() not in {data_state, "any"}:
            continue
        if persona and str(case.get("persona") or "any").lower() not in {persona, "any"}:
            continue
        filtered.append(case)

    if limit > 0:
        filtered = filtered[:limit]
    return filtered


def _extract_answer(body: dict[str, object]) -> str:
    if not isinstance(body, dict):
        return ""
    data = body.get("data") or {}
    if not isinstance(data, dict):
        return ""
    assistant = data.get("assistant_message") or {}
    if not isinstance(assistant, dict):
        return ""
    return str(assistant.get("content") or "")


def _score_case(case: dict[str, object], answer: str, status_code: int) -> dict[str, object]:
    expect_any = [str(item) for item in (case.get("expect_any") or [])]
    expect_all = [str(item) for item in (case.get("expect_all") or [])]
    reject_any = [str(item) for item in (case.get("reject_any") or [])]

    matched_any = [keyword for keyword in expect_any if keyword in answer]
    matched_all = [keyword for keyword in expect_all if keyword in answer]
    rejected = [keyword for keyword in reject_any if keyword in answer]

    passed_any = True if not expect_any else bool(matched_any)
    passed_all = True if not expect_all else len(matched_all) == len(expect_all)
    passed_reject = not rejected
    passed = status_code < 400 and passed_any and passed_all and passed_reject

    return {
        "id": case["id"],
        "stage": case.get("stage"),
        "priority": case.get("priority"),
        "category": case["category"],
        "data_state": case.get("data_state"),
        "persona": case.get("persona"),
        "message": case["message"],
        "status_code": status_code,
        "matched_any": matched_any,
        "matched_all": matched_all,
        "rejected_hits": rejected,
        "passed": passed,
        "answer_preview": answer[:280],
    }


def _summarize_by(results: list[dict[str, object]], field: str) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for result in results:
        grouped[str(result.get(field) or "unknown")].append(result)

    summary: list[dict[str, object]] = []
    for key, items in sorted(grouped.items()):
        total = len(items)
        passed = sum(1 for item in items if item["passed"])
        summary.append(
            {
                field: key,
                "passed": passed,
                "total": total,
                "pass_rate": round((passed / total) * 100, 1) if total else 0.0,
            }
        )
    return summary


def _run_consistency_check(
    *,
    client: httpx.Client,
    api_base: str,
    session_id: str,
    cases: list[dict[str, object]],
    repeat_count: int,
) -> list[dict[str, object]]:
    if repeat_count <= 1:
        return []

    sample_cases = [case for case in cases if str(case.get("priority")) in {"core", "high"}][:5]
    results: list[dict[str, object]] = []

    for case in sample_cases:
        answers: list[str] = []
        status_codes: list[int] = []
        for _ in range(repeat_count):
            response = client.post(
                f"{api_base}/chat/sessions/{session_id}/messages",
                json={"content": case["message"]},
            )
            status_codes.append(response.status_code)
            body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            answers.append(_extract_answer(body)[:240])

        normalized = [item.strip() for item in answers if item.strip()]
        unique_answer_count = len(set(normalized))
        results.append(
            {
                "id": case["id"],
                "message": case["message"],
                "status_codes": status_codes,
                "unique_answer_count": unique_answer_count,
                "is_consistent": unique_answer_count <= 1 and all(code < 400 for code in status_codes),
                "answer_previews": answers,
            }
        )
    return results


def main() -> int:
    api_base = (os.getenv("CHAT_EVAL_API_BASE") or "http://localhost:8000/api/v1").rstrip("/")
    session_id = os.getenv("CHAT_EVAL_SESSION_ID")
    access_token = os.getenv("CHAT_EVAL_ACCESS_TOKEN")
    repeat_count = int(os.getenv("CHAT_EVAL_REPEAT_COUNT") or "1")
    stop_on_fail = str(os.getenv("CHAT_EVAL_STOP_ON_FAIL") or "").strip().lower() in {"1", "true", "yes"}

    if not session_id or not access_token:
        print("CHAT_EVAL_SESSION_ID and CHAT_EVAL_ACCESS_TOKEN are required")
        return 1

    cases = _filter_cases(_load_cases())
    if not cases:
        print("No evaluation cases selected")
        return 1

    print(
        f"[eval] start total_cases={len(cases)} stage={os.getenv('CHAT_EVAL_STAGE') or 'core'} "
        f"persona={os.getenv('CHAT_EVAL_PERSONA') or 'any'} data_state={os.getenv('CHAT_EVAL_DATA_STATE') or 'any'} "
        f"preset={os.getenv('CHAT_EVAL_PRESET') or '-'} repeat_count={repeat_count}",
        file=sys.stderr,
        flush=True,
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    results: list[dict[str, object]] = []
    with httpx.Client(timeout=30.0, headers=headers) as client:
        for index, case in enumerate(cases, start=1):
            print(
                f"[eval] case {index}/{len(cases)} id={case['id']} category={case['category']}",
                file=sys.stderr,
                flush=True,
            )
            response = client.post(
                f"{api_base}/chat/sessions/{session_id}/messages",
                json={"content": case["message"]},
            )
            body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            answer = _extract_answer(body)
            scored = _score_case(case, answer, response.status_code)
            results.append(scored)
            print(
                f"[eval] case_done id={case['id']} status={response.status_code} passed={scored['passed']}",
                file=sys.stderr,
                flush=True,
            )
            if stop_on_fail and not scored["passed"]:
                break

        consistency_results = _run_consistency_check(
            client=client,
            api_base=api_base,
            session_id=session_id,
            cases=cases,
            repeat_count=repeat_count,
        )

    passed_count = sum(1 for item in results if item["passed"])
    total_count = len(results)
    failures = [item for item in results if not item["passed"]]

    output = {
        "selected_case_count": total_count,
        "passed": passed_count,
        "total": total_count,
        "pass_rate": round((passed_count / total_count) * 100, 1) if total_count else 0.0,
        "category_summary": _summarize_by(results, "category"),
        "stage_summary": _summarize_by(results, "stage"),
        "data_state_summary": _summarize_by(results, "data_state"),
        "persona_summary": _summarize_by(results, "persona"),
        "consistency_summary": {
            "repeat_count": repeat_count,
            "checked_cases": len(consistency_results),
            "consistent_cases": sum(1 for item in consistency_results if item["is_consistent"]),
            "results": consistency_results,
        },
        "failures": failures,
        "results": results,
    }
    print(
        f"[eval] done passed={passed_count}/{total_count} pass_rate="
        f"{round((passed_count / total_count) * 100, 1) if total_count else 0.0}",
        file=sys.stderr,
        flush=True,
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if passed_count == total_count else 2


if __name__ == "__main__":
    sys.exit(main())
