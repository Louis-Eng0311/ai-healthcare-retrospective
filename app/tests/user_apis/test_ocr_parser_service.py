from datetime import date
from pathlib import Path

from app.services.documents import DocumentService
from app.services.ocr import OcrService


def test_parse_extracted_meds_filters_receipt_noise():
    ocr_service = OcrService()
    raw_text = """
조제약사
백수정
약제비총액
약품사진
약품명
복약안내
뮤코스텐캡슐
백색 분말이 든 상단 암녹색 하단 담녹색 경질캡슐
완화시켜주는 약입니다.
코대원정
약품명
투약량
횟수
일수
총투
뮤코스텐캡슐
1
3
5
15
슈다페드정
1
3
5
15
코대원정
1
3
5
15
"""

    parsed_meds = ocr_service._parse_extracted_meds(raw_text=raw_text)
    parsed_names = [item["name"] for item in parsed_meds]

    assert "뮤코스텐캡슐" in parsed_names
    assert "슈다페드정" in parsed_names
    assert "코대원정" in parsed_names

    assert "백수정" not in parsed_names
    assert "약제비총액" not in parsed_names
    assert "경질캡슐" not in parsed_names
    assert "완화시켜주" not in parsed_names


def test_extract_barcode_values_from_raw_text():
    raw_text = """
[BARCODE_DETECTIONS]
type=QRCODE, value=https://example.com/qr/abc
type=CODE128, value=8801234567890
"""
    barcode_values = DocumentService._extract_barcode_values(raw_text=raw_text)
    assert barcode_values == ["https://example.com/qr/abc", "8801234567890"]


def test_normalize_frequency_text_for_storage_orders_time_slots():
    assert DocumentService._normalize_frequency_text_for_storage("3회 취침/점심") == "3회 점심/취침"
    assert DocumentService._normalize_frequency_text_for_storage("취침 전/아침") == "아침/취침"
    assert DocumentService._normalize_frequency_text_for_storage("하루 2회 저녁,아침") == "하루 2회 아침/저녁"


def test_normalize_frequency_text_for_storage_keeps_non_slot_text():
    assert DocumentService._normalize_frequency_text_for_storage("필요 시") == "필요 시"


def test_normalize_duration_text_for_guide_appends_day_for_numeric_only():
    assert DocumentService._normalize_duration_text_for_guide("3") == "3일"
    assert DocumentService._normalize_duration_text_for_guide("14") == "14일"
    assert DocumentService._normalize_duration_text_for_guide("7일분") == "7일분"
    assert DocumentService._normalize_duration_text_for_guide("5일") == "5일"
    assert DocumentService._normalize_duration_text_for_guide(None) is None


def test_resolve_media_type_falls_back_to_extension_when_guess_type_missing(monkeypatch):
    monkeypatch.setattr("app.services.documents.mimetypes.guess_type", lambda _filename: (None, None))
    assert DocumentService._resolve_media_type(Path("camera.jpg")) == "image/jpeg"
    assert DocumentService._resolve_media_type(Path("camera.png")) == "image/png"
    assert DocumentService._resolve_media_type(Path("camera.pdf")) == "application/pdf"


def test_parse_extracted_meds_uses_summary_schedule_map():
    ocr_service = OcrService()
    raw_text = """
복약안내
약품명
투약량
횟수
일수
총투
텔미누보정40/5m
1
1
60
60
코푸시럽
1
3
5
15
"""

    parsed_meds = ocr_service._parse_extracted_meds(raw_text=raw_text)
    parsed_map = {item["name"]: item for item in parsed_meds}

    assert "텔미누보정" in parsed_map
    assert parsed_map["텔미누보정"]["dosage_text"] == "1정씩"
    assert parsed_map["텔미누보정"]["frequency_text"] == "1회"
    assert parsed_map["텔미누보정"]["duration_text"] == "60일분"

    assert "코푸시럽" in parsed_map
    assert parsed_map["코푸시럽"]["dosage_text"] == "1포씩"
    assert parsed_map["코푸시럽"]["frequency_text"] == "3회"
    assert parsed_map["코푸시럽"]["duration_text"] == "5일분"


def test_parse_extracted_meds_excludes_receipt_rows_with_numeric_pattern():
    ocr_service = OcrService()
    raw_text = """
약품명
투약량
횟수
일수
총투
약제비총액
73980
뮤코스텐캡슐
1
3
5
15
"""

    parsed_meds = ocr_service._parse_extracted_meds(raw_text=raw_text)
    parsed_names = [item["name"] for item in parsed_meds]
    assert "뮤코스텐캡슐" in parsed_names
    assert "약제비총액" not in parsed_names


