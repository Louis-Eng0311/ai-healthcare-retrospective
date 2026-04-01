import React, { useEffect, useMemo, useRef, useState } from "react";

const BASE_MENU = [
  { key: "home", label: "홈", href: "/app" },
  { key: "documents", label: "처방전 업로드", href: "/app/documents" },
  { key: "ai", label: "AI 가이드", href: "/app/ai" },
  { key: "drug-search", label: "약 검색", href: "/app/drug-search" },
  { key: "caregiver", label: "알림센터", href: "/app/caregiver" },
  { key: "medication-check", label: "복약 체크", href: "/app/medication-check" },
  { key: "schedule", label: "스케줄", href: "/app/schedule" },
  { key: "health", label: "건강 프로필", href: "/app/health-profile" },
];
const API_PREFIX = "/api/v1";
const getChatStorageKey = (role, patientId) => `ai-chat-session:${role || "UNKNOWN"}:${patientId || "unknown"}`;
const isPendingAssistantMessage = (message) =>
  String(message?.role || "").toLowerCase() === "assistant" && ["queued", "processing"].includes(String(message?.status || ""));
const hasPendingAssistantMessages = (messages) => Array.isArray(messages) && messages.some(isPendingAssistantMessage);

const safeJson = async (res) => {
  try {
    return await res.json();
  } catch {
    return null;
  }
};

const formatApiError = (value) => {
  if (!value) return "알 수 없는 오류가 발생했습니다.";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map((item) => item?.msg || JSON.stringify(item)).join(", ");
  if (typeof value === "object") {
    if (value.detail) return formatApiError(value.detail);
    if (value.message) return formatApiError(value.message);
    return JSON.stringify(value);
  }
  return String(value);
};

const extractMePayload = (body) => {
  if (!body || typeof body !== "object") return null;
  if (body.data && typeof body.data === "object") return body.data;
  return body;
};

const handleLogout = async () => {
  try {
    await fetch("/api/v1/auth/logout", {
      method: "POST",
      credentials: "include",
    });
  } catch {
    // 네트워크 오류가 있어도 로컬 인증 정보는 정리
  } finally {
    localStorage.removeItem("access_token");
    localStorage.removeItem("login_role");
    document.cookie = "access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    document.cookie = "refresh_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    window.location.href = "/login";
  }
};

