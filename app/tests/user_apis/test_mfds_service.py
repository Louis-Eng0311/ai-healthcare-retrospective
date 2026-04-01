import pytest

from app.core import config
from app.services.mfds import MfdsService


def test_build_easy_drug_search_candidates_with_standard_code():
    candidates = MfdsService._build_easy_drug_search_candidates("8806449128112")
    assert candidates == [("itemName", "8806449128112")]


def test_build_easy_drug_search_candidates_with_item_seq():
    candidates = MfdsService._build_easy_drug_search_candidates("200904881")
    assert candidates == [("itemSeq", "200904881"), ("itemName", "200904881")]


def test_extract_item_seq_candidates_from_nedrug_html():
    sample_html = """
    <a href="/pbp/CCBBB01/getItemDetail?itemSeq=200904881" target="_blank">페인엔젤</a>
    <a href="/pbp/CCBBB01/getItemDetail?itemSeq=200904881" target="_blank">페인엔젤 중복</a>
    <a href="/pbp/CCBBB01/getItemDetail?itemSeq=202106092" target="_blank">타이레놀</a>
    """
    item_seqs = MfdsService._extract_item_seq_candidates_from_nedrug_html(sample_html)
    assert item_seqs == ["200904881", "202106092"]


@pytest.mark.asyncio
async def test_search_easy_drug_info_prefers_item_seq(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "MFDS_SERVICE_KEY", "dummy-key")
    service = MfdsService()
    calls: list[tuple[str, str]] = []

    async def fake_resolve_item_seq(self, standard_code: str):  # noqa: ARG001
        return ["200904881"]

    async def fake_request(self, query: str, num_of_rows: int, query_field: str = "itemName"):  # noqa: ARG001
        calls.append((query_field, query))
        return [
            {
                "ITEM_SEQ": "200904881",
                "ITEM_NAME": "페인엔젤-프로연질캡슐(덱시부프로펜)",
                "ENTP_NAME": "제이더블유중외제약(주)",
                "itemImage": "https://example.com/item.png",
            }
        ]

    async def fake_sync(self, items: list[dict]):  # noqa: ARG001
        return None

    monkeypatch.setattr(MfdsService, "_resolve_item_seq_candidates_by_standard_code", fake_resolve_item_seq)
    monkeypatch.setattr(MfdsService, "_request_easy_drug_info", fake_request)
    monkeypatch.setattr(MfdsService, "_sync_drug_info_cache", fake_sync)

    response = await service.search_easy_drug_info("8806449128112", num_of_rows=10)

    assert calls == [("itemSeq", "200904881")]
    assert response.total == 1
    assert response.items[0].item_seq == "200904881"
    assert response.items[0].item_name == "페인엔젤-프로연질캡슐(덱시부프로펜)"
    assert response.items[0].item_image == "https://example.com/item.png"


@pytest.mark.asyncio
async def test_search_easy_drug_info_falls_back_to_item_name(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "MFDS_SERVICE_KEY", "dummy-key")
    service = MfdsService()
    calls: list[tuple[str, str]] = []

    async def fake_resolve_item_seq(self, standard_code: str):  # noqa: ARG001
        return []

    async def fake_request(self, query: str, num_of_rows: int, query_field: str = "itemName"):  # noqa: ARG001
        calls.append((query_field, query))
        return [{"itemSeq": "201900002", "itemName": "폴백약"}]

    async def fake_sync(self, items: list[dict]):  # noqa: ARG001
        return None

    monkeypatch.setattr(MfdsService, "_resolve_item_seq_candidates_by_standard_code", fake_resolve_item_seq)
    monkeypatch.setattr(MfdsService, "_request_easy_drug_info", fake_request)
    monkeypatch.setattr(MfdsService, "_sync_drug_info_cache", fake_sync)

    response = await service.search_easy_drug_info("8806449128112", num_of_rows=5)

    assert calls == [("itemName", "8806449128112")]
    assert response.total == 1
    assert response.items[0].item_seq == "201900002"
    assert response.items[0].item_name == "폴백약"


@pytest.mark.asyncio
async def test_search_easy_drug_info_falls_back_to_dur_item_info(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "MFDS_SERVICE_KEY", "dummy-key")
    service = MfdsService()
    calls: list[tuple[str, str, str]] = []

    async def fake_request_easy(self, query: str, num_of_rows: int, query_field: str = "itemName"):  # noqa: ARG001
        calls.append(("easy", query_field, query))
        return []

    async def fake_request_dur(self, query: str, num_of_rows: int, query_field: str = "itemName"):  # noqa: ARG001
        calls.append(("dur", query_field, query))
        return [{"ITEM_SEQ": "202106092", "ITEM_NAME": "타이레놀"}]

    async def fake_sync(self, items: list[dict]):  # noqa: ARG001
        return None

    monkeypatch.setattr(MfdsService, "_request_easy_drug_info", fake_request_easy)
    monkeypatch.setattr(MfdsService, "_request_dur_item_info", fake_request_dur)
    monkeypatch.setattr(MfdsService, "_sync_drug_info_cache", fake_sync)

    response = await service.search_easy_drug_info("타이레놀", num_of_rows=5)

    assert calls == [("easy", "itemName", "타이레놀"), ("dur", "itemName", "타이레놀")]
    assert response.total == 1
    assert response.items[0].item_seq == "202106092"
    assert response.items[0].item_name == "타이레놀"