def test_parse_extracted_meds_parses_inline_summary_rows_with_codes():
    ocr_service = OcrService()
    raw_text = """
약품명 투여량 1회 1일투여횟수 총투약일수 용법
6489000030 노바스크정5mg/[내복]/1정 1 1 30
653501410 트라젠타듀오정2.5/12.5/[내복]/1정 1 1 30
664900660 피오글리/메트포르민정/1정 1 1 30
667700860 아토렌정10mg/1정 1 1 30
"""

    parsed_meds = ocr_service._parse_extracted_meds(raw_text=raw_text)
    parsed_map = {item["name"]: item for item in parsed_meds}

    assert "노바스크정" in parsed_map
    assert parsed_map["노바스크정"]["dosage_text"] == "1정씩"
    assert parsed_map["노바스크정"]["frequency_text"] == "1회"
    assert parsed_map["노바스크정"]["duration_text"] == "30일분"

    assert "트라젠타듀오정" in parsed_map
    assert parsed_map["트라젠타듀오정"]["frequency_text"] == "1회"
    assert parsed_map["트라젠타듀오정"]["duration_text"] == "30일분"

    assert "피오글리/메트포르민정" in parsed_map
    assert parsed_map["피오글리/메트포르민정"]["frequency_text"] == "1회"
    assert parsed_map["피오글리/메트포르민정"]["duration_text"] == "30일분"

    assert "아토렌정" in parsed_map
    assert parsed_map["아토렌정"]["frequency_text"] == "1회"
    assert parsed_map["아토렌정"]["duration_text"] == "30일분"

    assert "5/1정" not in parsed_map
    assert "10mg/1정" not in parsed_map


def test_parse_extracted_meds_maps_packed_schedule_lines_for_med_bag_format():
    ocr_service = OcrService()
    raw_text = """
약품사진
약품명
복약안내(투약량 / 횟수 / 일수)
인데놀정40mg
비시드에프정
모프롤정
동광알마게이트정
0.5정씩3회7일분
1정씩3회7일분
1정씩3회7일분
2정씩3회7일분
"""

    parsed_meds = ocr_service._parse_extracted_meds(raw_text=raw_text)
    parsed_map = {item["name"]: item for item in parsed_meds}

    assert "인데놀정" in parsed_map
    assert parsed_map["인데놀정"]["dosage_text"] == "0.5정씩"
    assert parsed_map["인데놀정"]["frequency_text"] == "3회"
    assert parsed_map["인데놀정"]["duration_text"] == "7일분"

    assert "비시드에프정" in parsed_map
    assert parsed_map["비시드에프정"]["dosage_text"] == "1정씩"
    assert parsed_map["비시드에프정"]["frequency_text"] == "3회"
    assert parsed_map["비시드에프정"]["duration_text"] == "7일분"

    assert "모프롤정" in parsed_map
    assert parsed_map["모프롤정"]["dosage_text"] == "1정씩"
    assert parsed_map["모프롤정"]["frequency_text"] == "3회"
    assert parsed_map["모프롤정"]["duration_text"] == "7일분"


def test_parse_extracted_meds_parses_numeric_summary_values_with_units():
    ocr_service = OcrService()
    raw_text = """
약품명
투약량
횟수
일수
총투
티지페논정
1정
1회
14일
14
"""

    parsed_meds = ocr_service._parse_extracted_meds(raw_text=raw_text)
    parsed_map = {item["name"]: item for item in parsed_meds}

    assert "티지페논정" in parsed_map
    assert parsed_map["티지페논정"]["dosage_text"] == "1정씩"
    assert parsed_map["티지페논정"]["frequency_text"] == "1회"
    assert parsed_map["티지페논정"]["duration_text"] == "14일분"


def test_parse_extracted_meds_keeps_non_summary_meds_when_summary_is_partial():
    ocr_service = OcrService()
    raw_text = """
약품사진
약품명
복약안내
티지페논정
1정씩1회30일분
노바스크정5mg
1정씩1회30일분
약품명
투약량
횟수
일수
총투
노바스크정5mg
1
1
30
30
"""

    parsed_meds = ocr_service._parse_extracted_meds(raw_text=raw_text)
    parsed_names = {item["name"] for item in parsed_meds}

    assert "노바스크정" in parsed_names
    assert "티지페논정" in parsed_names


def test_parse_extracted_meds_maps_numeric_packed_schedule_rows():
    ocr_service = OcrService()
    raw_text = """
약품사진
약품명
복약안내
티지페논정
노바스크정5mg
1정 2회 7일
0.5정 1회 14일
"""

    parsed_meds = ocr_service._parse_extracted_meds(raw_text=raw_text)
    parsed_map = {item["name"]: item for item in parsed_meds}

    assert parsed_map["티지페논정"]["dosage_text"] == "1정씩"
    assert parsed_map["티지페논정"]["frequency_text"] == "2회"
    assert parsed_map["티지페논정"]["duration_text"] == "7일분"

    assert parsed_map["노바스크정"]["dosage_text"] == "0.5정씩"
    assert parsed_map["노바스크정"]["frequency_text"] == "1회"
    assert parsed_map["노바스크정"]["duration_text"] == "14일분"


