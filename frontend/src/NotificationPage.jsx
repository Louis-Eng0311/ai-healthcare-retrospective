import React, { useEffect, useMemo, useState } from "react";
import AppLayout from "./components/AppLayout.jsx";

const API_PREFIX = "/api/v1";
const MAX_NOTIFICATION_CACHE = 100;

const TYPE_META = {
  intake_reminder: { label: "복약 리마인드", bg: "#dbeafe", color: "#2563eb" },
  missed_alert: { label: "미복용 알림", bg: "#ffedd5", color: "#ea580c" },
  hospital_schedule_reminder: { label: "병원 일정 알림", bg: "#e0f2fe", color: "#0369a1" },
  ocr_done: { label: "처방전 업데이트", bg: "#f3e8ff", color: "#a855f7" },
  ocr_failed: { label: "OCR 실패", bg: "#fee2e2", color: "#dc2626" },
  guide_ready: { label: "AI 가이드", bg: "#dcfce7", color: "#16a34a" },
  taken: { label: "복용 완료", bg: "#ccfbf1", color: "#0f766e" },
  default: { label: "알림", bg: "#e5e7eb", color: "#374151" },
};

const REMIND_TEMPLATE = {
  intake_reminder: {
    title: "복약 리마인드",
    message: "복약 시간이에요. 복용 여부를 확인해 주세요.",
  },
  missed_alert: {
    title: "복약 확인 요청",
    message: "아직 복용 기록이 없어요. 복용 여부를 확인해 주세요.",
  },
  ocr_done: {
    title: "처방전 등록 확인",
    message: "처방전 인식이 완료되었어요. 내용을 확인해 주세요.",
  },
  guide_ready: {
    title: "복약 가이드 준비 완료",
    message: "AI 복약 가이드가 준비되었어요. 확인해 주세요.",
  },
};

