import React, { useEffect, useMemo, useState } from "react";
import AppLayout from "./components/AppLayout.jsx";

const API_PREFIX = "/api/v1";

const SchedulePage = ({
  linkedPatients = [],
  myPatient = null,
  loginRole = "CAREGIVER",
  userName = "사용자",
  modeOptions = [],
  currentMode = "PATIENT",
  onModeChange,
}) => {
  const effectiveMode = currentMode || loginRole;
  const isCaregiver = effectiveMode === "CAREGIVER" || effectiveMode === "GUARDIAN";

  const patientsSource = useMemo(() => {
    if (!isCaregiver) {
      return myPatient ? [myPatient] : [];
    }
    return (linkedPatients || []).filter((patient) => patient?.id);
  }, [isCaregiver, linkedPatients, myPatient]);

  const normalizedPatients = useMemo(() => {
    return patientsSource.map((patient) => ({
      id: Number(patient.id),
      name: patient.name || `복약자 ${patient.id}`,
    }));
  }, [patientsSource]);

  const defaultPatientId = normalizedPatients[0]?.id ?? "";
  const initialSelectedPatientId = isCaregiver ? "all" : String(defaultPatientId || "");

  const [currentDate, setCurrentDate] = useState(new Date());
  const [schedules, setSchedules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedPatientId, setSelectedPatientId] = useState(initialSelectedPatientId);
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [showModal, setShowModal] = useState(false);
  const [selectedSchedule, setSelectedSchedule] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const notificationTarget = useMemo(() => {
    if (typeof window === "undefined") return null;

    const params = new URLSearchParams(window.location.search);
    const patientId = params.get("patient_id");
    const scheduleId = params.get("schedule_id");
    const scheduledAt = params.get("scheduled_at");

    if (!patientId && !scheduleId && !scheduledAt) {
      return null;
    }

    return {
      patientId: patientId ? Number(patientId) : null,
      scheduleId: scheduleId ? Number(scheduleId) : null,
      scheduledAt,
    };
  }, []);

  const [formData, setFormData] = useState({
    title: "",
    hospital_name: "",
    location: "",
    scheduled_at: "",
    description: "",
    patient_id: defaultPatientId || "",
  });

  const PATIENT_COLORS = ["#6c5ce7", "#00b894", "#e17055", "#0984e3", "#fdcb6e", "#d63031"];

  useEffect(() => {
    if (!defaultPatientId) return;

    setSelectedPatientId((prev) => {
      if (prev) return prev;
      return isCaregiver ? "all" : String(defaultPatientId);
    });

    setFormData((prev) => ({
      ...prev,
      patient_id: prev.patient_id || defaultPatientId,
    }));
  }, [defaultPatientId, isCaregiver]);

  useEffect(() => {
    if (!isCaregiver || !notificationTarget?.patientId) return;
    setSelectedPatientId((prev) =>
      String(prev) === String(notificationTarget.patientId) ? prev : String(notificationTarget.patientId)
    );
  }, [isCaregiver, notificationTarget]);

  const readCookie = (name) => {
    if (typeof document === "undefined") return null;
    const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
    return match ? decodeURIComponent(match[2]) : null;
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

  const loadSchedules = async () => {
    if (!normalizedPatients.length) {
      setSchedules([]);
      return;
    }

    setLoading(true);
    setErrorMessage(null);

    try {
      const responses = await Promise.all(
        normalizedPatients.map((patient) =>
          authFetch(`${API_PREFIX}/calendar/hospital?patient_id=${patient.id}`)
        )
      );

      const jsonList = await Promise.all(
        responses.map(async (res) => {
          if (!res.ok) {
            return { items: [] };
          }
          return res.json();
        })
      );

      const merged = jsonList.flatMap((data) => data.items || []);
      const dedupedMap = new Map();

      merged.forEach((item) => {
        dedupedMap.set(item.id, item);
      });

      const mergedSchedules = Array.from(dedupedMap.values()).sort(
        (a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at)
      );

      setSchedules(mergedSchedules);
    } catch (error) {
      console.error("Failed to load schedules:", error);
      setSchedules([]);
      setErrorMessage("일정을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSchedules();
  }, [normalizedPatients]);

  const getDaysInMonth = (date) => {
    const year = date.getFullYear();
    const month = date.getMonth();

    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const daysInMonth = lastDay.getDate();
    const startingDayOfWeek = (firstDay.getDay() + 6) % 7;
    const days = [];

    for (let i = 0; i < startingDayOfWeek; i++) {
      const prevMonthDay = new Date(year, month, -startingDayOfWeek + i + 1);
      days.push({ date: prevMonthDay, isCurrentMonth: false });
    }

    for (let i = 1; i <= daysInMonth; i++) {
      days.push({ date: new Date(year, month, i), isCurrentMonth: true });
    }

    const remainingDays = 42 - days.length;
    for (let i = 1; i <= remainingDays; i++) {
      days.push({ date: new Date(year, month + 1, i), isCurrentMonth: false });
    }

    return days;
  };

  const filteredSchedules = useMemo(() => {
    if (selectedPatientId === "all") return schedules;
    if (!selectedPatientId) return [];

    return schedules.filter((schedule) => schedule.patient_id === Number(selectedPatientId));
  }, [schedules, selectedPatientId]);

  const getSchedulesForDate = (date) => {
    return filteredSchedules.filter((schedule) => {
      const scheduleDate = new Date(schedule.scheduled_at);

      return (
        scheduleDate.getFullYear() === date.getFullYear() &&
        scheduleDate.getMonth() === date.getMonth() &&
        scheduleDate.getDate() === date.getDate()
      );
    });
  };

  const selectedDateSchedules = useMemo(() => {
    return getSchedulesForDate(selectedDate).sort(
      (a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at)
    );
  }, [filteredSchedules, selectedDate]);

  const highlightedScheduleId = useMemo(() => {
    if (!notificationTarget) return null;

    const matched = schedules.find((schedule) => {
      if (
        notificationTarget.patientId &&
        Number(schedule.patient_id) !== Number(notificationTarget.patientId)
      ) {
        return false;
      }

      if (
        notificationTarget.scheduleId &&
        Number(schedule.id) !== Number(notificationTarget.scheduleId)
      ) {
        return false;
      }

      if (
        notificationTarget.scheduledAt &&
        String(schedule.scheduled_at) !== String(notificationTarget.scheduledAt)
      ) {
        return false;
      }

      return true;
    });

    return matched?.id || null;
  }, [notificationTarget, schedules]);

  useEffect(() => {
    if (!highlightedScheduleId) return;

    const targetSchedule = schedules.find((schedule) => schedule.id === highlightedScheduleId);
    if (!targetSchedule) return;

    moveToScheduleDate(targetSchedule);

    const timer = window.setTimeout(() => {
      const target = document.getElementById(`schedule-item-${highlightedScheduleId}`);
      target?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 150);

    return () => window.clearTimeout(timer);
  }, [highlightedScheduleId, schedules]);

  const getPatientName = (patientId) => {
    const patient = normalizedPatients.find((p) => p.id === Number(patientId));
    return patient?.name || `복약자 ${patientId}`;
  };

  const getPatientColor = (patientId) => {
    const index = normalizedPatients.findIndex((p) => p.id === Number(patientId));
    if (index === -1) return "#6c5ce7";
    return PATIENT_COLORS[index % PATIENT_COLORS.length];
  };

  const isSameDay = (left, right) => {
    return (
      left.getFullYear() === right.getFullYear() &&
      left.getMonth() === right.getMonth() &&
      left.getDate() === right.getDate()
    );
  };

  const handlePrevMonth = () => {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1));
  };

  const handleNextMonth = () => {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1));
  };

  const handleToday = () => {
    const today = new Date();
    setCurrentDate(today);
    setSelectedDate(today);
  };

  const moveToScheduleDate = (schedule) => {
    const scheduleDate = new Date(schedule.scheduled_at);
    setCurrentDate(new Date(scheduleDate.getFullYear(), scheduleDate.getMonth(), 1));
    setSelectedDate(scheduleDate);
  };

  const handleSelectDate = (date) => {
    setSelectedDate(date);
    if (!isSameDay(currentDate, date)) {
      setCurrentDate(new Date(date.getFullYear(), date.getMonth(), 1));
    }
  };

  const handleAddSchedule = () => {
    const targetPatientId = selectedPatientId === "all" ? defaultPatientId : Number(selectedPatientId);
    const prefilledDate = selectedDate ? new Date(selectedDate) : new Date();
    prefilledDate.setHours(9, 0, 0, 0);

    setSelectedSchedule(null);
    setFormData({
      title: "",
      hospital_name: "",
      location: "",
      scheduled_at: prefilledDate.toISOString().slice(0, 16),
      description: "",
      patient_id: targetPatientId || "",
    });
    setShowModal(true);
  };

  const handleEditSchedule = (schedule) => {
    moveToScheduleDate(schedule);
    setSelectedSchedule(schedule);
    setFormData({
      title: schedule.title || "",
      hospital_name: schedule.hospital_name || "",
      location: schedule.location || "",
      scheduled_at: schedule.scheduled_at ? schedule.scheduled_at.slice(0, 16) : "",
      description: schedule.description || "",
      patient_id: schedule.patient_id,
    });
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage(null);

    try {
      if (selectedSchedule) {
        const res = await authFetch(`${API_PREFIX}/calendar/hospital/${selectedSchedule.id}`, {
          method: "PATCH",
          body: JSON.stringify(formData),
        });

        if (!res.ok) {
          setErrorMessage("일정 수정에 실패했습니다.");
          return;
        }
      } else {
        const res = await authFetch(`${API_PREFIX}/calendar/hospital`, {
          method: "POST",
          body: JSON.stringify(formData),
        });

        if (!res.ok) {
          setErrorMessage("일정 등록에 실패했습니다.");
          return;
        }
      }

      await loadSchedules();
      if (formData.scheduled_at) {
        const savedDate = new Date(formData.scheduled_at);
        setCurrentDate(new Date(savedDate.getFullYear(), savedDate.getMonth(), 1));
        setSelectedDate(savedDate);
      }
      setShowModal(false);
    } catch (error) {
      console.error("Failed to save schedule:", error);
      setErrorMessage("일정 저장 중 오류가 발생했습니다.");
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("일정을 삭제하시겠습니까?")) return;

    try {
      const res = await authFetch(`${API_PREFIX}/calendar/hospital/${id}`, {
        method: "DELETE",
      });

      if (!res.ok) {
        setErrorMessage("일정 삭제에 실패했습니다.");
        return;
      }

      await loadSchedules();
      setSelectedSchedule(null);
    } catch (error) {
      console.error("Failed to delete schedule:", error);
      setErrorMessage("일정 삭제 중 오류가 발생했습니다.");
    }
  };

  const days = getDaysInMonth(currentDate);
  const monthYear = currentDate.toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "long",
  });
  const selectedDateLabel = selectedDate.toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  });

  return (
    <>
      <AppLayout
        activeKey="schedule"
        title="스케줄"
        description="복약자별 병원 방문 일정을 확인하고 추가/수정할 수 있습니다."
        loginRole={loginRole}
        userName={userName}
        modeOptions={modeOptions}
        currentMode={currentMode}
        onModeChange={onModeChange}
      >
        <div className="container-fluid py-1">
          <div className="row g-3">
            <div className="col-md-3">
              <div className="card border-0 shadow-sm mb-3">
                <div className="card-body">
                {isCaregiver && (
                  <div className="mb-3">
                    <label className="form-label fw-semibold">복약자 선택</label>
                    <select
                      className="form-select"
                      value={selectedPatientId}
                      onChange={(e) => setSelectedPatientId(e.target.value)}
                      disabled={!normalizedPatients.length}
                    >
                      <option value="all">모두 보기</option>
                      {normalizedPatients.map((patient) => (
                        <option key={patient.id} value={String(patient.id)}>
                          {patient.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <button
                  className="btn btn-primary w-100 mb-3"
                  onClick={handleAddSchedule}
                  disabled={!normalizedPatients.length}
                >
                  + Add New Event
                </button>

                <h6 className="fw-bold mb-2">스케줄 요약</h6>
                <div className="small text-muted">
                  {isCaregiver
                    ? selectedPatientId === "all"
                      ? `전체 복약자의 등록된 병원 진료 예약 ${filteredSchedules.length}건`
                      : `선택한 복약자의 등록된 병원 진료 예약 ${filteredSchedules.length}건`
                    : `내 등록된 병원 진료 예약 ${filteredSchedules.length}건`}
                </div>

                <div className="small text-muted mt-2 mb-2">
                  최근 일정 {Math.min(filteredSchedules.length, 3)}건
                </div>

                {filteredSchedules.slice(0, 3).map((schedule) => (
                  <button
                    key={schedule.id}
                    type="button"
                    className="border-0 bg-transparent w-100 text-start p-0"
                    onClick={() => handleEditSchedule(schedule)}
                  >
                    <div
                      className="border-start border-3 ps-3 py-2 mt-2 rounded-end"
                      style={{
                        borderColor: getPatientColor(schedule.patient_id),
                        backgroundColor:
                          highlightedScheduleId === schedule.id ? "rgba(245, 158, 11, 0.14)" : "transparent",
                        boxShadow:
                          highlightedScheduleId === schedule.id
                            ? "0 0 0 3px rgba(245, 158, 11, 0.18)"
                            : "none",
                        transition: "all 0.2s ease",
                      }}
                    >
                      <div className="fw-semibold">{schedule.title}</div>
                      {isCaregiver && (
                        <div className="small text-muted">{getPatientName(schedule.patient_id)}</div>
                      )}
                      <div className="small text-muted">{schedule.hospital_name || "-"}</div>
                      <div className="small text-muted">{schedule.location || "-"}</div>
                      <div className="small text-muted">
                        {new Date(schedule.scheduled_at).toLocaleString("ko-KR")}
                      </div>
                    </div>
                  </button>
                ))}

                {filteredSchedules.length > 3 && (
                  <div className="small text-primary mt-2">
                    외 {filteredSchedules.length - 3}건의 일정이 더 있습니다.
                  </div>
                )}

                {!loading && filteredSchedules.length === 0 && (
                  <div className="small text-muted mt-3">등록된 일정이 없습니다.</div>
                )}
              </div>
            </div>

            <div className="card border-0 shadow-sm">
              <div className="card-body">
                <div className="d-flex justify-content-between align-items-center mb-2">
                  <h6 className="fw-bold mb-0">선택한 날짜 일정</h6>
                  <span className="badge text-bg-light">{selectedDateSchedules.length}건</span>
                </div>
                <div className="small text-muted mb-3">{selectedDateLabel}</div>

                {selectedDateSchedules.length === 0 ? (
                  <div className="small text-muted">선택한 날짜에 등록된 일정이 없습니다.</div>
                ) : (
                  selectedDateSchedules.map((schedule) => (
                    <button
                      key={schedule.id}
                      type="button"
                      className="border-0 bg-transparent w-100 text-start p-0"
                      onClick={() => handleEditSchedule(schedule)}
                    >
                      <div
                        id={`schedule-item-${schedule.id}`}
                        className="rounded-3 border px-3 py-2 mb-2"
                        style={{
                          backgroundColor:
                            highlightedScheduleId === schedule.id ? "#fff7d6" : "#fff",
                          borderColor:
                            highlightedScheduleId === schedule.id ? "#f59e0b" : undefined,
                          boxShadow:
                            highlightedScheduleId === schedule.id
                              ? "0 0 0 4px rgba(245, 158, 11, 0.18)"
                              : "none",
                          transition: "all 0.2s ease",
                        }}
                      >
                        <div className="d-flex align-items-center gap-2 mb-1 flex-wrap">
                          <span
                            className="rounded-pill"
                            style={{
                              width: 10,
                              height: 10,
                              backgroundColor: getPatientColor(schedule.patient_id),
                              display: "inline-block",
                            }}
                          />
                          <span className="fw-semibold">{schedule.title}</span>
                        </div>
                        {isCaregiver && (
                          <div className="small text-muted">{getPatientName(schedule.patient_id)}</div>
                        )}
                        <div className="small text-muted">{schedule.hospital_name || "-"}</div>
                        <div className="small text-muted">{schedule.location || "-"}</div>
                        <div className="small text-muted">
                          {new Date(schedule.scheduled_at).toLocaleString("ko-KR")}
                        </div>
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>
          </div>

          <div className="col-md-9">
            <div className="card border-0 shadow-sm">
              <div className="card-body">
                <div className="d-flex justify-content-between align-items-center mb-4 flex-wrap gap-2">
                  <div>
                    <h4 className="fw-bold mb-1">스케줄</h4>
                    <div className="small text-muted">월별 캘린더 기준으로 일정을 확인할 수 있습니다.</div>
                  </div>

                  <div className="d-flex align-items-center gap-2 flex-wrap">
                    <button className="btn btn-sm btn-outline-secondary" onClick={handleToday}>
                      Today
                    </button>
                    <button className="btn btn-sm btn-outline-secondary" onClick={handlePrevMonth}>
                      &lt;
                    </button>
                    <span className="fw-semibold">{monthYear}</span>
                    <button className="btn btn-sm btn-outline-secondary" onClick={handleNextMonth}>
                      &gt;
                    </button>
                  </div>
                </div>

                {errorMessage && <div className="alert alert-danger py-2">{errorMessage}</div>}

                {loading ? (
                  <div className="text-center py-5">
                    <div className="spinner-border" role="status">
                      <span className="visually-hidden">Loading...</span>
                    </div>
                  </div>
                ) : (
                  <div className="calendar-grid border rounded-4 overflow-hidden">
                    <div className="row g-0 border-bottom fw-semibold text-center" style={{ backgroundColor: "#f8f9fa" }}>
                      <div className="col p-2">MON</div>
                      <div className="col p-2">TUE</div>
                      <div className="col p-2">WED</div>
                      <div className="col p-2">THU</div>
                      <div className="col p-2">FRI</div>
                      <div className="col p-2">SAT</div>
                      <div className="col p-2">SUN</div>
                    </div>

                    {Array.from({ length: 6 }).map((_, weekIndex) => (
                      <div key={weekIndex} className="row g-0 border-bottom" style={{ minHeight: "110px" }}>
                        {days.slice(weekIndex * 7, (weekIndex + 1) * 7).map((day, dayIndex) => {
                          const daySchedules = getSchedulesForDate(day.date);
                          const isSelected = isSameDay(day.date, selectedDate);
                          const isToday = isSameDay(day.date, new Date());

                          return (
                            <div
                              key={dayIndex}
                              className={`col border-end p-2 ${!day.isCurrentMonth ? "text-muted" : ""}`}
                              style={{
                                backgroundColor: isSelected
                                  ? "#eef6ff"
                                  : day.isCurrentMonth
                                  ? "#fff"
                                  : "#f8f9fa",
                                cursor: "pointer",
                              }}
                              onClick={() => handleSelectDate(day.date)}
                            >
                              <div className="d-flex justify-content-end mb-1">
                                <span
                                  className="small px-2 py-1 rounded-pill"
                                  style={{
                                    backgroundColor: isToday ? "#dbeafe" : "transparent",
                                    color: isToday ? "#2563eb" : "inherit",
                                    fontWeight: isSelected ? 700 : 500,
                                  }}
                                >
                                  {day.date.getDate()}
                                </span>
                              </div>

                              {daySchedules.map((schedule) => (
                                <button
                                  key={schedule.id}
                                  type="button"
                                  className="small p-1 mb-1 rounded text-white border-0 w-100 text-start"
                                  style={{
                                    backgroundColor: getPatientColor(schedule.patient_id),
                                    cursor: "pointer",
                                    boxShadow:
                                      highlightedScheduleId === schedule.id
                                        ? "0 0 0 3px rgba(245, 158, 11, 0.28)"
                                        : "none",
                                  }}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleEditSchedule(schedule);
                                  }}
                                  title={`${getPatientName(schedule.patient_id)} / ${schedule.title}`}
                                >
                                  {isCaregiver && selectedPatientId === "all"
                                    ? `[${getPatientName(schedule.patient_id)}] ${schedule.title}`
                                    : schedule.title}
                                </button>
                              ))}
                            </div>
                          );
                        })}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {showModal && (
        <div className="modal show d-block" style={{ backgroundColor: "rgba(0,0,0,0.5)" }}>
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">{selectedSchedule ? "일정 수정" : "일정 추가"}</h5>
                <button type="button" className="btn-close" onClick={() => setShowModal(false)}></button>
              </div>

              <form onSubmit={handleSubmit}>
                <div className="modal-body">
                  {isCaregiver && (
                    <div className="mb-3">
                      <label className="form-label">복약자</label>
                      <select
                        className="form-select"
                        value={formData.patient_id}
                        onChange={(e) =>
                          setFormData({ ...formData, patient_id: Number(e.target.value) })
                        }
                        required
                      >
                        {normalizedPatients.map((patient) => (
                          <option key={patient.id} value={patient.id}>
                            {patient.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}

                  <div className="mb-3">
                    <label className="form-label">제목</label>
                    <input
                      type="text"
                      className="form-control"
                      value={formData.title}
                      onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                      required
                    />
                  </div>

                  <div className="mb-3">
                    <label className="form-label">병원명</label>
                    <input
                      type="text"
                      className="form-control"
                      value={formData.hospital_name}
                      onChange={(e) => setFormData({ ...formData, hospital_name: e.target.value })}
                    />
                  </div>

                  <div className="mb-3">
                    <label className="form-label">장소</label>
                    <input
                      type="text"
                      className="form-control"
                      value={formData.location}
                      onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                    />
                  </div>

                  <div className="mb-3">
                    <label className="form-label">예약 일시</label>
                    <input
                      type="datetime-local"
                      className="form-control"
                      value={formData.scheduled_at}
                      onChange={(e) => setFormData({ ...formData, scheduled_at: e.target.value })}
                      required
                    />
                  </div>

                  <div className="mb-3">
                    <label className="form-label">메모</label>
                    <textarea
                      className="form-control"
                      rows="3"
                      value={formData.description}
                      onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    ></textarea>
                  </div>
                </div>

                <div className="modal-footer">
                  {selectedSchedule && (
                    <button
                      type="button"
                      className="btn btn-danger me-auto"
                      onClick={async () => {
                        await handleDelete(selectedSchedule.id);
                        setShowModal(false);
                      }}
                    >
                      삭제
                    </button>
                  )}

                  <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>
                    취소
                  </button>

                  <button type="submit" className="btn btn-primary">
                    {selectedSchedule ? "수정" : "추가"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
      </AppLayout>
    </>
  );
};

export default SchedulePage;