def test_extract_ocr_fields_includes_bbox_metrics():
    data = {
        "images": [
            {
                "fields": [
                    {
                        "inferText": "인데놀정40mg",
                        "boundingPoly": {
                            "vertices": [
                                {"x": 10, "y": 20},
                                {"x": 110, "y": 20},
                                {"x": 110, "y": 40},
                                {"x": 10, "y": 40},
                            ]
                        },
                    }
                ]
            }
        ]
    }
    fields = OcrService._extract_ocr_fields(data=data)
    assert len(fields) == 1
    assert fields[0]["text"] == "인데놀정40mg"
    assert fields[0]["x_min"] == 10.0
    assert fields[0]["x_max"] == 110.0
    assert fields[0]["y_min"] == 20.0
    assert fields[0]["y_max"] == 40.0
    assert fields[0]["cx"] == 60.0
    assert fields[0]["cy"] == 30.0


def test_group_fields_into_rows_groups_by_y_and_sorts_x():
    ocr_service = OcrService()
    fields = [
        {"text": "B", "x_min": 200.0, "x_max": 260.0, "y_min": 100.0, "y_max": 120.0, "cx": 230.0, "cy": 110.0},
        {"text": "A", "x_min": 40.0, "x_max": 90.0, "y_min": 101.0, "y_max": 121.0, "cx": 65.0, "cy": 111.0},
        {"text": "C", "x_min": 45.0, "x_max": 95.0, "y_min": 150.0, "y_max": 170.0, "cx": 70.0, "cy": 160.0},
    ]

    rows = ocr_service._group_fields_into_rows(fields=fields, y_threshold=6.0)
    assert len(rows) == 2
    assert [item["text"] for item in rows[0]] == ["A", "B"]
    assert [item["text"] for item in rows[1]] == ["C"]


def test_split_med_name_and_strength_supports_suffix_patterns():
    ocr_service = OcrService()
    assert ocr_service._split_med_name_and_strength(text="인데놀정40mg") == ("인데놀정", "40mg")
    assert ocr_service._split_med_name_and_strength(text="튜란트과립200mg") == ("튜란트과립", "200mg")
    assert ocr_service._split_med_name_and_strength(text="큐로스트세립4mg") == ("큐로스트세립", "4mg")
    assert ocr_service._split_med_name_and_strength(text="텔미누보정40/5mg") == ("텔미누보정", "40/5mg")


def test_parse_extracted_meds_uses_med_guide_table_parser_with_ocr_fields():
    ocr_service = OcrService()
    ocr_fields = [
        {"text": "약품명", "x_min": 40.0, "x_max": 120.0, "y_min": 90.0, "y_max": 110.0, "cx": 80.0, "cy": 100.0},
        {"text": "복약안내", "x_min": 280.0, "x_max": 360.0, "y_min": 90.0, "y_max": 110.0, "cx": 320.0, "cy": 100.0},
        {
            "text": "인데놀정40mg",
            "x_min": 40.0,
            "x_max": 190.0,
            "y_min": 120.0,
            "y_max": 140.0,
            "cx": 115.0,
            "cy": 130.0,
        },
        {
            "text": "0.5정씩 3회 7일분",
            "x_min": 280.0,
            "x_max": 430.0,
            "y_min": 120.0,
            "y_max": 140.0,
            "cx": 355.0,
            "cy": 130.0,
        },
        {
            "text": "튜란트과립200mg",
            "x_min": 40.0,
            "x_max": 200.0,
            "y_min": 150.0,
            "y_max": 170.0,
            "cx": 120.0,
            "cy": 160.0,
        },
        {
            "text": "1포씩 3회 5일분",
            "x_min": 280.0,
            "x_max": 410.0,
            "y_min": 150.0,
            "y_max": 170.0,
            "cx": 345.0,
            "cy": 160.0,
        },
    ]

    parsed_meds = ocr_service._parse_extracted_meds(raw_text="", ocr_fields=ocr_fields)
    parsed_map = {item["name"]: item for item in parsed_meds}

    assert "인데놀정" in parsed_map
    assert parsed_map["인데놀정"]["dosage_text"] == "0.5정씩"
    assert parsed_map["인데놀정"]["frequency_text"] == "3회"
    assert parsed_map["인데놀정"]["duration_text"] == "7일분"

    assert "튜란트과립" in parsed_map
    assert parsed_map["튜란트과립"]["dosage_text"] == "1포씩"
    assert parsed_map["튜란트과립"]["frequency_text"] == "3회"
    assert parsed_map["튜란트과립"]["duration_text"] == "5일분"


