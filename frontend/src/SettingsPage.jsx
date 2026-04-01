import React, { useEffect, useState } from "react";
import AppLayout from "./components/AppLayout.jsx";
import { applyDarkMode, getStoredDarkMode } from "./theme.js";

const API_PREFIX = "/api/v1";

const safeJson = async (res) => {
  try {
    return await res.json();
  } catch {
    return null;
  }
};

const formatApiError = (value) => {
  if (!value) return "요청 처리 중 오류가 발생했습니다.";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map((item) => item?.msg || JSON.stringify(item)).join(", ");
  if (typeof value === "object") {
    if (value.detail) return formatApiError(value.detail);
    if (value.message) return formatApiError(value.message);
    return JSON.stringify(value);
  }
  return String(value);
};

const getInviteRemainingMs = (expiresAt) => {
  if (!expiresAt) return null;
  const expiresAtMs = new Date(expiresAt).getTime();
  if (Number.isNaN(expiresAtMs)) return null;
  return Math.max(0, expiresAtMs - Date.now());
};

const formatInviteRemainingTime = (remainingMs) => {
  if (remainingMs === null || remainingMs === undefined) return "—";
  const totalSeconds = Math.max(0, Math.ceil(remainingMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
};

const readCookie = (name) => {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
  return match ? decodeURIComponent(match[2]) : null;
};

const authFetch = async (path, options = {}) => {
  const headers = new Headers(options.headers || {});
  const token =
    typeof window !== "undefined"
      ? window.localStorage.getItem("access_token") || readCookie("access_token")
      : null;

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(path, {
    ...options,
    headers,
    credentials: "include",
  });
};

const SettingsPage = ({ modeOptions = [], currentMode = "PATIENT", onModeChange, selfPatient = null, userName = "사용자" }) => {
  const [loginRole, setLoginRole] = useState(() => {
    if (typeof window === "undefined") return "PATIENT";
    return window.localStorage.getItem("login_role") || "PATIENT";
  });

  const [settings, setSettings] = useState({
    dark_mode: getStoredDarkMode(),
    language: "ko",
    push_notifications: true,
  });
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsError, setSettingsError] = useState(null);
  const [settingsNotice, setSettingsNotice] = useState(null);

  const [inviteForm, setInviteForm] = useState({ expires_in_minutes: 5 });
  const [inviteState, setInviteState] = useState({
    loading: false,
    submitting: false,
    deleting: false,
    error: null,
    data: null,
    success: null,
  });
  const [inviteRemainingMs, setInviteRemainingMs] = useState(null);

  const [linkForm, setLinkForm] = useState({ code: "" });
  const [linkAction, setLinkAction] = useState({
    submitting: false,
    error: null,
    success: null,
  });

  const [linksState, setLinksState] = useState({
    loading: false,
    links: [],
    error: null,
  });
  const [showWithdrawConfirm, setShowWithdrawConfirm] = useState(false);
  const [withdrawState, setWithdrawState] = useState({
    submitting: false,
    error: null,
  });

  const normalizeMode = (mode) => (mode === "GUARDIAN" ? "CAREGIVER" : mode || "PATIENT");
  const effectiveMode = normalizeMode(currentMode || loginRole);
  const isPatientMode = effectiveMode === "PATIENT";
  const isCaregiverMode = effectiveMode === "CAREGIVER";
  const canCreateInvite = isPatientMode || effectiveMode === "ADMIN";
  const canLinkByCode = isCaregiverMode;

  const linkSectionTitle = isCaregiverMode ? "복약자 연동" : "보호자 연동";
  const linkSectionDescription = isCaregiverMode
    ? "복약자에게 받은 초대코드로 연동할 수 있습니다."
    : "보호자가 입력할 초대코드를 생성하고 연동 상태를 관리합니다.";
  const linkListTitle = isCaregiverMode ? "연동된 복약자 목록" : "연동된 보호자 목록";
  const linkListEmptyMessage = isCaregiverMode ? "연동된 복약자가 없습니다." : "연동된 보호자가 없습니다.";
  const linkListTargetHeader = isCaregiverMode ? "복약자" : "보호자";

  const resolveLinkedTargetLabel = (link) => {
    if (isCaregiverMode) {
      return link.patient_name || `복약자 #${link.patient_id}`;
    }
    return link.caregiver_name || `보호자 #${link.caregiver_user_id || "—"}`;
  };

  const loadSettings = async () => {
    setSettingsLoading(true);
    setSettingsError(null);
    try {
      const res = await authFetch(`${API_PREFIX}/settings`);
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      const data = await res.json();
      setSettings({
        dark_mode: !!data.dark_mode,
        language: data.language || "ko",
        push_notifications: data.push_notifications ?? true,
      });
    } catch (error) {
      setSettingsError(error?.message || String(error));
    } finally {
      setSettingsLoading(false);
    }
  };

  const patchSettings = async (payload) => {
    setSettingsSaving(true);
    setSettingsError(null);
    setSettingsNotice(null);
    try {
      const res = await authFetch(`${API_PREFIX}/settings`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      const data = await res.json();
      setSettings({
        dark_mode: !!data.dark_mode,
        language: data.language || "ko",
        push_notifications: data.push_notifications ?? true,
      });
      setSettingsNotice("설정이 저장되었습니다.");
    } catch (error) {
      setSettingsError(error?.message || String(error));
    } finally {
      setSettingsSaving(false);
    }
  };

  const loadLinks = async () => {
    setLinksState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const params = new URLSearchParams();
      params.set("mode", isCaregiverMode ? "CAREGIVER" : "PATIENT");
      const res = await authFetch(`${API_PREFIX}/users/links?${params.toString()}`);
      if (!res.ok) {
        if (res.status === 404) {
          setLinksState({ loading: false, links: [], error: null });
          return;
        }
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      const data = await res.json();
      const links =
        isCaregiverMode && selfPatient?.id
          ? (data.links || []).filter((link) => String(link.patient_id) !== String(selfPatient.id))
          : data.links || [];
      setLinksState({ loading: false, links, error: null });
    } catch (error) {
      setLinksState({ loading: false, links: [], error: error?.message || String(error) });
    }
  };

  const loadCurrentInviteCode = async () => {
    if (!canCreateInvite) return;
    setInviteState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const res = await authFetch(`${API_PREFIX}/users/invite-code`);
      if (!res.ok) {
        setInviteState((prev) => ({ ...prev, loading: false }));
        return;
      }
      const data = await res.json();
      setInviteState((prev) => ({ ...prev, loading: false, data, error: null }));
    } catch {
      setInviteState((prev) => ({ ...prev, loading: false }));
    }
  };

  const createInviteCode = async () => {
    setInviteState((prev) => ({ ...prev, submitting: true, error: null, success: null }));
    try {
      const payload = { expires_in_minutes: Number(inviteForm.expires_in_minutes) || 5 };
      const res = await authFetch(`${API_PREFIX}/users/invite-code`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      const data = await res.json();
      setInviteState((prev) => ({
        ...prev,
        submitting: false,
        error: null,
        success: "초대 코드가 생성되었습니다.",
        data,
      }));
    } catch (error) {
      setInviteState((prev) => ({
        ...prev,
        submitting: false,
        error: error?.message || String(error),
      }));
    }
  };

  const deleteInviteCode = async () => {
    setInviteState((prev) => ({ ...prev, deleting: true, error: null, success: null }));
    try {
      const res = await authFetch(`${API_PREFIX}/users/invite-code`, { method: "DELETE" });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      setInviteState((prev) => ({
        ...prev,
        deleting: false,
        error: null,
        success: "초대 코드가 삭제되었습니다.",
        data: null,
      }));
    } catch (error) {
      setInviteState((prev) => ({
        ...prev,
        deleting: false,
        error: error?.message || String(error),
      }));
    }
  };

  const linkByInviteCode = async (event) => {
    event.preventDefault();
    if (!linkForm.code.trim()) return;
    setLinkAction({ submitting: true, error: null, success: null });
    try {
      const res = await authFetch(`${API_PREFIX}/users/link`, {
        method: "POST",
        body: JSON.stringify({ code: linkForm.code.trim() }),
      });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      setLinkForm({ code: "" });
      setLinkAction({ submitting: false, error: null, success: "연동이 완료되었습니다." });
      await loadLinks();
    } catch (error) {
      setLinkAction({ submitting: false, error: error?.message || String(error), success: null });
    }
  };

  const unlinkById = async (linkId) => {
    if (!window.confirm("연동을 해제하시겠습니까?")) return;
    setLinkAction({ submitting: true, error: null, success: null });
    try {
      const res = await authFetch(`${API_PREFIX}/users/links/${linkId}`, { method: "DELETE" });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      setLinkAction({ submitting: false, error: null, success: "연동을 해제했습니다." });
      await loadLinks();
    } catch (error) {
      setLinkAction({ submitting: false, error: error?.message || String(error), success: null });
    }
  };

  const clearAuthState = () => {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("access_token");
      window.localStorage.removeItem("login_role");
    }
    if (typeof document !== "undefined") {
      document.cookie = "access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    }
  };

  const withdrawAccount = async () => {
    setWithdrawState({ submitting: true, error: null });
    try {
      const res = await authFetch(`${API_PREFIX}/users/me`, { method: "DELETE" });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      clearAuthState();
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
    } catch (error) {
      setWithdrawState({
        submitting: false,
        error: error?.message || "탈퇴 처리 중 오류가 발생했습니다.",
      });
    }
  };

  useEffect(() => {
    applyDarkMode(settings.dark_mode);
  }, [settings.dark_mode]);

  useEffect(() => {
    const persistedRole =
      typeof window !== "undefined" ? window.localStorage.getItem("login_role") || "PATIENT" : "PATIENT";
    setLoginRole(normalizeMode(currentMode || persistedRole));
    loadSettings();
    loadLinks();
    if (canCreateInvite) {
      loadCurrentInviteCode();
    } else {
      setInviteState((prev) => ({ ...prev, loading: false, error: null, success: null, data: null }));
    }
  }, [currentMode]);

  useEffect(() => {
    const expiresAt = inviteState.data?.expires_at;
    if (!expiresAt) {
      setInviteRemainingMs(null);
      return;
    }

    const updateRemaining = () => {
      setInviteRemainingMs(getInviteRemainingMs(expiresAt));
    };

    updateRemaining();
    const timerId = setInterval(updateRemaining, 1000);
    return () => clearInterval(timerId);
  }, [inviteState.data?.expires_at]);

  return (
    <AppLayout
      activeKey="settings"
      title="설정"
      description={isCaregiverMode ? "앱 환경과 복약자 연동을 관리합니다." : "앱 환경과 보호자 연동을 관리합니다."}
      loginRole={effectiveMode}
      userName={userName}
      modeOptions={modeOptions}
      currentMode={currentMode}
      onModeChange={onModeChange}
    >
      <div className="row g-4">
        <div className="col-xl-5">
          <div className="card border-0 shadow-sm mb-4">
            <div className="card-body">
              <h5 className="fw-bold mb-3">앱 설정</h5>
              {settingsLoading ? (
                <div className="text-muted">설정을 불러오는 중입니다...</div>
              ) : (
                <>
                  <div className="mb-3">
                    <label className="form-label">언어</label>
                    <select
                      className="form-select"
                      value={settings.language}
                      onChange={(event) => {
                        setSettings((prev) => ({ ...prev, language: event.target.value }));
                        patchSettings({ language: event.target.value });
                      }}
                      disabled={settingsSaving}
                    >
                      <option value="ko">한국어</option>
                      <option value="en">English</option>
                      <option value="ja">日本語</option>
                    </select>
                  </div>

                  <div className="form-check form-switch mb-3">
                    <input
                      className="form-check-input"
                      type="checkbox"
                      id="dark_mode_setting"
                      checked={settings.dark_mode}
                      onChange={(event) => {
                        setSettings((prev) => ({ ...prev, dark_mode: event.target.checked }));
                        patchSettings({ dark_mode: event.target.checked });
                      }}
                      disabled={settingsSaving}
                    />
                    <label className="form-check-label" htmlFor="dark_mode_setting">다크 모드</label>
                  </div>

                  <div className="form-check form-switch">
                    <input
                      className="form-check-input"
                      type="checkbox"
                      id="push_notifications_setting"
                      checked={settings.push_notifications}
                      onChange={(event) => {
                        setSettings((prev) => ({ ...prev, push_notifications: event.target.checked }));
                        patchSettings({ push_notifications: event.target.checked });
                      }}
                      disabled={settingsSaving}
                    />
                    <label className="form-check-label" htmlFor="push_notifications_setting">푸시 알림</label>
                  </div>
                </>
              )}

              {settingsError && <div className="alert alert-danger mt-3 mb-0">{settingsError}</div>}
              {settingsNotice && <div className="alert alert-success mt-3 mb-0">{settingsNotice}</div>}
            </div>
          </div>

          <div className="card border-0 shadow-sm">
            <div className="card-body">
              <h5 className="fw-bold mb-3">계정</h5>
              <div className="d-grid gap-2">
                <a className="btn btn-outline-primary" href="/app/profile">내 정보 수정</a>
                <a className="btn btn-outline-secondary" href="/login">로그인 화면으로 이동</a>
              </div>

              <hr className="my-4" />
              <div className="border border-danger rounded-3 p-3 bg-light">
                <h6 className="fw-semibold text-danger mb-2">회원 탈퇴</h6>
                <p className="text-muted small mb-3">탈퇴 시 계정이 비활성화되며 복구할 수 없습니다.</p>

                {!showWithdrawConfirm ? (
                  <button
                    type="button"
                    className="btn btn-outline-danger btn-sm"
                    onClick={() => {
                      setShowWithdrawConfirm(true);
                      setWithdrawState({ submitting: false, error: null });
                    }}
                  >
                    회원 탈퇴
                  </button>
                ) : (
                  <div className="border border-danger rounded-3 p-3">
                    <p className="fw-semibold text-danger mb-2">정말 탈퇴하시겠습니까?</p>
                    <p className="small text-muted mb-3">이 작업은 되돌릴 수 없습니다.</p>
                    <div className="d-flex gap-2">
                      <button
                        type="button"
                        className="btn btn-danger btn-sm"
                        onClick={withdrawAccount}
                        disabled={withdrawState.submitting}
                      >
                        {withdrawState.submitting ? "처리 중..." : "탈퇴 확인"}
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-secondary btn-sm"
                        onClick={() => {
                          setShowWithdrawConfirm(false);
                          setWithdrawState({ submitting: false, error: null });
                        }}
                        disabled={withdrawState.submitting}
                      >
                        취소
                      </button>
                    </div>
                  </div>
                )}

                {withdrawState.error && <div className="alert alert-danger mt-3 mb-0">{withdrawState.error}</div>}
              </div>
            </div>
          </div>
        </div>

        <div className="col-xl-7">
          <div className="card border-0 shadow-sm">
            <div className="card-body">
              <div className="d-flex justify-content-between align-items-center mb-3">
                <h5 className="fw-bold mb-0">{linkSectionTitle}</h5>
                <button
                  type="button"
                  className="btn btn-outline-secondary btn-sm"
                  onClick={loadLinks}
                  disabled={linksState.loading || linkAction.submitting}
                >
                  {linksState.loading ? "불러오는 중..." : "새로고침"}
                </button>
              </div>
              <div className="text-muted small mb-4">
                {linkSectionDescription}
              </div>

              {canCreateInvite && (
                <div className="border rounded-3 p-3 mb-4">
                  <h6 className="fw-semibold">초대코드 생성/삭제</h6>
                  <div className="row g-2 align-items-end mt-1">
                    <div className="col-md-5">
                      <label className="form-label small">만료 시간(분)</label>
                      <input
                        type="number"
                        min="1"
                        className="form-control"
                        value={inviteForm.expires_in_minutes}
                        onChange={(event) => setInviteForm({ expires_in_minutes: Number(event.target.value) || 1 })}
                      />
                    </div>
                    <div className="col-md-7 d-flex gap-2">
                      <button
                        type="button"
                        className="btn btn-primary w-100"
                        onClick={createInviteCode}
                        disabled={inviteState.submitting}
                      >
                        {inviteState.submitting ? "생성 중..." : "초대코드 생성"}
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-danger w-100"
                        onClick={deleteInviteCode}
                        disabled={inviteState.deleting}
                      >
                        {inviteState.deleting ? "삭제 중..." : "초대코드 삭제"}
                      </button>
                    </div>
                  </div>

                  {inviteState.loading && <div className="small text-muted mt-2">기존 코드 확인 중...</div>}
                  {inviteState.data && (
                    <div className="alert alert-success mt-3 mb-0">
                      코드: <strong>{inviteState.data.code}</strong>
                      <br />
                      만료: {inviteState.data.expires_at ? new Date(inviteState.data.expires_at).toLocaleString("ko-KR") : "—"}
                      <br />
                      남은 시간:{" "}
                      <strong className={inviteRemainingMs === 0 ? "text-danger" : ""}>
                        {formatInviteRemainingTime(inviteRemainingMs)}
                      </strong>
                      {inviteRemainingMs === 0 && <span className="text-danger ms-2">만료됨</span>}
                    </div>
                  )}
                  {inviteState.error && <div className="alert alert-danger mt-3 mb-0">{inviteState.error}</div>}
                  {inviteState.success && <div className="alert alert-info mt-3 mb-0">{inviteState.success}</div>}
                </div>
              )}

              {canLinkByCode && (
                <div className="border rounded-3 p-3 mb-4">
                  <h6 className="fw-semibold">복약자 연동</h6>
                  <form className="row g-2 mt-1 align-items-end" onSubmit={linkByInviteCode}>
                    <div className="col-md-8">
                      <label className="form-label small">초대코드 입력</label>
                      <input
                        className="form-control"
                        value={linkForm.code}
                        onChange={(event) => setLinkForm({ code: event.target.value })}
                        placeholder="초대코드 입력"
                        required
                      />
                    </div>
                    <div className="col-md-4 d-flex align-items-end">
                      <button className="btn btn-primary w-100" type="submit" disabled={linkAction.submitting}>
                        {linkAction.submitting ? "연동 중..." : "연동하기"}
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {linkAction.error && <div className="alert alert-danger">{linkAction.error}</div>}
              {linkAction.success && <div className="alert alert-success">{linkAction.success}</div>}
              {linksState.error && <div className="alert alert-danger">{linksState.error}</div>}

              <h6 className="fw-semibold mb-3">{linkListTitle}</h6>
              {linksState.loading && linksState.links.length === 0 ? (
                <div className="text-muted">연동 목록을 불러오는 중입니다...</div>
              ) : linksState.links.length === 0 ? (
                <div className="text-muted">{linkListEmptyMessage}</div>
              ) : (
                <div className="table-responsive">
                  <table className="table table-sm align-middle">
                    <thead>
                      <tr>
                        <th>{linkListTargetHeader}</th>
                        <th>상태</th>
                        <th>연동일</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {linksState.links.map((link) => (
                        <tr key={link.link_id}>
                          <td>{resolveLinkedTargetLabel(link)}</td>
                          <td>{link.status || "active"}</td>
                          <td>{link.linked_at ? new Date(link.linked_at).toLocaleString("ko-KR") : "—"}</td>
                          <td className="text-end">
                            <button
                              className="btn btn-outline-danger btn-sm"
                              onClick={() => unlinkById(link.link_id)}
                              disabled={linkAction.submitting}
                            >
                              해제
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
};

export default SettingsPage;
