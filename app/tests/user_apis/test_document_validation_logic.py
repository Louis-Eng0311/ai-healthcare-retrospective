from types import SimpleNamespace

from app.services.documents import DocumentService, DrugCacheResolution


def test_validation_marks_candidate_match_for_review():
    service = DocumentService()
    med = SimpleNamespace(dosage_text="5mg")
    cache = SimpleNamespace(dosage_info="1회 1정", mfds_item_seq="202106092")
    resolution = DrugCacheResolution(cache=cache, name_match_status="candidate")

    result = service._build_validation_status(med=med, cache_resolution=resolution)

    assert result.needs_review is True
    assert result.reason == "표준코드 확정이 필요한 후보 매칭"


def test_validation_marks_missing_standard_code_for_review():
    service = DocumentService()
    med = SimpleNamespace(dosage_text="1정")
    cache = SimpleNamespace(dosage_info=None, mfds_item_seq=None)
    resolution = DrugCacheResolution(cache=cache, name_match_status="exact")

    result = service._build_validation_status(med=med, cache_resolution=resolution)

    assert result.needs_review is True
    assert result.reason == "표준코드 누락"


def test_validation_passes_with_exact_match_and_standard_code():
    service = DocumentService()
    med = SimpleNamespace(dosage_text="5mg")
    cache = SimpleNamespace(dosage_info="5mg을 복용하세요", mfds_item_seq="202106092")
    resolution = DrugCacheResolution(cache=cache, name_match_status="exact")

    result = service._build_validation_status(med=med, cache_resolution=resolution)

    assert result.needs_review is False
    assert result.reason is None