const NotificationPage = ({
  linkedPatients = [],
  myPatient = null,
  selfPatient = null,
  loginRole = "PATIENT",
  me = null,
  userName = "사용자",
  modeOptions = [],
  currentMode = "PATIENT",
  onModeChange,
}) => {
  const effectiveMode = currentMode || loginRole;
  const isCaregiver = effectiveMode === "CAREGIVER" || effectiveMode === "GUARDIAN";

  const patientsSource = useMemo(() => {
    if (isCaregiver) {
      return (linkedPatients || []).filter((patient) => patient?.id);
    }
    return myPatient ? [myPatient] : [];
  }, [isCaregiver, linkedPatients, myPatient]);

  const normalizedPatients = useMemo(() => {
    return patientsSource.map((patient) => ({
      id: Number(patient.id),
      name: patient.name || patient.display_name || `복약자 ${patient.id}`,
    }));
  }, [patientsSource]);

  const caregiverPatientIdSet = useMemo(
    () =>
      new Set(
        normalizedPatients
          .map((patient) => Number(patient.id))
          .filter((id) => Number.isFinite(id) && id > 0)
      ),
    [normalizedPatients]
  );

  const selfPatientId = useMemo(() => {
    const id = Number(selfPatient?.id);
    return Number.isFinite(id) && id > 0 ? id : null;
  }, [selfPatient?.id]);

  const myPatientId = useMemo(() => {
    const id = Number(myPatient?.id);
    return Number.isFinite(id) && id > 0 ? id : null;
  }, [myPatient?.id]);

  const [notifications, setNotifications] = useState([]);
  const [nextCursor, setNextCursor] = useState(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState(null);

  const [unreadCount, setUnreadCount] = useState(0);

  const [settings, setSettings] = useState({
    intake_reminder: true,
    missed_alert: true,
    hospital_schedule_reminder: true,
    ocr_done: true,
    guide_ready: true,
  });
  const [settingsSubmitting, setSettingsSubmitting] = useState(false);

  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [patientFilter, setPatientFilter] = useState("all");
  const [unreadOnly, setUnreadOnly] = useState(false);

  const [remindForm, setRemindForm] = useState({
    patient_id: "",
    type: "intake_reminder",
    title: REMIND_TEMPLATE.intake_reminder.title,
    message: REMIND_TEMPLATE.intake_reminder.message,
  });
  const [remindSubmitting, setRemindSubmitting] = useState(false);
  const [remindMessage, setRemindMessage] = useState(null);

  useEffect(() => {
    if (!remindForm.patient_id && normalizedPatients[0]?.id) {
      setRemindForm((prev) => ({
        ...prev,
        patient_id: normalizedPatients[0].id,
      }));
    }
  }, [normalizedPatients, remindForm.patient_id]);

  const readCookie = (name) => {
    if (typeof document === "undefined") return null;
    const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
    return match ? decodeURIComponent(match[2]) : null;
  };

  const safeJson = async (res) => {
    try {
      return await res.json();
    } catch {
      return null;
    }
  };

  const authFetch = async (path, options = {}) => {
    const headers = new Headers(options.headers || {});

    if (!headers.has("Content-Type") && options.body) {
      headers.set("Content-Type", "application/json");
    }

    const accessToken =
      typeof window !== "undefined"
        ? window.localStorage.getItem("access_token") || readCookie("access_token")
        : null;

    if (accessToken) {
      headers.set("Authorization", `Bearer ${accessToken}`);
    }

    return fetch(path, {
      ...options,
      headers,
      credentials: "include",
    });
  };

  const resolveNotificationPatientId = (item) => {
    const payload = item?.payload || item?.payload_json || {};
    const candidate = payload?.patient_id ?? item?.patient_id;
    const id = Number(candidate);
    return Number.isFinite(id) && id > 0 ? id : null;
  };

  const isVisibleForCurrentMode = (item) => {
    const patientId = resolveNotificationPatientId(item);

    if (isCaregiver) {
      if (!patientId) return false;
      if (selfPatientId && patientId === selfPatientId) return false;
      return caregiverPatientIdSet.has(patientId);
    }

    if (!myPatientId) return true;
    if (!patientId) return false;
    return patientId === myPatientId;
  };

  const loadNotifications = async (cursor = null, append = false) => {
    if (!isCaregiver && !myPatientId) {
      setNotifications([]);
      setNextCursor(null);
      setError(null);
      setLoading(false);
      setActionLoading(false);
      return;
    }

    if (!append) {
      setLoading(true);
    } else {
      setActionLoading(true);
    }

    setError(null);

    try {
      const params = new URLSearchParams();
      params.set("limit", "20");
      if (cursor) {
        params.set("cursor", String(cursor));
      }
      if (!isCaregiver && myPatientId) {
        params.set("patient_id", String(myPatientId));
      }
      if (unreadOnly) {
        params.set("unread_only", "true");
      }

      const res = await authFetch(`${API_PREFIX}/notifications?${params.toString()}`);
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(body?.detail || `status ${res.status}`);
      }

      const body = await safeJson(res);
      const data = body?.data || body || {};
      const items = data?.items || [];
      const visibleItems = items.filter(isVisibleForCurrentMode);
      const cursorValue = data?.next_cursor ?? null;

      setNotifications((prev) => {
        const merged = append ? [...prev, ...visibleItems] : visibleItems;
        return merged.slice(-MAX_NOTIFICATION_CACHE);
      });
      setNextCursor(cursorValue);
    } catch (err) {
      setError(err.message || "알림을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
      setActionLoading(false);
    }
  };

  const loadUnreadCount = async () => {
    if (!isCaregiver && !myPatientId) {
      setUnreadCount(0);
      return;
    }

    if (isCaregiver) {
      return;
    }

    try {
      const params = new URLSearchParams();
      if (!isCaregiver && myPatientId) {
        params.set("patient_id", String(myPatientId));
      }
      const res = await authFetch(
        `${API_PREFIX}/notifications/unread-count${params.toString() ? `?${params.toString()}` : ""}`
      );
      if (!res.ok) return;

      const body = await safeJson(res);
      const data = body?.data || body || {};
      setUnreadCount(data?.count ?? 0);
    } catch {}
  };

  const loadSettings = async () => {
    try {
      const res = await authFetch(`${API_PREFIX}/notifications/settings`);
      if (!res.ok) return;

      const body = await safeJson(res);
      const data = body?.data || body;
      if (data) {
        setSettings({
          intake_reminder: !!data.intake_reminder,
          missed_alert: !!data.missed_alert,
          hospital_schedule_reminder: !!data.hospital_schedule_reminder,
          ocr_done: !!data.ocr_done,
          guide_ready: !!data.guide_ready,
        });
      }
    } catch {}
  };

  const loadAll = async () => {
    await Promise.all([loadNotifications(), loadUnreadCount(), loadSettings()]);
  };

  useEffect(() => {
    loadAll();
  }, [isCaregiver, myPatientId, selfPatientId, unreadOnly]);

  useEffect(() => {
    if (!isCaregiver) return;
    setUnreadCount(notifications.filter((item) => !item.read_at).length);
  }, [isCaregiver, notifications]);

  useEffect(() => {
    if (!isCaregiver || typeof window === "undefined") return;

    const params = new URLSearchParams(window.location.search);
    const prefill = params.get("prefill");

    if (prefill !== "1") return;

    const patientId = params.get("patient_id") || "";
    const type = params.get("type") || "missed_alert";
    const title = params.get("title") || "복약 확인 요청";
    const message =
      params.get("message") || "복용 기록이 없어 확인이 필요합니다. 복용 여부를 확인해 주세요.";

    setRemindForm((prev) => ({
      ...prev,
      patient_id: patientId,
      type,
      title,
      message,
    }));

    if (patientId) setPatientFilter(String(patientId));
    if (type) setTypeFilter(type);

    setRemindMessage("복약 체크 화면에서 알림 내용을 불러왔습니다. 확인 후 전송해주세요.");

    setTimeout(() => {
      const remindSection = document.getElementById("manual-remind-card");
      if (remindSection) {
        remindSection.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }, 120);

    params.delete("prefill");
    const queryString = params.toString();
    const nextUrl = `${window.location.pathname}${queryString ? `?${queryString}` : ""}`;
    window.history.replaceState({}, "", nextUrl);
  }, [isCaregiver]);

  const getPatientName = (patientId) => {
    const patient = normalizedPatients.find((p) => p.id === Number(patientId));
    return patient?.name || null;
  };

  const resolvePatientLabel = (item) => {
    const payload = item?.payload || item?.payload_json || {};
    const payloadPatientId = payload?.patient_id ?? item?.patient_id;
    const payloadPatientName = payload?.patient_name;

    if (payloadPatientName) return payloadPatientName;
    if (payloadPatientId) {
      if (!isCaregiver && myPatient?.id && Number(payloadPatientId) === Number(myPatient.id) && myPatient?.name) {
        return myPatient.name;
      }
      return getPatientName(payloadPatientId) || `복약자 ${payloadPatientId}`;
    }
    if (!isCaregiver && myPatient?.name) return myPatient.name;

    return null;
  };

  const filteredNotifications = useMemo(() => {
    return notifications.filter((item) => {
      const keyword = search.trim().toLowerCase();

      const patientLabel = resolvePatientLabel(item) || "";
      const title = item.title || "";
      const body = item.body || "";
      const type = item.type || "";
      const payloadPatientId = resolveNotificationPatientId(item);

      if (!isVisibleForCurrentMode(item)) return false;

      if (typeFilter !== "all" && type !== typeFilter) return false;

      if (patientFilter !== "all") {
        if (String(payloadPatientId || "") !== String(patientFilter)) return false;
      }

      if (unreadOnly && item.read_at) return false;

      if (!keyword) return true;

      return [patientLabel, title, body, type].join(" ").toLowerCase().includes(keyword);
    });
  }, [
    notifications,
    search,
    typeFilter,
    patientFilter,
    unreadOnly,
    isCaregiver,
    myPatient,
    myPatientId,
    selfPatientId,
    normalizedPatients,
  ]);

  const getTypeMeta = (type) => TYPE_META[type] || TYPE_META.default;

  const getActionLabel = (type) => {
    if (type === "hospital_schedule_reminder") return "일정 보기";
    if (type === "intake_reminder" || type === "missed_alert" || type === "taken") {
      return "복약 확인하기";
    }
    return "열기";
  };

  const markRead = async (notificationId, silent = false) => {
    const currentItem = notifications.find((item) => item.id === notificationId);
    if (currentItem?.read_at) return true;

    if (!silent) setActionLoading(true);

    try {
      const res = await authFetch(`${API_PREFIX}/notifications/${notificationId}/read`, {
        method: "PATCH",
      });

      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(body?.detail || `status ${res.status}`);
      }

      setNotifications((prev) =>
        prev.map((item) =>
          item.id === notificationId
            ? { ...item, read_at: item.read_at || new Date().toISOString() }
            : item
        )
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
      return true;
    } catch (err) {
      if (!silent) setError(err.message || "읽음 처리에 실패했습니다.");
      return false;
    } finally {
      if (!silent) setActionLoading(false);
    }
  };

  const markAllRead = async () => {
    setActionLoading(true);
    try {
      if (isCaregiver) {
        const unreadIds = notifications.filter((item) => !item.read_at).map((item) => item.id);
        if (unreadIds.length > 0) {
          const results = await Promise.all(unreadIds.map((id) => markRead(id, true)));
          if (results.some((ok) => !ok)) {
            throw new Error("일부 알림의 읽음 처리에 실패했습니다.");
          }
        }
        return;
      }

      const params = new URLSearchParams();
      if (!isCaregiver && myPatientId) {
        params.set("patient_id", String(myPatientId));
      }
      const res = await authFetch(`${API_PREFIX}/notifications/read-all${params.toString() ? `?${params.toString()}` : ""}`, {
        method: "PATCH",
      });

      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(body?.detail || `status ${res.status}`);
      }

      setNotifications((prev) =>
        prev.map((item) => ({
          ...item,
          read_at: item.read_at || new Date().toISOString(),
        }))
      );
      setUnreadCount(0);
    } catch (err) {
      setError(err.message || "전체 읽음 처리에 실패했습니다.");
    } finally {
      setActionLoading(false);
    }
  };

  const deleteNotification = async (notificationId) => {
    if (typeof window !== "undefined" && !window.confirm("이 알림을 삭제할까요?")) {
      return;
    }

    setActionLoading(true);
    setError(null);

    try {
      const res = await authFetch(`${API_PREFIX}/notifications/${notificationId}`, {
        method: "DELETE",
      });

      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(body?.detail || `status ${res.status}`);
      }

      const currentItem = notifications.find((item) => item.id === notificationId);
      setNotifications((prev) => prev.filter((item) => item.id !== notificationId));
      if (currentItem && !currentItem.read_at) {
        setUnreadCount((prev) => Math.max(0, prev - 1));
      }
    } catch (err) {
      setError(err.message || "알림 삭제에 실패했습니다.");
    } finally {
      setActionLoading(false);
    }
  };

  const submitSettings = async (e) => {
    e.preventDefault();
    setSettingsSubmitting(true);
    setError(null);

    try {
      const res = await authFetch(`${API_PREFIX}/notifications/settings`, {
        method: "PATCH",
        body: JSON.stringify(settings),
      });

      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(body?.detail || `status ${res.status}`);
      }

      await loadSettings();
    } catch (err) {
      setError(err.message || "설정 저장에 실패했습니다.");
    } finally {
      setSettingsSubmitting(false);
    }
  };

  const handleRemindTypeChange = (nextType) => {
    const template = REMIND_TEMPLATE[nextType] || { title: "", message: "" };

    setRemindForm((prev) => ({
      ...prev,
      type: nextType,
      title: template.title,
      message: template.message,
    }));
  };

  const scrollToManualRemind = () => {
    const remindSection = document.getElementById("manual-remind-card");
    if (remindSection) {
      remindSection.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const prefillRemindFromNotification = (item) => {
    const payload = item?.payload || item?.payload_json || {};
    const patientId = payload?.patient_id ?? item?.patient_id ?? "";
    const patientName = resolvePatientLabel(item) || "";
    const defaultMessage =
      payload?.scheduled_at || payload?.schedule_date
        ? `${patientName ? `${patientName} ` : ""}복용 기록이 없어 확인이 필요합니다. 복용 여부를 확인해 주세요.`
        : `${patientName ? `${patientName} ` : ""}아직 복용 기록이 없어요. 복용 여부를 확인해 주세요.`;

    setRemindForm({
      patient_id: patientId,
      type: "missed_alert",
      title: "복약 확인 요청",
      message: defaultMessage,
    });

    setRemindMessage("미복용 알림 내용을 불러왔습니다. 확인 후 전송해주세요.");
    scrollToManualRemind();
  };

  const buildNotificationTarget = (item) => {
    const payload = item?.payload || item?.payload_json || {};
    const patientId = payload?.patient_id ?? item?.patient_id;
    const scheduleId = payload?.schedule_id;
    const scheduleTimeId = payload?.schedule_time_id;
    const scheduledAt = payload?.scheduled_at;
    const scheduledDate = payload?.scheduled_date;
    const mealLabel = payload?.meal_label;
    const documentId = payload?.document_id;
    const guideId = payload?.guide_id;

    if (item.type === "intake_reminder" || item.type === "missed_alert" || item.type === "taken") {
      const params = new URLSearchParams();
      if (patientId) params.set("patient_id", patientId);
      if (scheduleId) params.set("schedule_id", scheduleId);
      if (scheduleTimeId) params.set("schedule_time_id", scheduleTimeId);
      if (scheduledAt) params.set("scheduled_at", scheduledAt);
      if (scheduledDate) params.set("scheduled_date", scheduledDate);
      if (mealLabel) params.set("meal_label", mealLabel);
      return `/app/medication-check${params.toString() ? `?${params.toString()}` : ""}`;
    }

    if (item.type === "hospital_schedule_reminder") {
      const params = new URLSearchParams();
      if (patientId) params.set("patient_id", patientId);
      if (scheduleId) params.set("schedule_id", scheduleId);
      if (scheduledAt) params.set("scheduled_at", scheduledAt);
      return `/app/schedule${params.toString() ? `?${params.toString()}` : ""}`;
    }

    if (item.type === "ocr_done" || item.type === "ocr_failed") {
      return documentId
        ? `/app/documents?document_id=${documentId}`
        : "/app/documents";
    }

    if (item.type === "guide_ready") {
      const params = new URLSearchParams();
      if (patientId) params.set("patient_id", patientId);
      if (documentId) params.set("document_id", documentId);
      if (guideId) params.set("guide_id", guideId);
      return `/app/ai${params.toString() ? `?${params.toString()}` : ""}`;
    }

    return null;
  };

  const handleNotificationClick = async (item) => {
    const readSuccess = await markRead(item.id, true);
    if (!readSuccess && !item.read_at) return;

    const target = buildNotificationTarget(item);
    if (target) window.location.href = target;
  };

  const submitRemind = async (e) => {
    e.preventDefault();

    if (!remindForm.patient_id) {
      setRemindMessage("복약자를 선택해주세요.");
      return;
    }

    if (!remindForm.title.trim()) {
      setRemindMessage("제목을 입력해주세요.");
      return;
    }

    if (!remindForm.message.trim()) {
      setRemindMessage("메시지를 입력해주세요.");
      return;
    }

    setRemindSubmitting(true);
    setRemindMessage(null);
    setError(null);

    try {
      const payload = {
        patient_id: Number(remindForm.patient_id),
        type: remindForm.type,
        title: remindForm.title.trim(),
        message: remindForm.message.trim(),
      };

      const res = await authFetch(`${API_PREFIX}/notifications/remind`, {
        method: "POST",
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(body?.detail || `status ${res.status}`);
      }

      setRemindMessage("리마인드를 전송했습니다.");
      await loadAll();
    } catch (err) {
      setRemindMessage(err.message || "리마인드 전송에 실패했습니다.");
    } finally {
      setRemindSubmitting(false);
    }
  };

  return (
    <AppLayout
      activeKey="caregiver"
      title="알림센터"
      description={isCaregiver ? "연동 복약자 기준 알림과 리마인드를 관리합니다." : "복약 알림을 한 화면에서 확인합니다."}
      loginRole={loginRole}
      userName={userName}
      modeOptions={modeOptions}
      currentMode={currentMode}
      onModeChange={onModeChange}
    >
      <div className="row g-4">
        <div className="col-xl-4">
          <div className="card border-0 shadow-sm mb-3">
            <div className="card-body">
                <h6 className="fw-bold mb-3">알림 요약</h6>
                <div className="small text-muted mb-2">총 알림 {notifications.length}건</div>
                <div className="small text-muted">미읽음 알림 {unreadCount}건</div>
            </div>
          </div>

          <div className="card border-0 shadow-sm mb-3">
            <div className="card-body">
                <h6 className="fw-bold mb-3">알림 설정</h6>

                <form onSubmit={submitSettings}>
                  <div className="form-check mb-2">
                    <input className="form-check-input" type="checkbox" id="intake_reminder" checked={settings.intake_reminder} onChange={(e) => setSettings((prev) => ({ ...prev, intake_reminder: e.target.checked }))} />
                    <label className="form-check-label" htmlFor="intake_reminder">복약 리마인드</label>
                  </div>

                  <div className="form-check mb-2">
                    <input className="form-check-input" type="checkbox" id="missed_alert" checked={settings.missed_alert} onChange={(e) => setSettings((prev) => ({ ...prev, missed_alert: e.target.checked }))} />
                    <label className="form-check-label" htmlFor="missed_alert">미복용 알림</label>
                  </div>

                  <div className="form-check mb-2">
                    <input className="form-check-input" type="checkbox" id="hospital_schedule_reminder" checked={settings.hospital_schedule_reminder} onChange={(e) => setSettings((prev) => ({ ...prev, hospital_schedule_reminder: e.target.checked }))} />
                    <label className="form-check-label" htmlFor="hospital_schedule_reminder">병원 일정 알림</label>
                  </div>

                  <div className="form-check mb-2">
                    <input className="form-check-input" type="checkbox" id="ocr_done" checked={settings.ocr_done} onChange={(e) => setSettings((prev) => ({ ...prev, ocr_done: e.target.checked }))} />
                    <label className="form-check-label" htmlFor="ocr_done">OCR 완료</label>
                  </div>

                  <div className="form-check mb-3">
                    <input className="form-check-input" type="checkbox" id="guide_ready" checked={settings.guide_ready} onChange={(e) => setSettings((prev) => ({ ...prev, guide_ready: e.target.checked }))} />
                    <label className="form-check-label" htmlFor="guide_ready">가이드 준비 완료</label>
                  </div>

                  <button type="submit" className="btn btn-outline-primary btn-sm w-100" disabled={settingsSubmitting}>
                    {settingsSubmitting ? "저장 중..." : "설정 저장"}
                  </button>
                </form>
            </div>
          </div>

          {isCaregiver && (
            <div className="card border-0 shadow-sm" id="manual-remind-card">
              <div className="card-body">
                  <h6 className="fw-bold mb-2">수동 리마인드</h6>
                  <div className="small text-muted mb-3">보호자가 직접 복약자에게 알림을 보낼 수 있습니다.</div>

                  <form onSubmit={submitRemind}>
                    <div className="mb-3">
                      <label className="form-label">복약자 선택</label>
                      <select className="form-select" value={remindForm.patient_id} onChange={(e) => setRemindForm((prev) => ({ ...prev, patient_id: e.target.value }))}>
                        <option value="">복약자를 선택해주세요</option>
                        {normalizedPatients.map((patient) => (
                          <option key={patient.id} value={patient.id}>
                            {patient.name}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="mb-3">
                      <label className="form-label">알림 종류</label>
                      <select className="form-select" value={remindForm.type} onChange={(e) => handleRemindTypeChange(e.target.value)}>
                        <option value="intake_reminder">복약 리마인드</option>
                        <option value="missed_alert">미복용 알림</option>
                        <option value="ocr_done">OCR 완료</option>
                        <option value="ocr_failed">OCR 실패</option>
                        <option value="guide_ready">가이드 준비 완료</option>
                      </select>
                    </div>

                    <div className="mb-3">
                      <label className="form-label">알림 제목</label>
                      <input className="form-control" placeholder="알림 제목을 입력해주세요" value={remindForm.title} onChange={(e) => setRemindForm((prev) => ({ ...prev, title: e.target.value }))} />
                    </div>

                    <div className="mb-3">
                      <label className="form-label">알림 메시지</label>
                      <textarea className="form-control" rows="3" placeholder="복약자에게 보낼 메시지를 입력해주세요" value={remindForm.message} onChange={(e) => setRemindForm((prev) => ({ ...prev, message: e.target.value }))} />
                    </div>

                    <button type="submit" className="btn btn-primary btn-sm w-100" disabled={remindSubmitting}>
                      {remindSubmitting ? "전송 중..." : "리마인드 전송"}
                    </button>

                    {remindMessage && (
                      <div className={`small mt-2 ${remindMessage.includes("실패") || remindMessage.includes("선택") || remindMessage.includes("입력") ? "text-danger" : "text-muted"}`}>
                        {remindMessage}
                      </div>
                    )}
                  </form>
              </div>
            </div>
          )}
        </div>

        <div className="col-xl-8">
            <div className="card border-0 shadow-sm">
              <div className="card-body">
                <div className="d-flex justify-content-between align-items-center mb-4 flex-wrap gap-2">
                  <div>
                    <h3 className="fw-bold mb-1">알림 센터</h3>
                    <div className="text-muted">미읽음 {unreadCount}건</div>
                    {unreadOnly && (
                      <div className="small text-muted">미읽음 알림만 표시 중입니다.</div>
                    )}
                  </div>

                  <div className="d-flex gap-2">
                    <button className="btn btn-outline-primary btn-sm" onClick={markAllRead} disabled={actionLoading}>
                      모두 읽음 처리
                    </button>
                  </div>
                </div>

                <div className="row g-2 mb-4">
                  <div className="col-md-4">
                    <input className="form-control" placeholder="알림 검색" value={search} onChange={(e) => setSearch(e.target.value)} />
                  </div>

                  <div className="col-md-3">
                    <select className="form-select" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
                      <option value="all">알림 종류 전체</option>
                      <option value="intake_reminder">복약 리마인드</option>
                      <option value="missed_alert">미복용 알림</option>
                      <option value="hospital_schedule_reminder">병원 일정 알림</option>
                      <option value="ocr_done">OCR 완료</option>
                      <option value="ocr_failed">OCR 실패</option>
                      <option value="guide_ready">가이드 준비 완료</option>
                    </select>
                  </div>

                  <div className="col-md-2">
                    <button
                      type="button"
                      className={`btn w-100 ${unreadOnly ? "btn-primary" : "btn-outline-secondary"}`}
                      onClick={() => setUnreadOnly((prev) => !prev)}
                    >
                      미읽음만
                    </button>
                  </div>

                  {isCaregiver && (
                    <div className="col-md-2">
                      <select className="form-select" value={patientFilter} onChange={(e) => setPatientFilter(e.target.value)}>
                        <option value="all">복약자 전체</option>
                        {normalizedPatients.map((patient) => (
                          <option key={patient.id} value={String(patient.id)}>
                            {patient.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}

                  <div className="col-md-2 d-grid">
                    <button type="button" className="btn btn-light border" onClick={() => {
                      setSearch("");
                      setTypeFilter("all");
                      setPatientFilter("all");
                      setUnreadOnly(false);
                    }}>
                      초기화
                    </button>
                  </div>
                </div>

                {error && <div className="alert alert-danger">{error}</div>}
                {unreadOnly && (
                  <div className="alert alert-light border small py-2">
                    `미읽음만` 필터가 켜진 상태에서는 읽음 처리 후 목록에서 바로 사라질 수 있습니다.
                  </div>
                )}

                {loading ? (
                  <div className="text-center py-5">
                    <div className="spinner-border" role="status">
                      <span className="visually-hidden">Loading...</span>
                    </div>
                  </div>
                ) : (
                  <div className="border rounded-4 overflow-hidden">
                    <div className="d-flex align-items-center px-4 py-3 border-bottom" style={{ backgroundColor: "#f8fafc" }}>
                      <div className="fw-semibold">알림 목록</div>
                    </div>

                    {filteredNotifications.length === 0 ? (
                      <div className="px-4 py-5 text-center text-muted">표시할 알림이 없습니다.</div>
                    ) : (
                      filteredNotifications.map((item) => {
                        const meta = getTypeMeta(item.type);
                        const patientLabel = resolvePatientLabel(item);

                        return (
                          <div
                            key={item.id}
                            className="px-4 py-3 border-bottom"
                            role="button"
                            tabIndex={0}
                            onClick={() => handleNotificationClick(item)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                handleNotificationClick(item);
                              }
                            }}
                            style={{
                              backgroundColor: item.read_at ? "#ffffff" : "#f8fbff",
                              borderLeft: item.read_at ? "4px solid transparent" : "4px solid #2563eb",
                              cursor: "pointer",
                              transition: "background-color 0.15s ease",
                            }}
                          >
                            <div className="d-flex justify-content-between align-items-start gap-3">
                              <div className="flex-grow-1">
                                <div className="d-flex align-items-center gap-2 flex-wrap mb-2">
                                  {!item.read_at && (
                                    <span style={{ width: 8, height: 8, borderRadius: "999px", backgroundColor: "#2563eb", display: "inline-block" }} />
                                  )}

                                  {isCaregiver && patientLabel && (
                                    <span className="fw-semibold">{patientLabel}</span>
                                  )}

                                  <span className="px-2 py-1 rounded-pill small fw-semibold" style={{ backgroundColor: meta.bg, color: meta.color }}>
                                    {meta.label}
                                  </span>
                                </div>

                                <div className="fw-semibold mb-1">{item.title || meta.label}</div>
                                <div className="text-muted small mb-2">{item.body || "알림 내용이 없습니다."}</div>

                                <div className="d-flex gap-2 flex-wrap">
                                  {!item.read_at && (
                                    <button className="btn btn-outline-primary btn-sm" onClick={(e) => {
                                      e.stopPropagation();
                                      markRead(item.id);
                                    }} disabled={actionLoading}>
                                      읽음 처리
                                    </button>
                                  )}

                                  {(item.type === "intake_reminder" || item.type === "missed_alert" || item.type === "taken" || item.type === "hospital_schedule_reminder") && (
                                    <button className="btn btn-outline-secondary btn-sm" onClick={(e) => {
                                      e.stopPropagation();
                                      handleNotificationClick(item);
                                    }}>
                                      {getActionLabel(item.type)}
                                    </button>
                                  )}

                                  {item.type === "missed_alert" && isCaregiver && (
                                    <button className="btn btn-warning btn-sm" onClick={(e) => {
                                      e.stopPropagation();
                                      prefillRemindFromNotification(item);
                                    }}>
                                      리마인드 보내기
                                    </button>
                                  )}
                                </div>
                              </div>

                              <div className="d-flex flex-column align-items-end gap-2">
                                <button
                                  type="button"
                                  className="btn btn-link btn-sm p-0 text-muted text-decoration-none"
                                  aria-label="알림 삭제"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    deleteNotification(item.id);
                                  }}
                                  disabled={actionLoading}
                                  style={{ lineHeight: 1 }}
                                >
                                  x
                                </button>
                                <div className="small text-muted">{new Date(item.created_at).toLocaleString("ko-KR")}</div>
                                {item.read_at && <span className="small text-muted">읽음</span>}
                              </div>
                            </div>
                          </div>
                        );
                      })
                    )}

                    {nextCursor && (
                      <div className="px-4 py-3 text-center">
                        <button className="btn btn-outline-primary btn-sm" onClick={() => loadNotifications(nextCursor, true)} disabled={actionLoading}>
                          더 보기
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
    </AppLayout>
  );
};

export default NotificationPage;
