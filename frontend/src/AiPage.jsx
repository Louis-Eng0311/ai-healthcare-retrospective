import React, { useEffect, useMemo, useRef, useState } from "react";
import AppLayout from "./components/AppLayout.jsx";

const API_PREFIX = "/api/v1";

const pageStyle = {
  minHeight: "100vh",
  background: "var(--app-body-bg)",
};

const mainCardStyle = {
  borderRadius: "18px",
  background: "var(--app-surface-bg)",
  border: "1px solid var(--app-surface-border)",
  boxShadow: "var(--app-surface-shadow)",
};

const blockCardStyle = {
  borderRadius: "16px",
  background: "var(--app-surface-bg)",
  border: "1px solid var(--app-surface-border)",
  boxShadow: "var(--app-surface-shadow)",
};

const metricCardStyle = {
  borderRadius: "14px",
  background: "var(--app-surface-subtle)",
  border: "1px solid var(--app-surface-border)",
  padding: "20px",
  height: "100%",
};

const chipStyle = {
  display: "inline-flex",
  alignItems: "center",
  borderRadius: "999px",
  padding: "6px 12px",
  border: "1px solid var(--app-surface-border)",
  background: "rgba(37, 99, 235, 0.16)",
  color: "var(--app-brand-color)",
  fontSize: "0.88rem",
  fontWeight: 600,
};

const statusColorMap = {
  DONE: { bg: "#eef6ff", color: "#1d4ed8", label: "가이드 준비 완료" },
  GENERATING: { bg: "#f8fafc", color: "#475569", label: "가이드 생성 중" },
  FAILED: { bg: "#fef2f2", color: "#b91c1c", label: "가이드 생성 실패" },
};

const heroBannerStyle = {
  borderRadius: "18px",
  padding: "28px",
  marginBottom: "28px",
  background: "linear-gradient(135deg, #13448e 0%, #2563eb 58%, #4b85e0 100%)",
  color: "#ffffff",
  boxShadow: "0 14px 32px rgba(37, 99, 235, 0.2)",
};

const primaryActionButtonStyle = {
  background: "#2563eb",
  borderColor: "#2563eb",
  color: "#ffffff",
  boxShadow: "0 8px 18px rgba(37, 99, 235, 0.18)",
};

const chatFeedbackReasons = [
  { value: "wrong_context", label: "문맥이 어긋나요" },
  { value: "not_helpful", label: "도움이 부족해요" },
  { value: "fact_error", label: "정보가 부정확해요" },
  { value: "too_generic", label: "너무 일반적이에요" },
];

const feedbackBaseButtonStyle = {
  borderRadius: "999px",
  border: "1px solid var(--app-surface-border)",
  background: "var(--app-surface-subtle)",
  color: "var(--app-text-color)",
  fontSize: "0.8rem",
  fontWeight: 600,
  padding: "7px 12px",
  lineHeight: 1,
  transition: "all 0.18s ease",
};

const feedbackSelectedButtonStyle = {
  background: "#eef9f2",
  borderColor: "#bfe6cb",
  color: "#1f7a45",
  boxShadow: "0 6px 14px rgba(31, 122, 69, 0.08)",
};

const feedbackNegativeButtonStyle = {
  background: "#fff5f5",
  borderColor: "#f1c8c8",
  color: "#c44a4a",
};

const scrollPanelStyle = {
  maxHeight: "320px",
  overflowY: "auto",
  paddingRight: "6px",
};

const guideBodyStyle = {
  whiteSpace: "pre-wrap",
  lineHeight: 1.75,
  overflowWrap: "anywhere",
  wordBreak: "break-word",
};

const normalizeProfileList = (value) => {
  if (Array.isArray(value)) return value.filter(Boolean).map((item) => String(item).trim()).filter(Boolean);
  if (!value) return [];
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return [];
    if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
      try {
        return normalizeProfileList(JSON.parse(trimmed));
      } catch {
        return trimmed.split(",").map((item) => item.trim()).filter(Boolean);
      }
    }
    return trimmed.split(",").map((item) => item.trim()).filter(Boolean);
  }
  return [];
};

const collectGuideLines = (section) => {
  if (!section) return [];
  const bodyLines = String(section.body || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  return [...bodyLines, ...(Array.isArray(section.bullets) ? section.bullets : [])].filter(Boolean);
};

const pickGuideSectionByKeyword = (sections, keywords) =>
  sections.find((section) => keywords.some((keyword) => String(section?.title || "").includes(keyword)));

const isGuideOverviewSection = (section) => {
  const title = String(section?.title || "").trim();
  if (!title) return false;
  return ["복약", "생활", "건강 프로필", "건강프로필", "확인 포인트", "주의", "위험", "신호"].some((keyword) =>
    title.includes(keyword),
  );
};

const uniqueGuideLines = (lines, seen = new Set()) =>
  lines.filter((line) => {
    const normalized = String(line).trim();
    if (!normalized || seen.has(normalized)) return false;
    seen.add(normalized);
    return true;
  });

const buildGuideBriefing = (guideSections, caregiverPoints) => {
  const summarySection = guideSections[0] || null;
  const medicationSection = pickGuideSectionByKeyword(guideSections, ["복약", "약"]) || summarySection;
  const lifestyleSection = pickGuideSectionByKeyword(guideSections, ["생활", "수면", "운동", "관리"]);
  const warningSection = pickGuideSectionByKeyword(guideSections, ["주의", "위험", "신호", "이상"]);
  const seen = new Set();

  return {
    summary: uniqueGuideLines(collectGuideLines(summarySection), seen).slice(0, 3),
    medication: uniqueGuideLines(collectGuideLines(medicationSection), seen).slice(0, 3),
    lifestyle: uniqueGuideLines(collectGuideLines(lifestyleSection), seen).slice(0, 3),
    warning: uniqueGuideLines([...collectGuideLines(warningSection), ...caregiverPoints], seen).slice(0, 3),
  };
};

const buildProfileBriefing = (profile) => {
  if (!profile) return ["건강 프로필이 아직 등록되지 않았습니다."];

  const conditions = normalizeProfileList(profile.conditions);
  const allergies = normalizeProfileList(profile.allergies);
  const lines = [];

  if (conditions.length > 0) lines.push(`기저 질환: ${conditions.slice(0, 2).join(", ")}`);
  if (allergies.length > 0) lines.push(`알레르기: ${allergies.slice(0, 2).join(", ")}`);
  if (profile.bmi) lines.push(`BMI: ${Number(profile.bmi).toFixed(1)}`);
  if (profile.avg_sleep_hours_per_day) lines.push(`수면: 하루 평균 ${profile.avg_sleep_hours_per_day}시간`);
  if (profile.avg_exercise_minutes_per_day) lines.push(`운동: 하루 평균 ${profile.avg_exercise_minutes_per_day}분`);
  if (profile.avg_alcohol_bottles_per_week) lines.push(`음주: 주 ${profile.avg_alcohol_bottles_per_week}병`);
  if (profile.is_smoker || profile.avg_cig_packs_per_week) {
    lines.push(`흡연: 주 ${profile.avg_cig_packs_per_week || 0}갑`);
  }
  if (typeof profile.is_hospitalized === "boolean") {
    lines.push(profile.is_hospitalized ? "현재 입원 상태" : "현재 외래 관리 중");
  }

  return lines.slice(0, 4);
};

const buildMedicationSnapshot = (items) => {
  if (!Array.isArray(items) || items.length === 0) {
    return [];
  }

  return items
    .slice(0, 3)
    .map((item) => {
      const pieces = [item.display_name, item.frequency_text || item.dosage || "복약 정보 확인 필요"].filter(Boolean);
      return pieces.join(" · ");
    });
};

const buildMedicationScheduleBriefing = (items) => {
  if (!Array.isArray(items) || items.length === 0) {
    return [];
  }

  return items.slice(0, 4).map((item) => {
    const parts = [
      item.display_name,
      item.frequency_text || "복용 시점 확인 필요",
      item.dosage || null,
    ].filter(Boolean);
    return parts.join(" · ");
  });
};

const normalizeMedicationLines = (value) => {
  const items = Array.isArray(value) ? value : value ? [value] : [];
  return items
    .flatMap((item) =>
      String(item || "")
        .split(/(?<=[.!?。])(?=\s|[가-힣A-Za-z0-9])/)
        .map((line) => line.trim())
        .filter(Boolean),
    );
};

function MetricTile({ label, value }) {
  return (
    <div style={metricCardStyle}>
      <div className="small text-muted">{label}</div>
      <div className="fw-semibold">{value}</div>
    </div>
  );
}

function BriefingCard({ title, lines, emptyText }) {
  return (
    <div style={{ ...metricCardStyle, padding: "18px 20px" }}>
      <div className="fw-semibold mb-2">{title}</div>
      <div style={scrollPanelStyle}>
        <ul className="mb-0 ps-3 small" style={{ ...guideBodyStyle, lineHeight: 1.8 }}>
          {(lines.length > 0 ? lines : [emptyText]).map((line, index) => (
            <li key={index} style={{ marginBottom: "6px" }}>
              {line}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

const safeJson = async (res) => {
  try {
    return await res.json();
  } catch {
    return null;
  }
};

const formatDateTime = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
};

const formatDate = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
  }).format(date);
};

const formatApiError = (value) => {
  if (!value) return "알 수 없는 오류가 발생했습니다.";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map((item) => item?.msg || JSON.stringify(item)).join(", ");
  if (typeof value === "object") {
    if (value.detail) return formatApiError(value.detail);
    if (value.message) return formatApiError(value.message);
    if (value.code && value.message) return `${value.message}`;
    return JSON.stringify(value);
  }
  return String(value);
};

const normalizeGuideSections = (guideDetail) => {
  const jsonSections = guideDetail?.content_json?.sections;
  if (Array.isArray(jsonSections) && jsonSections.length > 0) {
    return jsonSections.map((section, index) => ({
      id: `${section.title || "section"}-${index}`,
      title: section.title || `섹션 ${index + 1}`,
      body: section.body || "",
      bullets: Array.isArray(section.bullets) ? section.bullets.filter(Boolean) : [],
    }));
  }

  const text = guideDetail?.content_text || "";
  if (!text.trim()) return [];

  return text
    .split(/\n{2,}/)
    .map((chunk, index) => chunk.trim())
    .filter(Boolean)
    .map((chunk, index) => {
      const lines = chunk.split("\n").map((line) => line.trim()).filter(Boolean);
      if (lines.length === 0) {
        return null;
      }
      const [titleLine, ...rest] = lines;
      return {
        id: `fallback-${index}`,
        title: titleLine.length <= 24 ? titleLine : `가이드 ${index + 1}`,
        body: chunk,
        bullets: (rest.length > 0 ? rest : [chunk]).map((line) => line.replace(/^[-•]\s*/, "")),
      };
    })
    .filter(Boolean);
};

const normalizeCaregiverPoints = (guideDetail) => {
  const summary = guideDetail?.caregiver_summary;
  if (!summary) return [];
  if (Array.isArray(summary?.care_points)) return summary.care_points.filter(Boolean);
  if (Array.isArray(summary?.today_checklist) || Array.isArray(summary?.warning_signs)) {
    return [...(summary.today_checklist || []), ...(summary.warning_signs || [])].filter(Boolean);
  }
  if (Array.isArray(summary?.items)) return summary.items.filter(Boolean);
  if (typeof summary === "string") return [summary];
  return [];
};

const renderChatContent = (content) => {
  const lines = String(content || "").split("\n");
  const blocks = [];
  let listBuffer = [];

  const flushList = () => {
    if (listBuffer.length > 0) {
      blocks.push({ type: "list", items: listBuffer });
      listBuffer = [];
    }
  };

  lines.forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      flushList();
      return;
    }

    if (line.startsWith("- ")) {
      listBuffer.push(line.slice(2).trim());
      return;
    }

    flushList();
    blocks.push({ type: "paragraph", text: line });
  });

  flushList();

  return blocks.map((block, index) => {
    if (block.type === "list") {
      return (
        <ul key={`list-${index}`} className="mb-2 ps-3" style={{ lineHeight: 1.8 }}>
          {block.items.map((item, itemIndex) => (
            <li key={`item-${itemIndex}`} style={{ marginBottom: "4px" }}>
              {item}
            </li>
          ))}
        </ul>
      );
    }

    return (
      <p key={`paragraph-${index}`} className="mb-2" style={{ lineHeight: 1.8 }}>
        {block.text}
      </p>
    );
  });
};