def test_extract_med_name_candidate_from_text_ignores_trailing_noise():
    ocr_service = OcrService()
    assert ocr_service._extract_med_name_candidate_from_text("인데놀정40mg B") == ("인데놀정", "40mg")
    assert ocr_service._extract_med_name_candidate_from_text("에나론정10mg 삼환계") == ("에나론정", "10mg")
    assert ocr_service._extract_med_name_candidate_from_text("진양에페리손정에페") == ("진양에페리손정", None)
    assert ocr_service._extract_med_name_candidate_from_text("슈다페드정슈도에페") == ("슈다페드정", None)
    assert ocr_service._extract_med_name_candidate_from_text("푸마티펜정케토티펜") == ("푸마티펜정", None)
    assert ocr_service._extract_med_name_candidate_from_text("엘스테인캡슐에르도") == ("엘스테인캡슐", None)
    assert ocr_service._extract_med_name_candidate_from_text("오나렌정애엽95에") == ("오나렌정", None)
    assert ocr_service._extract_med_name_candidate_from_text("분할선을 가진 흰색의 소화관") is None
    assert ocr_service._extract_med_name_candidate_from_text("미황색의 장용성과립이 충전된 상부 적갈색 위식도") is None
    assert ocr_service._extract_med_name_candidate_from_text("백색의 장방형 정제 진양에페리손정") is None


def test_generic_descriptor_only_name_is_rejected():
    ocr_service = OcrService()
    assert ocr_service._is_suspicious_generic_med_name("장용성과립") is True
    assert ocr_service._is_suspicious_generic_med_name("서방성정") is True
    assert ocr_service._is_suspicious_generic_med_name("연질캡슐") is True
    assert ocr_service._is_valid_med_name("장용성과립") is False
    assert ocr_service._is_valid_med_name("서방성정") is False
    assert ocr_service._is_valid_med_name("연질캡슐") is False
    assert ocr_service._is_valid_med_name("인데놀정") is True


def test_looks_like_med_name_row_is_strict_for_descriptor_row():
    ocr_service = OcrService()
    assert ocr_service._looks_like_med_name_row("백색의 장방형 정제 제산제") is False
    assert ocr_service._looks_like_med_name_row("미황색의 장용성과립이 충전된 상부 적갈색 위식도") is False
    assert ocr_service._looks_like_med_name_row("인데놀정40mg B") is True


def test_parse_med_guide_table_skips_descriptor_rows_and_attaches_schedule_to_pending():
    ocr_service = OcrService()
    ocr_fields = [
        {"text": "약품명", "x_min": 40.0, "x_max": 120.0, "y_min": 90.0, "y_max": 110.0, "cx": 80.0, "cy": 100.0},
        {"text": "복약안내", "x_min": 280.0, "x_max": 360.0, "y_min": 90.0, "y_max": 110.0, "cx": 320.0, "cy": 100.0},
        {
            "text": "인데놀정40mg B",
            "x_min": 40.0,
            "x_max": 200.0,
            "y_min": 120.0,
            "y_max": 140.0,
            "cx": 120.0,
            "cy": 130.0,
        },
        {
            "text": "분할선을 가진 흰색의 소화관",
            "x_min": 40.0,
            "x_max": 240.0,
            "y_min": 145.0,
            "y_max": 165.0,
            "cx": 140.0,
            "cy": 155.0,
        },
        {
            "text": "0.5정씩 3회 7일분",
            "x_min": 280.0,
            "x_max": 430.0,
            "y_min": 170.0,
            "y_max": 190.0,
            "cx": 355.0,
            "cy": 180.0,
        },
        {
            "text": "에나론정10mg 삼환계",
            "x_min": 40.0,
            "x_max": 220.0,
            "y_min": 200.0,
            "y_max": 220.0,
            "cx": 130.0,
            "cy": 210.0,
        },
        {"text": "불면증", "x_min": 40.0, "x_max": 100.0, "y_min": 225.0, "y_max": 245.0, "cx": 70.0, "cy": 235.0},
        {
            "text": "1정씩 1회 14일분",
            "x_min": 280.0,
            "x_max": 420.0,
            "y_min": 250.0,
            "y_max": 270.0,
            "cx": 350.0,
            "cy": 260.0,
        },
    ]

    parsed_meds = ocr_service._parse_extracted_meds(raw_text="", ocr_fields=ocr_fields)
    parsed_names = {item["name"] for item in parsed_meds}
    parsed_map = {item["name"]: item for item in parsed_meds}

    assert "인데놀정" in parsed_names
    assert "에나론정" in parsed_names
    assert "분할선을 가진 흰색의 소화관" not in parsed_names
    assert "불면증" not in parsed_names

    assert parsed_map["인데놀정"]["frequency_text"] == "3회"
    assert parsed_map["인데놀정"]["duration_text"] == "7일분"
    assert parsed_map["에나론정"]["frequency_text"] == "1회"
    assert parsed_map["에나론정"]["duration_text"] == "14일분"


