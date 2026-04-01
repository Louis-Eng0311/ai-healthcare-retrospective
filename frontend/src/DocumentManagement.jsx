import React, { useEffect, useState, useCallback, useMemo, useRef } from "react";
import AppLayout from "./components/AppLayout.jsx";

const API_PREFIX = "/api/v1";
const MAX_UPLOAD_FILE_SIZE_BYTES = 10 * 1024 * 1024;
const TIME_SLOTS = ["아침", "점심", "저녁", "취침"];

const authFetch = async (url, options = {}) => {
  const token = localStorage.getItem("access_token");
  const headers = { ...options.headers };
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(url, { ...options, headers, credentials: "include" });
};

function StatCard({ label, value, unit, color }) {
  return (
    <div className="doc-stat-card">
      <div className="text-muted small mb-1">{label}</div>
      <div className="doc-stat-value" style={{ color: color || "#2563eb" }}>{value}</div>
      {unit && <div className="text-muted small">{unit}</div>}
    </div>
  );
}

const extractTimeSlots = (frequencyText = "") =>
  TIME_SLOTS.filter((slot) => String(frequencyText).includes(slot));

const updateFrequencyWithSlot = (frequencyText = "", slot, checked) => {
  const currentText = String(frequencyText || "").trim();
  const selectedSlots = extractTimeSlots(currentText);
  const nextSlots = checked
    ? Array.from(new Set([...selectedSlots, slot]))
    : selectedSlots.filter((item) => item !== slot);
  const orderedNextSlots = TIME_SLOTS.filter((timeSlot) => nextSlots.includes(timeSlot));

  const baseText = TIME_SLOTS.reduce((text, timeSlot) => text.replaceAll(timeSlot, " "), currentText)
    .replaceAll("/", " ")
    .replaceAll(",", " ")
    .replace(/\s+/g, " ")
    .trim();

  if (!baseText) {
    return orderedNextSlots.join("/");
  }

  if (orderedNextSlots.length === 0) {
    return baseText;
  }

  return `${baseText} ${orderedNextSlots.join("/")}`.trim();
};

function DrugRow({ drug, index, onChange, onDelete, isDurationMissing = false }) {
  const freq = drug.frequency_text || "";

  return (
    <tr>
      <td>
        <input
          className={`form-control form-control-sm ${!drug.name ? "is-invalid" : ""}`}
          value={drug.name}
          onChange={(e) => onChange(index, "name", e.target.value)}
          placeholder="약명 입력"
        />
      </td>
      <td>
        <input
          className="form-control form-control-sm"
          value={drug.dosage_text || ""}
          onChange={(e) => onChange(index, "dosage_text", e.target.value)}
          placeholder=""
        />
      </td>
      <td>
        <input
          className="form-control form-control-sm"
          value={drug.frequency_text || ""}
          onChange={(e) => onChange(index, "frequency_text", e.target.value)}
          placeholder="예: 2회"
        />
      </td>
      <td>
        <div className="d-flex gap-1 align-items-center">
          {TIME_SLOTS.map((slot) => {
            const checked = freq.includes(slot);
            return (
              <div key={slot} className="text-center" style={{ minWidth: 28 }}>
                <div className="small text-muted" style={{ fontSize: "0.65rem", lineHeight: 1 }}>{slot}</div>
                <input
                  type="checkbox"
                  className="form-check-input"
                  checked={checked}
                  onChange={(e) => onChange(index, "frequency_text", updateFrequencyWithSlot(freq, slot, e.target.checked))}
                  style={{ marginTop: 2 }}
                />
              </div>
            );
          })}
        </div>
      </td>
      <td>
        <input
          className={`form-control form-control-sm ${isDurationMissing ? "is-invalid" : ""}`}
          value={drug.duration_text || ""}
          onChange={(e) => onChange(index, "duration_text", e.target.value)}
          placeholder=""
        />
      </td>
      <td>
        <input
          className="form-control form-control-sm"
          value={drug.notes || ""}
          onChange={(e) => onChange(index, "notes", e.target.value)}
          placeholder="비고"
        />
      </td>
      <td>
        <button className="btn btn-outline-danger btn-sm" onClick={() => onDelete(index)}>🗑</button>
      </td>
    </tr>
  );
}

