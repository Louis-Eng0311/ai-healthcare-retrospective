import React, { useEffect, useMemo, useState } from "react";
import AppLayout from "./components/AppLayout.jsx";

const API_PREFIX = "/api/v1";

const pageToneStyle = {
  minHeight: "100%",
  background: "transparent",
};

const shellCardStyle = {
  borderRadius: "16px",
  background: "var(--app-surface-bg)",
  border: "1px solid var(--app-surface-border)",
  boxShadow: "var(--app-surface-shadow)",
};

const softPanelStyle = {
  border: "1px solid var(--app-surface-border)",
  borderRadius: "14px",
  background: "var(--app-surface-bg)",
  boxShadow: "none",
};

const metricPanelStyle = {
  border: "1px solid var(--app-surface-border)",
  borderRadius: "14px",
  background: "var(--app-surface-bg)",
  boxShadow: "none",
};

const primaryButtonStyle = {
  background: "#2563eb",
  borderColor: "#2563eb",
  color: "#ffffff",
  boxShadow: "none",
};

const secondaryButtonStyle = {
  borderColor: "#d4deee",
  color: "#475569",
  background: "#ffffff",
};

const dangerButtonStyle = {
  background: "#dc2626",
  borderColor: "#dc2626",
  color: "#ffffff",
};

const titleAccentStyle = {
  borderRadius: "14px",
  padding: "16px 18px",
  background: "var(--app-surface-subtle)",
  border: "1px solid var(--app-surface-border)",
  boxShadow: "none",
};

const emptyForm = {
  birth_year: "",
  sex: "",
  height_cm: "",
  weight_kg: "",
  allergies: "",
  conditions: "",
  meds: "",
  is_smoker: "",
  is_hospitalized: "",
  discharge_date: "",
  avg_sleep_hours_per_day: "",
  avg_cig_packs_per_week: "",
  avg_alcohol_bottles_per_week: "",
  avg_exercise_minutes_per_day: "",
  notes: "",
};

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
  if (Array.isArray(value)) {
    return value.map((item) => item?.msg || JSON.stringify(item)).join(", ");
  }
  if (typeof value === "object") {
    if (value.detail) return formatApiError(value.detail);
    if (value.message) return formatApiError(value.message);
    return JSON.stringify(value);
  }
  return String(value);
};

const toCommaString = (items) => (Array.isArray(items) && items.length > 0 ? items.join(", ") : "");

const buildPayload = (formData) => ({
  birth_year: formData.birth_year ? Number(formData.birth_year) : null,
  sex: formData.sex || null,
  height_cm: formData.height_cm ? Number(formData.height_cm) : null,
  weight_kg: formData.weight_kg ? Number(formData.weight_kg) : null,
  allergies: formData.allergies
    ? formData.allergies.split(",").map((item) => item.trim()).filter(Boolean)
    : [],
  conditions: formData.conditions
    ? formData.conditions.split(",").map((item) => item.trim()).filter(Boolean)
    : [],
  meds: formData.meds
    ? formData.meds.split(",").map((item) => item.trim()).filter(Boolean)
    : [],
  is_smoker: formData.is_smoker === "" ? null : formData.is_smoker === "true",
  is_hospitalized: formData.is_hospitalized === "" ? null : formData.is_hospitalized === "true",
  discharge_date: formData.discharge_date || null,
  avg_sleep_hours_per_day: formData.avg_sleep_hours_per_day ? Number(formData.avg_sleep_hours_per_day) : null,
  avg_cig_packs_per_week: formData.avg_cig_packs_per_week ? Number(formData.avg_cig_packs_per_week) : null,
  avg_alcohol_bottles_per_week: formData.avg_alcohol_bottles_per_week
    ? Number(formData.avg_alcohol_bottles_per_week)
    : null,
  avg_exercise_minutes_per_day: formData.avg_exercise_minutes_per_day ? Number(formData.avg_exercise_minutes_per_day) : null,
  notes: formData.notes || null,
});