const getGuideStatusMeta = (status) => statusColorMap[status] || { bg: "#f1f5f9", color: "#475569", label: status || "상태 미확인" };

const getChatStorageKey = (role, patientId) => `ai-chat-session:${role || "UNKNOWN"}:${patientId || "unknown"}`;
const isPendingAssistantMessage = (message) =>
  String(message?.role || "").toLowerCase() === "assistant" && ["queued", "processing"].includes(String(message?.status || ""));
const hasPendingAssistantMessages = (messages) => Array.isArray(messages) && messages.some(isPendingAssistantMessage);

const resolveChatSetupHint = ({ isCaregiver, selectedPatientId, profileMissing, profileError }) => {
  if (isCaregiver && !selectedPatientId) {
    return {
      title: "상담 대상을 먼저 선택해 주세요",
      description: "연동된 복약자를 선택하면 약속이가 해당 환자 기준으로 답변을 이어갑니다.",
      ctaLabel: null,
    };
  }

  if (!selectedPatientId && profileMissing) {
    return {
      title: "건강 프로필을 먼저 등록해 주세요",
      description: "프로필을 한 번 등록하면 상담 대상이 연결되고, 약속이가 환자 기준으로 대화를 시작할 수 있습니다.",
      ctaLabel: "건강 프로필 등록하기",
    };
  }

  if (!selectedPatientId && !isCaregiver) {
    return {
      title: "상담 대상을 불러오지 못했어요",
      description: profileError
        ? "현재 계정의 복약자 정보를 불러오지 못해 상담을 시작할 수 없습니다. 건강 프로필 페이지에서 다시 연결해 주세요."
        : "현재 계정의 복약자 정보가 연결되지 않아 상담을 시작할 수 없습니다. 건강 프로필 페이지에서 먼저 정보를 확인해 주세요.",
      ctaLabel: "건강 프로필 확인하기",
    };
  }

  return null;
};