def test_med_guide_parser_stops_before_summary_table_rows():
    ocr_service = OcrService()
    ocr_fields = [
        {"text": "약품명", "x_min": 40.0, "x_max": 120.0, "y_min": 90.0, "y_max": 110.0, "cx": 80.0, "cy": 100.0},
        {"text": "복약안내", "x_min": 280.0, "x_max": 360.0, "y_min": 90.0, "y_max": 110.0, "cx": 320.0, "cy": 100.0},
        {
            "text": "진양에페리손정에페",
            "x_min": 40.0,
            "x_max": 220.0,
            "y_min": 120.0,
            "y_max": 140.0,
            "cx": 130.0,
            "cy": 130.0,
        },
        {
            "text": "1정씩 3회 5일분",
            "x_min": 280.0,
            "x_max": 410.0,
            "y_min": 120.0,
            "y_max": 140.0,
            "cx": 345.0,
            "cy": 130.0,
        },
        {"text": "약품명", "x_min": 40.0, "x_max": 100.0, "y_min": 200.0, "y_max": 220.0, "cx": 70.0, "cy": 210.0},
        {"text": "투약량", "x_min": 140.0, "x_max": 200.0, "y_min": 200.0, "y_max": 220.0, "cx": 170.0, "cy": 210.0},
        {"text": "횟수", "x_min": 230.0, "x_max": 270.0, "y_min": 200.0, "y_max": 220.0, "cx": 250.0, "cy": 210.0},
        {"text": "일수", "x_min": 300.0, "x_max": 340.0, "y_min": 200.0, "y_max": 220.0, "cx": 320.0, "cy": 210.0},
        {
            "text": "슈다페드정슈도에페",
            "x_min": 40.0,
            "x_max": 210.0,
            "y_min": 230.0,
            "y_max": 250.0,
            "cx": 125.0,
            "cy": 240.0,
        },
    ]

    parsed_meds = ocr_service._parse_extracted_meds(raw_text="", ocr_fields=ocr_fields)
    parsed_names = {item["name"] for item in parsed_meds}
    parsed_map = {item["name"]: item for item in parsed_meds}

    assert "진양에페리손정" in parsed_names
    assert parsed_map["진양에페리손정"]["frequency_text"] == "3회"
    assert "슈다페드정" not in parsed_names


def test_segment_layout_regions_separates_med_guide_and_summary():
    ocr_service = OcrService()
    ocr_fields = [
        {"text": "영수증", "x_min": 20.0, "x_max": 80.0, "y_min": 40.0, "y_max": 60.0, "cx": 50.0, "cy": 50.0},
        {"text": "약품명", "x_min": 40.0, "x_max": 120.0, "y_min": 90.0, "y_max": 110.0, "cx": 80.0, "cy": 100.0},
        {"text": "복약안내", "x_min": 280.0, "x_max": 360.0, "y_min": 90.0, "y_max": 110.0, "cx": 320.0, "cy": 100.0},
        {
            "text": "슈다페드정슈도에페",
            "x_min": 40.0,
            "x_max": 210.0,
            "y_min": 125.0,
            "y_max": 145.0,
            "cx": 125.0,
            "cy": 135.0,
        },
        {
            "text": "1정씩 2회 5일분",
            "x_min": 280.0,
            "x_max": 420.0,
            "y_min": 125.0,
            "y_max": 145.0,
            "cx": 350.0,
            "cy": 135.0,
        },
        {"text": "약품명", "x_min": 40.0, "x_max": 100.0, "y_min": 220.0, "y_max": 240.0, "cx": 70.0, "cy": 230.0},
        {"text": "투약량", "x_min": 140.0, "x_max": 200.0, "y_min": 220.0, "y_max": 240.0, "cx": 170.0, "cy": 230.0},
        {"text": "횟수", "x_min": 230.0, "x_max": 270.0, "y_min": 220.0, "y_max": 240.0, "cx": 250.0, "cy": 230.0},
        {"text": "일수", "x_min": 300.0, "x_max": 340.0, "y_min": 220.0, "y_max": 240.0, "cx": 320.0, "cy": 230.0},
    ]

    layout = ocr_service._segment_layout_regions(ocr_fields=ocr_fields)
    med_guide_texts = {field["text"] for field in layout["med_guide_fields"]}  # type: ignore[index]
    summary_texts = {field["text"] for field in layout["summary_fields"]}  # type: ignore[index]

    assert "복약안내" in med_guide_texts
    assert "슈다페드정슈도에페" in med_guide_texts
    assert "투약량" in summary_texts
    assert "횟수" in summary_texts


