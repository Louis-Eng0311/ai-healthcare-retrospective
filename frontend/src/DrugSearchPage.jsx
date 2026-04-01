import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AppLayout from "./components/AppLayout.jsx";

const API_PREFIX = "/api/v1";
const BARCODE_FORMATS = [
  "qr_code",
  "code_128",
  "code_39",
  "ean_13",
  "ean_8",
  "upc_a",
  "upc_e",
];

const authFetch = async (url, options = {}) => {
  const token = localStorage.getItem("access_token");
  const headers = { ...options.headers };
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(url, { ...options, headers, credentials: "include" });
};

function ScrollableText({ value }) {
  const normalized = String(value || "").trim();
  if (!normalized) return <div className="drug-search-scroll-text">정보 없음</div>;
  return <div className="drug-search-scroll-text">{normalized}</div>;
}

const buildBarcodeDetector = () => {
  if (typeof window === "undefined" || !("BarcodeDetector" in window)) return null;
  try {
    return new window.BarcodeDetector({ formats: BARCODE_FORMATS });
  } catch {
    try {
      return new window.BarcodeDetector();
    } catch {
      return null;
    }
  }
};

function DrugSearchPage({ modeOptions = [], currentMode = "PATIENT", onModeChange, userName = "사용자" }) {
  const [query, setQuery] = useState("");
  const [searchedQuery, setSearchedQuery] = useState("");
  const [results, setResults] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const detectorRef = useRef(null);
  const rafRef = useRef(null);

  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraLoading, setCameraLoading] = useState(false);
  const [cameraError, setCameraError] = useState(null);
  const [scanStatus, setScanStatus] = useState("카메라를 열면 바코드 또는 QR 코드를 읽을 수 있습니다.");
  const [lastScannedValue, setLastScannedValue] = useState("");

  const nativeDetectorAvailable = useMemo(() => {
    if (typeof window === "undefined") return false;
    return "BarcodeDetector" in window;
  }, []);

  const stopCamera = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    detectorRef.current = null;
    setCameraOpen(false);
  }, []);

  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, [stopCamera]);

  const searchDrugs = useCallback(async (rawKeyword) => {
    const keyword = String(rawKeyword || "").trim();
    if (!keyword) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        drug_name: keyword,
        num_of_rows: "10",
      });
      const response = await authFetch(`${API_PREFIX}/documents/mfds/search?${params.toString()}`);
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `status ${response.status}`);
      }
      const body = await response.json();
      setResults(body.items || []);
      setTotal(body.total || 0);
      setSearchedQuery(body.query || keyword);
    } catch (err) {
      setError(err.message || "검색 중 오류가 발생했습니다.");
      setResults([]);
      setTotal(0);
      setSearchedQuery(keyword);
    } finally {
      setLoading(false);
    }
  }, []);

  const applyDetectedValue = useCallback(async (value) => {
    const normalized = String(value || "").trim();
    if (!normalized) return;
    setLastScannedValue(normalized);
    setQuery(normalized);
    setScanStatus(`인식됨: ${normalized}`);
    await searchDrugs(normalized);
  }, [searchDrugs]);

  const startCamera = useCallback(async () => {
    setCameraLoading(true);
    setCameraError(null);
    setScanStatus("카메라를 시작하는 중입니다...");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }

      detectorRef.current = buildBarcodeDetector();
      if (detectorRef.current) {
        setScanStatus("코드를 프레임 안에 맞춰주세요. 자동으로 인식합니다.");
      } else {
        setScanStatus("자동 인식 미지원 브라우저입니다. 아래 '현재 화면 인식' 버튼을 눌러주세요.");
      }
      setCameraOpen(true);
    } catch (err) {
      setCameraError(err.message || "카메라를 열 수 없습니다.");
      stopCamera();
      setScanStatus("카메라를 열지 못했습니다.");
    } finally {
      setCameraLoading(false);
    }
  }, [stopCamera]);

  useEffect(() => {
    if (!cameraOpen || !detectorRef.current) return undefined;

    let active = true;
    const detectLoop = async () => {
      if (!active || !videoRef.current || !detectorRef.current) return;

      if (videoRef.current.readyState >= 2) {
        try {
          const detections = await detectorRef.current.detect(videoRef.current);
          const rawValue = detections?.[0]?.rawValue;
          const normalized = typeof rawValue === "string" ? rawValue.trim() : "";
          if (normalized) {
            await applyDetectedValue(normalized);
            stopCamera();
            return;
          }
        } catch {
          // no-op: camera stream keeps running
        }
      }

      if (active) {
        rafRef.current = requestAnimationFrame(detectLoop);
      }
    };

    rafRef.current = requestAnimationFrame(detectLoop);
    return () => {
      active = false;
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [applyDetectedValue, cameraOpen, stopCamera]);

  const handleDecodeCurrentFrame = async () => {
    if (!cameraOpen || !videoRef.current || !canvasRef.current) return;
    setCameraError(null);
    setScanStatus("현재 화면에서 코드를 분석 중입니다...");
    try {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      canvas.width = video.videoWidth || 1280;
      canvas.height = video.videoHeight || 720;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("CANVAS_CONTEXT_UNAVAILABLE");
      context.drawImage(video, 0, 0, canvas.width, canvas.height);

      const blob = await new Promise((resolve) => {
        canvas.toBlob((value) => resolve(value), "image/png", 0.95);
      });
      if (!blob) throw new Error("CAPTURE_FAILED");

      const formData = new FormData();
      formData.append("file", blob, "camera-capture.png");
      const response = await authFetch(`${API_PREFIX}/documents/barcodes/decode`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `status ${response.status}`);
      }

      const body = await response.json();
      const detectedValue = body.items?.[0]?.barcode_value;
      if (!detectedValue) {
        setScanStatus("코드를 찾지 못했습니다. 거리/초점을 조정해 다시 시도해주세요.");
        return;
      }

      await applyDetectedValue(detectedValue);
      stopCamera();
    } catch (err) {
      setCameraError(err.message || "코드 인식에 실패했습니다.");
      setScanStatus("인식 실패. 카메라 각도와 밝기를 확인해주세요.");
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    await searchDrugs(query);
  };

  return (
    <AppLayout
      activeKey="drug-search"
      title="약 검색"
      description="약 이름·코드·카메라 스캔으로 약 정보를 조회합니다."
      userName={userName}
      modeOptions={modeOptions}
      currentMode={currentMode}
      onModeChange={onModeChange}
    >
        <div className="card border-0 shadow-sm mb-4">
          <div className="card-body">
            <h6 className="fw-bold mb-3">MFDS 약 정보 검색</h6>
            <form className="row g-2" onSubmit={handleSubmit}>
              <div className="col-md-9">
                <input
                  type="text"
                  className="form-control"
                  placeholder="약 이름, 품목기준코드, 표준코드 입력"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </div>
              <div className="col-md-3">
                <button type="submit" className="btn btn-primary w-100" disabled={loading || !query.trim()}>
                  {loading ? "검색 중..." : "검색"}
                </button>
              </div>
            </form>
            {searchedQuery && (
              <div className="small text-muted mt-3">
                검색어: <strong>{searchedQuery}</strong> · 결과 {total}건
              </div>
            )}
          </div>
        </div>

        <div className="card border-0 shadow-sm mb-4">
          <div className="card-body">
            <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
              <h6 className="fw-bold mb-0">카메라 코드 스캔</h6>
              <button
                className={`btn btn-sm ${cameraOpen ? "btn-outline-danger" : "btn-outline-primary"}`}
                onClick={cameraOpen ? stopCamera : startCamera}
                disabled={cameraLoading}
              >
                {cameraLoading ? "준비 중..." : cameraOpen ? "카메라 닫기" : "카메라 열기"}
              </button>
            </div>
            <div className="drug-scan-video-wrap mb-2">
              <video ref={videoRef} className="drug-scan-video" playsInline muted />
            </div>
            <canvas ref={canvasRef} className="d-none" />
            <div className="d-flex flex-wrap gap-2 mb-2">
              <button
                className="btn btn-outline-secondary btn-sm"
                onClick={handleDecodeCurrentFrame}
                disabled={!cameraOpen}
              >
                현재 화면 인식
              </button>
              {!nativeDetectorAvailable && (
                <span className="small text-muted align-self-center">
                  자동 인식 미지원 브라우저입니다. 현재 화면 인식 버튼을 사용하세요.
                </span>
              )}
            </div>
            <div className="small text-muted">{scanStatus}</div>
            {lastScannedValue && (
              <div className="small mt-1">
                마지막 인식값: <strong>{lastScannedValue}</strong>
              </div>
            )}
            {cameraError && <div className="alert alert-danger mt-3 mb-0">{cameraError}</div>}
          </div>
        </div>

        {error && <div className="alert alert-danger">{error}</div>}

        <div className="card border-0 shadow-sm">
          <div className="card-body">
            <h6 className="fw-bold mb-3">검색 결과</h6>
            {!loading && results.length === 0 && (
              <div className="text-muted py-4 text-center">검색 결과가 없습니다.</div>
            )}
            <div className="row g-3">
              {results.map((item) => (
                <div className="col-12" key={`${item.item_seq}-${item.item_name}`}>
                  <div className="drug-search-result-card">
                    <div className="d-flex flex-wrap justify-content-between gap-2 mb-2">
                      <div className="fw-semibold">{item.item_name || "이름 없음"}</div>
                      <span className="badge text-bg-light">품목코드 {item.item_seq || "N/A"}</span>
                    </div>
                    {item.item_image && (
                      <div className="mb-2">
                        <img
                          src={item.item_image}
                          alt={`${item.item_name || "약"} 이미지`}
                          className="drug-search-item-image"
                        />
                      </div>
                    )}
                    <div className="small text-muted mb-2">제조사: {item.entp_name || "정보 없음"}</div>
                    <div className="small mb-2"><strong>효능</strong>: <ScrollableText value={item.efficacy} /></div>
                    <div className="small mb-2"><strong>복용 방법</strong>: <ScrollableText value={item.dosage_info} /></div>
                    <div className="small"><strong>주의사항</strong>: <ScrollableText value={item.precautions} /></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
    </AppLayout>
  );
}

export default DrugSearchPage;