// 메인 뷰: 목록 or OCR 결과
function DocumentManagement({
  linkedPatients = [],
  myPatient = null,
  selfPatient = null,
  loginRole = "PATIENT",
  userName = "사용자",
  modeOptions = [],
  currentMode = "PATIENT",
  onModeChange,
}) {
  const effectiveMode = currentMode || loginRole;
  const isCaregiver = effectiveMode === "CAREGIVER" || effectiveMode === "GUARDIAN";
  const [view, setView] = useState("list"); // "list" | "ocr"
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [documentTitle, setDocumentTitle] = useState("");
  const [patientId, setPatientId] = useState("");
  const [listPatientFilter, setListPatientFilter] = useState("all");
  const [uploadNotice, setUploadNotice] = useState(null);

  // OCR 결과 뷰 상태
  const [currentDoc, setCurrentDoc] = useState(null);
  const [ocrStatus, setOcrStatus] = useState(null);
  const [drugs, setDrugs] = useState([]);
  const [drugsLoading, setDrugsLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deletingDocument, setDeletingDocument] = useState(false);
  const [bulkDeletingDocuments, setBulkDeletingDocuments] = useState(false);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState([]);
  const [saveMsg, setSaveMsg] = useState(null);
  const [durationValidationIndices, setDurationValidationIndices] = useState([]);
  const [pollingId, setPollingId] = useState(null);
  const [showReviewOnly, setShowReviewOnly] = useState(false);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [previewMimeType, setPreviewMimeType] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState(null);
  const uploadVideoRef = useRef(null);
  const uploadCanvasRef = useRef(null);
  const uploadStreamRef = useRef(null);
  const [uploadCameraOpen, setUploadCameraOpen] = useState(false);
  const [uploadCameraLoading, setUploadCameraLoading] = useState(false);
  const [uploadCameraError, setUploadCameraError] = useState(null);
  const [uploadCameraStatus, setUploadCameraStatus] = useState("카메라를 열어 처방전을 바로 촬영할 수 있습니다.");

  const loadDocuments = useCallback(async () => {
    if (!isCaregiver && !myPatient?.id) {
      setDocuments([]);
      setError(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (!isCaregiver && myPatient?.id) {
        params.set("patient_id", String(myPatient.id));
      }
      const query = params.toString();
      const res = await authFetch(`${API_PREFIX}/documents${query ? `?${query}` : ""}`);
      if (!res.ok) throw new Error(`status ${res.status}`);
      const data = await res.json();
      const items = data.items || [];
      const visibleItems =
        isCaregiver && selfPatient?.id
          ? items.filter((doc) => String(doc.patient_id) !== String(selfPatient.id))
          : items;
      setDocuments(visibleItems);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [isCaregiver, myPatient, selfPatient]);

  useEffect(() => { loadDocuments(); }, [loadDocuments]);

  useEffect(() => {
    if (isCaregiver) {
      setPatientId("");
      setListPatientFilter("all");
      return;
    }

    if (myPatient?.id) {
      setPatientId(String(myPatient.id));
      setListPatientFilter(String(myPatient.id));
      return;
    }

    setPatientId("");
    setListPatientFilter("all");
  }, [isCaregiver, myPatient]);

  useEffect(() => {
    if (view !== "list") return undefined;
    const hasPendingDocument = documents.some((doc) => {
      const status = doc.ocr_status || doc.status;
      return status === "queued" || status === "processing";
    });
    if (!hasPendingDocument) return undefined;

    const id = setInterval(() => {
      loadDocuments();
    }, 4000);
    return () => clearInterval(id);
  }, [documents, loadDocuments, view]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const stopUploadCamera = useCallback(() => {
    if (uploadStreamRef.current) {
      uploadStreamRef.current.getTracks().forEach((track) => track.stop());
      uploadStreamRef.current = null;
    }
    if (uploadVideoRef.current) {
      uploadVideoRef.current.srcObject = null;
    }
    setUploadCameraOpen(false);
  }, []);

  useEffect(() => {
    return () => {
      stopUploadCamera();
    };
  }, [stopUploadCamera]);

  useEffect(() => {
    if (view !== "list") {
      stopUploadCamera();
    }
  }, [stopUploadCamera, view]);

  useEffect(() => {
    if (!uploadCameraOpen) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        stopUploadCamera();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [stopUploadCamera, uploadCameraOpen]);

  const startUploadCamera = useCallback(async () => {
    setUploadCameraLoading(true);
    setUploadCameraError(null);
    setUploadCameraStatus("카메라를 시작하는 중입니다...");
    try {
      if (!navigator?.mediaDevices?.getUserMedia) {
        throw new Error("이 브라우저는 카메라 촬영을 지원하지 않습니다.");
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });
      uploadStreamRef.current = stream;
      setUploadCameraOpen(true);
      if (uploadVideoRef.current) {
        uploadVideoRef.current.srcObject = stream;
        await uploadVideoRef.current.play();
      }
      setUploadCameraStatus("처방전을 화면 안에 맞춘 뒤 '촬영 후 파일 적용' 버튼을 눌러주세요.");
    } catch (err) {
      setUploadCameraError(err?.message || "카메라를 열 수 없습니다.");
      setUploadCameraStatus("카메라를 열지 못했습니다.");
      stopUploadCamera();
    } finally {
      setUploadCameraLoading(false);
    }
  }, [stopUploadCamera]);

  const uploadPatientOptions = useMemo(() => {
    const patientMap = new Map();

    if (isCaregiver) {
      (linkedPatients || []).forEach((patient) => {
        if (!patient?.id) return;
        patientMap.set(String(patient.id), {
          value: String(patient.id),
          label: patient.name || `복약자 #${patient.id}`,
        });
      });
    } else if (myPatient?.id) {
      patientMap.set(String(myPatient.id), {
        value: String(myPatient.id),
        label: myPatient.name || "내 건강 프로필",
      });
    }

    (documents || []).forEach((doc) => {
      if (!doc?.patient_id) return;
      const key = String(doc.patient_id);
      if (!patientMap.has(key)) {
        patientMap.set(key, { value: key, label: `복약자 #${doc.patient_id}` });
      }
    });

    return Array.from(patientMap.values());
  }, [documents, isCaregiver, linkedPatients, myPatient]);

  const filteredDocuments = useMemo(() => {
    if (!isCaregiver) return documents;
    if (listPatientFilter === "all") return documents;
    return documents.filter((doc) => String(doc.patient_id) === String(listPatientFilter));
  }, [documents, isCaregiver, listPatientFilter]);
  const filteredDocumentIdKeys = useMemo(
    () => filteredDocuments.map((doc) => String(doc.document_id || doc.id)).filter(Boolean),
    [filteredDocuments],
  );
  const isAllFilteredSelected =
    filteredDocumentIdKeys.length > 0 && filteredDocumentIdKeys.every((docId) => selectedDocumentIds.includes(docId));

  useEffect(() => {
    setSelectedDocumentIds((prev) => prev.filter((docId) => filteredDocumentIdKeys.includes(docId)));
  }, [filteredDocumentIdKeys]);

  const getPatientDisplayLabel = useCallback(
    (targetPatientId) => {
      if (!targetPatientId) return "—";
      if (!isCaregiver && myPatient?.id && String(myPatient.id) === String(targetPatientId)) {
        return myPatient.name || "내 프로필";
      }
      const matched = uploadPatientOptions.find((patient) => String(patient.value) === String(targetPatientId));
      return matched?.label || `복약자 #${targetPatientId}`;
    },
    [isCaregiver, myPatient, uploadPatientOptions],
  );

  const validateUploadFile = useCallback((file) => {
    if (!file) return false;
    if (file.size > MAX_UPLOAD_FILE_SIZE_BYTES) {
      setError("파일 크기는 최대 10MB까지 업로드할 수 있습니다.");
      return false;
    }
    return true;
  }, []);

  const handleFileChange = (event) => {
    const file = event.target.files?.[0];
    if (!file) {
      setSelectedFile(null);
      return;
    }
    if (!validateUploadFile(file)) {
      setSelectedFile(null);
      event.target.value = "";
      return;
    }
    setError(null);
    setUploadCameraError(null);
    if (uploadCameraOpen) {
      stopUploadCamera();
    }
    setSelectedFile(file);
  };

  const handleCaptureForUpload = useCallback(async () => {
    if (!uploadCameraOpen || !uploadVideoRef.current || !uploadCanvasRef.current) return;
    setUploadCameraError(null);
    setUploadCameraStatus("촬영 중입니다...");
    try {
      const video = uploadVideoRef.current;
      const canvas = uploadCanvasRef.current;
      canvas.width = video.videoWidth || 1280;
      canvas.height = video.videoHeight || 720;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("캔버스 초기화에 실패했습니다.");
      context.drawImage(video, 0, 0, canvas.width, canvas.height);

      const blob = await new Promise((resolve) => {
        canvas.toBlob((value) => resolve(value), "image/jpeg", 0.92);
      });
      if (!blob) throw new Error("이미지 촬영에 실패했습니다.");

      const capturedFile = new File([blob], `ocr-camera-${Date.now()}.jpg`, {
        type: "image/jpeg",
        lastModified: Date.now(),
      });
      if (!validateUploadFile(capturedFile)) {
        return;
      }

      const fileInput = document.getElementById("fileInput");
      if (fileInput) fileInput.value = "";
      setSelectedFile(capturedFile);
      setError(null);
      setUploadCameraStatus("촬영 파일이 선택되었습니다. 업로드 버튼을 눌러주세요.");
      stopUploadCamera();
    } catch (err) {
      setUploadCameraError(err?.message || "카메라 촬영에 실패했습니다.");
      setUploadCameraStatus("촬영에 실패했습니다. 다시 시도해주세요.");
    }
  }, [stopUploadCamera, uploadCameraOpen, validateUploadFile]);

  const fetchDocumentBlob = useCallback(async (documentId) => {
    const response = await authFetch(`${API_PREFIX}/documents/${documentId}/file`);
    if (!response.ok) {
      throw new Error(`status ${response.status}`);
    }
    return response.blob();
  }, []);

  const loadDocumentPreview = useCallback(async (documentId) => {
    if (!documentId) return;
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const blob = await fetchDocumentBlob(documentId);
      const objectUrl = URL.createObjectURL(blob);
      setPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return objectUrl;
      });
      setPreviewMimeType(blob.type || "");
    } catch {
      setPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      setPreviewMimeType("");
      setPreviewError("미리보기를 불러오지 못했습니다.");
    } finally {
      setPreviewLoading(false);
    }
  }, [fetchDocumentBlob]);

  const handleOpenOriginalFile = useCallback(async (documentId) => {
    if (!documentId) return;
    try {
      const blob = await fetchDocumentBlob(documentId);
      const objectUrl = URL.createObjectURL(blob);
      const popup = window.open(objectUrl, "_blank", "noopener,noreferrer");
      if (!popup) {
        const link = document.createElement("a");
        link.href = objectUrl;
        link.download = currentDoc?.original_filename || `document-${documentId}`;
        document.body.appendChild(link);
        link.click();
        link.remove();
      }
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
    } catch (err) {
      setError(err.message || "원본 파일을 열지 못했습니다.");
    }
  }, [currentDoc, fetchDocumentBlob]);

  // 업로드: 목록 화면에서 처리 상태만 갱신
  const handleUpload = async (e) => {
    e.preventDefault();
    if (!selectedFile) return;
    if (!validateUploadFile(selectedFile)) return;
    if (isCaregiver && !patientId) {
      setError("업로드 대상을 선택해주세요.");
      setUploadNotice(null);
      return;
    }
    setUploading(true);
    setError(null);
    setUploadNotice(null);
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      if (patientId) formData.append("patient_id", patientId);
      if (documentTitle.trim()) formData.append("title", documentTitle.trim());

      const res = await authFetch(`${API_PREFIX}/documents/upload`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `status ${res.status}`);
      }
      await res.json();
      setSelectedFile(null);
      setDocumentTitle("");
      setPatientId("");
      setUploadCameraError(null);
      setUploadCameraStatus("카메라를 열어 처방전을 바로 촬영할 수 있습니다.");
      if (document.getElementById("fileInput")) document.getElementById("fileInput").value = "";
      setUploadNotice("업로드가 완료되었습니다. 문서 인식은 백그라운드에서 진행됩니다.");
      loadDocuments();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const refreshOcrStatus = async (docId, options = {}) => {
    const { loadSuccessDrugs = true } = options;
    try {
      const res = await authFetch(`${API_PREFIX}/documents/${docId}/status`);
      if (!res.ok) return null;
      const data = await res.json();
      setOcrStatus(data);
      if (loadSuccessDrugs && data.ocr_status === "success") {
        loadDrugs(docId);
      }
      return data;
    } catch {
      return null;
    }
  };

  // OCR 뷰 열기
  const openOcrView = (doc) => {
    if (pollingId) clearInterval(pollingId);
    const initialOcrStatus = doc.ocr_status || null;
    setCurrentDoc(doc);
    setView("ocr");
    setDrugs([]);
    setOcrStatus(null);
    setSaveMsg(null);
    setPreviewError(null);
    setPreviewMimeType("");
    setUploadNotice(null);
    loadDocumentPreview(doc.document_id);

    if (initialOcrStatus === "success") {
      setOcrStatus({
        document_id: doc.document_id,
        patient_id: doc.patient_id,
        document_status: doc.status || "uploaded",
        has_confirmed_meds: Boolean(doc.has_confirmed_meds),
        ocr_job_id: null,
        ocr_status: "success",
        retry_count: null,
        error_code: null,
        error_message: null,
        barcode_detected: false,
        barcode_count: 0,
        barcode_values: [],
        created_at: doc.created_at,
        updated_at: null,
      });
      loadDrugs(doc.document_id);
      refreshOcrStatus(doc.document_id, { loadSuccessDrugs: false }).then((statusData) => {
        if (!statusData) return;
        if (statusData.ocr_status === "queued" || statusData.ocr_status === "processing") {
          pollOcrStatus(doc.document_id);
        }
      });
      return;
    }

    pollOcrStatus(doc.document_id);
  };

  // OCR 상태 폴링
  const pollOcrStatus = async (docId) => {
    if (pollingId) clearInterval(pollingId);
    const poll = async () => {
      const data = await refreshOcrStatus(docId, { loadSuccessDrugs: true });
      if (!data) return false;
      if (data.ocr_status === "success") return true;
      if (data.ocr_status === "failed") return true;
      return false;
    };

    const done = await poll();
    if (done) return;

    const id = setInterval(async () => {
      const finished = await poll();
      if (finished) clearInterval(id);
    }, 2000);
    setPollingId(id);
  };

  useEffect(() => {
    return () => { if (pollingId) clearInterval(pollingId); };
  }, [pollingId]);

  // 약 목록 로드
  const loadDrugs = async (docId) => {
    setDrugsLoading(true);
    try {
      const res = await authFetch(`${API_PREFIX}/documents/${docId}/drugs?include_mfds=true`);
      if (!res.ok) throw new Error(`status ${res.status}`);
      const data = await res.json();
      setDrugs((data.items || []).map((d) => ({
        extracted_med_id: d.extracted_med_id,
        name: d.name,
        dosage_text: d.dosage_text || "",
        frequency_text: d.frequency_text || "",
        duration_text: d.duration_text || "",
        confidence: d.confidence,
        notes: "",
        needs_review: d.validation?.needs_review || false,
      })));
    } catch { /* ignore */ }
    finally { setDrugsLoading(false); }
  };

  const handleDrugChange = (idx, field, value) => {
    setDrugs((prev) => prev.map((d, i) => i === idx ? { ...d, [field]: value } : d));
    if (field === "duration_text") {
      const hasDuration = String(value || "").trim().length > 0;
      if (hasDuration) {
        setDurationValidationIndices((prev) => prev.filter((item) => item !== idx));
      }
    }
  };

  const handleDrugDelete = (idx) => {
    setDrugs((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleAddDrug = () => {
    setDrugs((prev) => [...prev, {
      extracted_med_id: null, name: "", dosage_text: "", frequency_text: "",
      duration_text: "", confidence: null, notes: "", needs_review: false,
    }]);
  };

  // 임시저장
  const handleTempSave = async () => {
    if (!currentDoc) return;
    setDurationValidationIndices([]);
    setSaving(true);
    setSaveMsg(null);
    try {
      const payload = {
        items: drugs.map((d) => ({
          extracted_med_id: d.extracted_med_id || undefined,
          name: d.name,
          dosage_text: d.dosage_text || null,
          frequency_text: d.frequency_text || null,
          duration_text: d.duration_text || null,
          confidence: d.confidence,
        })),
        replace_all: true,
        confirm: false,
      };
      const res = await authFetch(`${API_PREFIX}/documents/${currentDoc.document_id}/drugs`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `status ${res.status}`);
      }
      setSaveMsg({ type: "success", text: "임시저장 완료" });
    } catch (err) {
      setSaveMsg({ type: "danger", text: err.message });
    } finally { setSaving(false); }
  };

  // 확정하기
  const handleConfirm = async () => {
    if (!currentDoc) return;
    const missingDurationRows = drugs
      .map((drug, index) => ({ drug, index }))
      .filter(({ drug }) => String(drug.name || "").trim() && !String(drug.duration_text || "").trim())
      .map(({ index }) => index);
    if (missingDurationRows.length > 0) {
      const displayRows = missingDurationRows.map((index) => index + 1).join(", ");
      setDurationValidationIndices(missingDurationRows);
      setSaveMsg({ type: "danger", text: `기간(일)을 채워주세요. (누락 행: ${displayRows})` });
      return;
    }

    setDurationValidationIndices([]);
    const wasConfirmedDoc = Boolean(ocrStatus?.has_confirmed_meds || currentDoc?.has_confirmed_meds);
    setSaving(true);
    setSaveMsg(null);
    try {
      const payload = {
        items: drugs.map((d) => ({
          extracted_med_id: d.extracted_med_id || undefined,
          name: d.name,
          dosage_text: d.dosage_text || null,
          frequency_text: d.frequency_text || null,
          duration_text: d.duration_text || null,
          confidence: d.confidence,
        })),
        replace_all: true,
        confirm: true,
        force_confirm: true,
      };
      const res = await authFetch(`${API_PREFIX}/documents/${currentDoc.document_id}/drugs`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(typeof body.detail === "object" ? body.detail.message : (body.detail || `status ${res.status}`));
      }
      setCurrentDoc((prev) => (prev ? { ...prev, has_confirmed_meds: true } : prev));
      setOcrStatus((prev) => (prev ? { ...prev, has_confirmed_meds: true } : prev));
      setUploadNotice(
        wasConfirmedDoc
          ? "수정 완료! 복약 가이드에 반영되었습니다."
          : "확정 완료! 복약 가이드에 반영되었습니다.",
      );
      goBackToList();
    } catch (err) {
      setSaveMsg({ type: "danger", text: err.message });
    } finally { setSaving(false); }
  };

  const handleReupload = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !currentDoc) return;
    if (!validateUploadFile(file)) return;

    try {
      const formData = new FormData();
      formData.append("file", file);
      if (currentDoc.patient_id) formData.append("patient_id", String(currentDoc.patient_id));
      if (currentDoc.original_filename) formData.append("title", currentDoc.original_filename);

      const res = await authFetch(`${API_PREFIX}/documents/upload`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `status ${res.status}`);
      }

      setUploadNotice("문서를 다시 업로드했습니다. 문서 인식은 백그라운드에서 진행됩니다.");
      goBackToList();
    } catch (err) {
      setError(err.message || "재업로드에 실패했습니다.");
    }
  };

  const handleDeleteDocument = async (documentId, options = {}) => {
    if (!documentId || deletingDocument || bulkDeletingDocuments) return;
    const shouldDelete = window.confirm("이 문서를 삭제하시겠습니까?\n삭제 후 문서 목록에서 숨김 처리됩니다.");
    if (!shouldDelete) return;

    setDeletingDocument(true);
    setError(null);
    setUploadNotice(null);
    setSaveMsg(null);
    try {
      const res = await authFetch(`${API_PREFIX}/documents/${documentId}`, { method: "DELETE" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const detail =
          typeof body?.detail === "object"
            ? body?.detail?.message
            : body?.detail;
        throw new Error(detail || `status ${res.status}`);
      }

      if (options.afterDelete === "backToList") {
        setUploadNotice("문서가 삭제되었습니다.");
        goBackToList();
      } else {
        setSelectedDocumentIds((prev) => prev.filter((docId) => docId !== String(documentId)));
        setUploadNotice("문서가 삭제되었습니다.");
        await loadDocuments();
      }
    } catch (err) {
      setError(err?.message || "문서 삭제에 실패했습니다.");
    } finally {
      setDeletingDocument(false);
    }
  };

  const toggleSelectDocument = (documentId, checked) => {
    const targetId = String(documentId);
    setSelectedDocumentIds((prev) => {
      if (checked) {
        if (prev.includes(targetId)) return prev;
        return [...prev, targetId];
      }
      return prev.filter((id) => id !== targetId);
    });
  };

  const toggleSelectAllFilteredDocuments = (checked) => {
    setSelectedDocumentIds((prev) => {
      if (!checked) {
        return prev.filter((id) => !filteredDocumentIdKeys.includes(id));
      }
      return Array.from(new Set([...prev, ...filteredDocumentIdKeys]));
    });
  };

  const handleDeleteSelectedDocuments = async () => {
    if (selectedDocumentIds.length === 0 || deletingDocument || bulkDeletingDocuments) return;
    const shouldDelete = window.confirm(
      `선택한 문서 ${selectedDocumentIds.length}건을 삭제하시겠습니까?\n삭제 후 문서 목록에서 숨김 처리됩니다.`,
    );
    if (!shouldDelete) return;

    setBulkDeletingDocuments(true);
    setError(null);
    setUploadNotice(null);

    const deletedIds = [];
    let firstErrorMessage = "";

    try {
      for (const documentId of selectedDocumentIds) {
        const res = await authFetch(`${API_PREFIX}/documents/${documentId}`, { method: "DELETE" });
        if (res.ok) {
          deletedIds.push(documentId);
          continue;
        }

        if (!firstErrorMessage) {
          const body = await res.json().catch(() => ({}));
          const detail = typeof body?.detail === "object" ? body?.detail?.message : body?.detail;
          firstErrorMessage = detail || `status ${res.status}`;
        }
      }

      if (deletedIds.length > 0) {
        setSelectedDocumentIds((prev) => prev.filter((id) => !deletedIds.includes(id)));
      }
      await loadDocuments();

      if (deletedIds.length === selectedDocumentIds.length) {
        setUploadNotice(`${deletedIds.length}건의 문서를 삭제했습니다.`);
      } else if (deletedIds.length > 0) {
        setUploadNotice(`${deletedIds.length}건 삭제, ${selectedDocumentIds.length - deletedIds.length}건 실패`);
        if (firstErrorMessage) setError(firstErrorMessage);
      } else {
        setError(firstErrorMessage || "선택한 문서 삭제에 실패했습니다.");
      }
    } catch (err) {
      setError(err?.message || "선택한 문서 삭제 중 오류가 발생했습니다.");
    } finally {
      setBulkDeletingDocuments(false);
    }
  };

  const goBackToList = () => {
    stopUploadCamera();
    setView("list");
    setCurrentDoc(null);
    setOcrStatus(null);
    setDrugs([]);
    if (pollingId) clearInterval(pollingId);
    setPollingId(null);
    setPreviewMimeType("");
    setPreviewError(null);
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    loadDocuments();
  };

  // 통계 계산
  const reviewCount = drugs.filter((d) => d.needs_review).length;
  const avgConfidence = drugs.length > 0
    ? Math.round(drugs.reduce((s, d) => s + (d.confidence || 0), 0) / drugs.length * 100)
    : 0;
  const freqCount = drugs.filter((d) => d.frequency_text).length;

  const displayDrugs = showReviewOnly ? drugs.filter((d) => d.needs_review) : drugs;

  // ─── OCR 결과 뷰 ───
  if (view === "ocr") {
    const isProcessing = !ocrStatus || ocrStatus.ocr_status === "queued" || ocrStatus.ocr_status === "processing";
    const isFailed = ocrStatus?.ocr_status === "failed";
    const isSuccess = ocrStatus?.ocr_status === "success";
    const isConfirmedDoc = Boolean(ocrStatus?.has_confirmed_meds || currentDoc?.has_confirmed_meds);
    const confirmButtonLabel = isConfirmedDoc ? "수정하기" : "확정하기";
    const canPreviewPdf = Boolean(previewUrl) && (previewMimeType.includes("pdf") || currentDoc?.file_type === "pdf");
    const canPreviewImage = Boolean(previewUrl) && (
      previewMimeType.startsWith("image/") || currentDoc?.file_type === "image"
    );
    const documentInfoCard = (
      <div className="doc-info-card">
        <div className="d-flex align-items-center gap-2 mb-3">
          <span style={{ fontSize: "1.2rem" }}>📄</span>
          <strong>문서 정보</strong>
        </div>
        <div className="doc-preview-box">
          {previewLoading && (
            <div className="text-center py-4 text-muted">
              <div className="spinner-border spinner-border-sm text-primary mb-2" role="status" />
              <div className="small">문서 미리보기를 불러오는 중입니다.</div>
            </div>
          )}
          {!previewLoading && previewError && (
            <div className="text-center py-4 text-muted">
              <div style={{ fontSize: "1.5rem" }}>⚠️</div>
              <div className="small">{previewError}</div>
            </div>
          )}
          {!previewLoading && !previewError && canPreviewPdf && (
            <iframe title="문서 미리보기" src={previewUrl} className="doc-preview-frame" />
          )}
          {!previewLoading && !previewError && canPreviewImage && (
            <img src={previewUrl} alt="문서 미리보기" className="doc-preview-image" />
          )}
          {!previewLoading && !previewError && (!previewUrl || (!canPreviewPdf && !canPreviewImage)) && (
            <div className="text-muted text-center py-4">
              <div style={{ fontSize: "2rem" }}>📄</div>
              <div className="small">원본 보기로 확인해주세요.</div>
            </div>
          )}
        </div>
        <div className="mt-3 small">
          <div className="d-flex justify-content-between mb-1">
            <span className="text-muted">파일명</span>
            <span className="fw-semibold">{currentDoc.original_filename || "—"}</span>
          </div>
          <div className="d-flex justify-content-between mb-1">
            <span className="text-muted">업로드 날짜</span>
            <span className="fw-semibold">{currentDoc.created_at ? new Date(currentDoc.created_at).toLocaleString("ko-KR") : "—"}</span>
          </div>
          <div className="d-flex justify-content-between mb-1">
            <span className="text-muted">업로드 주체</span>
            <span className="fw-semibold">본인</span>
          </div>
          <div className="d-flex justify-content-between mb-1">
            <span className="text-muted">대상 복약자</span>
            <span className="fw-semibold">{getPatientDisplayLabel(currentDoc.patient_id)}</span>
          </div>
        </div>
        <div className="d-flex gap-2 mt-3">
          <button
            className="btn btn-outline-primary btn-sm flex-fill"
            onClick={() => handleOpenOriginalFile(currentDoc.document_id)}
          >
            원본 보기
          </button>
          <button className="btn btn-outline-secondary btn-sm flex-fill" onClick={() => {
            document.getElementById("reuploadInput")?.click();
          }}>다시 업로드</button>
          <button
            className="btn btn-outline-danger btn-sm flex-fill"
            onClick={() => handleDeleteDocument(currentDoc.document_id, { afterDelete: "backToList" })}
            disabled={deletingDocument}
          >
            {deletingDocument ? "삭제 중..." : "삭제"}
          </button>
          <input
            type="file"
            id="reuploadInput"
            className="d-none"
            accept="image/*,.pdf"
            onChange={handleReupload}
          />
        </div>
      </div>
    );

    return (
      <AppLayout
        activeKey="documents"
        title="처방전 업로드"
        description="처방전을 업로드하고 추출된 약 정보를 검토합니다."
        headerCompact
        loginRole={loginRole}
        userName={userName}
        modeOptions={modeOptions}
        currentMode={currentMode}
        onModeChange={onModeChange}
      >
          <div className="doc-header">
            <div className="d-flex align-items-center gap-2">
              {isSuccess && (
                <span className="badge bg-success-subtle text-success px-3 py-2" style={{ fontSize: "0.85rem" }}>
                  문서 인식 완료
                </span>
              )}
              <button
                className="btn btn-outline-danger btn-sm"
                onClick={() => currentDoc?.document_id && handleDeleteDocument(currentDoc.document_id, { afterDelete: "backToList" })}
                disabled={deletingDocument || !currentDoc?.document_id}
              >
                {deletingDocument ? "삭제 중..." : "문서 삭제"}
              </button>
            </div>
          </div>
          {error && (
            <div className="alert alert-danger alert-dismissible mt-3">
              {error}
              <button type="button" className="btn-close" onClick={() => setError(null)} />
            </div>
          )}

          {/* OCR 처리 중 */}
          {isProcessing && (
            <div className="text-center py-5">
              <div className="spinner-border text-primary mb-3" role="status" />
              <div className="text-muted">문서 인식 처리 중입니다... 잠시만 기다려주세요.</div>
            </div>
          )}

          {/* OCR 실패 */}
          {isFailed && (
            <>
              <div className="alert alert-danger">
                문서 인식에 실패했습니다. {ocrStatus.error_message || ""}
                <button className="btn btn-warning btn-sm ms-3" onClick={() => {
                  authFetch(`${API_PREFIX}/documents/${currentDoc.document_id}/retry`, { method: "POST" })
                    .then(() => pollOcrStatus(currentDoc.document_id));
                }}>재시도</button>
              </div>
              <div className="doc-top-cards mt-3">
                {documentInfoCard}
              </div>
            </>
          )}

          {/* OCR 성공 */}
          {isSuccess && (
            <>
              <div className="doc-result-intro">
                <h5 className="fw-bold mb-1">문서 인식 결과 확인</h5>
                <p className="text-muted mb-0">
                  {isConfirmedDoc
                    ? "확정된 약 정보를 수정하고 저장할 수 있습니다."
                    : "추출된 약 정보를 확인하고 필요 시 수정한 뒤 확정해주세요."}
                </p>
              </div>

              {/* 상단 카드 영역 */}
              <div className="doc-top-cards">
                {documentInfoCard}

                <StatCard label="추출된 약 개수" value={drugs.length} unit="개" color="#2563eb" />
                <StatCard label="복용 일정 감지" value={freqCount} unit="개" color="#7c3aed" />
                <StatCard label="검토 필요 항목" value={reviewCount} unit="개" color="#dc2626" />
                <StatCard label="신뢰도" value={avgConfidence} unit="%" color="#2563eb" />
              </div>

              {/* 약 정보 테이블 */}
              <div className="doc-drugs-section">
                <div className="d-flex align-items-center justify-content-between mb-3">
                  <div className="d-flex align-items-center gap-2">
                    <h5 className="fw-bold mb-0">약 정보 목록</h5>
                    <button className="btn btn-primary btn-sm" onClick={handleAddDrug}>+ 약 추가</button>
                  </div>
                  <label className="form-check-label d-flex align-items-center gap-1 small">
                    <input type="checkbox" className="form-check-input" checked={showReviewOnly}
                      onChange={(e) => setShowReviewOnly(e.target.checked)} />
                    검토 필요 항목만 보기
                  </label>
                </div>

                <div className="small text-muted mb-2">
                  ⚠ 확정된 약 리스트가 이후 가이드 생성에 사용됩니다.
                </div>

                {drugsLoading ? (
                  <div className="text-center py-4 text-muted">약 정보 불러오는 중...</div>
                ) : (
                  <div className="table-responsive">
                    <table className="table table-sm align-middle doc-drug-table">
                      <thead>
                        <tr>
                          <th>약명 <span className="text-danger">*</span></th>
                          <th>용량/단위</th>
                          <th>1일 횟수</th>
                          <th>복용 시간</th>
                          <th>기간(일)</th>
                          <th>비고</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {displayDrugs.map((drug, idx) => {
                          const realIdx = showReviewOnly ? drugs.indexOf(drug) : idx;
                          return (
                            <DrugRow
                              key={realIdx}
                              drug={drug}
                              index={realIdx}
                              onChange={handleDrugChange}
                              onDelete={handleDrugDelete}
                              isDurationMissing={durationValidationIndices.includes(realIdx)}
                            />
                          );
                        })}
                        {displayDrugs.length === 0 && (
                          <tr><td colSpan={7} className="text-center text-muted py-3">추출된 약이 없습니다.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* 하단 액션 */}
              {saveMsg && (
                <div className={`alert alert-${saveMsg.type} mt-3`}>{saveMsg.text}</div>
              )}
              <div className="doc-bottom-actions">
                <button className="btn btn-outline-secondary" onClick={handleTempSave} disabled={saving}>
                  임시저장
                </button>
                <button className="btn btn-primary btn-lg px-5" onClick={handleConfirm} disabled={saving}>
                  {confirmButtonLabel}
                </button>
                <button className="btn btn-outline-secondary" onClick={goBackToList}>
                  목록으로
                </button>
              </div>
            </>
          )}
      </AppLayout>
    );
  }

  // ─── 문서 목록 뷰 ───
  return (
    <AppLayout
      activeKey="documents"
      title="처방전 업로드"
      description="문서를 업로드하고 복약자별 처방전 상태를 확인합니다."
      loginRole={loginRole}
      userName={userName}
      modeOptions={modeOptions}
      currentMode={currentMode}
      onModeChange={onModeChange}
    >
        {error && (
          <div className="alert alert-danger alert-dismissible">
            {error}
            <button type="button" className="btn-close" onClick={() => setError(null)} />
          </div>
        )}
        {uploadNotice && (
          <div className="alert alert-success alert-dismissible">
            {uploadNotice}
            <button type="button" className="btn-close" onClick={() => setUploadNotice(null)} />
          </div>
        )}

        {/* 업로드 폼 */}
        <div className="card border-0 shadow-sm mb-4">
          <div className="card-body">
            <h6 className="fw-bold mb-3">처방전 업로드</h6>
            <form onSubmit={handleUpload}>
              <div className="row g-3 doc-upload-grid">
                <div className="col-md-4">
                  <label className="form-label small">파일 선택 (최대 10MB)</label>
                  <input
                    type="file"
                    id="fileInput"
                    className="form-control"
                    onChange={handleFileChange}
                    accept="image/*,.pdf"
                  />
                </div>
                <div className="col-md-3">
                  <label className="form-label small">문서명 (선택)</label>
                  <input
                    type="text"
                    className="form-control"
                    value={documentTitle}
                    onChange={(e) => setDocumentTitle(e.target.value)}
                    placeholder="예: 3월 외래 처방전"
                    maxLength={255}
                  />
                </div>
                <div className="col-md-3">
                  <label className="form-label small">복약자 선택</label>
                  {isCaregiver ? (
                    <select className="form-select" value={patientId} onChange={(e) => setPatientId(e.target.value)}>
                      <option value="">업로드 대상 선택</option>
                      {uploadPatientOptions.map((patient) => (
                        <option key={patient.value} value={patient.value}>
                          {patient.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <div className="form-control bg-light">
                      {myPatient?.name || "내 프로필"}
                    </div>
                  )}
                </div>
                <div className="col-md-2">
                  <button type="submit" className="btn btn-primary w-100" disabled={uploading || !selectedFile}>
                    {uploading ? "업로드 중..." : "업로드"}
                  </button>
                </div>
              </div>
              <div className="mt-3">
                <div className="d-flex flex-wrap justify-content-between align-items-center gap-2">
                  <div className="small fw-semibold">카메라 촬영 업로드</div>
                  <div className="d-flex flex-wrap gap-2">
                    <button
                      type="button"
                      className={`btn btn-sm ${uploadCameraOpen ? "btn-outline-danger" : "btn-outline-primary"}`}
                      onClick={uploadCameraOpen ? stopUploadCamera : startUploadCamera}
                      disabled={uploading || uploadCameraLoading}
                    >
                      {uploadCameraLoading ? "준비 중..." : uploadCameraOpen ? "카메라 닫기" : "카메라 열기"}
                    </button>
                  </div>
                </div>
                <canvas ref={uploadCanvasRef} className="d-none" />
                <div className="small text-muted mt-2">{uploadCameraStatus}</div>
                {selectedFile && (
                  <div className="small mt-1">
                    선택 파일: <strong>{selectedFile.name}</strong>
                  </div>
                )}
                {uploadCameraError && <div className="alert alert-danger mt-2 mb-0 py-2">{uploadCameraError}</div>}
                <div
                  className={`upload-camera-overlay ${uploadCameraOpen ? "is-open" : ""}`}
                  role="dialog"
                  aria-modal="true"
                  aria-label="처방전 카메라 촬영"
                  onClick={stopUploadCamera}
                >
                  <div className="upload-camera-panel" onClick={(event) => event.stopPropagation()}>
                    <div className="d-flex justify-content-between align-items-center gap-2 mb-3">
                      <h6 className="fw-bold mb-0">처방전 카메라 촬영</h6>
                      <button
                        type="button"
                        className="btn btn-outline-secondary btn-sm"
                        onClick={stopUploadCamera}
                        disabled={uploading}
                      >
                        닫기
                      </button>
                    </div>
                    <div className="upload-camera-video-wrap">
                      <video ref={uploadVideoRef} className="upload-camera-video" playsInline muted />
                    </div>
                    <div className="small text-muted mt-2 mb-3">
                      화면에 처방전 전체가 들어오도록 맞춘 뒤 촬영하세요.
                    </div>
                    <div className="d-flex flex-wrap justify-content-end gap-2">
                      <button
                        type="button"
                        className="btn btn-primary"
                        onClick={handleCaptureForUpload}
                        disabled={!uploadCameraOpen || uploading}
                      >
                        촬영 후 파일 적용
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </form>
          </div>
        </div>

        {/* 문서 목록 */}
        <div className="card border-0 shadow-sm">
          <div className="card-body">
            <div className="doc-list-toolbar mb-3">
              <h6 className="fw-bold mb-0">처방전 목록</h6>
              <div className="d-flex flex-wrap align-items-end gap-2">
                <div className="doc-list-filter">
                  <label className="form-label small mb-1">조회 대상 선택</label>
                  {isCaregiver ? (
                    <select
                      className="form-select form-select-sm"
                      value={listPatientFilter}
                      onChange={(event) => setListPatientFilter(event.target.value)}
                    >
                      <option value="all">전체 복약자</option>
                      {uploadPatientOptions.map((patient) => (
                        <option key={patient.value} value={patient.value}>
                          {patient.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <div className="form-control form-control-sm bg-light">
                      {myPatient?.name || "내 문서"}
                    </div>
                  )}
                </div>
                <button className="btn btn-outline-secondary btn-sm" onClick={loadDocuments} disabled={loading}>
                  {loading ? "로딩..." : "새로고침"}
                </button>
                <button
                  className="btn btn-outline-danger btn-sm"
                  onClick={handleDeleteSelectedDocuments}
                  disabled={
                    selectedDocumentIds.length === 0
                    || deletingDocument
                    || bulkDeletingDocuments
                    || loading
                  }
                >
                  {bulkDeletingDocuments ? "선택 삭제 중..." : `선택 삭제 (${selectedDocumentIds.length})`}
                </button>
              </div>
            </div>
            {filteredDocuments.length === 0 ? (
              <div className="text-center py-5 text-muted">등록된 처방전이 없습니다. 상단에서 문서를 업로드해보세요.</div>
            ) : (
              <div className="table-responsive">
                <table className="table table-hover align-middle">
                  <thead>
                    <tr>
                      <th style={{ width: "42px" }}>
                        <input
                          type="checkbox"
                          className="form-check-input"
                          checked={isAllFilteredSelected}
                          onChange={(event) => toggleSelectAllFilteredDocuments(event.target.checked)}
                          disabled={filteredDocumentIdKeys.length === 0 || deletingDocument || bulkDeletingDocuments}
                        />
                      </th>
                      <th>ID</th>
                      <th>파일명</th>
                      <th>대상 복약자</th>
                      <th>상태</th>
                      <th>업로드 일시</th>
                      <th>작업</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredDocuments.map((doc) => {
                      const docId = doc.document_id || doc.id;
                      const docIdKey = String(docId);
                      const st = doc.ocr_status || doc.status;
                      const badgeCls = { queued: "bg-warning", processing: "bg-info", success: "bg-success", failed: "bg-danger" }[st] || "bg-secondary";
                      const stText = { queued: "대기 중", processing: "처리 중", success: "완료", failed: "실패" }[st] || st;
                      return (
                        <tr key={docId}>
                          <td>
                            <input
                              type="checkbox"
                              className="form-check-input"
                              checked={selectedDocumentIds.includes(docIdKey)}
                              onChange={(event) => toggleSelectDocument(docIdKey, event.target.checked)}
                              disabled={deletingDocument || bulkDeletingDocuments}
                            />
                          </td>
                          <td>{docId}</td>
                          <td>{doc.original_filename || "—"}</td>
                          <td>{getPatientDisplayLabel(doc.patient_id)}</td>
                          <td><span className={`badge ${badgeCls}`}>{stText}</span></td>
                          <td>{new Date(doc.created_at).toLocaleString("ko-KR")}</td>
                          <td>
                            <div className="d-flex gap-2">
                              <button className="btn btn-outline-primary btn-sm" onClick={() => openOcrView({
                                document_id: docId, patient_id: doc.patient_id,
                                original_filename: doc.original_filename, created_at: doc.created_at,
                                uploaded_by_user_id: doc.uploaded_by_user_id,
                                status: doc.status, ocr_status: doc.ocr_status,
                                has_confirmed_meds: Boolean(doc.has_confirmed_meds),
                              })}>
                                인식 결과
                              </button>
                              <button
                                className="btn btn-outline-danger btn-sm"
                                onClick={() => handleDeleteDocument(docId)}
                                disabled={deletingDocument || bulkDeletingDocuments}
                              >
                                {deletingDocument ? "삭제 중..." : "삭제"}
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
    </AppLayout>
  );
}

export default DocumentManagement;