def test_pipeline_parses_med_blocks_and_normalizes_with_summary_dictionary():
    ocr_service = OcrService()
    ocr_fields = [
        {"text": "약품명", "x_min": 40.0, "x_max": 120.0, "y_min": 90.0, "y_max": 110.0, "cx": 80.0, "cy": 100.0},
        {"text": "복약안내", "x_min": 280.0, "x_max": 360.0, "y_min": 90.0, "y_max": 110.0, "cx": 320.0, "cy": 100.0},
        {
            "text": "슈다페드정슈도에페",
            "x_min": 40.0,
            "x_max": 210.0,
            "y_min": 130.0,
            "y_max": 150.0,
            "cx": 125.0,
            "cy": 140.0,
        },
        {
            "text": "백색의 장방형 정제",
            "x_min": 40.0,
            "x_max": 220.0,
            "y_min": 158.0,
            "y_max": 178.0,
            "cx": 130.0,
            "cy": 168.0,
        },
        {
            "text": "1정씩 2회 5일분",
            "x_min": 280.0,
            "x_max": 420.0,
            "y_min": 186.0,
            "y_max": 206.0,
            "cx": 350.0,
            "cy": 196.0,
        },
        {"text": "약품명", "x_min": 40.0, "x_max": 100.0, "y_min": 240.0, "y_max": 260.0, "cx": 70.0, "cy": 250.0},
        {"text": "투약량", "x_min": 140.0, "x_max": 200.0, "y_min": 240.0, "y_max": 260.0, "cx": 170.0, "cy": 250.0},
        {"text": "횟수", "x_min": 230.0, "x_max": 270.0, "y_min": 240.0, "y_max": 260.0, "cx": 250.0, "cy": 250.0},
        {"text": "일수", "x_min": 300.0, "x_max": 340.0, "y_min": 240.0, "y_max": 260.0, "cx": 320.0, "cy": 250.0},
        {"text": "슈다페드정", "x_min": 40.0, "x_max": 130.0, "y_min": 270.0, "y_max": 290.0, "cx": 85.0, "cy": 280.0},
        {"text": "1", "x_min": 150.0, "x_max": 160.0, "y_min": 270.0, "y_max": 290.0, "cx": 155.0, "cy": 280.0},
        {"text": "2", "x_min": 235.0, "x_max": 245.0, "y_min": 270.0, "y_max": 290.0, "cx": 240.0, "cy": 280.0},
        {"text": "5", "x_min": 305.0, "x_max": 315.0, "y_min": 270.0, "y_max": 290.0, "cx": 310.0, "cy": 280.0},
    ]

    parsed_meds = ocr_service._parse_extracted_meds(raw_text="", ocr_fields=ocr_fields)
    parsed_map = {item["name"]: item for item in parsed_meds}

    assert "슈다페드정" in parsed_map
    assert parsed_map["슈다페드정"]["dosage_text"] == "1정씩"
    assert parsed_map["슈다페드정"]["frequency_text"] == "2회"
    assert parsed_map["슈다페드정"]["duration_text"] == "5일분"


