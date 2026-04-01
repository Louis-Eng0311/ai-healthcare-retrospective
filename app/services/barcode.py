from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BarcodeDetection:
    barcode_type: str
    barcode_value: str


class BarcodeService:
    # REQ-DOC-009 - 바코드 인식
    def extract_from_file(self, file_path: Path) -> list[BarcodeDetection]:
        suffix = file_path.suffix.lower()
        detections: list[BarcodeDetection] = []

        if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
            detections.extend(self._decode_image_with_zxing(file_path=file_path))
            detections.extend(self._decode_image_with_pyzbar(file_path=file_path))
            detections.extend(self._decode_image_with_qr_detector(file_path=file_path))
            return self._deduplicate(detections)

        if suffix == ".pdf":
            detections.extend(self._decode_pdf_with_zxing(file_path=file_path))
            detections.extend(self._decode_pdf_with_pyzbar(file_path=file_path))
            return self._deduplicate(detections)

        return []

    # REQ-DOC-009 - 이미지 바코드 디코딩(zxing-cpp)
    @staticmethod
    def _decode_image_with_zxing(file_path: Path) -> list[BarcodeDetection]:
        try:
            import zxingcpp
            from PIL import Image
        except ImportError:
            return []

        try:
            with Image.open(file_path) as image:
                variants = BarcodeService._build_zxing_image_variants(image=image)
        except Exception:  # noqa: BLE001
            return []

        detections: list[BarcodeDetection] = []
        for variant in variants:
            try:
                results = zxingcpp.read_barcodes(variant)
            except Exception:  # noqa: BLE001
                continue
            for result in results:
                raw_value = str(getattr(result, "text", "")).strip()
                if not raw_value:
                    continue
                barcode_type = str(getattr(result, "format", "UNKNOWN")).replace("BarcodeFormat.", "").upper()
                detections.append(
                    BarcodeDetection(
                        barcode_type=barcode_type,
                        barcode_value=raw_value,
                    )
                )
        return detections

    # REQ-DOC-009 - zxing 인식률 향상을 위한 이미지 변형 생성
    @staticmethod
    def _build_zxing_image_variants(image):
        from PIL import Image

        rgb_image = image.convert("RGB")
        width, height = rgb_image.size
        top_right_crop = rgb_image.crop((max(width // 2, 0), 0, width, max(height // 2, 1)))
        upscaled = rgb_image.resize((max(width * 2, 1), max(height * 2, 1)), Image.Resampling.LANCZOS)
        upscaled_top_right_crop = top_right_crop.resize(
            (max(top_right_crop.size[0] * 2, 1), max(top_right_crop.size[1] * 2, 1)), Image.Resampling.LANCZOS
        )

        return [rgb_image, top_right_crop, upscaled, upscaled_top_right_crop]

    # REQ-DOC-009 - 이미지 바코드 디코딩(pyzbar)
    @staticmethod
    def _decode_image_with_pyzbar(file_path: Path) -> list[BarcodeDetection]:
        try:
            from PIL import Image
            from pyzbar.pyzbar import decode as zbar_decode
        except ImportError:
            return []

        try:
            with Image.open(file_path) as image:
                decoded_objects = zbar_decode(image)
        except Exception:  # noqa: BLE001
            return []

        detections: list[BarcodeDetection] = []
        for obj in decoded_objects:
            raw_value = obj.data.decode("utf-8", errors="ignore").strip()
            if not raw_value:
                continue
            detections.append(
                BarcodeDetection(
                    barcode_type=str(obj.type).upper(),
                    barcode_value=raw_value,
                )
            )
        return detections

    # REQ-DOC-009 - 이미지 바코드 디코딩(OpenCV QR fallback)
    @staticmethod
    def _decode_image_with_qr_detector(file_path: Path) -> list[BarcodeDetection]:
        try:
            import cv2
        except ImportError:
            return []

        image = cv2.imread(str(file_path))
        if image is None:
            return []

        detections: list[BarcodeDetection] = []
        detector = cv2.QRCodeDetector()

        frames_to_check = BarcodeService._build_qr_detection_frames(image=image)
        for frame in frames_to_check:
            try:
                has_multi, decoded_values, _, _ = detector.detectAndDecodeMulti(frame)
            except Exception:  # noqa: BLE001
                has_multi, decoded_values = False, []

            if has_multi and decoded_values:
                for value in decoded_values:
                    normalized_value = str(value).strip()
                    if normalized_value:
                        detections.append(BarcodeDetection(barcode_type="QRCODE", barcode_value=normalized_value))

            try:
                single_value, _, _ = detector.detectAndDecode(frame)
            except Exception:  # noqa: BLE001
                single_value = ""
            normalized_single_value = str(single_value).strip()
            if normalized_single_value:
                detections.append(BarcodeDetection(barcode_type="QRCODE", barcode_value=normalized_single_value))

        return BarcodeService._deduplicate(detections)

    # REQ-DOC-009 - QR 인식률 향상을 위한 이미지 변형 프레임 생성
    @staticmethod
    def _build_qr_detection_frames(image):
        import cv2

        height, width = image.shape[:2]
        top_right_crop = image[0 : max(height // 2, 1), max(width // 2, 0) : width]

        grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(grayscale, (3, 3), 0)
        upscaled = cv2.resize(image, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        upscaled_gray = cv2.resize(grayscale, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

        frames = [image, top_right_crop, grayscale, blurred, upscaled, upscaled_gray]
        return [frame for frame in frames if frame is not None and frame.size > 0]

    # REQ-DOC-009 - PDF 바코드 디코딩(zxing-cpp)
    @staticmethod
    def _decode_pdf_with_zxing(file_path: Path) -> list[BarcodeDetection]:
        try:
            import zxingcpp
            from pdf2image import convert_from_path
        except ImportError:
            return []

        try:
            pages = convert_from_path(str(file_path), dpi=220, first_page=1, last_page=2)
        except Exception:  # noqa: BLE001
            return []

        detections: list[BarcodeDetection] = []
        for page in pages:
            try:
                results = zxingcpp.read_barcodes(page)
            except Exception:  # noqa: BLE001
                continue
            for result in results:
                raw_value = str(getattr(result, "text", "")).strip()
                if not raw_value:
                    continue
                barcode_type = str(getattr(result, "format", "UNKNOWN")).replace("BarcodeFormat.", "").upper()
                detections.append(
                    BarcodeDetection(
                        barcode_type=barcode_type,
                        barcode_value=raw_value,
                    )
                )
        return detections

    # REQ-DOC-009 - PDF 바코드 디코딩(선택)
    @staticmethod
    def _decode_pdf_with_pyzbar(file_path: Path) -> list[BarcodeDetection]:
        try:
            from pdf2image import convert_from_path
            from pyzbar.pyzbar import decode as zbar_decode
        except ImportError:
            return []

        try:
            pages = convert_from_path(str(file_path), dpi=220, first_page=1, last_page=2)
        except Exception:  # noqa: BLE001
            return []

        detections: list[BarcodeDetection] = []
        for page in pages:
            try:
                decoded_objects = zbar_decode(page)
            except Exception:  # noqa: BLE001
                continue
            for obj in decoded_objects:
                raw_value = obj.data.decode("utf-8", errors="ignore").strip()
                if not raw_value:
                    continue
                detections.append(
                    BarcodeDetection(
                        barcode_type=str(obj.type).upper(),
                        barcode_value=raw_value,
                    )
                )
        return detections

    @staticmethod
    def _deduplicate(detections: list[BarcodeDetection]) -> list[BarcodeDetection]:
        deduplicated: list[BarcodeDetection] = []
        seen: set[tuple[str, str]] = set()
        for detection in detections:
            key = (detection.barcode_type, detection.barcode_value)
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(detection)
        return deduplicated