function HealthProfile({ modeOptions = [], currentMode = "PATIENT", onModeChange, selfPatient = null, userName = "사용자" }) {
  const searchParams = useMemo(() => new URLSearchParams(window.location.search), []);
  const requestedLinkId = searchParams.get("link_id");

  const [loginRole, setLoginRole] = useState(() => localStorage.getItem("login_role") || "PATIENT");
  const [linksState, setLinksState] = useState({ loading: false, data: null, error: null });
  const [selectedLinkId, setSelectedLinkId] = useState(
    requestedLinkId && requestedLinkId !== "me" ? requestedLinkId : ""
  );
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [editing, setEditing] = useState(false);
  const [formData, setFormData] = useState(emptyForm);
  const [profileMissing, setProfileMissing] = useState(false);
  const effectiveMode = currentMode || loginRole;
  const isCaregiver = effectiveMode === "CAREGIVER" || effectiveMode === "GUARDIAN";

  const authFetch = async (url, options = {}) => {
    const token = localStorage.getItem("access_token");
    const headers = {
      "Content-Type": "application/json",
      ...options.headers,
    };
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    return fetch(url, { ...options, headers, credentials: "include" });
  };

  const selectedLink =
    (linksState.data?.links || []).find((link) => String(link.link_id) === String(selectedLinkId)) || null;
  const selectedPatientLabel =
    selectedLink?.patient_name || (selectedLink?.patient_id ? `복약자 #${selectedLink.patient_id}` : null);

  const hydrateForm = (data) => {
    if (!data) {
      setFormData(emptyForm);
      return;
    }

    setFormData({
      birth_year: data.birth_year || "",
      sex: data.sex || "",
      height_cm: data.height_cm || "",
      weight_kg: data.weight_kg || "",
      allergies: toCommaString(data.allergies),
      conditions: toCommaString(data.conditions),
      meds: toCommaString(data.meds),
      is_smoker: data.is_smoker === null ? "" : String(data.is_smoker),
      is_hospitalized: data.is_hospitalized === null ? "" : String(data.is_hospitalized),
      discharge_date: data.discharge_date || "",
      avg_sleep_hours_per_day: data.avg_sleep_hours_per_day || "",
      avg_cig_packs_per_week: data.avg_cig_packs_per_week || "",
      avg_alcohol_bottles_per_week: data.avg_alcohol_bottles_per_week || "",
      avg_exercise_minutes_per_day: data.avg_exercise_minutes_per_day || "",
      notes: data.notes || "",
    });
  };

  const loadLinks = async () => {
    if (!isCaregiver) return;

    setLinksState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const res = await authFetch(`${API_PREFIX}/users/links`);
      if (!res.ok) {
        throw new Error(formatApiError(await safeJson(res)));
      }
      const body = await res.json();
      const links =
        isCaregiver && selfPatient?.id
          ? (body?.links || []).filter((link) => String(link.patient_id) !== String(selfPatient.id))
          : body?.links || [];
      setLinksState({ loading: false, data: { ...(body || {}), links }, error: null });
      if (links.length === 0) {
        setSelectedLinkId("");
      } else if (selectedLinkId === "me") {
        setSelectedLinkId("");
      } else if (selectedLinkId && !links.some((link) => String(link.link_id) === String(selectedLinkId))) {
        setSelectedLinkId("");
      }
    } catch (err) {
      setLinksState({ loading: false, data: null, error: err?.message || String(err) });
    }
  };

  const loadProfile = async () => {
    if (isCaregiver && !selectedLinkId) {
      setProfile(null);
      hydrateForm(null);
      setLoading(false);
      setError(null);
      setProfileMissing(false);
      return;
    }

    setLoading(true);
    setError(null);
    setProfileMissing(false);
    try {
      const endpoint =
        isCaregiver && selectedLinkId && selectedLinkId !== "me"
          ? `${API_PREFIX}/users/links/${selectedLinkId}/health-profile`
          : `${API_PREFIX}/users/me/health-profile`;
      const res = await authFetch(endpoint);
      if (res.ok) {
        const data = await res.json();
        setProfile(data?.data || null);
        hydrateForm(data?.data || null);
      } else if (res.status === 404) {
        setProfile(null);
        hydrateForm(null);
        setProfileMissing(true);
      } else {
        throw new Error(formatApiError(await safeJson(res)));
      }
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setLoginRole(localStorage.getItem("login_role") || "PATIENT");
  }, []);

  useEffect(() => {
    loadLinks();
  }, [isCaregiver]);

  useEffect(() => {
    loadProfile();
  }, [isCaregiver, selectedLinkId]);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setNotice(null);
    setFormData((prev) => {
      if (name === "is_hospitalized" && value !== "true") {
        return { ...prev, [name]: value, discharge_date: "" };
      }
      return { ...prev, [name]: value };
    });
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setNotice(null);

    try {
      const endpoint =
        isCaregiver && selectedLinkId && selectedLinkId !== "me"
          ? `${API_PREFIX}/users/links/${selectedLinkId}/health-profile`
          : `${API_PREFIX}/users/me/health-profile`;
      const method = profile ? "PATCH" : "POST";
      const res = await authFetch(endpoint, {
        method,
        body: JSON.stringify(buildPayload(formData)),
      });
      if (!res.ok) {
        throw new Error(formatApiError(await safeJson(res)));
      }
      await loadProfile();
      setEditing(false);
      setNotice(profile ? "건강 프로필이 수정되었습니다." : "건강 프로필이 등록되었습니다.");
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm("건강 프로필을 삭제하시겠습니까?")) return;

    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const endpoint =
        isCaregiver && selectedLinkId && selectedLinkId !== "me"
          ? `${API_PREFIX}/users/links/${selectedLinkId}/health-profile`
          : `${API_PREFIX}/users/me/health-profile`;
      const res = await authFetch(endpoint, { method: "DELETE" });
      if (!res.ok) {
        throw new Error(formatApiError(await safeJson(res)));
      }
      setProfile(null);
      hydrateForm(null);
      setEditing(false);
      setProfileMissing(true);
      setNotice("건강 프로필이 삭제되었습니다.");
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setSaving(false);
    }
  };

  const title =
    isCaregiver ? "건강 프로필 관리" : "건강 프로필";

  const handleCaregiverPatientChange = (nextValue) => {
    setSelectedLinkId(nextValue && nextValue !== "me" ? nextValue : "");
    setEditing(false);
    setNotice(null);
    setError(null);
  };

  if (loading && !profile && !(isCaregiver && !selectedLinkId)) {
    return (
      <AppLayout
        activeKey="health"
        title={title}
        description="건강 정보를 불러오는 중입니다."
        loginRole={loginRole}
        userName={userName}
        modeOptions={modeOptions}
        currentMode={currentMode}
        onModeChange={onModeChange}
      >
        <div className="text-center py-5">로딩 중...</div>
      </AppLayout>
    );
  }

  return (
    <AppLayout
      activeKey="health"
      title={title}
      description={isCaregiver ? "내 정보와 연동된 복약자 프로필을 함께 관리합니다." : "건강 정보를 정리하고 필요한 항목을 관리합니다."}
      loginRole={loginRole}
      userName={userName}
      modeOptions={modeOptions}
      currentMode={currentMode}
      onModeChange={onModeChange}
    >
      <div style={pageToneStyle} className="p-2">
      <div className="row justify-content-center">
        <div className="col-lg-9">
          <div className="card shadow-sm" style={shellCardStyle}>
            <div className="card-body">
              <div className="d-flex justify-content-between align-items-center mb-4">
                <div>
                  <h3 className="mb-1" style={{ color: "#1f2937" }}>{title}</h3>
                  <div className="text-muted small">
                    {isCaregiver
                      ? "내 정보와 연동된 복약자 프로필을 한 화면에서 관리할 수 있습니다."
                      : "건강 정보를 정리하고 필요한 항목을 바로 수정할 수 있습니다."}
                  </div>
                </div>
                <div className="d-flex gap-2">
                  {isCaregiver && selectedLinkId && !editing && (
                    <button
                      className="btn btn-secondary btn-sm"
                      style={secondaryButtonStyle}
                      onClick={() => handleCaregiverPatientChange("")}
                    >
                      뒤로가기
                    </button>
                  )}
                  {profile && !editing && (
                    <>
                      <button className="btn btn-primary btn-sm" style={primaryButtonStyle} onClick={() => setEditing(true)}>
                        수정
                      </button>
                      <button className="btn btn-danger btn-sm" style={dangerButtonStyle} onClick={handleDelete} disabled={saving}>
                        삭제
                      </button>
                    </>
                  )}
                  {editing && (
                    <button className="btn btn-secondary btn-sm" style={secondaryButtonStyle} onClick={() => setEditing(false)}>
                      취소
                    </button>
                  )}
                </div>
              </div>

              <div style={titleAccentStyle} className="mb-4">
                <div className="d-flex flex-wrap align-items-center justify-content-between gap-3">
                  <div>
                    <div className="small" style={{ color: "#6b7280" }}>프로필 활용 안내</div>
                    <div className="fw-semibold" style={{ color: "#334155" }}>
                      정리된 건강 정보는 가이드, 상담, 복약 관리 화면에서 공통으로 활용됩니다.
                    </div>
                  </div>
                  <div className="small" style={{ color: "#6b7280" }}>
                    수면 · 운동 · 알레르기 · 기저질환 · 복용약
                  </div>
                </div>
              </div>

              {isCaregiver && (
                <div className="mb-4">
                  <label className="form-label">관리 프로필 선택</label>
                  <div className="row g-2">
                    <div className="col-md-8">
                      <select
                        className="form-select"
                        value={selectedLinkId}
                        onChange={(event) => handleCaregiverPatientChange(event.target.value)}
                      >
                        <option value="">선택</option>
                        {(!linksState.data?.links || linksState.data.links.length === 0) && (
                          <option value="" disabled>연동된 복약자 없음</option>
                        )}
                        {(linksState.data?.links || []).map((link) => (
                          <option key={link.link_id} value={link.link_id}>
                            {link.patient_name || `복약자 #${link.patient_id}`}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="col-md-4">
                      <button
                        type="button"
                        className="btn btn-outline-primary w-100"
                        style={secondaryButtonStyle}
                        onClick={() => {
                          loadLinks();
                          loadProfile();
                        }}
                        disabled={linksState.loading || loading}
                      >
                        {linksState.loading || loading ? "불러오는 중..." : "다시 불러오기"}
                      </button>
                    </div>
                  </div>
                  {linksState.error && <div className="alert alert-danger mt-3 mb-0">{linksState.error}</div>}
                  {!linksState.error && (!linksState.data?.links || linksState.data.links.length === 0) && (
                    <div className="alert alert-secondary mt-3 mb-0">
                      아직 연동된 복약자가 없습니다. 연동된 복약자만 프로필을 등록·관리할 수 있습니다.
                    </div>
                  )}
                </div>
              )}

              {isCaregiver && selectedLink && (
                <div className="border rounded p-3 mb-4" style={softPanelStyle}>
                  <div className="d-flex flex-wrap justify-content-between align-items-start gap-3">
                    <div>
                      <div className="text-muted small">현재 선택된 복약자</div>
                      <div className="fw-semibold fs-5">{selectedPatientLabel}</div>
                      <div className="small text-muted mt-1">
                        연동 상태: {selectedLink.status === "active" ? "활성" : selectedLink.status || "—"}
                      </div>
                      {selectedLink.linked_at && (
                        <div className="small text-muted">
                          연동일 {new Date(selectedLink.linked_at).toLocaleDateString("ko-KR")}
                        </div>
                      )}
                    </div>
                    <div className="small text-muted">
                      보호자 연동 정보는 설정에서 관리할 수 있습니다.
                      <br />
                      문서 확인은 처방전 업로드 메뉴에서 할 수 있습니다.
                    </div>
                  </div>
                </div>
              )}

              {notice && <div className="alert alert-success">{notice}</div>}
              {error && <div className="alert alert-danger">{error}</div>}

              {!profile && !editing ? (
                <div className="text-center py-5">
                  <p className="text-muted mb-3">
                    {isCaregiver && selectedLink && profileMissing
                      ? `${selectedLink.patient_name || "선택한 복약자"}의 건강 프로필이 없습니다.`
                      : isCaregiver
                          ? "연동된 복약자를 선택해 주세요."
                        : "등록된 건강 프로필이 없습니다."}
                  </p>
                  {isCaregiver && selectedLink && (
                    <div className="small text-muted mb-3">
                      복약자 기본 정보와 생활습관을 먼저 등록해 두면 이후 가이드, 상담, 일정 기능에서 재사용됩니다.
                    </div>
                  )}
                  {isCaregiver && !selectedLink && (
                    <div className="small text-muted mb-3">
                      보호자 모드에서는 연동된 복약자의 건강 프로필만 등록·관리할 수 있습니다.
                    </div>
                  )}
                  {(!isCaregiver || selectedLink) && (
                    <button className="btn btn-primary" style={primaryButtonStyle} onClick={() => setEditing(true)}>
                      건강 프로필 등록
                    </button>
                  )}
                </div>
              ) : editing ? (
                <form onSubmit={handleSubmit}>
                  <div className="row g-3">
                    <div className="col-md-4">
                      <label className="form-label">출생연도</label>
                      <input
                        type="number"
                        className="form-control"
                        name="birth_year"
                        value={formData.birth_year}
                        onChange={handleChange}
                        min="1900"
                        max="2100"
                      />
                    </div>
                    <div className="col-md-4">
                      <label className="form-label">성별</label>
                      <select className="form-select" name="sex" value={formData.sex} onChange={handleChange}>
                        <option value="">선택</option>
                        <option value="MALE">남성</option>
                        <option value="FEMALE">여성</option>
                      </select>
                    </div>
                    <div className="col-md-4">
                      <label className="form-label">흡연 여부</label>
                      <select className="form-select" name="is_smoker" value={formData.is_smoker} onChange={handleChange}>
                        <option value="">선택</option>
                        <option value="true">흡연</option>
                        <option value="false">비흡연</option>
                      </select>
                    </div>

                    <div className="col-md-6">
                      <label className="form-label">키 (cm)</label>
                      <input type="number" className="form-control" name="height_cm" value={formData.height_cm} onChange={handleChange} step="0.1" />
                    </div>
                    <div className="col-md-6">
                      <label className="form-label">몸무게 (kg)</label>
                      <input type="number" className="form-control" name="weight_kg" value={formData.weight_kg} onChange={handleChange} step="0.1" />
                    </div>

                    <div className="col-md-6">
                      <label className="form-label">입원 여부</label>
                      <select
                        className="form-select"
                        name="is_hospitalized"
                        value={formData.is_hospitalized}
                        onChange={handleChange}
                      >
                        <option value="">선택</option>
                        <option value="true">현재 입원 중</option>
                        <option value="false">현재 입원 상태는 아님</option>
                      </select>
                    </div>
                    <div className="col-md-6">
                      <label className="form-label">퇴원 예정일</label>
                      <input
                        type="date"
                        className="form-control"
                        name="discharge_date"
                        value={formData.discharge_date}
                        onChange={handleChange}
                        disabled={formData.is_hospitalized !== "true"}
                      />
                      {formData.is_hospitalized !== "true" && (
                        <div className="form-text">현재 입원 중일 때만 입력합니다.</div>
                      )}
                    </div>

                    <div className="col-md-4">
                      <label className="form-label">하루 평균 수면 시간</label>
                      <input
                        type="number"
                        className="form-control"
                        name="avg_sleep_hours_per_day"
                        value={formData.avg_sleep_hours_per_day}
                        onChange={handleChange}
                        step="0.5"
                        placeholder="7"
                      />
                    </div>
                    <div className="col-md-4">
                      <label className="form-label">주간 흡연량(갑)</label>
                      <input
                        type="number"
                        className="form-control"
                        name="avg_cig_packs_per_week"
                        value={formData.avg_cig_packs_per_week}
                        onChange={handleChange}
                        step="0.1"
                        placeholder="0"
                      />
                    </div>
                    <div className="col-md-4">
                      <label className="form-label">주간 음주량(병)</label>
                      <input
                        type="number"
                        className="form-control"
                        name="avg_alcohol_bottles_per_week"
                        value={formData.avg_alcohol_bottles_per_week}
                        onChange={handleChange}
                        step="0.1"
                        placeholder="0"
                      />
                    </div>

                    <div className="col-md-6">
                      <label className="form-label">하루 평균 운동 시간 (분)</label>
                      <input
                        type="number"
                        className="form-control"
                        name="avg_exercise_minutes_per_day"
                        value={formData.avg_exercise_minutes_per_day}
                        onChange={handleChange}
                        placeholder="30"
                      />
                    </div>
                    <div className="col-md-6">
                      <label className="form-label">알레르기 (쉼표로 구분)</label>
                      <input
                        type="text"
                        className="form-control"
                        name="allergies"
                        value={formData.allergies}
                        onChange={handleChange}
                        placeholder="예: 페니실린, 땅콩"
                      />
                    </div>

                    <div className="col-12">
                      <label className="form-label">기저 질환 (쉼표로 구분)</label>
                      <textarea
                        className="form-control"
                        name="conditions"
                        value={formData.conditions}
                        onChange={handleChange}
                        rows="2"
                        placeholder="예: 고혈압, 당뇨"
                      />
                    </div>
                    <div className="col-12">
                      <label className="form-label">복용 중인 약 (쉼표로 구분)</label>
                      <textarea
                        className="form-control"
                        name="meds"
                        value={formData.meds}
                        onChange={handleChange}
                        rows="2"
                        placeholder="현재 복용 중인 약물"
                      />
                    </div>
                    <div className="col-12">
                      <label className="form-label">메모</label>
                      <textarea
                        className="form-control"
                        name="notes"
                        value={formData.notes}
                        onChange={handleChange}
                        rows="3"
                        placeholder="추가 정보"
                      />
                    </div>
                  </div>

                  <div className="d-grid gap-2 mt-4">
                    <button type="submit" className="btn btn-primary" style={primaryButtonStyle} disabled={saving}>
                      {saving ? "저장 중..." : profile ? "수정 완료" : "등록"}
                    </button>
                  </div>
                </form>
              ) : (
                <div className="row g-3">
                  <div className="col-md-6">
                    <div className="border rounded p-3 h-100" style={metricPanelStyle}>
                      <div className="text-muted small">기본 정보</div>
                      <div className="fw-semibold">
                        {profile.birth_year || "—"} / {profile.sex || "—"}
                      </div>
                      <div className="small text-muted mt-1">
                        {isCaregiver ? selectedPatientLabel || "선택된 복약자" : "본인 프로필"}
                      </div>
                    </div>
                  </div>
                  <div className="col-md-6">
                    <div className="border rounded p-3 h-100" style={metricPanelStyle}>
                      <div className="text-muted small">입원 여부</div>
                      <div className="fw-semibold">
                        {profile.is_hospitalized === null
                          ? "—"
                          : profile.is_hospitalized
                            ? "현재 입원 중"
                            : "현재 입원 상태는 아님"}
                      </div>
                      {profile.discharge_date && <div className="small text-muted mt-1">퇴원 예정일 {profile.discharge_date}</div>}
                    </div>
                  </div>
                  <div className="col-md-6">
                    <div className="border rounded p-3 h-100" style={metricPanelStyle}>
                      <div className="text-muted small">키</div>
                      <div className="fw-semibold">{profile.height_cm ? `${profile.height_cm} cm` : "—"}</div>
                    </div>
                  </div>
                  <div className="col-md-6">
                    <div className="border rounded p-3 h-100" style={metricPanelStyle}>
                      <div className="text-muted small">몸무게</div>
                      <div className="fw-semibold">{profile.weight_kg ? `${profile.weight_kg} kg` : "—"}</div>
                    </div>
                  </div>
                  <div className="col-md-6">
                    <div className="border rounded p-3 h-100" style={metricPanelStyle}>
                      <div className="text-muted small">BMI</div>
                      <div className="fw-semibold">{profile.bmi ? profile.bmi.toFixed(1) : "—"}</div>
                      {profile.bmi_status && <div className="small text-muted">{profile.bmi_status}</div>}
                      {profile.bmi_comment && <div className="small text-muted mt-1">{profile.bmi_comment}</div>}
                    </div>
                  </div>
                  <div className="col-md-6">
                    <div className="border rounded p-3 h-100" style={metricPanelStyle}>
                      <div className="text-muted small">흡연 여부</div>
                      <div className="fw-semibold">
                        {profile.is_smoker === null ? "—" : profile.is_smoker ? "흡연" : "비흡연"}
                      </div>
                    </div>
                  </div>
                  <div className="col-md-4">
                    <div className="border rounded p-3 h-100" style={metricPanelStyle}>
                      <div className="text-muted small">평균 수면 시간</div>
                      <div className="fw-semibold">
                        {profile.avg_sleep_hours_per_day ? `${profile.avg_sleep_hours_per_day}시간` : "—"}
                      </div>
                    </div>
                  </div>
                  <div className="col-md-4">
                    <div className="border rounded p-3 h-100" style={metricPanelStyle}>
                      <div className="text-muted small">주간 흡연량</div>
                      <div className="fw-semibold">
                        {profile.avg_cig_packs_per_week !== null && profile.avg_cig_packs_per_week !== undefined
                          ? `${profile.avg_cig_packs_per_week}갑`
                          : "—"}
                      </div>
                    </div>
                  </div>
                  <div className="col-md-4">
                    <div className="border rounded p-3 h-100" style={metricPanelStyle}>
                      <div className="text-muted small">주간 음주량</div>
                      <div className="fw-semibold">
                        {profile.avg_alcohol_bottles_per_week !== null && profile.avg_alcohol_bottles_per_week !== undefined
                          ? `${profile.avg_alcohol_bottles_per_week}병`
                          : "—"}
                      </div>
                    </div>
                  </div>
                  <div className="col-md-6">
                    <div className="border rounded p-3 h-100" style={metricPanelStyle}>
                      <div className="text-muted small">하루 평균 운동 시간</div>
                      <div className="fw-semibold">
                        {profile.avg_exercise_minutes_per_day ? `${profile.avg_exercise_minutes_per_day}분` : "—"}
                      </div>
                    </div>
                  </div>
                  <div className="col-md-6">
                    <div className="border rounded p-3 h-100" style={metricPanelStyle}>
                      <div className="text-muted small">알레르기</div>
                      <div className="fw-semibold">
                        {profile.allergies?.length > 0 ? profile.allergies.join(", ") : "—"}
                      </div>
                    </div>
                  </div>
                  <div className="col-12">
                    <div className="border rounded p-3" style={metricPanelStyle}>
                      <div className="text-muted small">기저 질환</div>
                      <div className="fw-semibold">
                        {profile.conditions?.length > 0 ? profile.conditions.join(", ") : "—"}
                      </div>
                    </div>
                  </div>
                  <div className="col-12">
                    <div className="border rounded p-3" style={metricPanelStyle}>
                      <div className="text-muted small">복용 중인 약</div>
                      <div className="fw-semibold">{profile.meds?.length > 0 ? profile.meds.join(", ") : "—"}</div>
                    </div>
                  </div>
                  {profile.notes && (
                    <div className="col-12">
                      <div className="border rounded p-3" style={metricPanelStyle}>
                        <div className="text-muted small">메모</div>
                        <div className="fw-semibold">{profile.notes}</div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      </div>
    </AppLayout>
  );
}

export default HealthProfile;