def test_parse_extracted_meds_with_ocr_fields_appends_missing_summary_meds():
    ocr_service = OcrService()
    ocr_fields = [
        {"text": "약품명", "x_min": 40.0, "x_max": 120.0, "y_min": 90.0, "y_max": 110.0, "cx": 80.0, "cy": 100.0},
        {"text": "복약안내", "x_min": 280.0, "x_max": 360.0, "y_min": 90.0, "y_max": 110.0, "cx": 320.0, "cy": 100.0},
        {
            "text": "인데놀정40mg",
            "x_min": 40.0,
            "x_max": 190.0,
            "y_min": 120.0,
            "y_max": 140.0,
            "cx": 115.0,
            "cy": 130.0,
        },
        {
            "text": "0.5정씩 3회 7일분",
            "x_min": 280.0,
            "x_max": 430.0,
            "y_min": 120.0,
            "y_max": 140.0,
            "cx": 355.0,
            "cy": 130.0,
        },
        {"text": "약품명", "x_min": 40.0, "x_max": 100.0, "y_min": 220.0, "y_max": 240.0, "cx": 70.0, "cy": 230.0},
        {"text": "투약량", "x_min": 140.0, "x_max": 200.0, "y_min": 220.0, "y_max": 240.0, "cx": 170.0, "cy": 230.0},
        {"text": "횟수", "x_min": 230.0, "x_max": 270.0, "y_min": 220.0, "y_max": 240.0, "cx": 250.0, "cy": 230.0},
        {"text": "일수", "x_min": 300.0, "x_max": 340.0, "y_min": 220.0, "y_max": 240.0, "cx": 320.0, "cy": 230.0},
        {
            "text": "인데놀정40mg",
            "x_min": 40.0,
            "x_max": 180.0,
            "y_min": 250.0,
            "y_max": 270.0,
            "cx": 110.0,
            "cy": 260.0,
        },
        {"text": "0.5", "x_min": 150.0, "x_max": 170.0, "y_min": 250.0, "y_max": 270.0, "cx": 160.0, "cy": 260.0},
        {"text": "3", "x_min": 235.0, "x_max": 245.0, "y_min": 250.0, "y_max": 270.0, "cx": 240.0, "cy": 260.0},
        {"text": "7", "x_min": 305.0, "x_max": 315.0, "y_min": 250.0, "y_max": 270.0, "cx": 310.0, "cy": 260.0},
        {"text": "슈다페드정", "x_min": 40.0, "x_max": 130.0, "y_min": 280.0, "y_max": 300.0, "cx": 85.0, "cy": 290.0},
        {"text": "1", "x_min": 150.0, "x_max": 160.0, "y_min": 280.0, "y_max": 300.0, "cx": 155.0, "cy": 290.0},
        {"text": "2", "x_min": 235.0, "x_max": 245.0, "y_min": 280.0, "y_max": 300.0, "cx": 240.0, "cy": 290.0},
        {"text": "5", "x_min": 305.0, "x_max": 315.0, "y_min": 280.0, "y_max": 300.0, "cx": 310.0, "cy": 290.0},
    ]

    parsed_meds = ocr_service._parse_extracted_meds(raw_text="", ocr_fields=ocr_fields)
    parsed_map = {item["name"]: item for item in parsed_meds}

    assert "인데놀정" in parsed_map
    assert parsed_map["인데놀정"]["frequency_text"] == "3회"
    assert parsed_map["인데놀정"]["duration_text"] == "7일분"

    assert "슈다페드정" in parsed_map
    assert parsed_map["슈다페드정"]["dosage_text"] == "1정씩"
    assert parsed_map["슈다페드정"]["frequency_text"] == "2회"
    assert parsed_map["슈다페드정"]["duration_text"] == "5일분"


def test_parse_extracted_meds_simple_parser_keeps_sparse_rows():
    ocr_service = OcrService()
    ocr_fields = [
        {"text": "약품명", "x_min": 40.0, "x_max": 120.0, "y_min": 80.0, "y_max": 100.0, "cx": 80.0, "cy": 90.0},
        {"text": "복약안내", "x_min": 280.0, "x_max": 360.0, "y_min": 80.0, "y_max": 100.0, "cx": 320.0, "cy": 90.0},
        {
            "text": "키목신캡슐500mg",
            "x_min": 40.0,
            "x_max": 210.0,
            "y_min": 115.0,
            "y_max": 135.0,
            "cx": 125.0,
            "cy": 125.0,
        },
        {
            "text": "1캡슐씩 3회 3일분",
            "x_min": 280.0,
            "x_max": 430.0,
            "y_min": 115.0,
            "y_max": 135.0,
            "cx": 355.0,
            "cy": 125.0,
        },
        {
            "text": "페나셋정",
            "x_min": 40.0,
            "x_max": 150.0,
            "y_min": 150.0,
            "y_max": 170.0,
            "cx": 95.0,
            "cy": 160.0,
        },
    ]

    parsed_meds = ocr_service._parse_extracted_meds(raw_text="", ocr_fields=ocr_fields)
    parsed_map = {item["name"]: item for item in parsed_meds}

    assert "키목신캡슐" in parsed_map
    assert parsed_map["키목신캡슐"]["dosage_text"] == "1캡슐씩"
    assert parsed_map["키목신캡슐"]["frequency_text"] == "3회"
    assert parsed_map["키목신캡슐"]["duration_text"] == "3일분"

    assert "페나셋정" in parsed_map
    assert parsed_map["페나셋정"]["dosage_text"] is None
    assert parsed_map["페나셋정"]["frequency_text"] is None
    assert parsed_map["페나셋정"]["duration_text"] is None