function AppLayout({
  activeKey,
  title,
  description,
  children,
  headerCompact = false,
  loginRole,
  userName,
  modeOptions = [],
  currentMode,
  onModeChange,
}) {
  const normalizeMode = (role) => {
    if (!role) return "PATIENT";
    return role === "GUARDIAN" ? "CAREGIVER" : role;
  };
  const modeLabelMap = {
    PATIENT: "복약자모드",
    CAREGIVER: "보호자모드",
    ADMIN: "관리자모드",
  };
  const resolvedLoginRole = normalizeMode(loginRole || localStorage.getItem("login_role") || "PATIENT");
  const resolvedUserName = userName || "사용자";
  const profileInitial = resolvedUserName?.trim()?.[0] || "U";
  const normalizedModeOptions = (Array.isArray(modeOptions) ? modeOptions : [])
    .map((option) => ({
      value: normalizeMode(option.value),
      label: option.label || modeLabelMap[normalizeMode(option.value)] || `${normalizeMode(option.value)}모드`,
    }))
    .filter((option, index, list) => option.value && list.findIndex((item) => item.value === option.value) === index);
  const effectiveModeOptions =
    normalizedModeOptions.length > 0
      ? normalizedModeOptions
      : [{ value: resolvedLoginRole, label: modeLabelMap[resolvedLoginRole] || `${resolvedLoginRole}모드` }];
  const effectiveCurrentMode = normalizeMode(currentMode || resolvedLoginRole);
  const sidebarModeLabel =
    effectiveModeOptions.find((option) => option.value === effectiveCurrentMode)?.label ||
    modeLabelMap[effectiveCurrentMode] ||
    `${effectiveCurrentMode}모드`;
  const canSwitchMode = typeof onModeChange === "function" && effectiveModeOptions.length > 1;
  const pathname = typeof window !== "undefined" ? window.location.pathname : "";
  const isAiPage = pathname.startsWith("/ai") || pathname.startsWith("/app/ai");
  const isChatMode = effectiveCurrentMode === "PATIENT" || effectiveCurrentMode === "CAREGIVER";
  const hasAccessToken = typeof window !== "undefined" && !!window.localStorage.getItem("access_token");
  const shouldRenderGlobalChat = !isAiPage && isChatMode && hasAccessToken;
  const isCaregiverMode = effectiveCurrentMode === "CAREGIVER";

  const [chatOpen, setChatOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [chatTargetsState, setChatTargetsState] = useState({ loading: false, items: [], error: null });
  const [selectedChatPatientId, setSelectedChatPatientId] = useState("");
  const [chatState, setChatState] = useState({
    loading: false,
    sending: false,
    sessionId: null,
    messages: [],
    error: null,
  });
  const chatContainerRef = useRef(null);

  const refreshAccessToken = async () => {
    const res = await fetch(`${API_PREFIX}/auth/token/refresh`, {
      method: "GET",
      credentials: "include",
    });
    if (!res.ok) return null;
    const body = await safeJson(res);
    const token = body?.access_token;
    if (token && typeof window !== "undefined") {
      window.localStorage.setItem("access_token", token);
    }
    return token || null;
  };

  const authFetch = async (url, options = {}, retryOnUnauthorized = true) => {
    const token = localStorage.getItem("access_token");
    const headers = new Headers(options.headers || {});
    if (options.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    const response = await fetch(url, {
      ...options,
      headers,
      credentials: "include",
    });

    if (response.status === 401 && retryOnUnauthorized) {
      const newToken = await refreshAccessToken();
      if (newToken) {
        headers.set("Authorization", `Bearer ${newToken}`);
        return fetch(url, {
          ...options,
          headers,
          credentials: "include",
        });
      }
    }

    return response;
  };

  const fetchSelfPatientContext = async () => {
    const meRes = await authFetch(`${API_PREFIX}/users/me`);
    if (meRes.ok) {
      const meBody = await meRes.json();
      const payload = extractMePayload(meBody);
      const patientId = String(payload?.patient_id || "");
      if (patientId) {
        return {
          patientId,
          label: payload?.name || resolvedUserName || "본인",
        };
      }
    } else {
      throw new Error(formatApiError(await safeJson(meRes)));
    }
    return { patientId: "", label: resolvedUserName || "본인" };
  };

  const loadChatTargets = async () => {
    if (!shouldRenderGlobalChat) {
      setChatTargetsState({ loading: false, items: [], error: null });
      setSelectedChatPatientId("");
      return { items: [], selectedId: "" };
    }

    setChatTargetsState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      if (isCaregiverMode) {
        const res = await authFetch(`${API_PREFIX}/users/links`);
        if (!res.ok) throw new Error(formatApiError(await safeJson(res)));
        const body = await res.json();
        const items = (body?.links || []).map((link) => ({
          value: String(link.patient_id),
          label: link.patient_name || `복약자 #${link.patient_id}`,
        }));
        const nextSelected =
          selectedChatPatientId && items.some((item) => item.value === selectedChatPatientId)
            ? selectedChatPatientId
            : items[0]?.value || "";
        setChatTargetsState({ loading: false, items, error: null });
        setSelectedChatPatientId(nextSelected);
        return { items, selectedId: nextSelected };
      }

      const meContext = await fetchSelfPatientContext();
      if (meContext.patientId) {
        const items = [{ value: meContext.patientId, label: meContext.label }];
        setChatTargetsState({ loading: false, items, error: null });
        setSelectedChatPatientId(meContext.patientId);
        return { items, selectedId: meContext.patientId };
      }

      const res = await authFetch(`${API_PREFIX}/users/me/health-profile`);
      if (res.status === 404) {
        setChatTargetsState({ loading: false, items: [], error: null });
        setSelectedChatPatientId("");
        return { items: [], selectedId: "" };
      }
      if (!res.ok) throw new Error(formatApiError(await safeJson(res)));
      const body = await res.json();
      const patientId = body?.data?.patient_id ? String(body.data.patient_id) : "";
      const items = patientId
        ? [{ value: patientId, label: resolvedUserName || "본인" }]
        : [];
      setChatTargetsState({ loading: false, items, error: null });
      setSelectedChatPatientId(patientId);
      return { items, selectedId: patientId };
    } catch (error) {
      const message = error?.message || String(error);
      setChatTargetsState({ loading: false, items: [], error: message });
      setSelectedChatPatientId("");
      return { items: [], selectedId: "" };
    }
  };

  const loadChatMessages = async (sessionId, options = {}) => {
    const { silent = false } = options;
    if (!sessionId) {
      setChatState((prev) => ({ ...prev, loading: false, sessionId: null, messages: [] }));
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
        loading: false,
        sessionId,
        messages: body?.data?.items || [],
        error: silent ? prev.error : null,
      }));
      return true;
    } catch (error) {
      setChatState((prev) => ({
        ...prev,
        loading: false,
        sessionId: null,
        messages: [],
        error: error?.message || String(error),
      }));
      return false;
    }
  };

  const ensurePatientContextForGlobalChat = async () => {
    if (selectedChatPatientId || isCaregiverMode) {
      return selectedChatPatientId;
    }

    const meContext = await fetchSelfPatientContext();
    if (meContext.patientId) {
      const items = [{ value: meContext.patientId, label: meContext.label }];
      setChatTargetsState({ loading: false, items, error: null });
      setSelectedChatPatientId(meContext.patientId);
      return meContext.patientId;
    }

    const profileRes = await authFetch(`${API_PREFIX}/users/me/health-profile`);
    if (profileRes.ok) {
      const profileBody = await profileRes.json();
      const patientId = String(profileBody?.data?.patient_id || "");
      if (patientId) {
        const items = [{ value: patientId, label: resolvedUserName || "본인" }];
        setChatTargetsState({ loading: false, items, error: null });
        setSelectedChatPatientId(patientId);
        return patientId;
      }
    } else if (profileRes.status !== 404) {
      throw new Error(formatApiError(await safeJson(profileRes)));
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

    const items = [{ value: patientId, label: resolvedUserName || "본인" }];
    setChatTargetsState({ loading: false, items, error: null });
    setSelectedChatPatientId(patientId);
    return patientId;
  };

  const ensureChatSession = async (patientId = selectedChatPatientId) => {
    let resolvedPatientId = patientId;
    if (!resolvedPatientId && !isCaregiverMode) {
      resolvedPatientId = await ensurePatientContextForGlobalChat();
    }

    if (!resolvedPatientId) {
      throw new Error("상담 대상을 먼저 선택해 주세요.");
    }
    if (chatState.sessionId) {
      return chatState.sessionId;
    }

    const storageKey = getChatStorageKey(effectiveCurrentMode, resolvedPatientId);
    const savedSessionId = localStorage.getItem(storageKey);
    if (savedSessionId) {
      const loaded = await loadChatMessages(savedSessionId);
      if (loaded) {
        return savedSessionId;
      }
      localStorage.removeItem(storageKey);
    }

    const res = await authFetch(`${API_PREFIX}/chat/sessions`, {
      method: "POST",
      body: JSON.stringify({
        patient_id: Number(resolvedPatientId),
        mode: isCaregiverMode ? "caregiver" : "general",
      }),
    });
    if (!res.ok) throw new Error(formatApiError(await safeJson(res)));
    const body = await res.json();
    const sessionId = String(body?.data?.session_id || "");
    if (!sessionId) throw new Error("채팅 세션을 생성하지 못했습니다.");

    localStorage.setItem(storageKey, sessionId);
    setChatState((prev) => ({ ...prev, sessionId, messages: [] }));
    return sessionId;
  };

  const openGlobalChat = async () => {
    setChatOpen(true);
    setChatState((prev) => ({ ...prev, error: null }));

    let patientId = selectedChatPatientId;
    if (!patientId) {
      if (isCaregiverMode) {
        const loaded = await loadChatTargets();
        patientId = loaded.selectedId;
      } else {
        try {
          patientId = await ensurePatientContextForGlobalChat();
        } catch (error) {
          setChatState((prev) => ({
            ...prev,
            error: error?.message || String(error),
          }));
          return;
        }
      }
    }
    if (!patientId) {
      setChatState((prev) => ({
        ...prev,
        error: isCaregiverMode
          ? "연동된 복약자가 없어 상담을 시작할 수 없습니다. 복약자 연결을 먼저 진행해 주세요."
          : "상담 대상 정보를 확인하지 못했습니다. 건강 프로필을 한 번 확인해 주세요.",
      }));
      return;
    }

    try {
      await ensureChatSession(patientId);
    } catch (error) {
      setChatState((prev) => ({ ...prev, error: error?.message || String(error) }));
    }
  };

  const closeGlobalChat = () => {
    setChatOpen(false);
  };

  const sendChatMessage = async () => {
    if (!chatInput.trim() || chatState.sending) return;

    const content = chatInput.trim();
    const tempKey = Date.now();
    const optimisticUserMessage = {
      id: `temp-user-${tempKey}`,
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
      const sessionId = await ensureChatSession(selectedChatPatientId);
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
          if (message.id === optimisticUserMessage.id) {
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
    if (!chatOpen || !chatState.sessionId || !hasPendingAssistantMessages(chatState.messages)) return undefined;

    const timer = window.setInterval(() => {
      loadChatMessages(chatState.sessionId, { silent: true });
    }, 2000);

    return () => window.clearInterval(timer);
  }, [chatOpen, chatState.sessionId, chatState.messages]);

  useEffect(() => {
    if (!shouldRenderGlobalChat) {
      setChatOpen(false);
      return;
    }
    loadChatTargets();
    setChatState((prev) => ({
      ...prev,
      sessionId: null,
      messages: [],
      error: null,
    }));
    setChatInput("");
  }, [shouldRenderGlobalChat, effectiveCurrentMode]);

  useEffect(() => {
    if (!shouldRenderGlobalChat) return;
    setChatState((prev) => ({
      ...prev,
      sessionId: null,
      messages: [],
      error: null,
    }));
  }, [selectedChatPatientId, effectiveCurrentMode, shouldRenderGlobalChat]);

  useEffect(() => {
    if (!shouldRenderGlobalChat || !chatOpen || !selectedChatPatientId) return;
    const storageKey = getChatStorageKey(effectiveCurrentMode, selectedChatPatientId);
    const savedSessionId = localStorage.getItem(storageKey);
    if (savedSessionId) {
      loadChatMessages(savedSessionId);
    } else {
      setChatState((prev) => ({ ...prev, sessionId: null, messages: [] }));
    }
  }, [chatOpen, selectedChatPatientId, effectiveCurrentMode, shouldRenderGlobalChat]);

  useEffect(() => {
    if (!chatOpen || !chatContainerRef.current) return;
    chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
  }, [chatOpen, chatState.messages, chatState.sending]);

  useEffect(() => {
    if (!mobileMenuOpen) return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleResize = () => {
      if (window.innerWidth > 992) {
        setMobileMenuOpen(false);
      }
    };

    window.addEventListener("resize", handleResize);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("resize", handleResize);
    };
  }, [mobileMenuOpen]);

  const menuItems = useMemo(() => {
    if (effectiveCurrentMode === "ADMIN") {
      return [
        ...BASE_MENU,
        { key: "admin-dashboard", label: "관리자 대시보드", href: "/app/dashboard" },
      ];
    }
    return BASE_MENU;
  }, [effectiveCurrentMode]);

  return (
    <div className="doc-layout">
      <div
        className={`doc-sidebar-backdrop ${mobileMenuOpen ? "is-open" : ""}`}
        onClick={() => setMobileMenuOpen(false)}
        aria-hidden={!mobileMenuOpen}
      />
      <aside className={`doc-sidebar ${mobileMenuOpen ? "is-open" : ""}`}>
        <div className="doc-sidebar-top">
          <div className="doc-sidebar-brand">
            <strong>복약관리시스템</strong>
            <div className="text-muted small">{sidebarModeLabel}</div>
          </div>
        </div>

        <div className="doc-sidebar-middle">
          <nav className="doc-sidebar-nav">
            {menuItems.map((item) => (
              <a
                key={item.key}
                className={`doc-sidebar-link ${item.key === activeKey ? "active" : ""}`}
                href={item.href}
                onClick={() => setMobileMenuOpen(false)}
              >
                {item.label}
              </a>
            ))}
          </nav>
        </div>

        <div className="doc-sidebar-bottom">
          <div className="doc-sidebar-footer">
            <a
              className={`doc-sidebar-link ${activeKey === "settings" ? "active" : ""}`}
              href="/app/settings"
              onClick={() => setMobileMenuOpen(false)}
            >
              설정
            </a>
          </div>
        </div>
      </aside>

      <main className="doc-main">
        <header className={`app-page-header ${headerCompact ? "app-page-header-compact" : ""}`}>
          <div className="app-page-heading">
            <button
              className="app-menu-toggle"
              type="button"
              onClick={() => setMobileMenuOpen((prev) => !prev)}
              aria-label={mobileMenuOpen ? "메뉴 닫기" : "메뉴 열기"}
              aria-expanded={mobileMenuOpen}
            >
              <span />
              <span />
              <span />
            </button>
            <h2 className="app-page-title">{title}</h2>
            {description && <p className="app-page-description">{description}</p>}
          </div>
          <div className="app-page-actions">
            <div className="app-selector-group">
              <label className="app-selector-label">현재 모드</label>
              <select
                className="form-select form-select-sm app-patient-select"
                value={effectiveCurrentMode}
                onChange={(event) => onModeChange?.(event.target.value)}
                disabled={!canSwitchMode}
              >
                {effectiveModeOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <a className="app-profile-button" href="/app/profile" title="프로필">
              {profileInitial}
            </a>
            <button className="btn btn-outline-secondary btn-sm app-logout-button" type="button" onClick={handleLogout}>
              로그아웃
            </button>
          </div>
        </header>
        {children}
      </main>

      {shouldRenderGlobalChat && (
        <>
          <button
            type="button"
            onClick={openGlobalChat}
            style={{
              position: "fixed",
              right: "calc(28px + (100vw - 100%))",
              bottom: "28px",
              width: "78px",
              height: "78px",
              borderRadius: "999px",
              border: "1px solid #cfe0fb",
              background: "linear-gradient(135deg, #ffffff 0%, #eaf2ff 100%)",
              boxShadow: "0 16px 30px rgba(37, 99, 235, 0.18)",
              cursor: "pointer",
              zIndex: 1050,
            }}
            aria-label="챗봇 열기"
          >
            <img src={`${import.meta.env.BASE_URL}mascot.png`} alt="약속이 열기" style={{ width: "48px", height: "48px" }} />
          </button>

          {chatOpen && (
            <div
              style={{
                position: "fixed",
                inset: 0,
                background: "rgba(9, 19, 31, 0.24)",
                zIndex: 1055,
              }}
              onClick={closeGlobalChat}
            >
              <div
                onClick={(event) => event.stopPropagation()}
                style={{
                  position: "absolute",
                  top: 0,
                  right: 0,
                  width: "min(560px, 100vw)",
                  height: "100vh",
                  background: "#ffffff",
                  boxShadow: "-16px 0 40px rgba(37, 99, 235, 0.18)",
                  display: "flex",
                  flexDirection: "column",
                }}
              >
                <div
                  style={{
                    padding: "20px 20px 16px",
                    borderBottom: "1px solid #e6edf4",
                    background: "linear-gradient(135deg, #f8fbff 0%, #edf4ff 100%)",
                  }}
                >
                  <div className="d-flex justify-content-between align-items-start gap-3">
                    <div className="d-flex gap-3">
                      <img src={`${import.meta.env.BASE_URL}mascot.png`} alt="약속이" style={{ width: "52px", height: "52px" }} />
                      <div>
                        <div className="small text-muted">AI 상담</div>
                        <div className="fw-semibold fs-5">약속이와 대화하기</div>
                        <div className="small text-muted mt-1">
                          {isCaregiverMode ? "연동 복약자 기준 상담" : "현재 복약 기록 기준 상담"}
                        </div>
                      </div>
                    </div>
                    <button className="btn btn-outline-secondary btn-sm" type="button" onClick={closeGlobalChat}>
                      닫기
                    </button>
                  </div>

                  {isCaregiverMode && (
                    <div
                      className="mt-3"
                      style={{
                        borderRadius: "14px",
                        border: "1px solid #d8e5f6",
                        background: "#ffffff",
                        padding: "10px 12px",
                      }}
                    >
                      <label className="form-label small text-muted mb-2">상담 대상</label>
                      <select
                        className="form-select form-select-sm"
                        value={selectedChatPatientId}
                        onChange={(event) => setSelectedChatPatientId(event.target.value)}
                        disabled={chatTargetsState.loading || chatTargetsState.items.length === 0}
                      >
                        {chatTargetsState.items.length === 0 && <option value="">선택 가능한 복약자 없음</option>}
                        {chatTargetsState.items.map((item) => (
                          <option key={item.value} value={item.value}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                      {chatTargetsState.error && <div className="small text-danger mt-2">{chatTargetsState.error}</div>}
                    </div>
                  )}
                </div>

                <div
                  ref={chatContainerRef}
                  style={{
                    flex: 1,
                    overflowY: "auto",
                    padding: "18px 20px",
                    background: "linear-gradient(180deg, #f9fbff 0%, #ffffff 100%)",
                  }}
                >
                  {chatState.loading ? (
                    <div className="text-muted small">대화 내역을 불러오는 중...</div>
                  ) : chatState.messages.length === 0 ? (
                    <div className="text-muted small">메시지를 보내 상담을 시작해 보세요.</div>
                  ) : (
                    <div className="d-flex flex-column gap-2">
                      {chatState.messages.map((message, index) => {
                        const isAssistant = String(message?.role || "").toLowerCase() === "assistant";
                        return (
                          <div
                            key={`${message?.id || "msg"}-${index}`}
                            style={{
                              alignSelf: isAssistant ? "flex-start" : "flex-end",
                              maxWidth: "86%",
                              borderRadius: "14px",
                              padding: "10px 12px",
                              background: isAssistant ? "#ffffff" : "#2563eb",
                              color: isAssistant ? "#1f2937" : "#ffffff",
                              border: isAssistant ? "1px solid #d9e3f5" : "1px solid #2563eb",
                              whiteSpace: "pre-wrap",
                              wordBreak: "break-word",
                              lineHeight: 1.6,
                              fontSize: "0.94rem",
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
                              message?.content || ""
                            )}
                            {message?.status === "failed" && (
                              <div style={{ color: "#c0392b", marginTop: "8px", fontSize: "0.82rem" }}>
                                {message?.error_message || "답변 생성 중 오류가 발생했습니다."}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                <div style={{ padding: "14px 16px", borderTop: "1px solid #e6edf4", background: "#ffffff" }}>
                  {chatState.error && <div className="alert alert-danger py-2 mb-2">{chatState.error}</div>}
                  <div className="input-group">
                    <input
                      type="text"
                      className="form-control"
                      placeholder="메시지를 입력하세요."
                      value={chatInput}
                      onChange={(event) => setChatInput(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && !event.shiftKey) {
                          event.preventDefault();
                          sendChatMessage();
                        }
                      }}
                      disabled={chatState.sending || !selectedChatPatientId}
                    />
                    <button
                      className="btn btn-primary"
                      type="button"
                      onClick={sendChatMessage}
                      disabled={chatState.sending || !chatInput.trim() || !selectedChatPatientId}
                    >
                      {chatState.sending ? "전송 중" : "보내기"}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default AppLayout;