function AiPage({
  modeOptions = [],
  currentMode = "PATIENT",
  onModeChange,
  userName = "사용자",
}) {
  const searchParams = useMemo(() => new URLSearchParams(window.location.search), []);
  const requestedPatientId = searchParams.get("patient_id");
  const requestedGuideId = searchParams.get("guide_id");
  const requestedDocumentId = searchParams.get("document_id");
  const shouldOpenChat = searchParams.get("open_chat") === "1";

  const readCookie = (name) => {
    if (typeof document === "undefined") return null;
    const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
    return match ? decodeURIComponent(match[2]) : null;
  };

  const [accessToken, setAccessToken] = useState(() => {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem("access_token") || readCookie("access_token");
  });
  const [loginRole, setLoginRole] = useState(() => {
    if (typeof window === "undefined") return "PATIENT";
    return window.localStorage.getItem("login_role") || "PATIENT";
  });

  const [meState, setMeState] = useState({ loading: false, data: null, error: null });
  const [linksState, setLinksState] = useState({ loading: false, data: null, error: null });
  const [profileState, setProfileState] = useState({ loading: false, data: null, error: null, missing: false });
  const [documentsState, setDocumentsState] = useState({ loading: false, data: [], error: null });
  const [medGuideState, setMedGuideState] = useState({ loading: false, data: [], error: null });
  const [guidesState, setGuidesState] = useState({ loading: false, data: [], error: null });
  const [guideDetailState, setGuideDetailState] = useState({ loading: false, data: null, error: null });
  const [guideActionState, setGuideActionState] = useState({ submitting: false, error: null, success: null });
  const [guideUpdatedAt, setGuideUpdatedAt] = useState(null);
  const [chatState, setChatState] = useState({
    open: shouldOpenChat,
    sessionId: null,
    loading: false,
    sending: false,
    messages: [],
    error: null,
  });
  const [chatInput, setChatInput] = useState("");
  const [chatFeedbackState, setChatFeedbackState] = useState({});
  const [selectedPatientId, setSelectedPatientId] = useState(requestedPatientId || "");
  const [selectedGuideId, setSelectedGuideId] = useState(requestedGuideId || "");
  const [selectedDocumentId, setSelectedDocumentId] = useState(requestedDocumentId || "");
  const effectiveMode = currentMode || loginRole;

  const chatContainerRef = useRef(null);
  const patientOptions = (linksState.data?.links || []).map((link) => ({
    value: String(link.patient_id),
    label: link.patient_name || `환자 #${link.patient_id}`,
  }));

  const refreshAccessToken = async () => {
    const res = await fetch(`${API_PREFIX}/auth/token/refresh`, {
      method: "GET",
      credentials: "include",
    });
    if (!res.ok) return null;
    const body = await safeJson(res);
    const token = body?.access_token;
    if (token) {
      if (typeof window !== "undefined") {
        window.localStorage.setItem("access_token", token);
      }
      setAccessToken(token);
    }
    return token || null;
  };

  const authFetch = async (path, options = {}, retryOnUnauthorized = true) => {
    const headers = new Headers(options.headers || {});
    if (!headers.has("Content-Type") && options.body) {
      headers.set("Content-Type", "application/json");
    }
    if (accessToken) {
      headers.set("Authorization", `Bearer ${accessToken}`);
    }

    const res = await fetch(path, {
      ...options,
      headers,
      credentials: "include",
    });

    if (res.status === 401 && retryOnUnauthorized) {
      const newToken = await refreshAccessToken();
      if (newToken) {
        headers.set("Authorization", `Bearer ${newToken}`);
        return fetch(path, {
          ...options,
          headers,
          credentials: "include",
        });
      }
    }

    return res;
  };

  const selectedLink = (linksState.data?.links || []).find((link) => String(link.patient_id) === String(selectedPatientId)) || null;
  const isCaregiver = effectiveMode === "CAREGIVER" || effectiveMode === "GUARDIAN";
  const activePatientLabel = isCaregiver
    ? selectedLink?.patient_name || (selectedPatientId ? `환자 #${selectedPatientId}` : "복약자 선택")
    : meState.data?.name || "내 프로필";
  const selectedGuide = guidesState.data.find((guide) => String(guide.guide_id) === String(selectedGuideId)) || null;
  const selectedDocument = documentsState.data.find((document) => String(document.document_id) === String(selectedDocumentId)) || null;
  const guideStatusMeta = getGuideStatusMeta(guideDetailState.data?.status || selectedGuide?.status);
  const guideSections = normalizeGuideSections(guideDetailState.data);
  const caregiverPoints = normalizeCaregiverPoints(guideDetailState.data);
  const primaryGuideSection = guideSections[0] || null;
  const visibleGuideSections = (primaryGuideSection ? guideSections.slice(1) : guideSections).filter(
    (section) => !isGuideOverviewSection(section),
  );
  const guideBriefing = buildGuideBriefing(guideSections, caregiverPoints);
  const profileBriefing = buildProfileBriefing(profileState.data);
  const medicationSnapshot = buildMedicationSnapshot(medGuideState.data);
  const medicationScheduleBriefing = buildMedicationScheduleBriefing(medGuideState.data);
  const chatSetupHint = resolveChatSetupHint({
    isCaregiver,
    selectedPatientId,
    profileMissing: profileState.missing,
    profileError: profileState.error,
  });

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [chatState.messages, chatState.sending, chatState.open]);

  useEffect(() => {
    setLoginRole(localStorage.getItem("login_role") || "PATIENT");
  }, []);

  useEffect(() => {
    setSelectedGuideId("");
    setSelectedDocumentId("");
    setGuideActionState({ submitting: false, error: null, success: null });
    setChatFeedbackState({});
    setChatState((prev) => ({
      ...prev,
      sessionId: null,
      messages: [],
      error: null,
    }));

    if (!isCaregiver) {
      setSelectedPatientId(meState.data?.patient_id ? String(meState.data.patient_id) : "");
      return;
    }

    const links = linksState.data?.links || [];
    const requestedMatch = links.find((link) => String(link.patient_id) === String(requestedPatientId));
    const firstLink = requestedMatch || links[0];
    setSelectedPatientId(firstLink?.patient_id ? String(firstLink.patient_id) : "");
  }, [isCaregiver, linksState.data, meState.data?.patient_id, requestedPatientId]);

  const loadMe = async () => {
    setMeState({ loading: true, data: null, error: null });
    try {
      const res = await authFetch(`${API_PREFIX}/users/me`);
      if (!res.ok) throw new Error(formatApiError(await safeJson(res)));
      const data = await res.json();
      setMeState({ loading: false, data, error: null });
    } catch (error) {
      setMeState({ loading: false, data: null, error: error?.message || String(error) });
    }
  };

  const loadLinks = async () => {
    if (!isCaregiver) {
      setLinksState({ loading: false, data: null, error: null });
      return;
    }
    setLinksState({ loading: true, data: null, error: null });
    try {
      const res = await authFetch(`${API_PREFIX}/users/links`);
      if (!res.ok) throw new Error(formatApiError(await safeJson(res)));
      const data = await res.json();
      setLinksState({ loading: false, data, error: null });
    } catch (error) {
      setLinksState({ loading: false, data: null, error: error?.message || String(error) });
    }
  };

  const loadProfile = async () => {
    if (isCaregiver && !selectedLink) {
      setProfileState({ loading: false, data: null, error: null, missing: false });
      return;
    }

    setProfileState((prev) => ({ ...prev, loading: true, error: null, missing: false }));
    try {
      const endpoint = isCaregiver
        ? `${API_PREFIX}/users/links/${selectedLink.link_id}/health-profile`
        : `${API_PREFIX}/users/me/health-profile`;
      const res = await authFetch(endpoint);
      if (res.ok) {
        const body = await res.json();
        setProfileState({ loading: false, data: body?.data || null, error: null, missing: false });
        if (!isCaregiver && body?.data?.patient_id) {
          setSelectedPatientId(String(body.data.patient_id));
        } else if (!selectedPatientId && body?.data?.patient_id) {
          setSelectedPatientId(String(body.data.patient_id));
        }
      } else if (res.status === 404) {
        setProfileState({ loading: false, data: null, error: null, missing: true });
      } else {
        throw new Error(formatApiError(await safeJson(res)));
      }
    } catch (error) {
      setProfileState({ loading: false, data: null, error: error?.message || String(error), missing: false });
    }
  };

  const loadDocuments = async () => {
    if (!selectedPatientId) {
      setDocumentsState({ loading: false, data: [], error: null });
      setSelectedDocumentId("");
      return;
    }

    setDocumentsState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const params = new URLSearchParams();
      params.set("document_status", "uploaded");
      if (selectedPatientId) {
        params.set("patient_id", selectedPatientId);
      }
      const res = await authFetch(`${API_PREFIX}/documents?${params.toString()}`);
      if (!res.ok) throw new Error(formatApiError(await safeJson(res)));
      const body = await res.json();
      const items = body?.items || [];
      setDocumentsState({ loading: false, data: items, error: null });

      if (!selectedDocumentId && items.length > 0) {
        setSelectedDocumentId(String(items[0].document_id));
      } else if (selectedDocumentId && !items.some((item) => String(item.document_id) === String(selectedDocumentId))) {
        setSelectedDocumentId(items[0] ? String(items[0].document_id) : "");
      }
    } catch (error) {
      setDocumentsState({ loading: false, data: [], error: error?.message || String(error) });
    }
  };

  const loadMedicationGuide = async () => {
    if (!selectedPatientId) {
      setMedGuideState({ loading: false, data: [], error: null });
      return;
    }

    setMedGuideState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const params = new URLSearchParams();
      params.set("patient_id", selectedPatientId);
      if (selectedDocumentId) {
        params.set("document_id", selectedDocumentId);
      }
      const res = await authFetch(`${API_PREFIX}/documents/medication-guide?${params.toString()}`);
      if (!res.ok) throw new Error(formatApiError(await safeJson(res)));
      const body = await res.json();
      setMedGuideState({ loading: false, data: body?.items || [], error: null });
    } catch (error) {
      setMedGuideState({ loading: false, data: [], error: error?.message || String(error) });
    }
  };

  const loadGuides = async () => {
    if (!selectedPatientId) {
      setGuidesState({ loading: false, data: [], error: null });
      return;
    }

    setGuidesState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const params = new URLSearchParams({ patient_id: selectedPatientId });
      const res = await authFetch(`${API_PREFIX}/guides?${params.toString()}`);
      if (!res.ok) throw new Error(formatApiError(await safeJson(res)));
      const body = await res.json();
      const items = body?.data?.items || [];
      setGuidesState({ loading: false, data: items, error: null });
      setGuideUpdatedAt(new Date().toISOString());

      const latestGuide = items[0] || null;
      if (!selectedGuideId && latestGuide) {
        setSelectedGuideId(String(latestGuide.guide_id));
      } else if (selectedGuideId && !items.some((item) => String(item.guide_id) === String(selectedGuideId))) {
        setSelectedGuideId(latestGuide ? String(latestGuide.guide_id) : "");
      }
    } catch (error) {
      setGuidesState({ loading: false, data: [], error: error?.message || String(error) });
    }
  };

  const loadGuideDetail = async (guideId) => {
    if (!guideId) {
      setGuideDetailState({ loading: false, data: null, error: null });
      return;
    }

    setGuideDetailState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const res = await authFetch(`${API_PREFIX}/guides/${guideId}`);
      if (!res.ok) throw new Error(formatApiError(await safeJson(res)));
      const body = await res.json();
      setGuideDetailState({ loading: false, data: body?.data || null, error: null });
      setGuideUpdatedAt(new Date().toISOString());
    } catch (error) {
      setGuideDetailState({ loading: false, data: null, error: error?.message || String(error) });
    }
  };

  const loadChatMessages = async (sessionId, options = {}) => {
    const { silent = false } = options;
    if (!sessionId) {
      setChatFeedbackState({});
      setChatState((prev) => ({ ...prev, sessionId: null, messages: [] }));
      return false;
    }

    if (!silent) {
      setChatState((prev) => ({ ...prev, loading: true, error: null }));
    }
    try {
      const res = await authFetch(`${API_PREFIX}/chat/sessions/${sessionId}/messages`);
      if (!res.ok) throw new Error(formatApiError(await safeJson(res)));
      const body = await res.json();
      setChatState((prev) => ({
        ...prev,
        sessionId,
        loading: false,
        error: silent ? prev.error : null,
        messages: body?.data?.items || [],
      }));
      if (!silent) {
        setChatFeedbackState({});
      }
      return true;
    } catch (error) {
      setChatState((prev) => ({
        ...prev,
        loading: false,
        error: error?.message || String(error),
        messages: [],
        sessionId: null,
      }));
      return false;
    }
  };

  const ensurePatientContextForChat = async () => {
    if (selectedPatientId || isCaregiver) {
      return selectedPatientId;
    }

    if (profileState.data?.patient_id) {
      const patientId = String(profileState.data.patient_id);
      setSelectedPatientId(patientId);
      return patientId;
    }

    const profileRes = await authFetch(`${API_PREFIX}/users/me/health-profile`);
    if (profileRes.ok) {
      const profileBody = await profileRes.json();
      const patientId = String(profileBody?.data?.patient_id || "");
      if (patientId) {
        setProfileState({ loading: false, data: profileBody?.data || null, error: null, missing: false });
        setSelectedPatientId(patientId);
        return patientId;
      }
    }

    const createRes = await authFetch(`${API_PREFIX}/users/me/health-profile`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    if (!createRes.ok) {
      throw new Error("상담을 시작할 환자 정보를 준비하지 못했습니다. 건강 프로필 페이지에서 먼저 확인해 주세요.");
    }

    const createBody = await createRes.json();
    const patientId = String(createBody?.data?.patient_id || "");
    if (!patientId) {
      throw new Error("상담 대상 정보를 확인하지 못했습니다. 건강 프로필을 한 번 확인해 주세요.");
    }

    setProfileState({ loading: false, data: createBody?.data || null, error: null, missing: false });
    setSelectedPatientId(patientId);
    return patientId;
  };

  const ensureChatSession = async () => {
    let resolvedPatientId = selectedPatientId;
    if (!resolvedPatientId && !isCaregiver) {
      resolvedPatientId = await ensurePatientContextForChat();
    }

    if (!resolvedPatientId) {
      throw new Error("먼저 환자를 선택해 주세요.");
    }

    if (chatState.sessionId) {
      return chatState.sessionId;
    }

    const storageKey = getChatStorageKey(effectiveMode, resolvedPatientId);
    const savedSessionId = typeof window !== "undefined" ? window.localStorage.getItem(storageKey) : null;
    if (savedSessionId) {
      const loaded = await loadChatMessages(savedSessionId);
      if (loaded) {
        return savedSessionId;
      }
      if (typeof window !== "undefined") {
        window.localStorage.removeItem(storageKey);
      }
    }

    const res = await authFetch(`${API_PREFIX}/chat/sessions`, {
      method: "POST",
      body: JSON.stringify({
        patient_id: Number(resolvedPatientId),
        mode: isCaregiver ? "caregiver" : "general",
      }),
    });
    if (!res.ok) {
      throw new Error(formatApiError(await safeJson(res)));
    }
    const body = await res.json();
    const sessionId = String(body?.data?.session_id || "");
    if (!sessionId) {
      throw new Error("채팅 세션을 생성하지 못했습니다.");
    }
    if (typeof window !== "undefined") {
      window.localStorage.setItem(storageKey, sessionId);
    }
    setChatFeedbackState({});
    setChatState((prev) => ({ ...prev, sessionId, messages: [] }));
    return sessionId;
  };

  const openChatPanel = async () => {
    setChatState((prev) => ({ ...prev, open: true, error: null }));
    try {
      await ensureChatSession();
    } catch (error) {
      const rawMessage = error?.message || String(error);
      const friendlyMessage =
        rawMessage === "먼저 환자를 선택해 주세요."
          ? chatSetupHint?.description || "상담 대상 정보가 아직 연결되지 않아 채팅을 시작할 수 없습니다."
          : rawMessage;
      setChatState((prev) => ({ ...prev, error: friendlyMessage }));
    }
  };

  const closeChatPanel = () => {
    setChatState((prev) => ({ ...prev, open: false }));
  };

  const sendChatMessage = async () => {
    if (!chatInput.trim() || chatState.sending) return;

    const content = chatInput.trim();
    const tempKey = Date.now();
    const optimisticUserMessage = {
      message_id: `temp-user-${tempKey}`,
      role: "user",
      content,
      status: "completed",
      created_at: new Date().toISOString(),
    };

    setChatState((prev) => ({
      ...prev,
      sending: true,
      error: null,
      messages: [...prev.messages, optimisticUserMessage],
    }));
    try {
      const sessionId = await ensureChatSession();
      setChatInput("");
      const res = await authFetch(`${API_PREFIX}/chat/sessions/${sessionId}/messages`, {
        method: "POST",
        body: JSON.stringify({ content }),
      });
      if (!res.ok) throw new Error(formatApiError(await safeJson(res)));
      const body = await res.json();
      const userMessage = body?.data?.user_message;
      const assistantMessage = body?.data?.assistant_message;
      setChatState((prev) => ({
        ...prev,
        sending: false,
        sessionId,
        messages: prev.messages.flatMap((message) => {
          if (message.message_id === optimisticUserMessage.message_id) {
            return [userMessage || message];
          }
          return [message];
        }).concat(assistantMessage ? [assistantMessage] : []),
      }));
    } catch (error) {
      setChatState((prev) => ({
        ...prev,
        sending: false,
        error: error?.message || String(error),
        messages: prev.messages,
      }));
    }
  };

  useEffect(() => {
    if (!chatState.open || !chatState.sessionId || !hasPendingAssistantMessages(chatState.messages)) return undefined;

    const timer = window.setInterval(() => {
      loadChatMessages(chatState.sessionId, { silent: true });
    }, 2000);

    return () => window.clearInterval(timer);
  }, [chatState.open, chatState.sessionId, chatState.messages]);

  const updateFeedbackState = (messageId, updater) => {
    setChatFeedbackState((prev) => {
      const current = prev[messageId] || {
        helpful: null,
        expanded: false,
        feedbackType: "",
        comment: "",
        submitting: false,
        success: false,
        error: null,
      };
      return {
        ...prev,
        [messageId]: typeof updater === "function" ? updater(current) : { ...current, ...updater },
      };
    });
  };

  const submitChatFeedback = async (messageId, draftState = null) => {
    if (!chatState.sessionId) return;
    const current = draftState || chatFeedbackState[messageId];
    if (!current || typeof current.helpful !== "boolean") return;
    if (current.helpful === false && !current.feedbackType) {
      updateFeedbackState(messageId, { error: "어떤 점이 아쉬웠는지 한 가지 선택해 주세요." });
      return;
    }

    updateFeedbackState(messageId, { submitting: true, error: null });
    try {
      const res = await authFetch(`${API_PREFIX}/chat/sessions/${chatState.sessionId}/feedback`, {
        method: "POST",
        body: JSON.stringify({
          assistant_message_id: Number(messageId),
          helpful: current.helpful,
          feedback_type: current.helpful ? null : current.feedbackType || null,
          comment: current.comment?.trim() || null,
        }),
      });
      if (!res.ok) throw new Error(formatApiError(await safeJson(res)));
      updateFeedbackState(messageId, (prev) => ({
        ...prev,
        submitting: false,
        success: true,
        expanded: false,
        error: null,
      }));
    } catch (error) {
      updateFeedbackState(messageId, {
        submitting: false,
        error: error?.message || String(error),
      });
    }
  };

  const handleFeedbackVote = (messageId, helpful) => {
    const nextState = {
      ...(chatFeedbackState[messageId] || {
        helpful: null,
        expanded: false,
        feedbackType: "",
        comment: "",
        submitting: false,
        success: false,
        error: null,
      }),
      helpful,
      expanded: helpful ? false : true,
      success: false,
      error: null,
      feedbackType: helpful ? "" : chatFeedbackState[messageId]?.feedbackType || "",
      comment: helpful ? "" : chatFeedbackState[messageId]?.comment || "",
    };
    updateFeedbackState(messageId, nextState);
    if (helpful) {
      submitChatFeedback(messageId, nextState);
    }
  };

  const handleGenerateGuide = async () => {
    if (!selectedDocumentId) {
      setGuideActionState({ submitting: false, error: "먼저 문서를 선택해 주세요.", success: null });
      return;
    }

    setGuideActionState({ submitting: true, error: null, success: null });
    try {
      const res = await authFetch(`${API_PREFIX}/guides/generate`, {
        method: "POST",
        body: JSON.stringify({ document_id: Number(selectedDocumentId) }),
      });
      if (!res.ok) throw new Error(formatApiError(await safeJson(res)));
      const body = await res.json();
      const guideId = body?.data?.guide_id;
      setGuideActionState({ submitting: false, error: null, success: "가이드 생성을 요청했습니다." });
      if (guideId) {
        setSelectedGuideId(String(guideId));
      }
      await loadGuides();
      if (guideId) {
        await loadGuideDetail(guideId);
      }
    } catch (error) {
      setGuideActionState({ submitting: false, error: error?.message || String(error), success: null });
    }
  };

  const handleRegenerateGuide = async () => {
    if (!selectedGuideId) return;
    setGuideActionState({ submitting: true, error: null, success: null });
    try {
      const res = await authFetch(`${API_PREFIX}/guides/${selectedGuideId}/regenerate`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(formatApiError(await safeJson(res)));
      const body = await res.json();
      const guideId = body?.data?.guide_id;
      setGuideActionState({ submitting: false, error: null, success: "가이드 재생성을 요청했습니다." });
      if (guideId) {
        setSelectedGuideId(String(guideId));
      }
      await loadGuides();
      if (guideId) {
        await loadGuideDetail(guideId);
      }
    } catch (error) {
      setGuideActionState({ submitting: false, error: error?.message || String(error), success: null });
    }
  };

  useEffect(() => {
    if (!accessToken) return;
    loadMe();
    if (isCaregiver) {
      loadLinks();
    } else {
      setLinksState({ loading: false, data: null, error: null });
    }
  }, [accessToken, isCaregiver]);

  useEffect(() => {
    if (isCaregiver) {
      if (!selectedLink && !selectedPatientId) return;
      loadProfile();
    } else {
      loadProfile();
    }
  }, [isCaregiver, selectedPatientId, linksState.data]);

  useEffect(() => {
    if (!accessToken) return;
    loadDocuments();
    loadGuides();
  }, [accessToken, selectedPatientId]);

  useEffect(() => {
    loadMedicationGuide();
  }, [selectedPatientId, selectedDocumentId]);

  useEffect(() => {
    loadGuideDetail(selectedGuideId);
  }, [selectedGuideId]);

  useEffect(() => {
    if (!chatState.open) return;
    if (!selectedPatientId) return;

    const storageKey = getChatStorageKey(effectiveMode, selectedPatientId);
    const savedSessionId = typeof window !== "undefined" ? window.localStorage.getItem(storageKey) : null;
    if (savedSessionId) {
      loadChatMessages(savedSessionId);
    } else {
      setChatState((prev) => ({ ...prev, sessionId: null, messages: [] }));
    }
  }, [chatState.open, selectedPatientId, effectiveMode]);

  useEffect(() => {
    const currentStatus = guideDetailState.data?.status || selectedGuide?.status;
    if (currentStatus !== "GENERATING") return undefined;

    const interval = window.setInterval(() => {
      loadGuides();
      if (selectedGuideId) {
        loadGuideDetail(selectedGuideId);
      }
    }, 4000);

    return () => window.clearInterval(interval);
  }, [guideDetailState.data?.status, selectedGuide?.status, selectedGuideId]);

  if (!accessToken) {
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
    return null;
  }

  return (
    <div style={pageStyle}>
      <AppLayout
        activeKey="ai"
        title="AI 가이드"
        description="복약 문서와 건강 정보를 바탕으로 맞춤 가이드를 확인하고 AI 상담을 이어갈 수 있습니다."
        loginRole={loginRole}
        userName={userName}
        modeOptions={modeOptions}
        currentMode={currentMode}
        onModeChange={onModeChange}
      >
        <div style={{ ...mainCardStyle, padding: "28px 30px 30px 30px" }}>

            <div style={heroBannerStyle}>
              <div className="row g-4 align-items-center">
                <div className="col-lg-8">
                  <div
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "10px",
                      padding: "8px 14px",
                      borderRadius: "999px",
                      background: "rgba(255,255,255,0.12)",
                      border: "1px solid rgba(255,255,255,0.16)",
                      color: "rgba(255,255,255,0.88)",
                      fontSize: "0.88rem",
                      fontWeight: 600,
                      marginBottom: "18px",
                    }}
                  >
                    <span style={{ opacity: 0.82 }}>선택 환자</span>
                    <span style={{ width: "4px", height: "4px", borderRadius: "999px", background: "rgba(255,255,255,0.72)" }} />
                    <span style={{ color: "#ffffff", fontWeight: 700 }}>
                      {selectedPatientId ? activePatientLabel : "미선택"}
                    </span>
                  </div>
                  <h2 className="mb-2" style={{ fontWeight: 800, letterSpacing: "-0.03em" }}>
                    {selectedPatientId ? `${activePatientLabel}님의 맞춤 복약 가이드` : "가이드를 확인할 환자를 선택해 주세요"}
                  </h2>
                  <div className="text-white-50" style={{ lineHeight: 1.75, maxWidth: "680px", fontSize: "0.98rem" }}>
                    {selectedPatientId
                      ? "문서, 건강정보, 복약 일정을 함께 확인하고 필요한 안내를 바로 살펴볼 수 있습니다."
                      : isCaregiver
                        ? "연동된 복약자를 선택하면 가이드와 상담 화면이 함께 활성화됩니다."
                        : "건강프로필이나 문서가 연결되면 맞춤 가이드가 준비됩니다."}
                  </div>
                </div>
                <div className="col-lg-4">
                  <div
                      style={{
                        borderRadius: "18px",
                        background: "rgba(255,255,255,0.12)",
                        border: "1px solid rgba(255,255,255,0.18)",
                        padding: "20px",
                      }}
                  >
                    <div className="small text-white-50 mb-2">건강 프로필 요약</div>
                    <div className="fw-semibold">{profileState.data ? `BMI ${profileState.data.bmi || "—"}` : "등록 전"}</div>
                    <div className="small text-white-50 mt-2">
                      {profileState.data?.conditions?.length
                        ? `기저 질환 ${profileState.data.conditions.join(", ")}`
                        : "기저 질환 정보 없음"}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="row g-4 mb-4">
              <div className="col-xl-4">
                <div style={{ ...blockCardStyle, padding: "24px", height: "100%" }}>
                  <div className="d-flex justify-content-between align-items-start mb-3">
                    <div>
                      <div className="small text-muted">상담 기준</div>
                      <h4 className="mb-1">선택 환자 정보</h4>
                    </div>
                    <button className="btn btn-outline-secondary btn-sm" onClick={() => { loadLinks(); loadProfile(); }}>
                      새로고침
                    </button>
                  </div>

                  {isCaregiver ? (
                    <>
                      <label className="form-label">연동 환자</label>
                      <select
                        className="form-select mb-3"
                        value={selectedPatientId}
                        onChange={(event) => {
                          setSelectedPatientId(event.target.value);
                          setSelectedGuideId("");
                          setSelectedDocumentId("");
                          setGuideActionState({ submitting: false, error: null, success: null });
                        }}
                      >
                        {(linksState.data?.links || []).length === 0 && <option value="">연동 환자 없음</option>}
                        {(linksState.data?.links || []).map((link) => (
                          <option key={link.link_id} value={link.patient_id}>
                            {link.patient_name || `환자 #${link.patient_id}`}
                          </option>
                        ))}
                      </select>
                      {linksState.error && <div className="alert alert-danger py-2">{linksState.error}</div>}
                    </>
                  ) : (
                    <div className="mb-3">
                      <div className="small text-muted">복약자</div>
                      <div className="fw-semibold">{meState.data?.name || "본인"}</div>
                    </div>
                  )}

                  <div className="row g-3">
                    <div className="col-6">
                      <MetricTile label="문서 수" value={<span className="fs-4 fw-semibold">{documentsState.data.length}</span>} />
                    </div>
                    <div className="col-6">
                      <MetricTile label="가이드 수" value={<span className="fs-4 fw-semibold">{guidesState.data.length}</span>} />
                    </div>
                    <div className="col-6">
                      <MetricTile
                        label="수면"
                        value={profileState.data?.avg_sleep_hours_per_day ? `${profileState.data.avg_sleep_hours_per_day}시간` : "—"}
                      />
                    </div>
                    <div className="col-6">
                      <MetricTile
                        label="운동"
                        value={profileState.data?.avg_exercise_minutes_per_day ? `${profileState.data.avg_exercise_minutes_per_day}분` : "—"}
                      />
                    </div>
                  </div>

                  <div className="mt-3 small text-muted" style={{ lineHeight: 1.7 }}>
                    {profileState.error
                      ? `건강 프로필 조회 오류: ${profileState.error}`
                      : profileState.missing
                        ? "건강 프로필이 아직 등록되지 않았습니다."
                        : "환자 기록이 가이드와 상담에 함께 반영됩니다."}
                  </div>
                </div>
              </div>

              <div className="col-xl-8">
                <div style={{ ...blockCardStyle, padding: "24px", height: "100%" }}>
                  <div className="d-flex flex-wrap justify-content-between align-items-start gap-3 mb-3">
                    <div>
                      <div className="small text-muted">가이드 작업</div>
                      <h4 className="mb-1">문서 선택과 가이드 생성</h4>
                    </div>
                    <div className="d-flex gap-2">
                      <button
                        className="btn btn-outline-primary btn-sm"
                        onClick={handleGenerateGuide}
                        disabled={guideActionState.submitting || !selectedDocumentId}
                        style={primaryActionButtonStyle}
                      >
                        {guideActionState.submitting ? "요청 중..." : "가이드 생성"}
                      </button>
                      <button
                        className="btn btn-outline-secondary btn-sm"
                        onClick={handleRegenerateGuide}
                        disabled={guideActionState.submitting || !selectedGuideId}
                      >
                        재생성
                      </button>
                    </div>
                  </div>

                  <div className="row g-3">
                    <div className="col-md-6">
                      <label className="form-label">기존 문서 선택</label>
                      <select
                        className="form-select"
                        value={selectedDocumentId}
                        onChange={(event) => setSelectedDocumentId(event.target.value)}
                      >
                        {documentsState.data.length === 0 && <option value="">선택 가능한 문서 없음</option>}
                        {documentsState.data.map((document) => (
                          <option key={document.document_id} value={document.document_id}>
                            {document.original_filename || `문서 #${document.document_id}`}
                          </option>
                        ))}
                      </select>
                      <div className="small text-muted mt-2">
                        {selectedDocument
                          ? `OCR 상태 ${selectedDocument.ocr_status || "미확인"} · 업로드 ${formatDateTime(selectedDocument.created_at)}`
                          : documentsState.loading
                            ? "문서 목록을 불러오는 중입니다."
                            : documentsState.error || "문서가 없으면 먼저 문서 관리에서 업로드해 주세요."}
                      </div>
                    </div>

                    <div className="col-md-6">
                      <label className="form-label">가이드 버전 선택</label>
                      <select
                        className="form-select"
                        value={selectedGuideId}
                        onChange={(event) => setSelectedGuideId(event.target.value)}
                      >
                        {guidesState.data.length === 0 && <option value="">가이드 없음</option>}
                        {guidesState.data.map((guide) => (
                          <option key={guide.guide_id} value={guide.guide_id}>
                            v{guide.version} · {guide.status} · {formatDateTime(guide.created_at)}
                          </option>
                        ))}
                      </select>
                      <div className="small text-muted mt-2">
                        최신 가이드부터 표시합니다. 생성 중 상태면 자동으로 다시 조회합니다.
                      </div>
                    </div>
                  </div>

                  {guideActionState.error && <div className="alert alert-danger mt-3 mb-0">{guideActionState.error}</div>}
                  {guideActionState.success && <div className="alert alert-success mt-3 mb-0">{guideActionState.success}</div>}
                </div>
              </div>
            </div>

            <div className="row g-4 mb-4">
              <div className="col-12">
                <div style={{ ...blockCardStyle, padding: "24px" }}>
                  <div className="d-flex justify-content-between align-items-center mb-3">
                    <div>
                      <div className="small text-muted">Medication Guide</div>
                      <h4 className="mb-1">복약 안내</h4>
                    </div>
                    <span style={chipStyle}>{medGuideState.data.length}개 약</span>
                  </div>

                  {medGuideState.loading ? (
                    <div className="text-muted">복약 안내를 불러오는 중입니다.</div>
                  ) : medGuideState.error ? (
                    <div className="alert alert-danger mb-0">{medGuideState.error}</div>
                  ) : medGuideState.data.length === 0 ? (
                    <div className="text-muted">확정된 약 정보가 아직 없습니다.</div>
                  ) : (
                    <div className="d-grid gap-3" style={{ maxHeight: "560px", overflowY: "auto", paddingRight: "4px" }}>
                      {medGuideState.data.map((item) => (
                        <div key={item.patient_med_id} style={metricCardStyle}>
                          <div className="d-flex justify-content-between align-items-start gap-3 mb-2">
                            <div>
                              <div className="fw-semibold">{item.display_name}</div>
                              <div className="small text-muted">{item.dosage || "용량 미등록"} · {item.frequency_text || "빈도 미등록"}</div>
                            </div>
                            <span style={chipStyle}>{item.data_source === "ocr_mfds" ? "검증됨" : "OCR 기준"}</span>
                          </div>
                          <div style={scrollPanelStyle}>
                            <div className="small text-muted mb-2" style={guideBodyStyle}>
                              {item.efficacy_summary || "효능 요약 정보가 없습니다."}
                            </div>
                            <div className="small mb-2">
                              <strong>복용 방법</strong>
                              <ul className="mb-0 mt-1 ps-3" style={guideBodyStyle}>
                                {(normalizeMedicationLines(item.dosage_instructions).length > 0
                                  ? normalizeMedicationLines(item.dosage_instructions)
                                  : ["등록된 복용 방법이 없습니다."])
                                  .map((line, index) => <li key={index}>{line}</li>)}
                              </ul>
                            </div>
                            <div className="small">
                              <strong>주의사항</strong>
                              <ul className="mb-0 mt-1 ps-3" style={guideBodyStyle}>
                                {(normalizeMedicationLines(item.precautions).length > 0
                                  ? normalizeMedicationLines(item.precautions)
                                  : ["등록된 주의사항이 없습니다."])
                                  .map((line, index) => <li key={index}>{line}</li>)}
                              </ul>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="col-12">
                <div style={{ ...blockCardStyle, padding: "24px", maxHeight: "820px", overflowY: "auto" }}>
                  <div className="d-flex justify-content-between align-items-center gap-3 mb-3">
                    <div>
                      <div className="small text-muted">Guide Detail</div>
                      <h4 className="mb-1">생활 습관 가이드</h4>
                      <div className="small text-muted">
                        마지막 확인 {guideUpdatedAt ? formatDateTime(guideUpdatedAt) : "—"}
                      </div>
                    </div>
                    <div className="d-flex align-items-center gap-2">
                      <button
                        className="btn btn-outline-secondary btn-sm"
                        onClick={() => {
                          loadGuides();
                          if (selectedGuideId) {
                            loadGuideDetail(selectedGuideId);
                          }
                        }}
                      >
                        상태 확인
                      </button>
                      <span
                        style={{
                          ...chipStyle,
                          background: guideStatusMeta.bg,
                          color: guideStatusMeta.color,
                          borderColor: "transparent",
                        }}
                      >
                        {guideStatusMeta.label}
                      </span>
                    </div>
                  </div>

                  {guideDetailState.loading ? (
                    <div className="text-muted">가이드 상세를 불러오는 중입니다.</div>
                  ) : guideDetailState.error ? (
                    <div className="alert alert-danger">{guideDetailState.error}</div>
                  ) : !guideDetailState.data ? (
                    <div className="text-muted">
                      아직 선택된 가이드가 없습니다. 문서를 선택한 뒤 가이드를 생성해 주세요.
                    </div>
                  ) : (
                    <>
                      {guideDetailState.data.status === "GENERATING" && (
                        <div className="alert alert-info">
                          가이드 재생성 요청이 접수되었습니다. 4초마다 자동으로 상태를 확인하고 있으며, 필요하면 `상태 확인` 버튼으로 즉시 갱신할 수 있습니다.
                        </div>
                      )}
                      {guideDetailState.data.status === "FAILED" && (
                        <div className="alert alert-warning">
                          가이드 생성이 완료되지 않았습니다. 문서 상태와 확정 약 정보를 확인한 뒤 다시 생성해 주세요.
                        </div>
                      )}
                      <div
                        style={{
                          borderRadius: "18px",
                          border: "1px solid var(--app-surface-border)",
                          padding: "18px",
                          background: "var(--app-surface-subtle)",
                          marginBottom: "18px",
                        }}
                      >
                        <div className="fw-semibold mb-2">
                          {guideDetailState.data.content_json?.summary
                            || primaryGuideSection?.title
                            || "가이드 요약"}
                        </div>
                        <div className="small text-muted">
                          가이드 v{guideDetailState.data.version || 1} · 마지막 업데이트 {formatDateTime(guideDetailState.data.updated_at)}
                        </div>
                        {primaryGuideSection?.body && (
                          <div className="small text-muted mt-3" style={guideBodyStyle}>
                            {primaryGuideSection.body}
                          </div>
                        )}
                      </div>

                      <div className="row g-3 mb-3">
                        <div className="col-md-6">
                          <BriefingCard title="확인 포인트" lines={guideBriefing.warning} emptyText="먼저 확인할 포인트가 아직 없습니다." />
                        </div>
                        <div className="col-md-6">
                          <BriefingCard
                            title="복약 스케줄"
                            lines={medicationScheduleBriefing.length > 0 ? medicationScheduleBriefing : medicationSnapshot}
                            emptyText="확정된 약 정보가 준비되면 복약 일정이 여기에 표시됩니다."
                          />
                        </div>
                        <div className="col-md-6">
                          <BriefingCard title="생활 관리" lines={guideBriefing.lifestyle} emptyText="생활 관리 안내가 아직 없습니다." />
                        </div>
                        <div className="col-md-6">
                          <BriefingCard title="건강 프로필 요약" lines={profileBriefing} emptyText="건강 프로필 요약이 아직 없습니다." />
                        </div>
                      </div>

                      {visibleGuideSections.length > 0 ? (
                        <div className="d-grid gap-3">
                          {visibleGuideSections.map((section) => (
                            <div
                              key={section.id}
                              style={{
                                ...metricCardStyle,
                                padding: "18px 20px",
                              }}
                            >
                              <div className="fw-semibold mb-2">{section.title}</div>
                              <div style={scrollPanelStyle}>
                                {section.body && (
                                  <div className="small text-muted mb-3" style={guideBodyStyle}>
                                    {section.body}
                                  </div>
                                )}
                                {section.bullets.length > 0 && (
                                  <ul className="mb-0 ps-3 small" style={{ ...guideBodyStyle, lineHeight: 1.8 }}>
                                    {section.bullets.map((line, index) => (
                                      <li key={index} style={{ marginBottom: "6px" }}>{line}</li>
                                    ))}
                                  </ul>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="small text-muted mb-3">가이드 본문이 아직 생성되지 않았습니다.</div>
                      )}

                      {caregiverPoints.length > 0 && (
                        <div className="mt-4">
                          <div className="fw-semibold mb-2">보호자 체크포인트</div>
                          <div className="d-flex flex-wrap gap-2">
                            {caregiverPoints.map((point, index) => (
                              <span key={index} style={chipStyle}>{point}</span>
                            ))}
                          </div>
                        </div>
                      )}

                      {guideDetailState.data.disclaimer && (
                        <div className="small text-muted mt-4">{guideDetailState.data.disclaimer}</div>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>

            <div className="row g-4">
              <div className="col-lg-8">
                <div
                  style={{
                    ...blockCardStyle,
                    padding: "26px",
                    background: "var(--app-surface-bg)",
                    border: "1px solid var(--app-surface-border)",
                    height: "100%",
                  }}
                >
                  <div className="mb-4">
                    <div>
                      <div className="small text-muted">AI 상담</div>
                      <h4 className="mb-2" style={{ fontWeight: 800, color: "var(--app-text-strong)" }}>약속이와 대화하기</h4>
                      <div style={{ color: "var(--app-text-muted)", lineHeight: 1.75, maxWidth: "620px" }}>
                        선택한 환자 기록을 바탕으로 가이드와 복약 정보를 함께 보며 상담할 수 있습니다.
                      </div>
                    </div>
                  </div>

                  <div className="row g-3 align-items-stretch">
                    <div className="col-md-8">
                      <div
                        style={{
                          borderRadius: "20px",
                          background: "var(--app-surface-bg)",
                          border: "1px solid var(--app-surface-border)",
                          padding: "18px",
                          height: "100%",
                          display: "flex",
                          flexDirection: "column",
                          justifyContent: "center",
                        }}
                      >
                        <div className="small text-muted mb-4" style={{ lineHeight: 1.8, fontSize: "0.95rem" }}>
                          자주 묻는 질문으로 상담을 시작해보세요.
                        </div>
                        <div className="d-flex flex-wrap gap-2">
                          <button
                            className="btn btn-outline-secondary"
                            style={{ fontSize: "0.95rem", padding: "10px 14px" }}
                            onClick={() => { setChatInput("복용할 때 주의할 점이 뭐야"); openChatPanel(); }}
                          >
                            주의사항 질문
                          </button>
                          <button
                            className="btn btn-outline-secondary"
                            style={{ fontSize: "0.95rem", padding: "10px 14px" }}
                            onClick={() => { setChatInput("이 약은 어떤 약이야?"); openChatPanel(); }}
                          >
                            약 설명 질문
                          </button>
                          <button
                            className="btn btn-outline-secondary"
                            style={{ fontSize: "0.95rem", padding: "10px 14px" }}
                            onClick={() => { setChatInput("생활 습관에서 조심할 점을 알려줘"); openChatPanel(); }}
                          >
                            생활 습관 질문
                          </button>
                        </div>
                      </div>
                    </div>
                    <div className="col-md-4">
                      <button
                        type="button"
                        onClick={openChatPanel}
                        style={{
                          width: "100%",
                          height: "100%",
                          border: "1px solid var(--app-surface-border)",
                          background: "var(--app-surface-subtle)",
                          borderRadius: "20px",
                          cursor: "pointer",
                          textAlign: "center",
                          display: "flex",
                          flexDirection: "column",
                          justifyContent: "center",
                          alignItems: "center",
                          gap: "8px",
                          padding: "18px",
                        }}
                      >
                        <img src={`${import.meta.env.BASE_URL}mascot.png`} alt="약속이 챗봇 열기" style={{ width: "84px", height: "auto" }} />
                        <div className="fw-semibold" style={{ color: "var(--app-brand-color)" }}>약속이 AI 상담</div>
                        <div className="small text-muted text-center">가이드 내용을 이어서 질문하고 답변을 확인하세요.</div>
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              <div className="col-lg-4">
                <div style={{ ...blockCardStyle, padding: "24px", height: "100%" }}>
                  <div className="small text-muted">진행 상태</div>
                  <h4 className="mb-3">현재 체크포인트</h4>
                  <div className="d-grid gap-3">
                    <div style={metricCardStyle}>
                      <div className="small text-muted mb-1">가이드 상태</div>
                      <div className="fw-semibold">{guideStatusMeta.label}</div>
                    </div>
                    <div style={metricCardStyle}>
                      <div className="small text-muted mb-1">문서 연결</div>
                      <div className="fw-semibold">{selectedDocument ? selectedDocument.original_filename || `문서 #${selectedDocument.document_id}` : "문서 미선택"}</div>
                    </div>
                    <div style={metricCardStyle}>
                      <div className="small text-muted mb-1">챗 세션</div>
                      <div className="fw-semibold">{chatState.sessionId ? `상담 세션 #${chatState.sessionId}` : "아직 생성 전"}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
      </AppLayout>

      {/* Louis수정(기능추가): 로고 및 플로팅 버튼으로 열 수 있는 우측 슬라이드 챗봇 패널 */}
      <button
        type="button"
        onClick={openChatPanel}
        style={{
          position: "fixed",
          right: "calc(28px + (100vw - 100%))",
          bottom: "28px",
          width: "78px",
          height: "78px",
          borderRadius: "999px",
          border: "1px solid var(--app-surface-border)",
          background: "var(--app-surface-subtle)",
          boxShadow: "0 16px 30px rgba(37, 99, 235, 0.18)",
          cursor: "pointer",
          zIndex: 1050,
        }}
      >
        <img src={`${import.meta.env.BASE_URL}mascot.png`} alt="약속이 열기" style={{ width: "48px", height: "48px" }} />
      </button>

      {chatState.open && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(9, 19, 31, 0.24)",
            zIndex: 1055,
          }}
          onClick={closeChatPanel}
        >
          <div
            onClick={(event) => event.stopPropagation()}
            style={{
              position: "absolute",
              top: 0,
              right: 0,
              width: "min(620px, 100vw)",
              height: "100vh",
              background: "var(--app-surface-bg)",
              boxShadow: "-16px 0 40px rgba(37, 99, 235, 0.18)",
              display: "flex",
              flexDirection: "column",
            }}
          >
            <div
              style={{
                padding: "22px 22px 18px 22px",
                borderBottom: "1px solid var(--app-surface-border)",
                background: "var(--app-surface-subtle)",
              }}
            >
              <div className="d-flex justify-content-between align-items-start gap-3">
                <div className="d-flex gap-3">
                  <img src={`${import.meta.env.BASE_URL}mascot.png`} alt="약속이" style={{ width: "56px", height: "56px" }} />
                  <div>
                    <div className="small text-muted">AI 상담</div>
                    <div className="fw-semibold fs-5">약속이와 대화하기</div>
                    <div className="small text-muted mt-1">
                      {isCaregiver ? "연동 환자 기준 상담" : "현재 복약 기록 기준 상담"}
                    </div>
                  </div>
                </div>
                <button className="btn btn-outline-secondary btn-sm" onClick={closeChatPanel}>
                  닫기
                </button>
              </div>
              {isCaregiver && patientOptions.length > 0 && (
                <div
                  className="mt-3"
                  style={{
                    borderRadius: "16px",
                    border: "1px solid var(--app-surface-border)",
                    background: "var(--app-surface-bg)",
                    padding: "12px 14px",
                  }}
                >
                  <label className="form-label small text-muted mb-2">상담 대상</label>
                  <select
                    className="form-select form-select-sm"
                    value={selectedPatientId}
                    onChange={(event) => {
                      setSelectedPatientId(event.target.value);
                      setSelectedGuideId("");
                      setSelectedDocumentId("");
                      setGuideActionState({ submitting: false, error: null, success: null });
                    }}
                  >
                    {patientOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            <div
              ref={chatContainerRef}
              style={{
                flex: 1,
                overflowY: "auto",
                padding: "24px",
                background: "var(--app-body-bg)",
              }}
            >
              {chatState.messages.length === 0 ? (
                <div
                  style={{
                    height: "100%",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    textAlign: "center",
                    color: "var(--app-text-muted)",
                    gap: "12px",
                  }}
                >
                  <img src={`${import.meta.env.BASE_URL}mascot.png`} alt="약속이" style={{ width: "88px", height: "88px" }} />
                  <div className="fw-semibold">{chatSetupHint?.title || "안녕하세요, 약속이예요."}</div>
                  <div className="small" style={{ maxWidth: "360px", lineHeight: 1.75 }}>
                    {chatSetupHint?.description || "약 설명, 복약 일정, 가이드 내용, 생활 관리 포인트를 이어서 물어보세요."}
                  </div>
                  {chatSetupHint?.ctaLabel && (
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      style={primaryActionButtonStyle}
                      onClick={() => {
                        window.location.href = "/app/profile";
                      }}
                    >
                      {chatSetupHint.ctaLabel}
                    </button>
                  )}
                </div>
              ) : (
                <div className="d-grid gap-3">
                  {(() => {
                    let assistantOrder = 0;
                    return chatState.messages.map((message) => {
                    const isAssistant = message.role === "assistant";
                    if (isAssistant) assistantOrder += 1;
                    const shouldShowFeedback =
                      isAssistant &&
                      String(message.content || "").trim().length >= 1;
                    const feedback = chatFeedbackState[message.message_id] || {
                      helpful: null,
                      expanded: false,
                      feedbackType: "",
                      comment: "",
                      submitting: false,
                      success: false,
                      error: null,
                    };

                    return (
                      <div
                        key={message.message_id || `${message.role}-${message.created_at}-${message.content.slice(0, 12)}`}
                        style={{
                          display: "flex",
                          justifyContent: message.role === "user" ? "flex-end" : "flex-start",
                        }}
                      >
                        <div
                          style={{
                            maxWidth: "90%",
                            borderRadius: "20px",
                            padding: "16px 18px",
                            background: message.role === "user" ? "#1f6fb2" : "var(--app-surface-bg)",
                            color: message.role === "user" ? "#ffffff" : "var(--app-text-color)",
                            border: message.role === "user" ? "none" : "1px solid var(--app-surface-border)",
                            boxShadow: "0 8px 18px rgba(15, 23, 42, 0.06)",
                            whiteSpace: "pre-wrap",
                            lineHeight: 1.8,
                            fontSize: "0.98rem",
                          }}
                        >
                          {isPendingAssistantMessage(message) ? (
                            <div className="chat-typing-bubble" aria-live="polite" aria-label="AI가 응답을 준비하고 있습니다.">
                              <span className="chat-typing-label">답변 준비 중</span>
                              <span className="chat-typing-dots" aria-hidden="true">
                                <span />
                                <span />
                                <span />
                              </span>
                            </div>
                          ) : (
                            <div>{renderChatContent(message.content)}</div>
                          )}
                          {message.status === "failed" && (
                            <div className="small mt-3" style={{ color: "#c0392b", lineHeight: 1.7 }}>
                              {message.error_message || "답변 생성 중 오류가 발생했습니다."}
                            </div>
                          )}
                          {message.emergency_message && (
                            <div className="small mt-3" style={{ color: message.role === "user" ? "#dfeeff" : "#c0392b", lineHeight: 1.7 }}>
                              {message.emergency_message}
                            </div>
                          )}
                          {message.disclaimer && (
                            <div className="small mt-3" style={{ color: message.role === "user" ? "#dfeeff" : "var(--app-text-muted)", lineHeight: 1.7 }}>
                              {message.disclaimer}
                            </div>
                          )}
                          {shouldShowFeedback && (
                            <div
                              className="mt-3"
                              style={{
                                borderTop: "1px solid var(--app-surface-border)",
                                paddingTop: "12px",
                              }}
                            >
                              <div
                                className="d-flex flex-wrap align-items-center gap-2"
                                style={{ marginBottom: feedback.expanded || feedback.success || feedback.error ? "10px" : 0 }}
                              >
                                <span className="small" style={{ color: "var(--app-text-muted)", fontWeight: 600, marginRight: "2px" }}>
                                  답변이 어떠셨나요?
                                </span>
                                <button
                                  type="button"
                                  className="btn btn-sm"
                                  onClick={() => handleFeedbackVote(message.message_id, true)}
                                  disabled={feedback.submitting}
                                  style={{
                                    ...feedbackBaseButtonStyle,
                                    ...(feedback.helpful === true ? feedbackSelectedButtonStyle : {}),
                                  }}
                                >
                                  🙂 만족했어요
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-sm"
                                  onClick={() => handleFeedbackVote(message.message_id, false)}
                                  disabled={feedback.submitting}
                                  style={{
                                    ...feedbackBaseButtonStyle,
                                    ...(feedback.helpful === false ? feedbackNegativeButtonStyle : {}),
                                  }}
                                >
                                  🙁 아쉬워요
                                </button>
                                {feedback.success && (
                                  <span
                                    className="small"
                                    style={{
                                      color: feedback.helpful ? "#256c3d" : "#7c4f16",
                                      background: feedback.helpful ? "#edf9f1" : "#fff6e8",
                                      border: `1px solid ${feedback.helpful ? "#c9e8d1" : "#f5ddb3"}`,
                                      borderRadius: "999px",
                                      padding: "6px 10px",
                                      lineHeight: 1,
                                      fontWeight: 600,
                                    }}
                                  >
                                    {feedback.helpful ? "만족한 답변으로 기록했어요" : "아쉬운 점을 기록했어요"}
                                  </span>
                                )}
                              </div>

                              {feedback.expanded && (
                                <div
                                  style={{
                                    borderRadius: "16px",
                                    background: "var(--app-surface-subtle)",
                                    border: "1px solid var(--app-surface-border)",
                                    padding: "14px",
                                  }}
                                >
                                  <div className="small mb-2" style={{ color: "var(--app-text-muted)", fontWeight: 600 }}>
                                    어떤 점이 아쉬웠나요?
                                  </div>
                                  <div className="d-flex flex-wrap gap-2 mb-3">
                                    {chatFeedbackReasons.map((reason) => (
                                      <button
                                        key={reason.value}
                                        type="button"
                                        className="btn btn-sm"
                                        onClick={() =>
                                          updateFeedbackState(message.message_id, {
                                            feedbackType: reason.value,
                                            error: null,
                                          })
                                        }
                                        disabled={feedback.submitting}
                                        style={{
                                          ...feedbackBaseButtonStyle,
                                          ...(feedback.feedbackType === reason.value ? feedbackSelectedButtonStyle : {}),
                                        }}
                                      >
                                        {reason.label}
                                      </button>
                                    ))}
                                  </div>
                                  <textarea
                                    className="form-control form-control-sm"
                                    rows={2}
                                    placeholder="원하시면 짧게 덧붙여 주세요."
                                    value={feedback.comment}
                                    disabled={feedback.submitting}
                                    onChange={(event) =>
                                      updateFeedbackState(message.message_id, {
                                        comment: event.target.value,
                                        error: null,
                                      })
                                    }
                                    style={{
                                      resize: "none",
                                      borderRadius: "12px",
                                      borderColor: "var(--app-surface-border)",
                                      background: "var(--app-surface-bg)",
                                    }}
                                  />
                                  {feedback.error && (
                                    <div className="small mt-2" style={{ color: "#c24141" }}>
                                      {feedback.error}
                                    </div>
                                  )}
                                  <div className="d-flex justify-content-end gap-2 mt-3">
                                    <button
                                      type="button"
                                      className="btn btn-light btn-sm"
                                      disabled={feedback.submitting}
                                      onClick={() =>
                                        updateFeedbackState(message.message_id, {
                                          expanded: false,
                                          error: null,
                                        })
                                      }
                                    >
                                      닫기
                                    </button>
                                    <button
                                      type="button"
                                      className="btn btn-primary btn-sm"
                                      disabled={feedback.submitting}
                                      style={primaryActionButtonStyle}
                                      onClick={() => submitChatFeedback(message.message_id)}
                                    >
                                      {feedback.submitting ? "저장 중" : "의견 보내기"}
                                    </button>
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })})()}
                </div>
              )}
            </div>

            <div
              style={{
                padding: "18px 20px 20px 20px",
                borderTop: "1px solid var(--app-surface-border)",
                background: "var(--app-surface-bg)",
              }}
            >
              {chatState.error && <div className="alert alert-danger py-2 mb-3">{chatState.error}</div>}
              <div className="d-flex gap-2">
                <textarea
                  className="form-control"
                  rows={3}
                  value={chatInput}
                  onChange={(event) => setChatInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      sendChatMessage();
                    }
                  }}
                  placeholder="예: 메트포르민정 복용 시 주의할 점이 뭐야?"
                  disabled={chatState.sending}
                />
                <button
                  className="btn btn-primary"
                  onClick={sendChatMessage}
                  disabled={chatState.sending || !chatInput.trim()}
                  style={{ minWidth: "96px" }}
                >
                  {chatState.sending ? "전송 중" : "보내기"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AiPage;
