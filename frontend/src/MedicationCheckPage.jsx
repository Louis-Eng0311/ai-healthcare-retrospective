import React, { useEffect, useMemo, useRef, useState } from "react";
import AppLayout from "./components/AppLayout.jsx";

const API_PREFIX = "/api/v1";

const toDateKey = (value) => {
  if (!value) return "";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const getMonthRange = (value) => {
  const date = value ? new Date(`${value}T00:00:00`) : new Date();
  if (Number.isNaN(date.getTime())) {
    return { from: "", to: "" };
  }
  const monthStart = new Date(date.getFullYear(), date.getMonth(), 1);
  const monthEnd = new Date(date.getFullYear(), date.getMonth() + 1, 0);
  return {
    from: toDateKey(monthStart),
    to: toDateKey(monthEnd),
  };
};

const STATUS_META = {
  taken: { label: "복용완료", color: "#2563eb", dot: "#14b8a6", bg: "#eef4ff" },
  pending: { label: "복용대기", color: "#b7791f", dot: "#f4b400", bg: "#fff8e8" },
  missed: { label: "미복용", color: "#ef4444", dot: "#ef4444", bg: "#fff1f2" },
  skipped: { label: "건너뜀", color: "#6b7280", dot: "#9ca3af", bg: "#f3f4f6" },
};

const MEAL_ORDER = ["아침", "점심", "저녁", "취침 전"];

const MedicationCheckPage = ({
  linkedPatients = [],
  myPatient = null,
  loginRole = "PATIENT",
  me = null,
  userName = "사용자",
  modeOptions = [],
  currentMode = "PATIENT",
  onModeChange,
}) => {
  const effectiveMode = currentMode || loginRole;
  const isCaregiver = effectiveMode === "CAREGIVER" || effectiveMode === "GUARDIAN";

  const patients = useMemo(() => {
    if (isCaregiver) {
      return (linkedPatients || [])
        .filter((patient) => patient?.id)
        .map((patient) => ({
          id: Number(patient.id),
          name: patient.name || patient.display_name || `피보호자 ${patient.id}`,
          ageLabel: patient.ageLabel || patient.subtitle || "",
          imageUrl: patient.imageUrl || "",
        }));
    }

    return myPatient?.id
      ? [
          {
            id: Number(myPatient.id),
            name: myPatient.name || myPatient.display_name || "복약자",
            ageLabel: myPatient.ageLabel || "",
            imageUrl: myPatient.imageUrl || "",
          },
        ]
      : [];
  }, [isCaregiver, linkedPatients, myPatient]);
  const [selectedPatientId, setSelectedPatientId] = useState(
    isCaregiver ? "all" : patients[0]?.id || ""
  );
  const [selectedDate, setSelectedDate] = useState(() =>
    new Date().toISOString().slice(0, 10)
  );
  const selectedMonthKey = useMemo(() => {
    const date = selectedDate ? new Date(`${selectedDate}T00:00:00`) : new Date();
    if (Number.isNaN(date.getTime())) return "";
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
  }, [selectedDate]);

  const [statusData, setStatusData] = useState([]);
  const [calendarStatusData, setCalendarStatusData] = useState([]);
  const [summaryMap, setSummaryMap] = useState({});
  const [loading, setLoading] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState(null);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [selectedMealLabel, setSelectedMealLabel] = useState("아침");
  const [selectedCaregiverMealByPatient, setSelectedCaregiverMealByPatient] = useState({});
  const [mealReminderDraft, setMealReminderDraft] = useState(null);
  const [notificationTargetApplied, setNotificationTargetApplied] = useState(false);
  const statusLoadVersionRef = useRef(0);
  const calendarLoadVersionRef = useRef(0);
  const calendarCacheRef = useRef(new Map());
  const notificationTarget = useMemo(() => {
    if (typeof window === "undefined") return null;

    const params = new URLSearchParams(window.location.search);
    const patientId = params.get("patient_id");
    const scheduleId = params.get("schedule_id");
    const scheduleTimeId = params.get("schedule_time_id");
    const scheduledAt = params.get("scheduled_at");
    const scheduledDate = params.get("scheduled_date");
    const mealLabel = params.get("meal_label");

    if (!patientId && !scheduleId && !scheduleTimeId && !scheduledAt && !scheduledDate && !mealLabel) {
      return null;
    }

    return {
      patientId: patientId ? Number(patientId) : null,
      scheduleId: scheduleId ? Number(scheduleId) : null,
      scheduleTimeId: scheduleTimeId ? Number(scheduleTimeId) : null,
      scheduledAt,
      scheduledDate: scheduledDate || (scheduledAt ? String(scheduledAt).slice(0, 10) : null),
      mealLabel,
    };
  }, []);

  useEffect(() => {
    if (isCaregiver) {
      if (patients.length === 0) {
        setSelectedPatientId("");
        return;
      }
      if (selectedPatientId === "all") {
        return;
      }
      const hasSelectedPatient = patients.some(
        (patient) => String(patient.id) === String(selectedPatientId)
      );
      if (!hasSelectedPatient) {
        setSelectedPatientId("all");
      }
      return;
    }

    setSelectedPatientId(patients[0]?.id || "");
    setSelectedIds([]);
    setSelectedCaregiverMealByPatient({});
  }, [isCaregiver, patients, selectedPatientId]);

  useEffect(() => {
    if (!notificationTarget?.scheduledDate) return;
    setSelectedDate((prev) =>
      prev === notificationTarget.scheduledDate ? prev : notificationTarget.scheduledDate
    );
  }, [notificationTarget]);

  useEffect(() => {
    if (!isCaregiver || !notificationTarget?.patientId) return;
    setSelectedPatientId((prev) =>
      String(prev) === String(notificationTarget.patientId) ? prev : String(notificationTarget.patientId)
    );
  }, [isCaregiver, notificationTarget]);

  useEffect(() => {
    if (!notificationTarget || notificationTargetApplied || typeof window === "undefined") return;

    const params = new URLSearchParams(window.location.search);
    params.delete("patient_id");
    params.delete("schedule_id");
    params.delete("schedule_time_id");
    params.delete("scheduled_at");
    params.delete("scheduled_date");
    params.delete("meal_label");
    const nextUrl = `${window.location.pathname}${params.toString() ? `?${params.toString()}` : ""}`;
    window.history.replaceState({}, "", nextUrl);
    setNotificationTargetApplied(true);
  }, [notificationTarget, notificationTargetApplied]);

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

  const getErrorMessage = (body, status) => {
    if (Array.isArray(body?.detail)) {
      return body.detail
        .map((d) => d?.msg || d?.message || JSON.stringify(d))
        .join(", ");
    }

    if (typeof body?.detail === "string") {
      return body.detail;
    }

    if (typeof body?.message === "string") {
      return body.message;
    }

    if (typeof body?.error?.message === "string") {
      return body.error.message;
    }

    return `status ${status}`;
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

  const inferMealLabel = (scheduledAt) => {
    try {
      const date = new Date(scheduledAt);
      const hour = date.getHours();

      if (hour < 10) return "아침";
      if (hour < 15) return "점심";
      if (hour < 20) return "저녁";
      return "취침 전";
    } catch {
      return "복약";
    }
  };

  const formatTime = (scheduledAt) => {
    try {
      const date = new Date(scheduledAt);
      return date.toLocaleTimeString("ko-KR", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
    } catch {
      return "";
    }
  };

  const normalizeStatus = (raw) => {
    const value = String(raw || "").toLowerCase();
    if (value === "taken") return "taken";
    if (value === "missed") return "missed";
    if (value === "skipped") return "skipped";
    return "pending";
  };

  const flattenStatusResponse = (responseData, patientId) => {
    const days = responseData?.days || [];
    const patientInfo = patients.find((p) => p.id === Number(patientId));

    if (!Array.isArray(days)) return [];

    return days.flatMap((dayBlock) => {
      const day = dayBlock?.day;
      const items = Array.isArray(dayBlock?.items) ? dayBlock.items : [];

      return items.map((item, index) => ({
        id: `${patientId}-${item.schedule_id}-${item.schedule_time_id}-${item.scheduled_at || index}`,
        patient_id: Number(patientId),
        patient_name: patientInfo?.name || `복약자 ${patientId}`,
        patient_age_label: patientInfo?.ageLabel || "",
        imageUrl: patientInfo?.imageUrl || "",
        day,
        schedule_id: Number(item.schedule_id),
        schedule_time_id: Number(item.schedule_time_id),
        patient_med_id: Number(item.patient_med_id),
        medication_name: item.medication_name || null,
        scheduled_at: item.scheduled_at,
        scheduled_date: item.scheduled_at ? String(item.scheduled_at).slice(0, 10) : day,
        scheduled_time: formatTime(item.scheduled_at),
        meal_label: inferMealLabel(item.scheduled_at),
        status: normalizeStatus(item.status),
        taken_at: item.taken_at,
        note: item.note,
      }));
    });
  };

  const fetchPatientStatus = async (patientId) => {
    const params = new URLSearchParams();
    params.set("patient_id", String(patientId));
    params.set("from", selectedDate);
    params.set("to", selectedDate);

    const res = await authFetch(`${API_PREFIX}/schedules/status?${params.toString()}`);
    const body = await safeJson(res);

    if (!res.ok) {
      throw new Error(getErrorMessage(body, res.status));
    }

    const data = body?.data || body || {};

    return {
      patientId,
      items: flattenStatusResponse(data, patientId),
      summary: data?.summary || null,
    };
  };

  const fetchPatientCalendarStatus = async (patientId, from, to) => {
    const params = new URLSearchParams();
    params.set("patient_id", String(patientId));
    params.set("from", from);
    params.set("to", to);

    const res = await authFetch(`${API_PREFIX}/schedules/status?${params.toString()}`);
    const body = await safeJson(res);

    if (!res.ok) {
      throw new Error(getErrorMessage(body, res.status));
    }

    const data = body?.data || body || {};
    return flattenStatusResponse(data, patientId);
  };

  const resolveTargetPatientIds = () => {
    if (isCaregiver) {
      if (selectedPatientId === "all") {
        return patients.map((p) => p.id);
      }
      if (selectedPatientId) {
        return [Number(selectedPatientId)];
      }
      return [];
    }

    if (patients[0]?.id) {
      return [patients[0].id];
    }

    return [];
  };

  const loadStatus = async () => {
    const requestVersion = statusLoadVersionRef.current + 1;
    statusLoadVersionRef.current = requestVersion;
    setLoading(true);
    setError(null);

    try {
      const targets = resolveTargetPatientIds();

      if (targets.length === 0) {
        if (requestVersion !== statusLoadVersionRef.current) return;
        setStatusData([]);
        setSummaryMap({});
        return;
      }

      const results = await Promise.all(targets.map((patientId) => fetchPatientStatus(patientId)));

      const mergedItems = results.flatMap((result) => result.items);
      const nextSummaryMap = {};
      results.forEach((result) => {
        nextSummaryMap[result.patientId] = result.summary;
      });

      if (requestVersion !== statusLoadVersionRef.current) return;
      setStatusData(mergedItems);
      setSummaryMap(nextSummaryMap);
    } catch (err) {
      if (requestVersion !== statusLoadVersionRef.current) return;
      setError(err.message || "복약 현황을 불러오지 못했습니다.");
      setStatusData([]);
      setSummaryMap({});
    } finally {
      if (requestVersion !== statusLoadVersionRef.current) return;
      setLoading(false);
    }
  };

  const loadCalendarStatus = async () => {
    const requestVersion = calendarLoadVersionRef.current + 1;
    calendarLoadVersionRef.current = requestVersion;
    const targets = resolveTargetPatientIds();
    if (targets.length === 0) {
      if (requestVersion !== calendarLoadVersionRef.current) return;
      setCalendarStatusData([]);
      return;
    }

    const { from, to } = getMonthRange(selectedDate);
    const cacheKey = `${targets.join(",")}:${from}:${to}`;
    const cachedRows = calendarCacheRef.current.get(cacheKey);
    if (cachedRows) {
      if (requestVersion !== calendarLoadVersionRef.current) return;
      setCalendarStatusData(cachedRows);
      return;
    }

    try {
      const rows = await Promise.all(
        targets.map((patientId) => fetchPatientCalendarStatus(patientId, from, to))
      );
      const flattenedRows = rows.flat();
      calendarCacheRef.current.set(cacheKey, flattenedRows);
      if (requestVersion !== calendarLoadVersionRef.current) return;
      setCalendarStatusData(flattenedRows);
    } catch {
      if (requestVersion !== calendarLoadVersionRef.current) return;
      setCalendarStatusData([]);
    }
  };

  const refreshMedicationView = async () => {
    await Promise.all([loadStatus(), loadCalendarStatus()]);
  };

  useEffect(() => {
    loadStatus();
  }, [selectedPatientId, selectedDate, isCaregiver, patients.length]);

  useEffect(() => {
    let active = true;

    const loadCalendarStatusEffect = async () => {
      try {
        await loadCalendarStatus();
      } catch {
        if (active) {
          setCalendarStatusData([]);
        }
      }
    };

    loadCalendarStatusEffect();

    return () => {
      active = false;
    };
  }, [selectedPatientId, selectedMonthKey, isCaregiver, patients.length]);

  const filteredItems = useMemo(() => {
    if (!isCaregiver || selectedPatientId === "all") return statusData;
    return statusData.filter((item) => String(item.patient_id) === String(selectedPatientId));
  }, [statusData, selectedPatientId, isCaregiver]);

  const groupedByPatient = useMemo(() => {
    const map = new Map();

    filteredItems.forEach((item) => {
      const current = map.get(item.patient_id) || {
        patient_id: item.patient_id,
        patient_name: item.patient_name,
        patient_age_label: item.patient_age_label,
        imageUrl: item.imageUrl,
        items: [],
      };
      current.items.push(item);
      map.set(item.patient_id, current);
    });

    return Array.from(map.values()).map((group) => ({
      ...group,
      items: group.items.sort((a, b) => {
        const aIndex = MEAL_ORDER.includes(a.meal_label) ? MEAL_ORDER.indexOf(a.meal_label) : 999;
        const bIndex = MEAL_ORDER.includes(b.meal_label) ? MEAL_ORDER.indexOf(b.meal_label) : 999;
        if (aIndex !== bIndex) return aIndex - bIndex;
        return String(a.scheduled_at).localeCompare(String(b.scheduled_at));
      }),
    }));
  }, [filteredItems]);

  const summary = useMemo(() => {
    const patientCount = groupedByPatient.length;
    const takenCount = filteredItems.filter((item) => item.status === "taken").length;
    const missedCount = filteredItems.filter((item) => item.status === "missed").length;
    return { patientCount, takenCount, missedCount };
  }, [filteredItems, groupedByPatient]);

  const getMedicationLabel = (item) =>
    item.medication_name || `복약 항목 #${item.patient_med_id}`;

  const getMealStatusSummary = (items) => {
    const takenCount = items.filter((item) => item.status === "taken").length;
    const skippedCount = items.filter((item) => item.status === "skipped").length;
    const missedCount = items.filter((item) => item.status === "missed").length;
    const pendingCount = items.filter((item) => item.status === "pending").length;

    return { takenCount, skippedCount, missedCount, pendingCount };
  };

  const groupedByMealForSelf = useMemo(() => {
    const groups = new Map();

    filteredItems.forEach((item) => {
      const key = item.meal_label || "기타";
      const current = groups.get(key) || { meal_label: key, items: [] };
      current.items.push(item);
      groups.set(key, current);
    });

    return Array.from(groups.values()).sort((a, b) => {
      const aIndex = MEAL_ORDER.includes(a.meal_label) ? MEAL_ORDER.indexOf(a.meal_label) : 999;
      const bIndex = MEAL_ORDER.includes(b.meal_label) ? MEAL_ORDER.indexOf(b.meal_label) : 999;
      return aIndex - bIndex;
    });
  }, [filteredItems]);

  const groupedByPatientWithMeals = useMemo(() => {
    return groupedByPatient.map((group) => {
      const mealMap = new Map();

      group.items.forEach((item) => {
        const mealKey = item.meal_label || "기타";
        const current = mealMap.get(mealKey) || { meal_label: mealKey, items: [] };
        current.items.push(item);
        mealMap.set(mealKey, current);
      });

      const meals = Array.from(mealMap.values())
        .map((mealGroup) => ({
          ...mealGroup,
          items: mealGroup.items.sort((a, b) => String(a.scheduled_at).localeCompare(String(b.scheduled_at))),
          summary: getMealStatusSummary(mealGroup.items),
        }))
        .sort((a, b) => {
          const aIndex = MEAL_ORDER.includes(a.meal_label) ? MEAL_ORDER.indexOf(a.meal_label) : 999;
          const bIndex = MEAL_ORDER.includes(b.meal_label) ? MEAL_ORDER.indexOf(b.meal_label) : 999;
          return aIndex - bIndex;
        });

      return {
        ...group,
        meals,
      };
    });
  }, [groupedByPatient]);

  const highlightedItemId = useMemo(() => {
    if (!notificationTarget) return null;

    const targetScheduledAt = notificationTarget.scheduledAt
      ? String(notificationTarget.scheduledAt)
      : null;
    const targetScheduledDate = notificationTarget.scheduledDate
      ? String(notificationTarget.scheduledDate)
      : null;
    const targetMealLabel = notificationTarget.mealLabel ? String(notificationTarget.mealLabel) : null;

    const matched = filteredItems.find((item) => {
      if (
        notificationTarget.patientId &&
        Number(item.patient_id) !== Number(notificationTarget.patientId)
      ) {
        return false;
      }

      if (
        notificationTarget.scheduleId &&
        Number(item.schedule_id) !== Number(notificationTarget.scheduleId)
      ) {
        return false;
      }

      if (
        notificationTarget.scheduleTimeId &&
        Number(item.schedule_time_id) !== Number(notificationTarget.scheduleTimeId)
      ) {
        return false;
      }

      if (targetScheduledDate && String(item.scheduled_date) !== targetScheduledDate) {
        return false;
      }

      if (targetMealLabel && String(item.meal_label) !== targetMealLabel) {
        return false;
      }

      if (targetScheduledAt && String(item.scheduled_at) !== targetScheduledAt) {
        return false;
      }

      return true;
    });

    return matched?.id || null;
  }, [filteredItems, notificationTarget]);

  useEffect(() => {
    if (!highlightedItemId) return;

    const timer = window.setTimeout(() => {
      const target = document.getElementById(`medication-item-${highlightedItemId}`);
      target?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 150);

    return () => window.clearTimeout(timer);
  }, [highlightedItemId]);

  useEffect(() => {
    if (groupedByMealForSelf.length === 0) return;

    if (
      !notificationTargetApplied &&
      notificationTarget?.mealLabel &&
      groupedByMealForSelf.some((group) => group.meal_label === notificationTarget.mealLabel) &&
      selectedMealLabel !== notificationTarget.mealLabel
    ) {
      setSelectedMealLabel(notificationTarget.mealLabel);
      return;
    }

    const highlightedItem = filteredItems.find((item) => item.id === highlightedItemId);
    const highlightedMeal = highlightedItem?.meal_label;
    if (
      highlightedMeal &&
      groupedByMealForSelf.some((group) => group.meal_label === highlightedMeal) &&
      selectedMealLabel !== highlightedMeal
    ) {
      setSelectedMealLabel(highlightedMeal);
      return;
    }

    if (!groupedByMealForSelf.some((group) => group.meal_label === selectedMealLabel)) {
      setSelectedMealLabel(groupedByMealForSelf[0].meal_label);
    }
  }, [groupedByMealForSelf, highlightedItemId, filteredItems, selectedMealLabel, notificationTarget, notificationTargetApplied]);

  const selectedMealGroup = useMemo(() => {
    return (
      groupedByMealForSelf.find((group) => group.meal_label === selectedMealLabel) ||
      groupedByMealForSelf[0] ||
      null
    );
  }, [groupedByMealForSelf, selectedMealLabel]);

  const selectedMealSummary = useMemo(() => {
    if (!selectedMealGroup) {
      return null;
    }

    return getMealStatusSummary(selectedMealGroup.items);
  }, [selectedMealGroup]);

  const monthlyCalendar = useMemo(() => {
    const selected = selectedDate ? new Date(`${selectedDate}T00:00:00`) : new Date();
    if (Number.isNaN(selected.getTime())) {
      return { monthLabel: "", weeks: [] };
    }

    const firstDay = new Date(selected.getFullYear(), selected.getMonth(), 1);
    const lastDay = new Date(selected.getFullYear(), selected.getMonth() + 1, 0);
    const startWeekday = firstDay.getDay();
    const totalDays = lastDay.getDate();

    const dayMap = new Map();
    calendarStatusData.forEach((item) => {
      const dateKey = item.scheduled_date || (item.scheduled_at ? String(item.scheduled_at).slice(0, 10) : "");
      if (!dateKey) return;
      const current = dayMap.get(dateKey) || {
        taken: 0,
        missed: 0,
        pending: 0,
        skipped: 0,
      };
      current[item.status] = (current[item.status] || 0) + 1;
      dayMap.set(dateKey, current);
    });

    const cells = [];
    for (let i = 0; i < startWeekday; i += 1) {
      cells.push(null);
    }

    for (let day = 1; day <= totalDays; day += 1) {
      const date = new Date(selected.getFullYear(), selected.getMonth(), day);
      const dateKey = toDateKey(date);
      cells.push({
        day,
        dateKey,
        summary: dayMap.get(dateKey) || null,
        isToday: dateKey === toDateKey(new Date()),
        isSelected: dateKey === selectedDate,
      });
    }

    while (cells.length % 7 !== 0) {
      cells.push(null);
    }

    const weeks = [];
    for (let index = 0; index < cells.length; index += 7) {
      weeks.push(cells.slice(index, index + 7));
    }

    return {
      monthLabel: new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "long" }).format(firstDay),
      weeks,
    };
  }, [calendarStatusData, selectedDate]);

  const toggleSelectedPatient = (patientId) => {
    setSelectedIds((prev) =>
      prev.includes(patientId)
        ? prev.filter((id) => id !== patientId)
        : [...prev, patientId]
    );
  };

  const toggleAllSelected = () => {
    const allIds = groupedByPatient.map((group) => group.patient_id);
    if (selectedIds.length === allIds.length) {
      setSelectedIds([]);
      return;
    }
    setSelectedIds(allIds);
  };

  const toggleCaregiverMeal = (patientId, mealLabel) => {
    setSelectedCaregiverMealByPatient((prev) => ({
      ...prev,
      [patientId]: mealLabel,
    }));
  };

  const openMealReminderConfirm = (patientId, patientName, mealGroup) => {
    const targets = mealGroup.items.filter(
      (item) => item.status !== "taken" && item.status !== "skipped"
    );

    if (targets.length === 0) {
      setSuccessMessage(`${mealGroup.meal_label} 시간대는 이미 모두 처리되었습니다.`);
      return;
    }

    setMealReminderDraft({
      patientId,
      patientName,
      mealGroup,
      medicationNames: formatReminderMedicationNames(targets),
      pendingCount: targets.length,
    });
  };

  const closeMealReminderConfirm = () => {
    setMealReminderDraft(null);
  };

  const handleCheck = async (item) => {
    setActionLoadingId(item.id);
    setError(null);
    setSuccessMessage(null);

    try {
      const res = await authFetch(`${API_PREFIX}/schedules/${item.schedule_id}/check`, {
        method: "POST",
        body: JSON.stringify({
          schedule_time_id: item.schedule_time_id,
          scheduled_date: item.scheduled_date,
        }),
      });

      const body = await safeJson(res);

      if (!res.ok) {
        throw new Error(getErrorMessage(body, res.status));
      }

      setStatusData((prev) =>
        prev.map((current) =>
          current.id === item.id
            ? {
                ...current,
                status: "taken",
                taken_at: body?.data?.taken_at || body?.taken_at || new Date().toISOString(),
              }
            : current
        )
      );
      setSuccessMessage(`${item.scheduled_time} 복약 상태를 복용 완료로 반영했습니다.`);
      await refreshMedicationView();
    } catch (err) {
      setError(err.message || "복용 완료 처리에 실패했습니다.");
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleSkip = async (item) => {
    setActionLoadingId(item.id);
    setError(null);
    setSuccessMessage(null);

    try {
      const res = await authFetch(`${API_PREFIX}/schedules/${item.schedule_id}/skip`, {
        method: "POST",
        body: JSON.stringify({
          schedule_time_id: item.schedule_time_id,
          scheduled_date: item.scheduled_date,
        }),
      });

      const body = await safeJson(res);

      if (!res.ok) {
        throw new Error(getErrorMessage(body, res.status));
      }

      setStatusData((prev) =>
        prev.map((current) =>
          current.id === item.id
            ? {
                ...current,
                status: "skipped",
                taken_at: null,
              }
            : current
        )
      );
      setSuccessMessage(`${item.scheduled_time} 복약 상태를 건너뜀으로 반영했습니다.`);
      await refreshMedicationView();
    } catch (err) {
      setError(err.message || "건너뛰기 처리에 실패했습니다.");
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleUndo = async (item) => {
    setActionLoadingId(item.id);
    setError(null);
    setSuccessMessage(null);

    try {
      const res = await authFetch(`${API_PREFIX}/schedules/${item.schedule_id}/check`, {
        method: "DELETE",
        body: JSON.stringify({
          schedule_time_id: item.schedule_time_id,
          scheduled_date: item.scheduled_date,
        }),
      });

      const body = await safeJson(res);

      if (!res.ok) {
        throw new Error(getErrorMessage(body, res.status));
      }

      setStatusData((prev) =>
        prev.map((current) =>
          current.id === item.id
            ? { ...current, status: "pending", taken_at: null }
            : current
        )
      );
      setSuccessMessage(`${item.scheduled_time} 복약 상태를 다시 확인 전으로 되돌렸습니다.`);
      await refreshMedicationView();
    } catch (err) {
      setError(err.message || "복약 기록 취소에 실패했습니다.");
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleBulkCheck = async (items, mealLabel) => {
    const targets = items.filter((item) => item.status !== "taken" && item.status !== "skipped");
    const actionLabel = mealLabel === "caregiver-visible" ? "보이는 항목" : mealLabel;
    if (targets.length === 0) {
      setSuccessMessage(`${actionLabel}은 이미 모두 처리되었습니다.`);
      return;
    }

    setActionLoadingId(`bulk-${mealLabel}`);
    setError(null);
    setSuccessMessage(null);

    try {
      for (const item of targets) {
        const res = await authFetch(`${API_PREFIX}/schedules/${item.schedule_id}/check`, {
          method: "POST",
          body: JSON.stringify({
            schedule_time_id: item.schedule_time_id,
            scheduled_date: item.scheduled_date,
          }),
        });

        const body = await safeJson(res);
        if (!res.ok) {
          throw new Error(getErrorMessage(body, res.status));
        }

        setStatusData((prev) =>
          prev.map((current) =>
            current.id === item.id
              ? {
                  ...current,
                  status: "taken",
                  taken_at: body?.data?.taken_at || body?.taken_at || new Date().toISOString(),
                }
              : current
          )
        );
      }

      setSuccessMessage(`${actionLabel} 복약 항목 ${targets.length}건을 한 번에 복용완료 처리했습니다.`);
      await refreshMedicationView();
    } catch (err) {
      setError(err.message || "일괄 복용완료 처리에 실패했습니다.");
    } finally {
      setActionLoadingId(null);
    }
  };

  const formatReminderMedicationNames = (items) => {
    const names = Array.from(
      new Set(
        items
          .map((item) => getMedicationLabel(item))
          .filter((name) => typeof name === "string" && name.trim())
      )
    );

    if (names.length === 0) {
      return "복약 항목";
    }

    if (names.length <= 3) {
      return names.join(", ");
    }

    return `${names.slice(0, 3).join(", ")} 외 ${names.length - 3}개`;
  };

  const handleMealReminder = async (patientId, patientName, mealGroup) => {
    const targets = mealGroup.items.filter(
      (item) => item.status !== "taken" && item.status !== "skipped"
    );

    if (targets.length === 0) {
      setSuccessMessage(`${mealGroup.meal_label} 시간대는 이미 모두 처리되었습니다.`);
      return;
    }

    const hasMissed = targets.some((item) => item.status === "missed");
    const medicationNames = formatReminderMedicationNames(targets);
    const actionKey = `remind-${patientId}-${mealGroup.meal_label}`;

    setActionLoadingId(actionKey);
    setError(null);
    setSuccessMessage(null);

    try {
      const res = await authFetch(`${API_PREFIX}/notifications/remind`, {
        method: "POST",
        body: JSON.stringify({
          patient_id: Number(patientId),
          type: hasMissed ? "missed_alert" : "intake_reminder",
          title: `${mealGroup.meal_label} 복약 다시 알리기`,
          message: `${patientName ? `${patientName}님의 ` : ""}${mealGroup.meal_label} 복약 시간입니다. ${medicationNames} 복용 여부를 확인해 주세요.`,
        }),
      });

      const body = await safeJson(res);
      if (!res.ok) {
        throw new Error(getErrorMessage(body, res.status));
      }

      setSuccessMessage(`${patientName}님의 ${mealGroup.meal_label} 복약 리마인드를 보냈습니다.`);
    } catch (err) {
      setError(err.message || "복약 리마인드 전송에 실패했습니다.");
    } finally {
      setActionLoadingId(null);
    }
  };

  useEffect(() => {
    if (!isCaregiver) return;

    setSelectedCaregiverMealByPatient((prev) => {
      const next = { ...prev };
      let changed = false;

      groupedByPatientWithMeals.forEach((group) => {
        const availableMeals = group.meals || [];
        if (availableMeals.length === 0) {
          if (next[group.patient_id]) {
            delete next[group.patient_id];
            changed = true;
          }
          return;
        }

        const currentMeal = next[group.patient_id];
        const exists = availableMeals.some((meal) => meal.meal_label === currentMeal);
        if (exists) return;

        const defaultMeal =
          availableMeals.find((meal) => meal.summary.missedCount > 0)?.meal_label ||
          availableMeals[0].meal_label;
        next[group.patient_id] = defaultMeal;
        changed = true;
      });

      return changed ? next : prev;
    });
  }, [groupedByPatientWithMeals, isCaregiver]);

  useEffect(() => {
    if (!successMessage) return undefined;

    const timer = window.setTimeout(() => {
      setSuccessMessage(null);
    }, 2500);

    return () => window.clearTimeout(timer);
  }, [successMessage]);

  const goToNotificationPage = (patientId, item) => {
    const patientName =
      item?.patient_name ||
      patients.find((p) => p.id === Number(patientId))?.name ||
      "";

    const params = new URLSearchParams();

    if (patientId) params.set("patient_id", String(patientId));
    if (item?.schedule_id) params.set("schedule_id", String(item.schedule_id));

    params.set("prefill", "1");
    params.set("type", "missed_alert");
    params.set("title", "복약 확인 요청");
    params.set(
      "message",
      `${patientName ? `${patientName} ` : ""}복용 기록이 없어 확인이 필요합니다. 복용 여부를 확인해 주세요.`
    );

    window.location.href = `/app/notifications?${params.toString()}`;
  };

  const formatSelectedDate = () => {
    try {
      return new Intl.DateTimeFormat("ko-KR", {
        year: "numeric",
        month: "long",
        day: "numeric",
        weekday: "long",
      }).format(new Date(selectedDate));
    } catch {
      return selectedDate;
    }
  };

  const renderStatusLegend = () => (
    <div className="d-flex align-items-center justify-content-end gap-3 flex-wrap small text-muted mt-3">
      {Object.entries(STATUS_META).map(([key, value]) => (
        <div className="d-flex align-items-center gap-1" key={key}>
          <span
            style={{
              width: 12,
              height: 12,
              borderRadius: "999px",
              display: "inline-block",
              backgroundColor: value.dot,
            }}
          />
          {value.label}
        </div>
      ))}
    </div>
  );

  return (
    <AppLayout
      activeKey="medication-check"
      title="복약 체크"
      description={isCaregiver ? "연동 복약자의 복약 상태를 확인하고 필요한 알림을 보낼 수 있습니다." : "오늘 복약 일정을 확인하고 상태를 기록하세요."}
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
              <h6 className="fw-bold mb-3">기준 날짜</h6>
              <input
                className="form-control"
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
              />
            </div>
          </div>

          <div className="card border-0 shadow-sm mb-3">
            <div className="card-body">
              <div className="d-flex justify-content-between align-items-center mb-3">
                <h6 className="fw-bold mb-0">복약 미니달력</h6>
                <div className="small text-muted">{monthlyCalendar.monthLabel}</div>
              </div>

              <div
                className="small text-muted mb-2"
                style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0, 1fr))", gap: 4, textAlign: "center" }}
              >
                {["일", "월", "화", "수", "목", "금", "토"].map((label) => (
                  <div key={label}>{label}</div>
                ))}
              </div>

              <div className="d-flex flex-column gap-1">
                {monthlyCalendar.weeks.map((week, weekIndex) => (
                  <div
                    key={`week-${weekIndex}`}
                    style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0, 1fr))", gap: 4 }}
                  >
                    {week.map((cell, cellIndex) => {
                      if (!cell) {
                        return <div key={`empty-${weekIndex}-${cellIndex}`} />;
                      }

                      const summary = cell.summary;
                      const dayStyle = {
                        minHeight: 54,
                        borderRadius: 10,
                        border: cell.isSelected ? "2px solid #2563eb" : "1px solid #e5e7eb",
                        backgroundColor: "#ffffff",
                        padding: "6px 2px",
                        cursor: "pointer",
                        transition: "all 0.15s ease",
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "space-between",
                      };

                      if (summary?.missed) {
                        dayStyle.backgroundColor = "#fee2e2";
                        dayStyle.border = cell.isSelected ? "2px solid #dc2626" : "1px solid #fca5a5";
                      } else if (summary?.pending) {
                        dayStyle.backgroundColor = "#fef3c7";
                        dayStyle.border = cell.isSelected ? "2px solid #d97706" : "1px solid #fcd34d";
                      } else if (summary?.taken || summary?.skipped) {
                        dayStyle.backgroundColor = "#dcfce7";
                        dayStyle.border = cell.isSelected ? "2px solid #16a34a" : "1px solid #86efac";
                      }

                      return (
                        <div key={cell.dateKey}>
                          <button
                            type="button"
                            className="btn btn-link text-decoration-none p-0 w-100 h-100"
                            style={dayStyle}
                            onClick={() => setSelectedDate(cell.dateKey)}
                          >
                            <div className="fw-semibold" style={{ color: cell.isToday ? "#2563eb" : "#111827" }}>
                              {cell.day}
                            </div>
                            <div className="d-flex align-items-center justify-content-center gap-1 mt-1" style={{ minHeight: 12 }}>
                              {summary?.taken || summary?.skipped ? (
                                <span style={{ width: 8, height: 8, borderRadius: "999px", backgroundColor: "#16a34a", display: "inline-block" }} />
                              ) : null}
                              {summary?.pending ? (
                                <span style={{ width: 8, height: 8, borderRadius: "999px", backgroundColor: "#d97706", display: "inline-block" }} />
                              ) : null}
                              {summary?.missed ? (
                                <span style={{ width: 8, height: 8, borderRadius: "999px", backgroundColor: "#dc2626", display: "inline-block" }} />
                              ) : null}
                            </div>
                          </button>
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>

              <div className="d-flex flex-wrap gap-2 mt-3 small">
                <span className="badge text-bg-light">흰색: 일정 없음</span>
                <span className="badge" style={{ backgroundColor: "#dcfce7", color: "#166534" }}>초록: 기록 있음</span>
                <span className="badge" style={{ backgroundColor: "#fef3c7", color: "#92400e" }}>노랑: 복용 예정</span>
                <span className="badge" style={{ backgroundColor: "#fee2e2", color: "#b91c1c" }}>빨강: 미복용</span>
              </div>
            </div>
          </div>

            {isCaregiver && (
              <div className="card border-0 shadow-sm mb-3">
                <div className="card-body">
                  <h6 className="fw-bold mb-3">피보호자 선택</h6>
                  <select
                    className="form-select mb-3"
                    value={selectedPatientId}
                    onChange={(e) => setSelectedPatientId(e.target.value)}
                  >
                    <option value="all">전체 보기</option>
                    {patients.map((patient) => (
                      <option key={patient.id} value={patient.id}>
                        {patient.name}
                      </option>
                    ))}
                  </select>

                  <button
                    type="button"
                    className="btn btn-primary btn-sm w-100"
                    onClick={toggleAllSelected}
                    disabled={groupedByPatient.length === 0}
                  >
                    {selectedIds.length === groupedByPatient.length ? "전체 선택 해제" : "전체 알림 보내기"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-outline-primary btn-sm w-100 mt-2"
                    onClick={() => handleBulkCheck(filteredItems, "caregiver-visible")}
                    disabled={
                      filteredItems.length === 0 ||
                      filteredItems.every((item) => item.status === "taken" || item.status === "skipped") ||
                      actionLoadingId === "bulk-caregiver-visible"
                    }
                  >
                    {actionLoadingId === "bulk-caregiver-visible" ? "처리 중..." : "보이는 항목 전체 복용완료"}
                  </button>
                </div>
              </div>
            )}

            <div className="card border-0 shadow-sm">
              <div className="card-body">
                <h6 className="fw-bold mb-3">오늘 요약</h6>
                <div className="mb-2 small text-muted">대상 복약자 {summary.patientCount}명</div>
                <div className="mb-2 small text-muted">복용 완료 {summary.takenCount}건</div>
                <div className="small text-muted">미복용 {summary.missedCount}건</div>
              </div>
            </div>
          </div>

        <div className="col-xl-8">
            <div className="card border-0 shadow-sm">
              <div className="card-body">
                <div className="d-flex justify-content-between align-items-start gap-3 flex-wrap mb-4">
                  <div>
                    <h2 className="fw-bold mb-1">복약 체크</h2>
                    <div className="text-muted">{formatSelectedDate()}</div>
                  </div>
                </div>

                {error && <div className="alert alert-danger">{error}</div>}
                {successMessage && <div className="alert alert-success py-2">{successMessage}</div>}

                {loading ? (
                  <div className="text-center py-5">
                    <div className="spinner-border" role="status">
                      <span className="visually-hidden">Loading...</span>
                    </div>
                  </div>
                ) : groupedByPatient.length === 0 ? (
                  <div className="text-center py-5 text-muted">표시할 복약 일정이 없습니다.</div>
                ) : isCaregiver ? (
                  <>
                    <div className="row g-3 mb-4">
                      <div className="col-md-4">
                        <div className="card border-0" style={{ backgroundColor: "#f8fafc" }}>
                          <div className="card-body">
                            <div className="small text-muted mb-2">총 피보호자</div>
                            <div className="fs-2 fw-bold">{summary.patientCount}명</div>
                          </div>
                        </div>
                      </div>
                      <div className="col-md-4">
                        <div className="card border-0" style={{ backgroundColor: "#f8fafc" }}>
                          <div className="card-body">
                            <div className="small text-muted mb-2">오늘 복용 완료</div>
                            <div className="fs-2 fw-bold">{summary.takenCount}건</div>
                          </div>
                        </div>
                      </div>
                      <div className="col-md-4">
                        <div className="card border-0" style={{ backgroundColor: "#f8fafc" }}>
                          <div className="card-body">
                            <div className="small text-muted mb-2">미복용</div>
                            <div className="fs-2 fw-bold">{summary.missedCount}건</div>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="card border-0" style={{ backgroundColor: "#f9fbff" }}>
                      <div className="card-body">
                        <div className="fw-bold fs-5 mb-3">피보호자 목록</div>

                        {groupedByPatient.map((group) => (
                          <div
                            key={group.patient_id}
                            className="border rounded-4 p-3 mb-3"
                            style={{ backgroundColor: "#fff" }}
                          >
                            {(() => {
                              const patientMealGroup =
                                groupedByPatientWithMeals.find(
                                  (patientGroup) => patientGroup.patient_id === group.patient_id
                                ) || null;
                              const meals = patientMealGroup?.meals || [];
                              const activeMealLabel =
                                selectedCaregiverMealByPatient[group.patient_id] ||
                                meals.find((meal) => meal.summary.missedCount > 0)?.meal_label ||
                                meals[0]?.meal_label ||
                                null;
                              const activeMealGroup =
                                meals.find((meal) => meal.meal_label === activeMealLabel) || null;
                              const activeMealTargets =
                                activeMealGroup?.items.filter(
                                  (item) => item.status !== "taken" && item.status !== "skipped"
                                ) || [];

                              return (
                                <>
                            <div className="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3">
                              <div className="d-flex align-items-center gap-2">
                                <input
                                  type="checkbox"
                                  className="form-check-input mt-0"
                                  checked={selectedIds.includes(group.patient_id)}
                                  onChange={() => toggleSelectedPatient(group.patient_id)}
                                />
                                <div
                                  className="rounded-circle bg-light d-flex align-items-center justify-content-center"
                                  style={{ width: 36, height: 36, overflow: "hidden" }}
                                >
                                  {group.imageUrl ? (
                                    <img
                                      src={group.imageUrl}
                                      alt={group.patient_name}
                                      style={{ width: "100%", height: "100%", objectFit: "cover" }}
                                    />
                                  ) : (
                                    <span className="small">{group.patient_name.slice(0, 1)}</span>
                                  )}
                                </div>
                                <div>
                                  <div className="fw-semibold">{group.patient_name}</div>
                                  {group.patient_age_label && (
                                    <div className="small text-muted">{group.patient_age_label}</div>
                                  )}
                                </div>
                              </div>

                            </div>

                            <div className="d-flex gap-2 flex-wrap mb-3">
                              {meals.map((mealGroup) => (
                                <button
                                  key={`${group.patient_id}-${mealGroup.meal_label}`}
                                  type="button"
                                  className={`btn btn-sm ${
                                    activeMealLabel === mealGroup.meal_label
                                      ? "btn-primary"
                                      : "btn-outline-secondary"
                                  }`}
                                  onClick={() => toggleCaregiverMeal(group.patient_id, mealGroup.meal_label)}
                                >
                                  {mealGroup.meal_label}
                                  {` `}
                                  <span className="small">{mealGroup.items.length}개</span>
                                  {mealGroup.summary.missedCount > 0
                                    ? ` · 미복용 ${mealGroup.summary.missedCount}`
                                    : mealGroup.summary.pendingCount > 0
                                    ? ` · 대기 ${mealGroup.summary.pendingCount}`
                                    : ""}
                                </button>
                              ))}
                            </div>

                            {activeMealGroup && (
                              <div
                                className="rounded-4 p-3 mb-3"
                                style={{ backgroundColor: "#f8fafc", border: "1px solid #e5e7eb" }}
                              >
                                <div className="d-flex justify-content-between align-items-start gap-3 flex-wrap">
                                  <div>
                                    <div className="fw-semibold">{activeMealGroup.meal_label} 복약 요약</div>
                                    <div className="small text-muted mt-1">
                                      {activeMealGroup.items.length}개 항목
                                      {activeMealGroup.summary.pendingCount > 0
                                        ? ` · 대기 ${activeMealGroup.summary.pendingCount}건`
                                        : ""}
                                      {activeMealGroup.summary.missedCount > 0
                                        ? ` · 미복용 ${activeMealGroup.summary.missedCount}건`
                                        : ""}
                                    </div>
                                    <div className="small text-muted mt-1">
                                      {activeMealGroup.items.map((item) => getMedicationLabel(item)).join(", ")}
                                    </div>
                                  </div>
                                  <div className="d-flex gap-2 flex-wrap">
                                    <button
                                      type="button"
                                      className="btn btn-primary btn-sm"
                                      disabled={
                                        activeMealTargets.length === 0 ||
                                        actionLoadingId === `bulk-${group.patient_id}-${activeMealGroup.meal_label}`
                                      }
                                      onClick={() =>
                                        handleBulkCheck(
                                          activeMealGroup.items,
                                          `${group.patient_id}-${activeMealGroup.meal_label}`
                                        )
                                      }
                                    >
                                      {actionLoadingId === `bulk-${group.patient_id}-${activeMealGroup.meal_label}`
                                        ? "처리 중..."
                                        : "이 시간대 복용완료"}
                                    </button>
                                    <button
                                      type="button"
                                      className="btn btn-outline-warning btn-sm"
                                      disabled={
                                        activeMealTargets.length === 0 ||
                                        actionLoadingId === `remind-${group.patient_id}-${activeMealGroup.meal_label}`
                                      }
                                      onClick={() =>
                                        openMealReminderConfirm(
                                          group.patient_id,
                                          group.patient_name,
                                          activeMealGroup
                                        )
                                      }
                                    >
                                      복약 다시 알리기
                                    </button>
                                  </div>
                                </div>
                              </div>
                            )}

                            <div className="row g-2">
                              {(activeMealGroup?.items || []).map((item) => {
                                const meta = STATUS_META[item.status] || STATUS_META.pending;
                                const isHighlighted = highlightedItemId === item.id;

                                return (
                                  <div className="col-md-4" key={item.id}>
                                    <div
                                      id={`medication-item-${item.id}`}
                                      className="rounded-4 p-3 h-100"
                                      style={{
                                        backgroundColor: isHighlighted ? "#fff7d6" : meta.bg,
                                        border: isHighlighted ? "2px solid #f59e0b" : "1px solid transparent",
                                        boxShadow: isHighlighted
                                          ? "0 0 0 4px rgba(245, 158, 11, 0.18)"
                                          : "none",
                                        transition: "all 0.2s ease",
                                      }}
                                    >
                                      <div className="d-flex justify-content-between align-items-center mb-2">
                                        <div>
                                          <div className="small fw-semibold">{item.meal_label}</div>
                                          <div className="small text-muted">{item.scheduled_time}</div>
                                        </div>
                                        <span
                                          style={{
                                            width: 12,
                                            height: 12,
                                            borderRadius: "999px",
                                            display: "inline-block",
                                            backgroundColor: meta.dot,
                                          }}
                                        />
                                      </div>

                                      <div className="small text-muted mb-2">{getMedicationLabel(item)}</div>

                                      {item.status === "taken" ? (
                                        <button
                                          className="btn btn-sm w-100 mb-2"
                                          style={{
                                            backgroundColor: meta.color,
                                            color: "#fff",
                                            border: "none",
                                          }}
                                          disabled={actionLoadingId === item.id}
                                          onClick={() => handleUndo(item)}
                                        >
                                          {actionLoadingId === item.id ? "처리 중..." : "복용완료"}
                                        </button>
                                      ) : item.status === "skipped" ? (
                                        <button
                                          className="btn btn-secondary btn-sm w-100 mb-2"
                                          onClick={() => handleUndo(item)}
                                          disabled={actionLoadingId === item.id}
                                        >
                                          {actionLoadingId === item.id ? "처리 중..." : "건너뜀 (취소)"}
                                        </button>
                                      ) : (
                                        <>
                                          <button
                                            className="btn btn-sm w-100 mb-2"
                                            style={{
                                              backgroundColor: item.status === "missed" ? "#ef4444" : "#2563eb",
                                              color: "#fff",
                                              border: "none",
                                            }}
                                            disabled={actionLoadingId === item.id}
                                            onClick={() => handleCheck(item)}
                                          >
                                            {actionLoadingId === item.id
                                              ? "처리 중..."
                                              : item.status === "missed"
                                              ? "지금 복용 체크"
                                              : "복용하기"}
                                          </button>

                                          <button
                                            className="btn btn-outline-secondary btn-sm w-100"
                                            disabled={actionLoadingId === item.id}
                                            onClick={() => handleSkip(item)}
                                          >
                                            건너뛰기
                                          </button>
                                        </>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                                </>
                              );
                            })()}
                          </div>
                        ))}

                        {renderStatusLegend()}
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="card border-0" style={{ backgroundColor: "#f9fbff" }}>
                    <div className="card-body">
                      <div className="rounded-4 p-4 mb-4" style={{ backgroundColor: "#fff" }}>
                        <div className="fs-2 fw-bold mb-2">
                          안녕하세요, {me?.name || patients[0]?.name || "회원"}님
                        </div>
                        <div className="text-muted">오늘 복약해야 하는 시간대만 골라서 확인해보세요.</div>
                      </div>

                      <div className="fw-bold fs-2 mb-1">오늘의 복약 스케줄</div>
                      <div className="text-muted mb-4">{formatSelectedDate()}</div>

                      <div className="d-flex gap-2 flex-wrap mb-4">
                        {MEAL_ORDER.map((mealLabel) => {
                          const mealGroup = groupedByMealForSelf.find((group) => group.meal_label === mealLabel);
                          const isSelected = selectedMealGroup?.meal_label === mealLabel;

                          return (
                            <button
                              key={mealLabel}
                              type="button"
                              className={`btn ${isSelected ? "btn-primary" : "btn-outline-secondary"}`}
                              disabled={!mealGroup}
                              onClick={() => setSelectedMealLabel(mealLabel)}
                            >
                              {mealLabel}
                              {mealGroup ? ` ${mealGroup.items.length}` : ""}
                            </button>
                          );
                        })}
                      </div>

                      {!selectedMealGroup ? (
                        <div className="rounded-4 p-4 text-center text-muted" style={{ backgroundColor: "#fff" }}>
                          선택한 날짜에 복약 일정이 없습니다.
                        </div>
                      ) : (
                        <div className="rounded-4 p-4" style={{ backgroundColor: "#fff" }}>
                          {(() => {
                            const mealSummary = getMealStatusSummary(selectedMealGroup.items);
                            const bulkTargets = selectedMealGroup.items.filter(
                              (item) => item.status !== "taken" && item.status !== "skipped"
                            );

                            return (
                          <div className="d-flex justify-content-between align-items-start gap-3 flex-wrap mb-4">
                            <div>
                              <div className="fs-3 fw-bold mb-1">{selectedMealGroup.meal_label}</div>
                              <div className="text-muted small">
                                {selectedMealGroup.items.map((item) => getMedicationLabel(item)).join(", ")}
                              </div>
                            </div>
                            <div className="d-flex flex-column align-items-start align-items-md-end gap-2">
                              <div className="small text-muted">
                                {selectedMealGroup.items.length}개의 복약 항목
                                {mealSummary.missedCount > 0 ? ` · 미복용 ${mealSummary.missedCount}건` : ""}
                              </div>
                              <button
                                type="button"
                                className="btn btn-primary btn-sm"
                                disabled={bulkTargets.length === 0 || actionLoadingId === `bulk-${selectedMealGroup.meal_label}`}
                                onClick={() => handleBulkCheck(selectedMealGroup.items, selectedMealGroup.meal_label)}
                              >
                                {actionLoadingId === `bulk-${selectedMealGroup.meal_label}`
                                  ? "처리 중..."
                                  : "이 시간대 전체 복용완료"}
                              </button>
                            </div>
                          </div>
                            );
                          })()}

                          <div className="d-flex flex-column gap-3">
                            {selectedMealGroup.items.map((item) => {
                              const meta = STATUS_META[item.status] || STATUS_META.pending;
                              const isHighlighted = highlightedItemId === item.id;

                              return (
                                <div
                                  key={item.id}
                                  id={`medication-item-${item.id}`}
                                  className="rounded-4 p-3"
                                  style={{
                                    backgroundColor: isHighlighted ? "#fff7d6" : meta.bg,
                                    border: isHighlighted ? "2px solid #f59e0b" : "1px solid transparent",
                                    boxShadow: isHighlighted ? "0 0 0 4px rgba(245, 158, 11, 0.18)" : "none",
                                    transition: "all 0.2s ease",
                                  }}
                                >
                                  <div className="d-flex justify-content-between align-items-start gap-3 flex-wrap">
                                    <div>
                                      <div className="d-flex align-items-center gap-2 mb-1">
                                        <div className="fw-semibold">{getMedicationLabel(item)}</div>
                                        <span
                                          style={{
                                            width: 12,
                                            height: 12,
                                            borderRadius: "999px",
                                            display: "inline-block",
                                            backgroundColor: meta.dot,
                                          }}
                                        />
                                      </div>
                                      <div className="small text-muted">{item.scheduled_time} 복용</div>
                                    </div>

                                    <div className="d-flex align-items-center gap-2 flex-wrap">
                                      {item.status === "taken" ? (
                                        <button
                                          className="btn btn-sm"
                                          style={{
                                            backgroundColor: meta.color,
                                            color: "#fff",
                                            border: "none",
                                            minWidth: 110,
                                          }}
                                          onClick={() => handleUndo(item)}
                                          disabled={actionLoadingId === item.id}
                                        >
                                          {actionLoadingId === item.id ? "처리 중..." : "복용완료"}
                                        </button>
                                      ) : item.status === "skipped" ? (
                                        <button
                                          className="btn btn-secondary btn-sm"
                                          onClick={() => handleUndo(item)}
                                          disabled={actionLoadingId === item.id}
                                        >
                                          {actionLoadingId === item.id ? "처리 중..." : "건너뜀 (취소)"}
                                        </button>
                                      ) : (
                                        <>
                                          <button
                                            className="btn btn-sm"
                                            style={{
                                              backgroundColor: item.status === "missed" ? "#ef4444" : "#2563eb",
                                              color: "#fff",
                                              border: "none",
                                              minWidth: 110,
                                            }}
                                            onClick={() => handleCheck(item)}
                                            disabled={actionLoadingId === item.id}
                                          >
                                            {actionLoadingId === item.id
                                              ? "처리 중..."
                                              : item.status === "missed"
                                              ? "지금 복용 체크"
                                              : "복용하기"}
                                          </button>

                                          <button
                                            className="btn btn-outline-secondary btn-sm"
                                            onClick={() => handleSkip(item)}
                                            disabled={actionLoadingId === item.id}
                                          >
                                            건너뛰기
                                          </button>
                                        </>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      {renderStatusLegend()}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
        {mealReminderDraft && (
          <div
            className="position-fixed top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center"
            style={{ backgroundColor: "rgba(15, 23, 42, 0.45)", zIndex: 1050, padding: "1rem" }}
          >
            <div className="card border-0 shadow-lg" style={{ width: "100%", maxWidth: 480 }}>
              <div className="card-body p-4">
                <div className="fw-bold fs-5 mb-2">복약 리마인드를 보낼까요?</div>
                <div className="text-muted mb-3">
                  {mealReminderDraft.patientName}님의 {mealReminderDraft.mealGroup.meal_label} 복약을 다시 알립니다.
                </div>
                <div
                  className="rounded-4 p-3 mb-3"
                  style={{ backgroundColor: "#f8fafc", border: "1px solid #e5e7eb" }}
                >
                  <div className="small text-muted mb-1">대상 약</div>
                  <div className="fw-semibold">{mealReminderDraft.medicationNames}</div>
                  <div className="small text-muted mt-2">
                    미처리 항목 {mealReminderDraft.pendingCount}건
                  </div>
                </div>
                <div className="d-flex justify-content-end gap-2">
                  <button
                    type="button"
                    className="btn btn-outline-secondary"
                    onClick={closeMealReminderConfirm}
                    disabled={
                      actionLoadingId ===
                      `remind-${mealReminderDraft.patientId}-${mealReminderDraft.mealGroup.meal_label}`
                    }
                  >
                    취소
                  </button>
                  <button
                    type="button"
                    className="btn btn-warning"
                    onClick={async () => {
                      await handleMealReminder(
                        mealReminderDraft.patientId,
                        mealReminderDraft.patientName,
                        mealReminderDraft.mealGroup
                      );
                      closeMealReminderConfirm();
                    }}
                    disabled={
                      actionLoadingId ===
                      `remind-${mealReminderDraft.patientId}-${mealReminderDraft.mealGroup.meal_label}`
                    }
                  >
                    {actionLoadingId ===
                    `remind-${mealReminderDraft.patientId}-${mealReminderDraft.mealGroup.meal_label}`
                      ? "전송 중..."
                      : "리마인드 보내기"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
    </AppLayout>
  );
};

export default MedicationCheckPage;
