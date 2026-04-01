import React, { useEffect, useState } from "react";

const API_PREFIX = "/api/v1";

function CaregiverManagement() {
  const [links, setLinks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [linkCode, setLinkCode] = useState("");
  const [linkingPatient, setLinkingPatient] = useState(false);
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [selectedPatientMeta, setSelectedPatientMeta] = useState(null);

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

  const loadLinks = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`${API_PREFIX}/users/links`);
      if (!res.ok) {
        if (res.status === 404) {
          setLinks([]);
          setError(null);
          return;
        }
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `status ${res.status}`);
      }
      const data = await res.json();
      setLinks(data.links || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLinks();
  }, []);

  const handleLinkPatient = async (e) => {
    e.preventDefault();
    if (!linkCode.trim()) return;

    setLinkingPatient(true);
    setError(null);
    try {
      const res = await authFetch(`${API_PREFIX}/users/link`, {
        method: "POST",
        body: JSON.stringify({ code: linkCode }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `status ${res.status}`);
      }
      setLinkCode("");
      await loadLinks();
      alert("복약자 연동이 완료되었습니다.");
    } catch (err) {
      setError(err.message);
    } finally {
      setLinkingPatient(false);
    }
  };

  const handleUnlink = async (linkId) => {
    if (!confirm("연동을 해제하시겠습니까?")) return;

    try {
      const res = await authFetch(`${API_PREFIX}/users/links/${linkId}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `status ${res.status}`);
      }
      await loadLinks();
      alert("연동이 해제되었습니다.");
    } catch (err) {
      setError(err.message);
    }
  };

  const viewPatientProfile = async (linkId) => {
    const currentLink = links.find((link) => link.link_id === linkId) || null;
    try {
      const res = await authFetch(`${API_PREFIX}/users/links/${linkId}/health-profile`);
      if (res.ok) {
        const data = await res.json();
        setSelectedPatient(data.data);
        // Louis수정(기능추가): 모달에서도 어떤 복약자를 보고 있는지와 후속 동선을 함께 유지
        setSelectedPatientMeta(currentLink);
      } else if (res.status === 404) {
        setSelectedPatient(null);
        setSelectedPatientMeta(null);
        alert("복약자의 건강 프로필이 아직 등록되지 않았습니다.");
      } else {
        throw new Error(`status ${res.status}`);
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const viewPatientDocuments = (patientId) => {
    window.location.href = `/app/documents?patient_id=${patientId}`;
  };

  // Louis수정(기능추가): 보호자가 연동 복약자 건강 프로필 편집 화면으로 바로 진입할 수 있게 추가
  const editPatientProfile = (linkId) => {
    window.location.href = `/app/health-profile?link_id=${linkId}`;
  };

  // Louis수정(기능추가): 보호자가 연동 복약자 기준 AI 상담으로 바로 이동할 수 있게 추가
  const openPatientAi = (patientId) => {
    window.location.href = `/app/ai?patient_id=${patientId}&open_chat=1`;
  };

  return (
    <div className="container py-5">
      <div className="d-flex align-items-center mb-4">
        <a href="/app" style={{ cursor: 'pointer', textDecoration: 'none' }}>
          <img src={`${import.meta.env.BASE_URL}mascot.png`} alt="약속이" style={{ width: '120px', height: 'auto', marginRight: '20px' }} />
        </a>
        <h2 className="mb-0">보호자 관리</h2>
      </div>

      {error && (
        <div className="alert alert-danger alert-dismissible">
          {error}
          <button type="button" className="btn-close" onClick={() => setError(null)}></button>
        </div>
      )}

      {/* 복약자 연동 */}
      <div className="card mb-4">
        <div className="card-body">
          <h5 className="card-title">복약자 연동</h5>
          <p className="text-muted">복약자가 생성한 초대 코드를 입력하여 연동하세요.</p>
          <form onSubmit={handleLinkPatient}>
            <div className="row g-3">
              <div className="col-md-8">
                <input
                  type="text"
                  className="form-control"
                  value={linkCode}
                  onChange={(e) => setLinkCode(e.target.value)}
                  placeholder="초대 코드 입력"
                  required
                />
              </div>
              <div className="col-md-4">
                <button type="submit" className="btn btn-primary w-100" disabled={linkingPatient}>
                  {linkingPatient ? "연동 중..." : "연동하기"}
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>

      {/* 연동된 복약자 목록 */}
      <div className="card">
        <div className="card-body">
          <div className="d-flex justify-content-between align-items-center mb-3">
            <h5 className="card-title mb-0">연동된 복약자 목록</h5>
            <button className="btn btn-outline-primary btn-sm" onClick={loadLinks} disabled={loading}>
              {loading ? "로딩 중..." : "새로고침"}
            </button>
          </div>

          {loading && links.length === 0 ? (
            <div className="text-center py-5">로딩 중...</div>
          ) : links.length === 0 ? (
            <div className="text-center py-5 text-muted">연동된 복약자가 없습니다.</div>
          ) : (
            <div className="row g-3">
              {links.map((link) => (
                <div key={link.link_id} className="col-md-6">
                  <div className="card h-100">
                    <div className="card-body">
                      <div className="d-flex justify-content-between align-items-start mb-3">
                        <div>
                          <h6 className="card-title mb-1">
                            {link.patient_name || `복약자 #${link.patient_id}`}
                          </h6>
                          <span className={`badge ${link.status === "active" ? "bg-success" : "bg-secondary"}`}>
                            {link.status === "active" ? "활성" : link.status}
                          </span>
                        </div>
                        <button
                          className="btn btn-sm btn-outline-danger"
                          onClick={() => handleUnlink(link.link_id)}
                        >
                          연동 해제
                        </button>
                      </div>

                      <div className="mb-3">
                        <div className="text-muted small">복약자 ID</div>
                        <div>{link.patient_id}</div>
                      </div>

                      <div className="mb-3">
                        <div className="text-muted small">연동 일시</div>
                        <div>{new Date(link.linked_at).toLocaleString("ko-KR")}</div>
                      </div>

                      <div className="d-grid gap-2">
                        <button
                          className="btn btn-outline-primary btn-sm"
                          onClick={() => viewPatientProfile(link.link_id)}
                        >
                          건강 프로필 보기
                        </button>
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => editPatientProfile(link.link_id)}
                        >
                          건강 프로필 수정
                        </button>
                        <button
                          className="btn btn-outline-secondary btn-sm"
                          onClick={() => viewPatientDocuments(link.patient_id)}
                        >
                          문서 관리
                        </button>
                        <button
                          className="btn btn-outline-dark btn-sm"
                          onClick={() => openPatientAi(link.patient_id)}
                        >
                          AI 상담
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 복약자 프로필 모달 */}
      {selectedPatient && (
        <div className="modal show d-block" style={{ backgroundColor: "rgba(0,0,0,0.5)" }}>
          <div className="modal-dialog modal-lg modal-dialog-centered modal-dialog-scrollable">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">
                  {selectedPatientMeta?.patient_name || "복약자"} 건강 프로필
                </h5>
                <button
                  type="button"
                  className="btn-close"
                  onClick={() => {
                    setSelectedPatient(null);
                    setSelectedPatientMeta(null);
                  }}
                ></button>
              </div>
              <div className="modal-body">
                <div className="row g-3">
                  <div className="col-md-6">
                    <div className="border rounded p-3">
                      <div className="text-muted small">출생연도</div>
                      <div className="fw-semibold">{selectedPatient.birth_year || "—"}</div>
                    </div>
                  </div>
                  <div className="col-md-6">
                    <div className="border rounded p-3">
                      <div className="text-muted small">성별</div>
                      <div className="fw-semibold">{selectedPatient.sex || "—"}</div>
                    </div>
                  </div>
                  <div className="col-md-6">
                    <div className="border rounded p-3">
                      <div className="text-muted small">키</div>
                      <div className="fw-semibold">
                        {selectedPatient.height_cm ? `${selectedPatient.height_cm} cm` : "—"}
                      </div>
                    </div>
                  </div>
                  <div className="col-md-6">
                    <div className="border rounded p-3">
                      <div className="text-muted small">몸무게</div>
                      <div className="fw-semibold">
                        {selectedPatient.weight_kg ? `${selectedPatient.weight_kg} kg` : "—"}
                      </div>
                    </div>
                  </div>
                  <div className="col-md-6">
                    <div className="border rounded p-3">
                      <div className="text-muted small">BMI</div>
                      <div className="fw-semibold">
                        {selectedPatient.bmi ? selectedPatient.bmi.toFixed(1) : "—"}
                      </div>
                      {selectedPatient.bmi_status && (
                        <div className="small text-muted">{selectedPatient.bmi_status}</div>
                      )}
                    </div>
                  </div>
                  <div className="col-md-6">
                    <div className="border rounded p-3">
                      <div className="text-muted small">흡연 여부</div>
                      <div className="fw-semibold">
                        {selectedPatient.is_smoker === null
                          ? "—"
                          : selectedPatient.is_smoker
                          ? "흡연"
                          : "비흡연"}
                      </div>
                    </div>
                  </div>
                  <div className="col-md-6">
                    <div className="border rounded p-3">
                      <div className="text-muted small">입원 여부</div>
                      <div className="fw-semibold">
                        {selectedPatient.is_hospitalized === null
                          ? "—"
                          : selectedPatient.is_hospitalized
                          ? "현재 입원 중"
                          : "현재 입원 상태는 아님"}
                      </div>
                      {selectedPatient.discharge_date && (
                        <div className="small text-muted mt-1">퇴원 예정일 {selectedPatient.discharge_date}</div>
                      )}
                    </div>
                  </div>
                  <div className="col-md-6">
                    <div className="border rounded p-3">
                      <div className="text-muted small">평균 수면 시간</div>
                      <div className="fw-semibold">
                        {selectedPatient.avg_sleep_hours_per_day
                          ? `${selectedPatient.avg_sleep_hours_per_day}시간`
                          : "—"}
                      </div>
                    </div>
                  </div>
                  <div className="col-md-6">
                    <div className="border rounded p-3">
                      <div className="text-muted small">하루 평균 운동 시간</div>
                      <div className="fw-semibold">
                        {selectedPatient.avg_exercise_minutes_per_day
                          ? `${selectedPatient.avg_exercise_minutes_per_day}분`
                          : "—"}
                      </div>
                    </div>
                  </div>
                  <div className="col-md-6">
                    <div className="border rounded p-3">
                      <div className="text-muted small">주간 흡연량</div>
                      <div className="fw-semibold">
                        {selectedPatient.avg_cig_packs_per_week !== null &&
                        selectedPatient.avg_cig_packs_per_week !== undefined
                          ? `${selectedPatient.avg_cig_packs_per_week}갑`
                          : "—"}
                      </div>
                    </div>
                  </div>
                  <div className="col-md-6">
                    <div className="border rounded p-3">
                      <div className="text-muted small">주간 음주량</div>
                      <div className="fw-semibold">
                        {selectedPatient.avg_alcohol_bottles_per_week !== null &&
                        selectedPatient.avg_alcohol_bottles_per_week !== undefined
                          ? `${selectedPatient.avg_alcohol_bottles_per_week}병`
                          : "—"}
                      </div>
                    </div>
                  </div>
                  <div className="col-12">
                    <div className="border rounded p-3">
                      <div className="text-muted small">알레르기</div>
                      <div className="fw-semibold">
                        {selectedPatient.allergies?.length > 0
                          ? selectedPatient.allergies.join(", ")
                          : "—"}
                      </div>
                    </div>
                  </div>
                  <div className="col-12">
                    <div className="border rounded p-3">
                      <div className="text-muted small">기저 질환</div>
                      <div className="fw-semibold">
                        {selectedPatient.conditions?.length > 0
                          ? selectedPatient.conditions.join(", ")
                          : "—"}
                      </div>
                    </div>
                  </div>
                  <div className="col-12">
                    <div className="border rounded p-3">
                      <div className="text-muted small">복용 중인 약</div>
                      <div className="fw-semibold">
                        {selectedPatient.meds?.length > 0 ? selectedPatient.meds.join(", ") : "—"}
                      </div>
                    </div>
                  </div>
                  {selectedPatient.notes && (
                    <div className="col-12">
                      <div className="border rounded p-3">
                        <div className="text-muted small">메모</div>
                        <div className="fw-semibold">{selectedPatient.notes}</div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
              <div className="modal-footer">
                {selectedPatientMeta?.link_id && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => editPatientProfile(selectedPatientMeta.link_id)}
                  >
                    건강 프로필 수정
                  </button>
                )}
                {selectedPatientMeta?.patient_id && (
                  <button
                    type="button"
                    className="btn btn-outline-secondary"
                    onClick={() => viewPatientDocuments(selectedPatientMeta.patient_id)}
                  >
                    문서 관리
                  </button>
                )}
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => {
                    setSelectedPatient(null);
                    setSelectedPatientMeta(null);
                  }}
                >
                  닫기
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CaregiverManagement;