def test_parse_extracted_meds_simple_parser_prefers_guide_dosage_over_strength():
    ocr_service = OcrService()
    ocr_fields = [
        {"text": "약품명", "x_min": 40.0, "x_max": 120.0, "y_min": 90.0, "y_max": 110.0, "cx": 80.0, "cy": 100.0},
        {"text": "복약안내", "x_min": 280.0, "x_max": 360.0, "y_min": 90.0, "y_max": 110.0, "cx": 320.0, "cy": 100.0},
        {
            "text": "브로니제장용정150mg",
            "x_min": 40.0,
            "x_max": 220.0,
            "y_min": 125.0,
            "y_max": 145.0,
            "cx": 130.0,
            "cy": 135.0,
        },
        {
            "text": "1정씩 2회 3일분",
            "x_min": 280.0,
            "x_max": 420.0,
            "y_min": 125.0,
            "y_max": 145.0,
            "cx": 350.0,
            "cy": 135.0,
        },
    ]

    parsed_meds = ocr_service._parse_extracted_meds(raw_text="", ocr_fields=ocr_fields)
    parsed_map = {item["name"]: item for item in parsed_meds}

    assert "브로니제장용정" in parsed_map
    assert parsed_map["브로니제장용정"]["dosage_text"] == "1정씩"
    assert parsed_map["브로니제장용정"]["frequency_text"] == "2회"
    assert parsed_map["브로니제장용정"]["duration_text"] == "3일분"


def test_parse_extracted_meds_falls_back_when_simple_parser_has_no_med_guide():
    ocr_service = OcrService()
    ocr_fields = [
        {"text": "약품명", "x_min": 40.0, "x_max": 100.0, "y_min": 210.0, "y_max": 230.0, "cx": 70.0, "cy": 220.0},
        {"text": "투약량", "x_min": 140.0, "x_max": 200.0, "y_min": 210.0, "y_max": 230.0, "cx": 170.0, "cy": 220.0},
        {"text": "횟수", "x_min": 230.0, "x_max": 270.0, "y_min": 210.0, "y_max": 230.0, "cx": 250.0, "cy": 220.0},
        {"text": "일수", "x_min": 300.0, "x_max": 340.0, "y_min": 210.0, "y_max": 230.0, "cx": 320.0, "cy": 220.0},
        {
            "text": "코푸시럽",
            "x_min": 40.0,
            "x_max": 120.0,
            "y_min": 240.0,
            "y_max": 260.0,
            "cx": 80.0,
            "cy": 250.0,
        },
        {"text": "1", "x_min": 150.0, "x_max": 160.0, "y_min": 240.0, "y_max": 260.0, "cx": 155.0, "cy": 250.0},
        {"text": "3", "x_min": 235.0, "x_max": 245.0, "y_min": 240.0, "y_max": 260.0, "cx": 240.0, "cy": 250.0},
        {"text": "5", "x_min": 305.0, "x_max": 315.0, "y_min": 240.0, "y_max": 260.0, "cx": 310.0, "cy": 250.0},
    ]

    parsed_meds = ocr_service._parse_extracted_meds(raw_text="", ocr_fields=ocr_fields)
    parsed_map = {item["name"]: item for item in parsed_meds}

    assert "코푸시럽" in parsed_map
    assert parsed_map["코푸시럽"]["dosage_text"] == "1포씩"
    assert parsed_map["코푸시럽"]["frequency_text"] == "3회"
    assert parsed_map["코푸시럽"]["duration_text"] == "5일분"


def test_extract_simple_schedule_from_text_normalizes_day_format():
    ocr_service = OcrService()
    schedule = ocr_service._extract_simple_schedule_from_text("1정 2회 7일")

    assert schedule is not None
    assert schedule["dosage_text"] == "1정씩"
    assert schedule["frequency_text"] == "2회"
    assert schedule["duration_text"] == "7일분"


def test_is_retryable_naver_ocr_http_status():
    assert OcrService._is_retryable_naver_ocr_http_status(429) is True
    assert OcrService._is_retryable_naver_ocr_http_status(500) is True
    assert OcrService._is_retryable_naver_ocr_http_status(503) is True
    assert OcrService._is_retryable_naver_ocr_http_status(400) is False


def test_extract_schedule_end_date_defaults_to_start_date_when_duration_missing():
    start_date = date(2026, 3, 23)

    assert DocumentService._extract_schedule_end_date(start_date=start_date, duration_text=None) == start_date
    assert (
        DocumentService._extract_schedule_end_date(start_date=start_date, duration_text="복용기간 미상") == start_date
    )
    assert DocumentService._extract_schedule_end_date(start_date=start_date, duration_text="0일") == start_date


def test_extract_schedule_end_date_uses_duration_when_present():
    start_date = date(2026, 3, 23)

    assert DocumentService._extract_schedule_end_date(start_date=start_date, duration_text="3일분") == date(2026, 3, 25)
