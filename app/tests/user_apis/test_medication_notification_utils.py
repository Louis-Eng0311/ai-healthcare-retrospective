from types import SimpleNamespace

from app.services.medication_notifications import _extract_reminder_key, _is_enabled_from_map


def test_extract_reminder_key_from_valid_payload():
    payload = '{"reminder_key":"med:1:2026-04-02:아침:intake","patient_id":1}'
    assert _extract_reminder_key(payload) == "med:1:2026-04-02:아침:intake"


def test_extract_reminder_key_returns_none_on_invalid_payload():
    assert _extract_reminder_key("not-json") is None
    assert _extract_reminder_key('{"patient_id":1}') is None
    assert _extract_reminder_key("") is None


def test_is_enabled_from_map_defaults_true_when_missing():
    assert _is_enabled_from_map(settings_map={}, user_id=7, field_name="intake_reminder") is True


def test_is_enabled_from_map_reads_boolean_field():
    settings_map = {3: SimpleNamespace(intake_reminder=False, missed_alert=True)}
    assert _is_enabled_from_map(settings_map=settings_map, user_id=3, field_name="intake_reminder") is False
    assert _is_enabled_from_map(settings_map=settings_map, user_id=3, field_name="missed_alert") is True
