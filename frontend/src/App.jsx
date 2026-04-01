import React, { useEffect, useMemo, useState } from "react";
import AdminDashboard from "./AdminDashboard.jsx";
import HealthProfile from "./HealthProfile.jsx";
import DocumentManagement from "./DocumentManagement.jsx";
import CaregiverManagement from "./CaregiverManagement.jsx";
import AiPage from "./AiPage.jsx";
import SchedulePage from "./SchedulePage.jsx";
import SettingsPage from "./SettingsPage.jsx";
import NotificationPage from "./NotificationPage.jsx";
import DrugSearchPage from "./DrugSearchPage.jsx";
import MedicationCheckPage from "./MedicationCheckPage.jsx";
import LandingPage from "./LandingPage.jsx";
import AppLayout from "./components/AppLayout.jsx";
import { applyDarkMode, getStoredDarkMode } from "./theme.js";

const API_PREFIX = "/api/v1";
const DEVICE_ID_STORAGE_KEY = "device_id";
const HOME_MEAL_ORDER = ["아침", "점심", "저녁", "취침"];
const HOME_MEDICATION_GROUP_LIMIT = 5;
const VALID_LOGIN_ROLES = new Set(["PATIENT", "CAREGIVER", "GUARDIAN", "ADMIN"]);



const safeJson = async (res) => {
  try {
    return await res.json();
  } catch {
    return null;
  }
};

const decodeJwtPayload = (token) => {
  if (!token || typeof token !== "string") {
    return null;
  }
  const parts = token.split(".");
  if (parts.length < 2) {
    return null;
  }
  const payloadSegment = parts[1];
  const normalized = payloadSegment.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
  try {
    const decodeBase64 = typeof window !== "undefined" && typeof window.atob === "function" ? window.atob : atob;
    return JSON.parse(decodeBase64(padded));
  } catch {
    return null;
  }
};

const extractLoginRoleFromAccessToken = (token) => {
  const payload = decodeJwtPayload(token);
  const role = String(payload?.login_role || "").toUpperCase();
  if (!VALID_LOGIN_ROLES.has(role)) {
    return null;
  }
  return role;
};

const formatDateTime = (value) => {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
};

const formatDateTimeKst = (value) => {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Seoul"
  }).format(date);
};

const formatClockTime = (value) => {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return date.toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  });
};

const normalizeIntakeStatus = (rawStatus) => {
  const value = String(rawStatus || "").toLowerCase();
  if (value === "taken") return "taken";
  if (value === "missed") return "missed";
  if (value === "skipped") return "skipped";
  return "pending";
};

const intakeStatusLabel = (status) => {
  if (status === "taken") return "복용완료";
  if (status === "missed") return "미복용";
  if (status === "skipped") return "건너뜀";
  return "복용대기";
};

const inferHomeMealLabel = (scheduledAt) => {
  const date = new Date(scheduledAt);
  if (Number.isNaN(date.getTime())) return "기타";
  const hour = date.getHours();
  if (hour < 10) return "아침";
  if (hour < 15) return "점심";
  if (hour < 20) return "저녁";
  return "취침";
};

const resolveGroupIntakeStatus = (statuses = []) => {
  if (statuses.includes("missed")) return "missed";
  if (statuses.includes("pending")) return "pending";
  if (statuses.length > 0 && statuses.every((status) => status === "taken")) return "taken";
  if (statuses.length > 0 && statuses.every((status) => status === "skipped")) return "skipped";
  if (statuses.includes("taken")) return "taken";
  if (statuses.includes("skipped")) return "skipped";
  return "pending";
};

const toDateKey = (value) => {
  if (!value) return "";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
};

const resolveNotificationPatientId = (item) => {
  const payloadPatientId = item?.payload?.patient_id;
  if (payloadPatientId !== undefined && payloadPatientId !== null && payloadPatientId !== "") {
    const id = Number(payloadPatientId);
    return Number.isFinite(id) && id > 0 ? id : null;
  }
  const fallbackId = Number(item?.patient_id);
  return Number.isFinite(fallbackId) && fallbackId > 0 ? fallbackId : null;
};

const resolveClientDeviceId = () => {
  if (typeof window === "undefined") {
    return null;
  }
  const storedId = window.localStorage.getItem(DEVICE_ID_STORAGE_KEY);
  if (storedId) {
    return storedId;
  }
  const generatedId =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `web-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
  window.localStorage.setItem(DEVICE_ID_STORAGE_KEY, generatedId);
  return generatedId;
};

const resolveClientPlatform = () => {
  if (typeof navigator === "undefined") {
    return "web";
  }
  const uaPlatform = navigator.userAgentData?.platform;
  const platform = uaPlatform || navigator.platform || "web";
  return String(platform).slice(0, 30);
};

function App() {
  const [healthStatus, setHealthStatus] = useState({
    loading: false,
    data: null,
    error: null
  });
  const [roles, setRoles] = useState([]);
  const [rolesError, setRolesError] = useState(null);
  const [loginForm, setLoginForm] = useState({
    email: "",
    password: "",
    role: "PATIENT"
  });
  const [loginState, setLoginState] = useState({
    submitting: false,
    error: null
  });
  const [findEmailForm, setFindEmailForm] = useState({
    name: "",
    phoneNumber: ""
  });
  const [findEmailState, setFindEmailState] = useState({
    submitting: false,
    error: null,
    email: null
  });
  const [resetPasswordForm, setResetPasswordForm] = useState({
    email: "",
    name: "",
    phoneNumber: "",
    newPassword: "",
    newPasswordConfirm: ""
  });
  const [resetPasswordState, setResetPasswordState] = useState({
    submitting: false,
    error: null,
    success: false
  });
  const [showFindModal, setShowFindModal] = useState(false);
  const [findModalTab, setFindModalTab] = useState("email");
  const [authChecking, setAuthChecking] = useState(true);
  const readCookie = (name) => {
    if (typeof document === "undefined") {
      return null;
    }
    const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
    return match ? decodeURIComponent(match[2]) : null;
  };

  const [accessToken, setAccessToken] = useState(() => {
    if (typeof window === "undefined") {
      return null;
    }
    return window.localStorage.getItem("access_token") || readCookie("access_token");
  });
  const [loginRole, setLoginRole] = useState(() => {
    if (typeof window === "undefined") {
      return "PATIENT";
    }
    return window.localStorage.getItem("login_role") || "PATIENT";
  });
  const [signupForm, setSignupForm] = useState({
    name: "",
    role: "PATIENT",
    email: "",
    password: "",
    passwordConfirm: "",
    gender: "MALE",
    birthDate: "",
    phoneNumber: "",
    privacyConsent: false
  });
  const [signupState, setSignupState] = useState({
    submitting: false,
    error: null,
    success: false
  });

  const [meState, setMeState] = useState({
    loading: false,
    data: null,
    error: null
  });
  const [profileForm, setProfileForm] = useState({
    name: "",
    email: "",
    phone_number: "",
    birthday: "",
    gender: "MALE"
  });
  const [profileState, setProfileState] = useState({
    submitting: false,
    error: null,
    success: false
  });
  const [linkedDeviceCount, setLinkedDeviceCount] = useState(null);
  const [lastLoginAt, setLastLoginAt] = useState(null);

  const [inviteState, setInviteState] = useState({
    submitting: false,
    error: null,
    data: null
  });
  const [inviteDeleteState, setInviteDeleteState] = useState({
    submitting: false,
    error: null,
    success: false
  });
  const [inviteCodeForm, setInviteCodeForm] = useState({
    expires_in_minutes: 5
  });
  const [linkForm, setLinkForm] = useState({
    code: ""
  });
  const [linksState, setLinksState] = useState({
    loading: false,
    data: null,
    error: null
  });
  const [linkAction, setLinkAction] = useState({
    submitting: false,
    error: null,
    success: null
  });

  const [notificationsState, setNotificationsState] = useState({
    loading: false,
    items: [],
    nextCursor: null,
    error: null
  });
  const [notificationsAction, setNotificationsAction] = useState({
    submitting: false,
    error: null
  });
  const [unreadCountState, setUnreadCountState] = useState({
    loading: false,
    count: 0,
    error: null
  });
  const [settingsState, setSettingsState] = useState({
    loading: false,
    data: null,
    error: null,
    submitting: false,
    success: false
  });
  const [remindForm, setRemindForm] = useState({
    patient_id: "",
    type: "intake_reminder",
    title: "복약 리마인드",
    message: "복약 시간이예요! 확인해 주세요.",
    payload: '{"schedule_id":123}'
  });
  const [remindState, setRemindState] = useState({
    submitting: false,
    error: null,
    success: null
  });

  const pathname = typeof window !== "undefined" ? window.location.pathname : "/";
  const isLandingPage = useMemo(() => {
    return pathname === "/";
  }, [pathname]);
  const isLoginPage = useMemo(() => {
    return pathname.startsWith("/login") || pathname.startsWith("/app/login");
  }, [pathname]);
  const isSignupPage = useMemo(() => {
    return pathname.startsWith("/signup") || pathname.startsWith("/app/signup");
  }, [pathname]);
  const isProfilePage = useMemo(() => {
    return pathname.startsWith("/profile") || pathname.startsWith("/app/profile");
  }, [pathname]);
  const isDashboardPage = useMemo(() => {
    return pathname.startsWith("/dashboard") || pathname.startsWith("/app/dashboard");
  }, [pathname]);
  const isHealthProfilePage = useMemo(() => {
    return pathname.startsWith("/health-profile") || pathname.startsWith("/app/health-profile");
  }, [pathname]);
  const isDocumentsPage = useMemo(() => {
    return pathname.startsWith("/documents") || pathname.startsWith("/app/documents");
  }, [pathname]);
  const isCaregiverPage = useMemo(() => {
    return pathname.startsWith("/caregiver") || pathname.startsWith("/app/caregiver");
  }, [pathname]);
  const isAiPage = useMemo(() => {
    return pathname.startsWith("/ai") || pathname.startsWith("/app/ai");
  }, [pathname]);
  const isDrugSearchPage = useMemo(() => {
    return pathname.startsWith("/drug-search") || pathname.startsWith("/app/drug-search");
  }, [pathname]);
  const isMedicationCheckPage = useMemo(() => {
    return pathname.startsWith("/medication-check") || pathname.startsWith("/app/medication-check");
  }, [pathname]);
  const isSchedulePage = useMemo(() => {
    return pathname.startsWith("/schedule") || pathname.startsWith("/app/schedule");
  }, [pathname]);
  const isSettingsPage = useMemo(() => {
    return pathname.startsWith("/settings") || pathname.startsWith("/app/settings");
  }, [pathname]);
  const isHomePage =
    !isLoginPage &&
    !isSignupPage &&
    !isProfilePage &&
    !isDashboardPage &&
    !isHealthProfilePage &&
    !isDocumentsPage &&
    !isCaregiverPage &&
    !isAiPage &&
    !isDrugSearchPage &&
    !isMedicationCheckPage &&
    !isSchedulePage &&
    !isSettingsPage;

  const persistAccessToken = (token) => {
    if (typeof window !== "undefined") {
      if (token) {
        window.localStorage.setItem("access_token", token);
      } else {
        window.localStorage.removeItem("access_token");
      }
    }
    if (typeof document !== "undefined") {
      if (token) {
        document.cookie = `access_token=${encodeURIComponent(token)}; path=/;`;
      } else {
        document.cookie = "access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
      }
    }
    setAccessToken(token);
  };

  const persistLoginRole = (role) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem("login_role", role);
    }
    setLoginRole(role);
  };

  const refreshAccessToken = async () => {
    const res = await fetch(`${API_PREFIX}/auth/token/refresh`, {
      method: "GET",
      credentials: "include"
    });
    if (!res.ok) {
      return null;
    }
    const body = await safeJson(res);
    const token = body?.access_token;
    if (token) {
      persistAccessToken(token);
      const roleFromToken = extractLoginRoleFromAccessToken(token);
      if (roleFromToken) {
        persistLoginRole(roleFromToken);
      }
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
      credentials: "include"
    });
    if (res.status === 401 && retryOnUnauthorized) {
      const newToken = await refreshAccessToken();
      if (newToken) {
        headers.set("Authorization", `Bearer ${newToken}`);
        return fetch(path, {
          ...options,
          headers,
          credentials: "include"
        });
      }
    }
    return res;
  };

  useEffect(() => {
    applyDarkMode(getStoredDarkMode());
  }, []);

  useEffect(() => {
    if (!accessToken) {
      setLinkedDeviceCount(null);
      setLastLoginAt(null);
      return;
    }
    let mounted = true;
    const syncThemeFromSettings = async () => {
      try {
        const res = await authFetch(`${API_PREFIX}/settings`);
        if (!res.ok) {
          return;
        }
        const data = await res.json();
        if (!mounted) {
          return;
        }
        applyDarkMode(!!data.dark_mode);
      } catch {
        // ignore theme sync errors
      }
    };
    syncThemeFromSettings();
    return () => {
      mounted = false;
    };
  }, [accessToken]);

  useEffect(() => {
    if (!isSignupPage) {
      return;
    }
    let isMounted = true;
    const loadRoles = async () => {
      try {
        const res = await fetch("/api/v1/public/roles");
        if (!res.ok) {
          throw new Error(`status ${res.status}`);
        }
        const data = await res.json();
        if (isMounted) {
          setRoles(data);
          setRolesError(null);
        }
      } catch (error) {
        if (isMounted) {
          setRolesError(error.message);
        }
      }
    };
    loadRoles();
    return () => {
      isMounted = false;
    };
  }, [isSignupPage]);

  useEffect(() => {
    if (!accessToken) {
      setLinkedDeviceCount(null);
      setLastLoginAt(null);
      return;
    }
    const loadMe = async () => {
      setMeState({ loading: true, data: null, error: null });
      try {
        const res = await authFetch(`${API_PREFIX}/users/me`);
        if (!res.ok) {
          const body = await safeJson(res);
          throw new Error(body?.detail || `status ${res.status}`);
        }
        const data = await res.json();
        setMeState({ loading: false, data, error: null });
      } catch (error) {
        setMeState({ loading: false, data: null, error: error.message });
      }
    };

    const loadLinks = async () => {
      setLinksState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const res = await authFetch(`${API_PREFIX}/users/links`);
        if (!res.ok) {
          const body = await safeJson(res);
          throw new Error(body?.detail || `status ${res.status}`);
        }
        const data = await res.json();
        setLinksState({ loading: false, data, error: null });
      } catch (error) {
        setLinksState({ loading: false, data: null, error: error.message });
      }
    };

    const registerCurrentDevice = async () => {
      const deviceId = resolveClientDeviceId();
      if (!deviceId) {
        return;
      }

      try {
        const res = await authFetch(`${API_PREFIX}/users/me/devices/register`, {
          method: "POST",
          body: JSON.stringify({
            device_id: deviceId,
            platform: resolveClientPlatform()
          })
        });
        if (!res.ok) {
          return;
        }
        const data = await res.json();
        const count = Number(data?.linked_device_count);
        setLinkedDeviceCount(Number.isFinite(count) ? count : null);
        setLastLoginAt(data?.last_login_at || null);
      } catch {
        // ignore device registration failures
      }
    };

    loadMe();
    loadLinks();
    registerCurrentDevice();
    // 알림 기능은 DB 스키마 문제로 비활성화
    // loadNotifications();
    // loadUnreadCount();
    // loadSettings();
  }, [accessToken]);

  useEffect(() => {
    let active = true;
    const bootstrapAuth = async () => {
      if (accessToken) {
        if (active) {
          setAuthChecking(false);
        }
        return;
      }
      try {
        await refreshAccessToken();
      } catch {
        // ignore refresh failures
      } finally {
        if (active) {
          setAuthChecking(false);
        }
      }
    };
    bootstrapAuth();
    return () => {
      active = false;
    };
  }, [accessToken]);

  useEffect(() => {
    if (!meState.data) {
      return;
    }
    setProfileForm({
      name: meState.data.name || "",
      email: meState.data.email || "",
      phone_number: meState.data.phone_number || "",
      birthday: meState.data.birthday || "",
      gender: meState.data.gender || "MALE"
    });
  }, [meState.data]);

  const linkedPatients = useMemo(() => {
    const links = linksState.data?.links || [];
    const uniqueMap = new Map();

    links.forEach((link) => {
      if (!link.patient_id) return;

      uniqueMap.set(Number(link.patient_id), {
        id: Number(link.patient_id),
        name: link.patient_name || `복약자 ${link.patient_id}`,
      });
    });

    return Array.from(uniqueMap.values());
  }, [linksState.data]);

  const normalizedLoginMode = loginRole === "GUARDIAN" ? "CAREGIVER" : loginRole;

  const ownedPatientProfile = useMemo(() => {
    if (!meState.data?.patient_id) return null;
    return {
      id: Number(meState.data.patient_id),
      name: meState.data.name || `복약자 ${meState.data.patient_id}`,
    };
  }, [meState.data]);

  const myPatient = useMemo(() => {
    if (normalizedLoginMode !== "PATIENT") return null;
    return ownedPatientProfile;
  }, [normalizedLoginMode, ownedPatientProfile]);

  const isCaregiverRole = normalizedLoginMode === "CAREGIVER";
  const hasPatientMode = Boolean(ownedPatientProfile?.id);
  const hasCaregiverMode = isCaregiverRole || linksState.data?.role === "CAREGIVER";
  const hasAdminMode = normalizedLoginMode === "ADMIN";
  const layoutUserName =
    normalizedLoginMode === "PATIENT"
      ? myPatient?.name || meState.data?.name
      : meState.data?.name;
  const modeOptions = useMemo(() => {
    const options = [];
    if (hasPatientMode) {
      options.push({ value: "PATIENT", label: "복약자모드" });
    }
    if (hasCaregiverMode) {
      options.push({ value: "CAREGIVER", label: "보호자모드" });
    }
    if (hasAdminMode) {
      options.push({ value: "ADMIN", label: "관리자모드" });
    }
    if (options.length === 0) {
      options.push({ value: normalizedLoginMode || "PATIENT", label: `${normalizedLoginMode || "PATIENT"}모드` });
    }
    return options;
  }, [hasAdminMode, hasCaregiverMode, hasPatientMode, normalizedLoginMode]);
  const handleModeChange = (nextMode) => {
    if (!nextMode) return;
    if (nextMode === normalizedLoginMode) return;

    if (typeof window !== "undefined") {
      const currentPath = window.location.pathname;
      let nextPath = currentPath;

      if (nextMode === "ADMIN") {
        nextPath = "/app/dashboard";
      } else if (currentPath.startsWith("/app/dashboard") || currentPath.startsWith("/dashboard")) {
        nextPath = "/app";
      }

      if (nextPath !== currentPath) {
        window.history.replaceState({}, "", nextPath);
      }
    }

    setHomePatientId("");
    persistLoginRole(nextMode);
  };
  const [homePatientId, setHomePatientId] = useState("");
  const [homeScheduleState, setHomeScheduleState] = useState({
    loading: false,
    items: [],
    error: null
  });
  const [homeMedicationState, setHomeMedicationState] = useState({
    loading: false,
    items: [],
    summaryByPatient: {},
    error: null
  });
  const [homeNotificationsState, setHomeNotificationsState] = useState({
    loading: false,
    items: [],
    error: null
  });
  const [homeSelectedDate, setHomeSelectedDate] = useState(() => toDateKey(new Date()));

  useEffect(() => {
    if (!isCaregiverRole) return;
    if (homePatientId) return;
    if (linkedPatients.length > 0) {
      setHomePatientId("all");
      return;
    }
    setHomePatientId("");
  }, [homePatientId, isCaregiverRole, linkedPatients]);

  const activeHomePatient = useMemo(() => {
    if (!isCaregiverRole) return myPatient;
    if (homePatientId === "all") return null;
    return linkedPatients.find((patient) => String(patient.id) === String(homePatientId)) || linkedPatients[0] || null;
  }, [homePatientId, isCaregiverRole, linkedPatients, myPatient]);

  const homePatientNameMap = useMemo(() => {
    const map = new Map();
    linkedPatients.forEach((patient) => {
      if (!patient?.id) return;
      map.set(Number(patient.id), patient.name || patient.display_name || `복약자 ${patient.id}`);
    });
    if (myPatient?.id) {
      map.set(Number(myPatient.id), myPatient.name || myPatient.display_name || `복약자 ${myPatient.id}`);
    }
    return map;
  }, [linkedPatients, myPatient]);

  const selectedHomePatientIds = useMemo(() => {
    if (isCaregiverRole) {
      if (homePatientId === "all") {
        return linkedPatients.map((patient) => Number(patient.id)).filter(Boolean);
      }
      const targetId = homePatientId ? Number(homePatientId) : Number(linkedPatients[0]?.id);
      return targetId ? [targetId] : [];
    }

    const myId = Number(myPatient?.id);
    return myId ? [myId] : [];
  }, [homePatientId, isCaregiverRole, linkedPatients, myPatient]);

  const selectedHomePatientKey = useMemo(() => selectedHomePatientIds.join(","), [selectedHomePatientIds]);

  useEffect(() => {
    if (!accessToken || !isHomePage) return;
    if (selectedHomePatientIds.length === 0) {
      setHomeScheduleState({ loading: false, items: [], error: null });
      return;
    }

    let isMounted = true;

    const loadHomeSchedules = async () => {
      setHomeScheduleState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const responses = await Promise.all(
          selectedHomePatientIds.map((patientId) =>
            authFetch(`${API_PREFIX}/calendar/hospital?patient_id=${patientId}`)
          )
        );

        const jsonList = await Promise.all(
          responses.map(async (res) => {
            if (!res.ok) return { items: [] };
            return (await safeJson(res)) || { items: [] };
          })
        );

        const merged = jsonList.flatMap((data) => data.items || []);
        const dedupedMap = new Map();

        merged.forEach((item) => {
          dedupedMap.set(item.id, item);
        });

        const items = Array.from(dedupedMap.values()).sort(
          (a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at)
        );

        if (isMounted) {
          setHomeScheduleState({ loading: false, items, error: null });
        }
      } catch (error) {
        if (isMounted) {
          setHomeScheduleState({ loading: false, items: [], error: error.message || "일정 조회 실패" });
        }
      }
    };

    loadHomeSchedules();
    return () => {
      isMounted = false;
    };
  }, [accessToken, isHomePage, selectedHomePatientKey]);

  useEffect(() => {
    if (!accessToken || !isHomePage) return;
    if (selectedHomePatientIds.length === 0) {
      setHomeMedicationState({ loading: false, items: [], summaryByPatient: {}, error: null });
      return;
    }

    let isMounted = true;

    const loadHomeMedicationStatus = async () => {
      const todayKey = toDateKey(new Date());
      setHomeMedicationState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const rows = await Promise.all(
          selectedHomePatientIds.map(async (patientId) => {
            const params = new URLSearchParams();
            params.set("patient_id", String(patientId));
            params.set("from", todayKey);
            params.set("to", todayKey);

            const guideParams = new URLSearchParams();
            guideParams.set("patient_id", String(patientId));
            guideParams.set("include_other_active", "true");

            const [statusRes, guideRes] = await Promise.all([
              authFetch(`${API_PREFIX}/schedules/status?${params.toString()}`),
              authFetch(`${API_PREFIX}/documents/medication-guide?${guideParams.toString()}`)
            ]);

            const guideMap = {};
            if (guideRes.ok) {
              const guideBody = await safeJson(guideRes);
              const guideData = guideBody?.data || guideBody || {};
              const guideItems = Array.isArray(guideData.items) ? guideData.items : [];
              guideItems.forEach((guideItem) => {
                const medId = Number(guideItem?.patient_med_id);
                const displayName = String(guideItem?.display_name || "").trim();
                if (!medId || !displayName) return;
                guideMap[medId] = displayName;
              });
            }

            if (!statusRes.ok) {
              return { patientId, items: [], summary: null, guideMap };
            }

            const body = await safeJson(statusRes);
            const data = body?.data || body || {};
            const days = Array.isArray(data.days) ? data.days : [];

            const items = days.flatMap((dayBlock) => {
              const day = dayBlock?.day;
              const dayItems = Array.isArray(dayBlock?.items) ? dayBlock.items : [];
              return dayItems.map((item, index) => ({
                id: `${patientId}-${item.schedule_id}-${item.schedule_time_id}-${item.scheduled_at || index}`,
                patient_id: patientId,
                patient_med_id: Number(item.patient_med_id),
                schedule_id: Number(item.schedule_id),
                schedule_time_id: Number(item.schedule_time_id),
                scheduled_at: item.scheduled_at,
                scheduled_date: day,
                status: normalizeIntakeStatus(item.status),
                taken_at: item.taken_at,
                display_name: String(item.display_name || "").trim()
              }));
            });

            return {
              patientId,
              items,
              summary: data.summary || null,
              guideMap
            };
          })
        );

        const summaryByPatient = {};
        const medNameMap = new Map();
        rows.forEach((row) => {
          if (row.summary) {
            summaryByPatient[row.patientId] = row.summary;
          }
          Object.entries(row.guideMap || {}).forEach(([patientMedId, displayName]) => {
            if (!displayName) return;
            medNameMap.set(`${row.patientId}-${patientMedId}`, displayName);
          });
        });

        const items = rows
          .flatMap((row) => row.items)
          .map((item) => {
            const mappedName = medNameMap.get(`${item.patient_id}-${item.patient_med_id}`) || "";
            return {
              ...item,
              display_name: item.display_name || mappedName
            };
          })
          .sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at));

        if (isMounted) {
          setHomeMedicationState({
            loading: false,
            items,
            summaryByPatient,
            error: null
          });
        }
      } catch (error) {
        if (isMounted) {
          setHomeMedicationState({
            loading: false,
            items: [],
            summaryByPatient: {},
            error: error.message || "복약 상태 조회 실패"
          });
        }
      }
    };

    loadHomeMedicationStatus();
    return () => {
      isMounted = false;
    };
  }, [accessToken, isHomePage, selectedHomePatientKey]);

  useEffect(() => {
    if (!accessToken || !isHomePage) return;

    let isMounted = true;

    const loadHomeNotifications = async () => {
      setHomeNotificationsState({ loading: true, items: [], error: null });
      try {
        const params = new URLSearchParams();
        params.set("limit", isCaregiverRole ? "30" : "10");
        if (!isCaregiverRole && myPatient?.id) {
          params.set("patient_id", String(myPatient.id));
        }
        const res = await authFetch(`${API_PREFIX}/notifications?${params.toString()}`);
        if (!res.ok) {
          const body = await safeJson(res);
          throw new Error(formatApiError(body) || `status ${res.status}`);
        }

        const body = await safeJson(res);
        const data = body?.data || body || {};
        const items = Array.isArray(data.items) ? data.items : [];
        if (isMounted) {
          setHomeNotificationsState({ loading: false, items, error: null });
        }
      } catch (error) {
        if (isMounted) {
          setHomeNotificationsState({ loading: false, items: [], error: error.message || "알림 조회 실패" });
        }
      }
    };

    loadHomeNotifications();
    return () => {
      isMounted = false;
    };
  }, [accessToken, isHomePage, isCaregiverRole, normalizedLoginMode, myPatient?.id]);

  const checkHealth = async () => {
    setHealthStatus({ loading: true, data: null, error: null });
    try {
      const res = await fetch("/api/health");
      if (!res.ok) {
        throw new Error(`status ${res.status}`);
      }
      const body = await res.json();
      setHealthStatus({ loading: false, data: body, error: null });
    } catch (error) {
      setHealthStatus({ loading: false, data: null, error: error.message });
    }
  };

  const handleSignupChange = (event) => {
    const { name, value } = event.target;
    setSignupForm((prev) => ({
      ...prev,
      [name]: event.target.type === "checkbox" ? event.target.checked : value
    }));
  };

  const handleLoginChange = (event) => {
    const { name, value } = event.target;
    setLoginForm((prev) => ({
      ...prev,
      [name]: value
    }));
  };

  const handleProfileChange = (event) => {
    const { name, value } = event.target;
    setProfileForm((prev) => ({
      ...prev,
      [name]: value
    }));
  };

  const resolveRoleLabel = (role) => {
    if (!role) {
      return "";
    }
    if (role.description) {
      return role.description;
    }
    const code = role.code || role.name || "";
    const normalized = code.toUpperCase();
    if (normalized === "PATIENT") {
      return "복약자";
    }
    if (normalized === "CAREGIVER" || normalized === "GUARDIAN") {
      return "보호자";
    }
    if (normalized === "ADMIN") {
      return "관리자";
    }
    return code;
  };

  const formatValidationError = (item) => {
    if (!item || typeof item !== "object") {
      return null;
    }
    const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : null;
    if (item.type === "string_too_short" && item.ctx?.min_length) {
      if (field === "password") {
        return `비밀번호는 최소 ${item.ctx.min_length}자 이상이어야 합니다.`;
      }
      return `${field ?? "입력값"}은(는) 최소 ${item.ctx.min_length}자 이상이어야 합니다.`;
    }
    if (item.type === "value_error.email") {
      return "이메일 형식이 올바르지 않습니다.";
    }
    if (field === "phone_number" && item.type === "value_error") {
      return "휴대폰 번호 형식이 올바르지 않습니다.";
    }
    if (field === "birth_date" || field === "birthday") {
      return "생년월일 형식이 올바르지 않습니다.";
    }
    if (item.msg) {
      return item.msg;
    }
    return null;
  };

  const formatApiError = (value) => {
    if (!value) {
      return "알 수 없는 오류가 발생했습니다.";
    }
    if (typeof value === "string") {
      return value;
    }
    if (Array.isArray(value)) {
      const messages = value.map((item) => formatValidationError(item) || formatApiError(item));
      return messages.filter(Boolean).join(", ");
    }
    if (typeof value === "object") {
      if (Object.keys(value).length === 0) {
        return null;
      }
      if (value.detail) {
        return formatApiError(value.detail);
      }
      if (value.message) {
        return formatApiError(value.message);
      }
      return JSON.stringify(value);
    }
    return String(value);
  };

  const handleSignupSubmit = async (event) => {
    if (event?.preventDefault) {
      event.preventDefault();
    }
    if (signupForm.password !== signupForm.passwordConfirm) {
      setSignupState({ submitting: false, error: "비밀번호가 일치하지 않습니다.", success: false });
      return;
    }
    if (!signupForm.privacyConsent) {
      setSignupState({ submitting: false, error: "개인정보 수집·이용에 동의해 주세요.", success: false });
      return;
    }
    setSignupState({ submitting: true, error: null, success: false });
    try {
      const payload = {
        email: signupForm.email,
        password: signupForm.password,
        name: signupForm.name,
        gender: signupForm.gender,
        birth_date: signupForm.birthDate,
        phone_number: signupForm.phoneNumber,
        role: signupForm.role
      };
      const res = await fetch("/api/v1/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const message = formatApiError(body) || `status ${res.status}`;
        throw new Error(message);
      }
      setSignupState({ submitting: false, error: null, success: true });
      window.location.href = "/login";
    } catch (error) {
      setSignupState({
        submitting: false,
        error: formatApiError(error?.message || error),
        success: false
      });
    }
  };

  const handleLoginSubmit = async (event) => {
    if (event?.preventDefault) {
      event.preventDefault();
    }
    setLoginState({ submitting: true, error: null });
    try {
      const payload = {
        email: loginForm.email,
        password: loginForm.password,
        role: loginForm.role
      };
      const res = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const message = formatApiError(body) || `status ${res.status}`;
        throw new Error(message);
      }
      const body = await res.json().catch(() => ({}));
      const token = body?.access_token;
      const role = body?.login_role || loginForm.role;
      if (token) {
        persistAccessToken(token);
      }
      if (role) {
        persistLoginRole(role);
      }
      setLoginState({ submitting: false, error: null });
      window.location.href = "/app";
    } catch (error) {
      setLoginState({ submitting: false, error: formatApiError(error?.message || error) });
    }
  };

  const handleFindEmailSubmit = async (event) => {
    event.preventDefault();
    setFindEmailState({ submitting: true, error: null, email: null });
    try {
      const payload = {
        name: findEmailForm.name,
        phone_number: findEmailForm.phoneNumber
      };
      const res = await fetch("/api/v1/auth/find-email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      const body = await res.json();
      setFindEmailState({ submitting: false, error: null, email: body.email });
    } catch (error) {
      setFindEmailState({ submitting: false, error: formatApiError(error?.message || error), email: null });
    }
  };

  const handleResetPasswordSubmit = async (event) => {
    event.preventDefault();
    if (resetPasswordForm.newPassword !== resetPasswordForm.newPasswordConfirm) {
      setResetPasswordState({ submitting: false, error: "비밀번호가 일치하지 않습니다.", success: false });
      return;
    }
    setResetPasswordState({ submitting: true, error: null, success: false });
    try {
      const payload = {
        email: resetPasswordForm.email,
        name: resetPasswordForm.name,
        phone_number: resetPasswordForm.phoneNumber,
        new_password: resetPasswordForm.newPassword
      };
      const res = await fetch("/api/v1/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      setResetPasswordState({ submitting: false, error: null, success: true });
      setTimeout(() => {
        setShowFindModal(false);
        setResetPasswordState({ submitting: false, error: null, success: false });
        setResetPasswordForm({ email: "", name: "", phoneNumber: "", newPassword: "", newPasswordConfirm: "" });
      }, 2000);
    } catch (error) {
      setResetPasswordState({ submitting: false, error: formatApiError(error?.message || error), success: false });
    }
  };

  const startSocialLogin = async (provider, role) => {
    setLoginState({ submitting: true, error: null });
    try {
      const params = new URLSearchParams();
      if (role) {
        params.set("role", role);
      }
      const res = await fetch(`${API_PREFIX}/auth/social/${provider}/login?${params.toString()}`);
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      const body = await safeJson(res);
      const authorizeUrl = body?.authorize_url;
      if (!authorizeUrl) {
        throw new Error("소셜 로그인 URL을 가져오지 못했습니다.");
      }
      persistAccessToken(null);
      persistLoginRole(role || loginForm.role || "PATIENT");
      window.location.href = authorizeUrl;
    } catch (error) {
      setLoginState({ submitting: false, error: formatApiError(error?.message || error) });
    }
  };

  const handleLogout = async (event) => {
    if (event?.preventDefault) {
      event.preventDefault();
    }
    try {
      await fetch(`${API_PREFIX}/auth/logout`, { method: "POST", credentials: "include" });
    } catch {
      // ignore network failures; still clear local auth state
    } finally {
      persistAccessToken(null);
      setMeState({ loading: false, data: null, error: null });
      setLinksState({ loading: false, data: null, error: null });
      setNotificationsState({ loading: false, items: [], nextCursor: null, error: null });
      setUnreadCountState({ loading: false, count: 0, error: null });
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
    }
  };

  const [showWithdrawConfirm, setShowWithdrawConfirm] = useState(false);
  const [withdrawState, setWithdrawState] = useState({ submitting: false, error: null });

  const handleWithdraw = async () => {
    setWithdrawState({ submitting: true, error: null });
    try {
      const res = await authFetch(`${API_PREFIX}/users/me`, { method: "DELETE" });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      persistAccessToken(null);
      window.location.href = "/login";
    } catch (error) {
      setWithdrawState({ submitting: false, error: error.message || "탈퇴 처리 중 오류가 발생했습니다." });
    }
  };

  const submitProfileUpdate = async (event) => {
    event.preventDefault();
    setProfileState({ submitting: true, error: null, success: false });
    try {
      const payload = {};
      if (profileForm.name) payload.name = profileForm.name;
      if (profileForm.email) payload.email = profileForm.email;
      if (profileForm.phone_number) payload.phone_number = profileForm.phone_number;
      if (profileForm.birthday) payload.birthday = profileForm.birthday;
      if (profileForm.gender) payload.gender = profileForm.gender;

      const res = await authFetch(`${API_PREFIX}/users/me`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      const data = await res.json();
      setMeState({ loading: false, data, error: null });
      setProfileState({ submitting: false, error: null, success: true });
    } catch (error) {
      setProfileState({ submitting: false, error: formatApiError(error?.message || error), success: false });
    }
  };

  const createInviteCode = async () => {
    setInviteState({ submitting: true, error: null, data: null });
    try {
      const payload = {
        expires_in_minutes: Number(inviteCodeForm.expires_in_minutes) || 5
      };
      const res = await authFetch(`${API_PREFIX}/users/invite-code`, {
        method: "POST",
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      const data = await res.json();
      setInviteState({ submitting: false, error: null, data });
    } catch (error) {
      setInviteState({ submitting: false, error: formatApiError(error?.message || error), data: null });
    }
  };

  const deleteInviteCode = async () => {
    setInviteDeleteState({ submitting: true, error: null, success: false });
    try {
      const res = await authFetch(`${API_PREFIX}/users/invite-code`, { method: "DELETE" });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      setInviteDeleteState({ submitting: false, error: null, success: true });
      setInviteState((prev) => ({ ...prev, data: null }));
    } catch (error) {
      setInviteDeleteState({
        submitting: false,
        error: formatApiError(error?.message || error),
        success: false
      });
    }
  };

  const linkByInviteCode = async (event) => {
    event.preventDefault();
    setLinkAction({ submitting: true, error: null, success: null });
    try {
      const payload = { code: linkForm.code };
      const res = await authFetch(`${API_PREFIX}/users/link`, {
        method: "POST",
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      await res.json();
      setLinkAction({ submitting: false, error: null, success: "연동 완료" });
      const reload = await authFetch(`${API_PREFIX}/users/links`);
      if (reload.ok) {
        const data = await reload.json();
        setLinksState({ loading: false, data, error: null });
      }
    } catch (error) {
      setLinkAction({ submitting: false, error: formatApiError(error?.message || error), success: null });
    }
  };

  const unlinkPatient = async (linkId) => {
    setLinkAction({ submitting: true, error: null, success: null });
    try {
      const res = await authFetch(`${API_PREFIX}/users/links/${linkId}`, {
        method: "DELETE"
      });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      await res.json();
      setLinkAction({ submitting: false, error: null, success: "연동 해제 완료" });
      const reload = await authFetch(`${API_PREFIX}/users/links`);
      if (reload.ok) {
        const data = await reload.json();
        setLinksState({ loading: false, data, error: null });
      }
    } catch (error) {
      setLinkAction({ submitting: false, error: formatApiError(error?.message || error), success: null });
    }
  };

  const loadMoreNotifications = async () => {
    if (notificationsState.loading) {
      return;
    }
    setNotificationsState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const params = new URLSearchParams();
      params.set("limit", "20");
      if (notificationsState.nextCursor) {
        params.set("cursor", notificationsState.nextCursor);
      }
      const res = await authFetch(`${API_PREFIX}/notifications?${params.toString()}`);
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      const body = await safeJson(res);
      const data = body?.data || body;
      setNotificationsState((prev) => ({
        loading: false,
        items: [...prev.items, ...(data?.items || [])],
        nextCursor: data?.next_cursor ?? null,
        error: null
      }));
    } catch (error) {
      setNotificationsState((prev) => ({ ...prev, loading: false, error: error.message }));
    }
  };

  const markNotificationRead = async (notificationId) => {
    setNotificationsAction({ submitting: true, error: null });
    try {
      const res = await authFetch(`${API_PREFIX}/notifications/${notificationId}/read`, {
        method: "PATCH"
      });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      setNotificationsState((prev) => ({
        ...prev,
        items: prev.items.map((item) =>
          item.id === notificationId ? { ...item, read_at: item.read_at || new Date().toISOString() } : item
        )
      }));
      setUnreadCountState((prev) => ({ ...prev, count: Math.max(0, prev.count - 1) }));
      setNotificationsAction({ submitting: false, error: null });
    } catch (error) {
      setNotificationsAction({ submitting: false, error: formatApiError(error?.message || error) });
    }
  };

  const markAllNotificationsRead = async () => {
    setNotificationsAction({ submitting: true, error: null });
    try {
      const res = await authFetch(`${API_PREFIX}/notifications/read-all`, {
        method: "PATCH"
      });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      setNotificationsState((prev) => ({
        ...prev,
        items: prev.items.map((item) => ({ ...item, read_at: item.read_at || new Date().toISOString() }))
      }));
      setUnreadCountState((prev) => ({ ...prev, count: 0 }));
      setNotificationsAction({ submitting: false, error: null });
    } catch (error) {
      setNotificationsAction({ submitting: false, error: formatApiError(error?.message || error) });
    }
  };

  const handleSettingsChange = (event) => {
    const { name, checked } = event.target;
    setSettingsState((prev) => ({
      ...prev,
      data: {
        ...(prev.data || {}),
        [name]: checked
      },
      success: false
    }));
  };

  const submitSettingsUpdate = async (event) => {
    event.preventDefault();
    if (!settingsState.data) {
      return;
    }
    setSettingsState((prev) => ({ ...prev, submitting: true, error: null, success: false }));
    try {
      const res = await authFetch(`${API_PREFIX}/notifications/settings`, {
        method: "PATCH",
        body: JSON.stringify(settingsState.data)
      });
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      const body = await safeJson(res);
      const data = body?.data || body;
      setSettingsState((prev) => ({
        ...prev,
        submitting: false,
        data,
        success: true,
        error: null
      }));
    } catch (error) {
      setSettingsState((prev) => ({
        ...prev,
        submitting: false,
        error: formatApiError(error?.message || error),
        success: false
      }));
    }
  };

  const handleRemindChange = (event) => {
    const { name, value } = event.target;
    setRemindForm((prev) => ({
      ...prev,
      [name]: value
    }));
  };

  const submitRemind = async (event) => {
    event.preventDefault();
    
    if (!remindForm.patient_id) {
      setRemindState({ submitting: false, error: "복약자를 선택해주세요.", success: null });
      return;
    }
    
    setRemindState({ submitting: true, error: null, success: null });
    try {
      const payload = {
        patient_id: Number(remindForm.patient_id),
        type: remindForm.type,
        title: remindForm.title || "복약 리마인드",
        message: remindForm.message || "복약 시간이예요! 확인해 주세요."
      };
      
      if (remindForm.payload && remindForm.payload.trim()) {
        try {
          payload.payload = JSON.parse(remindForm.payload);
        } catch {
          throw new Error("payload는 유효한 JSON 형식이어야 합니다.");
        }
      }
      
      const res = await authFetch(`${API_PREFIX}/notifications/remind`, {
        method: "POST",
        body: JSON.stringify(payload)
      });
      
      if (!res.ok) {
        const body = await safeJson(res);
        throw new Error(formatApiError(body) || `status ${res.status}`);
      }
      
      setRemindState({ submitting: false, error: null, success: "리마인드 전송 완료" });
      
      // 성공 후 폼 초기화
      setTimeout(() => {
        setRemindState({ submitting: false, error: null, success: null });
      }, 3000);
    } catch (error) {
      setRemindState({ submitting: false, error: formatApiError(error?.message || error), success: null });
    }
  };

  if (isLandingPage) {
    return <LandingPage />;
  }

  if (isSignupPage) {
    return (
      <div className="login-page">
        <div className="container">
          <div className="row justify-content-center">
            <div className="col-lg-6">
              <div className="card shadow-lg border-0">
                <div className="card-body p-4">
                  <h2 className="fw-bold mb-2">회원가입</h2>
                  <p className="text-muted mb-4">팀 계정을 생성하세요.</p>
                  <form onSubmit={handleSignupSubmit}>
                    <div className="row g-3">
                      <div className="col-md-6">
                        <label className="form-label">이름</label>
                        <input
                          type="text"
                          className="form-control"
                          name="name"
                          value={signupForm.name}
                          onChange={handleSignupChange}
                          placeholder="홍길동"
                          required
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">역할</label>
                        <select
                          className="form-select"
                          name="role"
                          value={signupForm.role}
                          onChange={handleSignupChange}
                        >
                          <option value="PATIENT">복약자</option>
                          <option value="CAREGIVER">보호자</option>
                        </select>
                      </div>
                      <div className="col-12">
                        <label className="form-label">이메일</label>
                        <input
                          type="email"
                          className="form-control"
                          name="email"
                          value={signupForm.email}
                          onChange={handleSignupChange}
                          placeholder="name@clinic.com"
                          required
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">성별</label>
                        <select
                          className="form-select"
                          name="gender"
                          value={signupForm.gender}
                          onChange={handleSignupChange}
                        >
                          <option value="MALE">남성</option>
                          <option value="FEMALE">여성</option>
                        </select>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">생년월일</label>
                        <input
                          type="date"
                          className="form-control"
                          name="birthDate"
                          value={signupForm.birthDate}
                          onChange={handleSignupChange}
                          required
                        />
                      </div>
                      <div className="col-12">
                        <label className="form-label">휴대폰 번호</label>
                        <input
                          type="tel"
                          className="form-control"
                          name="phoneNumber"
                          value={signupForm.phoneNumber}
                          onChange={handleSignupChange}
                          placeholder="01012345678"
                          required
                        />
                      </div>
                      <div className="col-12">
                        <div className="form-check">
                          <input
                            className="form-check-input"
                            type="checkbox"
                            id="privacyConsent"
                            name="privacyConsent"
                            checked={signupForm.privacyConsent}
                            onChange={handleSignupChange}
                            required
                          />
                          <label className="form-check-label" htmlFor="privacyConsent">
                            개인정보 수집·이용에 동의합니다(필수)
                          </label>
                        </div>
                        <div className="small text-muted mt-1">
                          <div>수집·이용 목적: 회원가입, 본인확인, 서비스 제공 및 고객지원</div>
                          <div>수집 항목: 이름, 이메일(아이디), 비밀번호, 성별, 생년월일, 휴대폰 번호</div>
                          <div>보유·이용 기간: 회원 탈퇴 시까지(단, 관계법령에 따라 보관이 필요한 경우 해당 기간 보관)</div>
                          <div>동의 거부 권리: 개인정보 수집·이용에 대한 동의를 거부할 수 있으나, 동의 거부 시 회원가입이 제한됩니다.</div>
                        </div>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">비밀번호</label>
                        <input
                          type="password"
                          className="form-control"
                          name="password"
                          value={signupForm.password}
                          onChange={handleSignupChange}
                          placeholder="비밀번호 입력"
                          required
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">비밀번호 확인</label>
                        <input
                          type="password"
                          className="form-control"
                          name="passwordConfirm"
                          value={signupForm.passwordConfirm}
                          onChange={handleSignupChange}
                          placeholder="비밀번호 확인"
                          required
                        />
                      </div>
                    </div>
                    <div className="d-grid gap-2 mt-4">
                      <button type="submit" className="btn btn-primary btn-lg" disabled={signupState.submitting}>
                        {signupState.submitting ? "처리 중..." : "회원가입"}
                      </button>
                      <a className="btn btn-outline-secondary" href="/login">
                        로그인으로 돌아가기
                      </a>
                    </div>
                  </form>
                  {signupState.error && <div className="alert alert-danger mt-3">{signupState.error}</div>}
                  {signupState.success && <div className="alert alert-success mt-3">회원가입 완료</div>}
                  <div className="mt-4 small text-muted">
                    계정 생성 시 약관에 동의한 것으로 간주합니다.
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (isLoginPage) {
    if (accessToken) {
      window.location.href = "/app";
      return null;
    }
    if (authChecking) {
      return (
        <div className="login-page">
          <div className="container text-center">
            <div className="py-5 text-muted">로그인 상태 확인 중...</div>
          </div>
        </div>
      );
    }
    return (
      <div className="login-page">
        <div className="container">
          <div className="row justify-content-center">
            <div className="col-lg-5">
              <div className="card shadow-lg border-0">
                <div className="card-body p-4">
                  <h2 className="fw-bold mb-2">로그인</h2>
                  <p className="text-muted mb-4">팀 계정으로 로그인하세요.</p>
                  <div>
                    <div className="mb-3">
                      <label className="form-label">이메일</label>
                      <input
                        type="email"
                        className="form-control"
                        name="email"
                        value={loginForm.email}
                        onChange={handleLoginChange}
                        placeholder="name@clinic.com"
                        required
                      />
                    </div>
                    <div className="mb-3">
                      <label className="form-label">비밀번호</label>
                      <input
                        type="password"
                        className="form-control"
                        name="password"
                        value={loginForm.password}
                        onChange={handleLoginChange}
                        placeholder="비밀번호 입력"
                        required
                      />
                    </div>
                    <div className="mb-4">
                      <label className="form-label">역할</label>
                      <select
                        className="form-select"
                        name="role"
                        value={loginForm.role}
                        onChange={handleLoginChange}
                      >
                        <option value="PATIENT">복약자</option>
                        <option value="CAREGIVER">보호자</option>
                        <option value="ADMIN">관리자</option>
                      </select>
                    </div>
                    <div className="d-grid gap-2">
                      <button
                        type="button"
                        className="btn btn-primary btn-lg"
                        disabled={loginState.submitting}
                        onClick={handleLoginSubmit}
                      >
                        {loginState.submitting ? "처리 중..." : "로그인"}
                      </button>
                      <button
                        type="button"
                        className="btn btn-kakao btn-lg"
                        onClick={() => startSocialLogin("kakao", loginForm.role)}
                        disabled={loginState.submitting}
                      >
                        카카오톡 간편로그인
                      </button>
                      <a className="btn btn-outline-secondary" href="/signup">
                        회원가입
                      </a>
                      <button
                        type="button"
                        className="btn btn-link text-muted"
                        onClick={() => {
                          setShowFindModal(true);
                          setFindModalTab("email");
                        }}
                      >
                        아이디/비밀번호 찾기
                      </button>
                    </div>
                  </div>
                  {loginState.error && <div className="alert alert-danger mt-3">{loginState.error}</div>}
                </div>
              </div>
            </div>
          </div>
        </div>
        {showFindModal && (
          <div className="modal show d-block" style={{ backgroundColor: "rgba(0,0,0,0.5)" }}>
            <div className="modal-dialog modal-dialog-centered">
              <div className="modal-content">
                <div className="modal-header">
                  <h5 className="modal-title">아이디/비밀번호 찾기</h5>
                  <button
                    type="button"
                    className="btn-close"
                    onClick={() => {
                      setShowFindModal(false);
                      setFindEmailState({ submitting: false, error: null, email: null });
                      setResetPasswordState({ submitting: false, error: null, success: false });
                      setFindEmailForm({ name: "", phoneNumber: "" });
                      setResetPasswordForm({ email: "", name: "", phoneNumber: "", newPassword: "", newPasswordConfirm: "" });
                    }}
                  ></button>
                </div>
                <div className="modal-body">
                  <ul className="nav nav-tabs mb-3">
                    <li className="nav-item">
                      <button
                        className={`nav-link ${findModalTab === "email" ? "active" : ""}`}
                        onClick={() => setFindModalTab("email")}
                      >
                        아이디 찾기
                      </button>
                    </li>
                    <li className="nav-item">
                      <button
                        className={`nav-link ${findModalTab === "password" ? "active" : ""}`}
                        onClick={() => setFindModalTab("password")}
                      >
                        비밀번호 재설정
                      </button>
                    </li>
                  </ul>
                  {findModalTab === "email" && (
                    <form onSubmit={handleFindEmailSubmit}>
                      <div className="mb-3">
                        <label className="form-label">이름</label>
                        <input
                          type="text"
                          className="form-control"
                          value={findEmailForm.name}
                          onChange={(e) => setFindEmailForm({ ...findEmailForm, name: e.target.value })}
                          required
                        />
                      </div>
                      <div className="mb-3">
                        <label className="form-label">휴대폰 번호</label>
                        <input
                          type="tel"
                          className="form-control"
                          value={findEmailForm.phoneNumber}
                          onChange={(e) => setFindEmailForm({ ...findEmailForm, phoneNumber: e.target.value })}
                          placeholder="01012345678"
                          required
                        />
                      </div>
                      <button type="submit" className="btn btn-primary w-100" disabled={findEmailState.submitting}>
                        {findEmailState.submitting ? "확인 중..." : "아이디 찾기"}
                      </button>
                      {findEmailState.error && <div className="alert alert-danger mt-3">{findEmailState.error}</div>}
                      {findEmailState.email && (
                        <div className="alert alert-success mt-3">
                          회원님의 아이디는 <strong>{findEmailState.email}</strong> 입니다.
                        </div>
                      )}
                    </form>
                  )}
                  {findModalTab === "password" && (
                    <form onSubmit={handleResetPasswordSubmit}>
                      <div className="mb-3">
                        <label className="form-label">이메일</label>
                        <input
                          type="email"
                          className="form-control"
                          value={resetPasswordForm.email}
                          onChange={(e) => setResetPasswordForm({ ...resetPasswordForm, email: e.target.value })}
                          required
                        />
                      </div>
                      <div className="mb-3">
                        <label className="form-label">이름</label>
                        <input
                          type="text"
                          className="form-control"
                          value={resetPasswordForm.name}
                          onChange={(e) => setResetPasswordForm({ ...resetPasswordForm, name: e.target.value })}
                          required
                        />
                      </div>
                      <div className="mb-3">
                        <label className="form-label">휴대폰 번호</label>
                        <input
                          type="tel"
                          className="form-control"
                          value={resetPasswordForm.phoneNumber}
                          onChange={(e) => setResetPasswordForm({ ...resetPasswordForm, phoneNumber: e.target.value })}
                          placeholder="01012345678"
                          required
                        />
                      </div>
                      <div className="mb-3">
                        <label className="form-label">새 비밀번호</label>
                        <input
                          type="password"
                          className="form-control"
                          value={resetPasswordForm.newPassword}
                          onChange={(e) => setResetPasswordForm({ ...resetPasswordForm, newPassword: e.target.value })}
                          required
                        />
                      </div>
                      <div className="mb-3">
                        <label className="form-label">새 비밀번호 확인</label>
                        <input
                          type="password"
                          className="form-control"
                          value={resetPasswordForm.newPasswordConfirm}
                          onChange={(e) => setResetPasswordForm({ ...resetPasswordForm, newPasswordConfirm: e.target.value })}
                          required
                        />
                      </div>
                      <button type="submit" className="btn btn-primary w-100" disabled={resetPasswordState.submitting}>
                        {resetPasswordState.submitting ? "처리 중..." : "비밀번호 재설정"}
                      </button>
                      {resetPasswordState.error && <div className="alert alert-danger mt-3">{resetPasswordState.error}</div>}
                      {resetPasswordState.success && <div className="alert alert-success mt-3">비밀번호가 재설정되었습니다.</div>}
                    </form>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  if (!isLoginPage && !isSignupPage && !accessToken) {
    if (authChecking) {
      return (
        <div className="login-page">
          <div className="container text-center">
            <div className="py-5 text-muted">인증 상태 확인 중...</div>
          </div>
        </div>
      );
    }
    window.location.href = "/login";
    return null;
  }

  if (isProfilePage && !accessToken) {
    if (authChecking) {
      return (
        <div className="login-page">
          <div className="container text-center">
            <div className="py-5 text-muted">인증 상태 확인 중...</div>
          </div>
        </div>
      );
    }
    window.location.href = "/login";
    return null;
  }

  if (isDashboardPage) {
    if (!accessToken) {
      if (authChecking) {
        return (
          <div className="login-page">
            <div className="container text-center">
              <div className="py-5 text-muted">인증 상태 확인 중...</div>
            </div>
          </div>
        );
      }
      window.location.href = "/login";
      return null;
    }
    if (normalizedLoginMode !== "ADMIN") {
      return (
        <AppLayout
          activeKey="admin-dashboard"
          title="접근 불가"
          description="관리자만 접근할 수 있는 페이지입니다."
          loginRole={loginRole}
          modeOptions={modeOptions}
          currentMode={normalizedLoginMode}
          onModeChange={handleModeChange}
        >
          <div className="alert alert-danger mt-3">관리자 계정으로 로그인해주세요.</div>
        </AppLayout>
      );
    }
    return (
      <AdminDashboard
        modeOptions={modeOptions}
        currentMode={normalizedLoginMode}
        onModeChange={handleModeChange}
      />
    );
  }

  if (isHealthProfilePage) {
    if (!accessToken) {
      if (authChecking) {
        return (
          <div className="login-page">
            <div className="container text-center">
              <div className="py-5 text-muted">인증 상태 확인 중...</div>
            </div>
          </div>
        );
      }
      window.location.href = "/login";
      return null;
    }
    return (
      <HealthProfile
        modeOptions={modeOptions}
        currentMode={normalizedLoginMode}
        onModeChange={handleModeChange}
        selfPatient={ownedPatientProfile}
        userName={meState.data?.name}
      />
    );
  }

  if (isDocumentsPage) {
    if (!accessToken) {
      if (authChecking) {
        return (
          <div className="login-page">
            <div className="container text-center">
              <div className="py-5 text-muted">인증 상태 확인 중...</div>
            </div>
          </div>
        );
      }
      window.location.href = "/login";
      return null;
    }
    return (
      <DocumentManagement
        linkedPatients={linkedPatients}
        myPatient={myPatient}
        selfPatient={ownedPatientProfile}
        loginRole={loginRole}
        userName={meState.data?.name}
        modeOptions={modeOptions}
        currentMode={normalizedLoginMode}
        onModeChange={handleModeChange}
      />
    );
  }

  if (isCaregiverPage) {
    if (!accessToken) {
      if (authChecking) {
        return (
          <div className="login-page">
            <div className="container text-center">
              <div className="py-5 text-muted">인증 상태 확인 중...</div>
            </div>
          </div>
        );
      }
      window.location.href = "/login";
      return null;
    }

    return (
      <NotificationPage
        linkedPatients={linkedPatients}
        myPatient={myPatient}
        selfPatient={ownedPatientProfile}
        loginRole={loginRole}
        me={meState.data}
        userName={meState.data?.name}
        modeOptions={modeOptions}
        currentMode={normalizedLoginMode}
        onModeChange={handleModeChange}
      />
    );
  }

  if (isAiPage) {
    if (!accessToken) {
      if (authChecking) {
        return (
          <div className="login-page">
            <div className="container text-center">
              <div className="py-5 text-muted">인증 상태 확인 중...</div>
            </div>
          </div>
        );
      }
      window.location.href = "/login";
      return null;
    }
    return (
      <AiPage
        userName={meState.data?.name}
        modeOptions={modeOptions}
        currentMode={normalizedLoginMode}
        onModeChange={handleModeChange}
      />
    );
  }

  if (isDrugSearchPage) {
    if (!accessToken) {
      if (authChecking) {
        return (
          <div className="login-page">
            <div className="container text-center">
              <div className="py-5 text-muted">인증 상태 확인 중...</div>
            </div>
          </div>
        );
      }
      window.location.href = "/login";
      return null;
    }
    return (
      <DrugSearchPage
        userName={meState.data?.name}
        modeOptions={modeOptions}
        currentMode={normalizedLoginMode}
        onModeChange={handleModeChange}
      />
    );
  }

  if (isMedicationCheckPage) {
    if (!accessToken) {
      if (authChecking) {
        return (
          <div className="login-page">
            <div className="container text-center">
              <div className="py-5 text-muted">인증 상태 확인 중...</div>
            </div>
          </div>
        );
      }
      window.location.href = "/login";
      return null;
    }

    return (
      <MedicationCheckPage
        linkedPatients={linkedPatients}
        myPatient={myPatient}
        loginRole={loginRole}
        me={meState.data}
        userName={meState.data?.name}
        modeOptions={modeOptions}
        currentMode={normalizedLoginMode}
        onModeChange={handleModeChange}
      />
    );
  }

  if (isSchedulePage) {
    if (!accessToken) {
      if (authChecking) {
        return (
          <div className="login-page">
            <div className="container text-center">
              <div className="py-5 text-muted">인증 상태 확인 중...</div>
            </div>
          </div>
        );
      }
      window.location.href = "/login";
      return null;
    }

    return (
      <SchedulePage
        linkedPatients={linkedPatients}
        myPatient={myPatient}
        loginRole={loginRole}
        userName={meState.data?.name}
        modeOptions={modeOptions}
        currentMode={normalizedLoginMode}
        onModeChange={handleModeChange}
      />
    );
  }

  if (isSettingsPage) {
    if (!accessToken) {
      if (authChecking) {
        return (
          <div className="login-page">
            <div className="container text-center">
              <div className="py-5 text-muted">인증 상태 확인 중...</div>
            </div>
          </div>
        );
      }
      window.location.href = "/login";
      return null;
    }
    return (
      <SettingsPage
        modeOptions={modeOptions}
        currentMode={normalizedLoginMode}
        onModeChange={handleModeChange}
        selfPatient={ownedPatientProfile}
        userName={meState.data?.name}
      />
    );
  }

  if (isProfilePage) {
    return (
      <AppLayout
        activeKey="settings"
        title="개인정보"
        description="계정 정보와 보안 설정을 관리하세요."
        loginRole={loginRole}
        userName={layoutUserName}
        modeOptions={modeOptions}
        currentMode={normalizedLoginMode}
        onModeChange={handleModeChange}
      >
        <div className="container my-3">
          <div className="row g-4">
            <div className="col-lg-6">
              <div className="card border-0 shadow-sm">
                <div className="card-body">
                  <h5 className="card-title">기본 정보</h5>
                  <p className="text-muted">계정에 등록된 기본 정보를 확인하세요.</p>
                  {meState.loading && <div className="text-muted">불러오는 중...</div>}
                  {meState.error && <div className="alert alert-danger">{meState.error}</div>}
                  {meState.data && (
                    <div className="row g-3">
                      <div className="col-md-6">
                        <div className="border rounded-3 p-3 h-100">
                          <div className="text-muted small">이메일</div>
                          <div className="fw-semibold">{meState.data.email}</div>
                        </div>
                      </div>
                      <div className="col-md-6">
                        <div className="border rounded-3 p-3 h-100">
                          <div className="text-muted small">역할</div>
                          <div className="fw-semibold">{loginRole}</div>
                        </div>
                      </div>
                      <div className="col-md-6">
                        <div className="border rounded-3 p-3 h-100">
                          <div className="text-muted small">계정 상태</div>
                          <div className="fw-semibold">활성</div>
                        </div>
                      </div>
                      <div className="col-md-6">
                        <div className="border rounded-3 p-3 h-100">
                          <div className="text-muted small">연락처</div>
                          <div className="fw-semibold">{meState.data.phone_number || "—"}</div>
                        </div>
                      </div>
                    </div>
                  )}
                  <form className="mt-4" onSubmit={submitProfileUpdate}>
                    <div className="row g-3">
                      <div className="col-md-6">
                        <label className="form-label">이름</label>
                        <input
                          className="form-control"
                          name="name"
                          value={profileForm.name}
                          onChange={handleProfileChange}
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">이메일</label>
                        <input
                          type="email"
                          className="form-control"
                          name="email"
                          value={profileForm.email}
                          onChange={handleProfileChange}
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">휴대폰 번호</label>
                        <input
                          className="form-control"
                          name="phone_number"
                          value={profileForm.phone_number}
                          onChange={handleProfileChange}
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">생년월일</label>
                        <input
                          type="date"
                          className="form-control"
                          name="birthday"
                          value={profileForm.birthday || ""}
                          onChange={handleProfileChange}
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">성별</label>
                        <select
                          className="form-select"
                          name="gender"
                          value={profileForm.gender}
                          onChange={handleProfileChange}
                        >
                          <option value="MALE">남성</option>
                          <option value="FEMALE">여성</option>
                        </select>
                      </div>
                    </div>
                    <div className="d-flex gap-2 mt-4">
                      <button className="btn btn-outline-primary" type="submit" disabled={profileState.submitting}>
                        {profileState.submitting ? "저장 중..." : "정보 수정"}
                      </button>
                      <button
                        className="btn btn-outline-secondary"
                        type="button"
                        onClick={() => {
                          if (!meState.data) {
                            return;
                          }
                          setProfileForm({
                            name: meState.data.name || "",
                            email: meState.data.email || "",
                            phone_number: meState.data.phone_number || "",
                            birthday: meState.data.birthday || "",
                            gender: meState.data.gender || "MALE"
                          });
                        }}
                      >
                        초기화
                      </button>
                      <button
                        className="btn btn-outline-danger"
                        type="button"
                        onClick={() => setShowWithdrawConfirm(true)}
                      >
                        회원탈퇴
                      </button>
                    </div>
                    {profileState.error && <div className="alert alert-danger mt-3">{profileState.error}</div>}
                    {profileState.success && <div className="alert alert-success mt-3">저장 완료</div>}
                  </form>
                </div>
              </div>
            </div>
            <div className="col-lg-6">
              <div className="card border-0 shadow-sm h-100">
                <div className="card-body">
                  <h5 className="card-title">보안 설정</h5>
                  <p className="text-muted">최근 로그인 활동과 보안 옵션을 관리하세요.</p>
                  <ul className="list-group list-group-flush">
                    <li className="list-group-item d-flex justify-content-between">
                      <span>최근 로그인</span>
                      <span className="fw-semibold">{lastLoginAt ? formatDateTimeKst(lastLoginAt) : "확인 중..."}</span>
                    </li>
                    <li className="list-group-item d-flex justify-content-between">
                      <span>2단계 인증</span>
                      <span className="fw-semibold">미설정</span>
                    </li>
                    <li className="list-group-item d-flex justify-content-between">
                      <span>연동된 기기</span>
                      <span className="fw-semibold">
                        {linkedDeviceCount === null ? "확인 중..." : `${linkedDeviceCount}대`}
                      </span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      </AppLayout>
    );
  }

  if (normalizedLoginMode === "ADMIN") {
    return (
      <AdminDashboard
        modeOptions={modeOptions}
        currentMode={normalizedLoginMode}
        onModeChange={handleModeChange}
      />
    );
  }

  const homeTitle = "홈";
  const homeDescription = isCaregiverRole
    ? "연동된 복약자의 일정과 복약 상태를 확인하세요."
    : "오늘 복약 일정과 새로운 알림을 확인하세요.";
  const isCaregiverAllView = isCaregiverRole && homePatientId === "all";
  const selectedHomePatientLabel = isCaregiverRole
    ? isCaregiverAllView
      ? "전체 복약자"
      : activeHomePatient?.name || "복약자 선택 필요"
    : meState.data?.name || "내 계정";
  const heroTitle = isCaregiverRole ? "보호자 관리 홈" : "복약자 서비스 홈";
  const heroSubtitle = isCaregiverRole
    ? "연동된 복약자의 일정과 복약 상태를 확인하세요."
    : "오늘 복약 일정과 새로운 알림을 확인하세요.";

  const rawHomeNotificationItems = homeNotificationsState.items || [];
  const homeNotificationItems = (() => {
    const selfPatientId = Number(ownedPatientProfile?.id);
    const normalizedSelfPatientId = Number.isFinite(selfPatientId) && selfPatientId > 0 ? selfPatientId : null;
    const caregiverPatientIdSet = new Set(
      linkedPatients
        .map((patient) => Number(patient?.id))
        .filter((id) => Number.isFinite(id) && id > 0)
    );
    const myPatientId = Number(myPatient?.id);
    const normalizedMyPatientId = Number.isFinite(myPatientId) && myPatientId > 0 ? myPatientId : null;

    const isVisibleForMode = (item) => {
      const patientId = resolveNotificationPatientId(item);
      if (isCaregiverRole) {
        if (!patientId) return false;
        if (normalizedSelfPatientId && patientId === normalizedSelfPatientId) return false;
        return caregiverPatientIdSet.has(patientId);
      }
      if (!normalizedMyPatientId) return true;
      if (!patientId) return false;
      return patientId === normalizedMyPatientId;
    };

    const modeFilteredItems = rawHomeNotificationItems.filter(isVisibleForMode);

    if (isCaregiverRole) {
      if (homePatientId === "all") {
        return modeFilteredItems.slice(0, 5);
      }
      const targetPatientId = Number(selectedHomePatientIds[0]);
      if (!targetPatientId) {
        return modeFilteredItems.slice(0, 5);
      }
      return modeFilteredItems
        .filter((item) => {
          const patientId = resolveNotificationPatientId(item);
          return patientId === targetPatientId;
        })
        .slice(0, 5);
    }

    if (!normalizedMyPatientId) {
      return modeFilteredItems.slice(0, 5);
    }

    return modeFilteredItems
      .filter((item) => {
        const patientId = resolveNotificationPatientId(item);
        return patientId === normalizedMyPatientId;
      })
      .slice(0, 5);
  })();
  const unreadNotificationCount = homeNotificationItems.filter((item) => !item.read_at).length;

  const homeToday = new Date();
  const todayKey = toDateKey(homeToday);
  const calendarYear = homeToday.getFullYear();
  const calendarMonth = homeToday.getMonth();
  const monthLabel = `${calendarYear}.${String(calendarMonth + 1).padStart(2, "0")}`;
  const firstDayOffset = new Date(calendarYear, calendarMonth, 1).getDay();
  const daysInMonth = new Date(calendarYear, calendarMonth + 1, 0).getDate();
  const calendarCells = [
    ...Array.from({ length: firstDayOffset }, () => null),
    ...Array.from({ length: daysInMonth }, (_, index) => index + 1),
  ];

  const scheduleItemsThisMonth = (homeScheduleState.items || []).filter((item) => {
    const date = new Date(item.scheduled_at);
    return date.getFullYear() === calendarYear && date.getMonth() === calendarMonth;
  });
  const calendarEventMap = scheduleItemsThisMonth.reduce((acc, item) => {
    const date = new Date(item.scheduled_at);
    const day = date.getDate();
    const events = acc.get(day) || [];
    events.push(item);
    acc.set(day, events);
    return acc;
  }, new Map());
  const selectedScheduleDateKey = homeSelectedDate || todayKey;
  const selectedScheduleItems = (homeScheduleState.items || [])
    .filter((item) => toDateKey(item.scheduled_at) === selectedScheduleDateKey)
    .sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at));
  const selectedScheduleDateLabel = (() => {
    const date = new Date(selectedScheduleDateKey);
    if (Number.isNaN(date.getTime())) return "선택 일정";
    return date.toLocaleDateString("ko-KR", {
      month: "long",
      day: "numeric",
      weekday: "short"
    });
  })();

  const medicationItems = (homeMedicationState.items || []).sort(
    (a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at)
  );
  const takenMedicationCount = medicationItems.filter((item) => item.status === "taken").length;
  const pendingMedicationItems = medicationItems.filter((item) => item.status === "pending");
  const nextMedicationItem =
    pendingMedicationItems.find((item) => new Date(item.scheduled_at) >= homeToday) ||
    pendingMedicationItems[0] ||
    medicationItems[0] ||
    null;
  const remainingMedicationCount = Math.max(0, medicationItems.length - takenMedicationCount);

  const getPatientLabel = (patientId) => {
    if (!patientId) return "복약자";
    return homePatientNameMap.get(Number(patientId)) || `복약자 ${patientId}`;
  };

  const caregiverNeedCheckItems = medicationItems.filter(
    (item) => item.status === "pending" || item.status === "missed"
  );
  const caregiverNeedCheckPatientCount = new Set(caregiverNeedCheckItems.map((item) => item.patient_id)).size;
  const caregiverMissedCount = medicationItems.filter((item) => item.status === "missed").length;
  const medicationListSource = isCaregiverRole
    ? (caregiverNeedCheckItems.length > 0 ? caregiverNeedCheckItems : medicationItems)
    : medicationItems;

  const medicationGroupMap = new Map();
  medicationListSource.forEach((item) => {
    const date = new Date(item.scheduled_at);
    const sortTime = Number.isNaN(date.getTime()) ? Number.MAX_SAFE_INTEGER : date.getTime();
    const timeKey = Number.isNaN(date.getTime()) ? String(item.schedule_time_id || item.id || "") : `${date.getHours()}:${date.getMinutes()}`;
    const mealLabel = inferHomeMealLabel(item.scheduled_at);
    const patientKey = isCaregiverRole ? String(item.patient_id || "0") : "self";
    const groupKey = `${patientKey}-${mealLabel}-${timeKey}`;
    const fallbackPatientMedId = Number(item.patient_med_id);
    const medName =
      String(item.display_name || "").trim() ||
      (Number.isFinite(fallbackPatientMedId) && fallbackPatientMedId > 0
        ? `복약 항목 ${fallbackPatientMedId}`
        : "복약 항목");

    const current = medicationGroupMap.get(groupKey) || {
      id: groupKey,
      patient_id: item.patient_id,
      meal_label: mealLabel,
      time_label: formatClockTime(item.scheduled_at),
      sort_time: sortTime,
      med_names: [],
      statuses: [],
    };

    if (!current.med_names.includes(medName)) {
      current.med_names.push(medName);
    }
    current.statuses.push(item.status);

    if (sortTime < current.sort_time) {
      current.sort_time = sortTime;
      current.time_label = formatClockTime(item.scheduled_at);
    }

    medicationGroupMap.set(groupKey, current);
  });

  const groupedMedicationRows = Array.from(medicationGroupMap.values())
    .map((row) => ({
      ...row,
      status: resolveGroupIntakeStatus(row.statuses),
      main_label: isCaregiverRole
        ? `${getPatientLabel(row.patient_id)} · ${row.med_names.join(", ")}`
        : row.med_names.join(", ")
    }))
    .sort((a, b) => {
      const aMealIndex = HOME_MEAL_ORDER.includes(a.meal_label) ? HOME_MEAL_ORDER.indexOf(a.meal_label) : 999;
      const bMealIndex = HOME_MEAL_ORDER.includes(b.meal_label) ? HOME_MEAL_ORDER.indexOf(b.meal_label) : 999;
      if (aMealIndex !== bMealIndex) return aMealIndex - bMealIndex;
      if (a.sort_time !== b.sort_time) return a.sort_time - b.sort_time;
      return String(a.main_label).localeCompare(String(b.main_label), "ko");
    });

  const groupedMedicationSections = [
    ...HOME_MEAL_ORDER.map((mealLabel) => ({
      meal_label: mealLabel,
      rows: groupedMedicationRows.filter((row) => row.meal_label === mealLabel)
    })).filter((section) => section.rows.length > 0),
    ...(groupedMedicationRows.some((row) => !HOME_MEAL_ORDER.includes(row.meal_label))
      ? [{
          meal_label: "기타",
          rows: groupedMedicationRows.filter((row) => !HOME_MEAL_ORDER.includes(row.meal_label))
        }]
      : [])
  ];

  const limitedMedicationSections = [];
  let remainingGroupRows = HOME_MEDICATION_GROUP_LIMIT;
  groupedMedicationSections.forEach((section) => {
    if (remainingGroupRows <= 0) return;
    const rows = section.rows.slice(0, remainingGroupRows);
    if (rows.length === 0) return;
    limitedMedicationSections.push({ ...section, rows });
    remainingGroupRows -= rows.length;
  });

  return (
    <AppLayout
      activeKey="home"
      title={homeTitle}
      description={homeDescription}
      loginRole={loginRole}
      userName={layoutUserName}
      modeOptions={modeOptions}
      currentMode={normalizedLoginMode}
      onModeChange={handleModeChange}
    >
      <section className={`home-hero-banner home-hero-banner-compact ${isCaregiverRole ? "home-hero-banner-caregiver" : "home-hero-banner-patient"} mb-4`}>
        <div className="home-hero-main">
          <div>
            <div className="home-hero-brand">(주)케어브릿지</div>
            <h1 className="home-hero-title">{heroTitle}</h1>
            <p className="home-hero-subtitle mb-0">{heroSubtitle}</p>
          </div>
          <div className="home-hero-side home-hero-side-compact">
            <div className="home-hero-chip">
              <span className="home-hero-chip-label">{isCaregiverRole ? "현재 선택 복약자" : "사용자"}</span>
              <strong>{selectedHomePatientLabel}</strong>
            </div>
            <div className="home-hero-chip">
              <span className="home-hero-chip-label">미확인 알림</span>
              <strong>{unreadNotificationCount}건</strong>
            </div>
          </div>
        </div>
        <img className="home-hero-mascot-floating" src={`${import.meta.env.BASE_URL}mascot.png`} alt="" aria-hidden="true" />
      </section>

      <div className="home-core-grid">
        <section className="card home-info-card home-core-card home-core-calendar-card">
          <div className="card-body">
            {isCaregiverRole && (
              <div>
                <label className="form-label small mb-1">보기 기준</label>
                <select
                  className="form-select form-select-sm"
                  value={homePatientId || ""}
                  onChange={(event) => setHomePatientId(event.target.value)}
                >
                  {linkedPatients.length > 0 && <option value="all">전체 복약자</option>}
                  {linkedPatients.length === 0 && <option value="">연동 복약자 없음</option>}
                  {linkedPatients.map((patient) => (
                    <option key={patient.id} value={String(patient.id)}>
                      {patient.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="home-mini-calendar mt-3">
              <div className="home-mini-calendar-head">
                <strong>{monthLabel}</strong>
                <span className="small text-muted">오늘 {homeToday.getDate()}일</span>
              </div>
              <div className="home-mini-calendar-weekdays">
                {["일", "월", "화", "수", "목", "금", "토"].map((day) => (
                  <span key={day}>{day}</span>
                ))}
              </div>
              <div className="home-mini-calendar-grid">
                {calendarCells.map((day, index) => {
                  const dayEvents = day === null ? [] : calendarEventMap.get(day) || [];
                  return (
                    <div
                      key={`${day || "empty"}-${index}`}
                      className={[
                        "home-mini-calendar-cell",
                        day === null ? "is-empty" : "",
                        day === homeToday.getDate() ? "is-today" : "",
                        day !== null &&
                        selectedScheduleDateKey ===
                          `${calendarYear}-${String(calendarMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`
                          ? "is-selected"
                          : "",
                        dayEvents.length > 0 ? "has-event" : "",
                      ].join(" ").trim()}
                      onClick={() => {
                        if (day === null) return;
                        setHomeSelectedDate(
                          `${calendarYear}-${String(calendarMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`
                        );
                      }}
                    >
                      {day !== null && <div className="home-mini-calendar-date">{day}</div>}
                      {dayEvents.length > 0 && (
                        <div className="home-mini-calendar-events">
                          {dayEvents.slice(0, 2).map((eventItem) => {
                            const patientLabel = getPatientLabel(eventItem.patient_id);
                            const title = eventItem.title || "일정";
                            const label = isCaregiverRole && isCaregiverAllView ? `[${patientLabel}] ${title}` : title;
                            return (
                              <div key={eventItem.id} className="home-mini-calendar-event" title={label}>
                                {label}
                              </div>
                            );
                          })}
                          {dayEvents.length > 2 && (
                            <div className="home-mini-calendar-more">+{dayEvents.length - 2}</div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="home-inline-list mt-3">
              <div className="home-inline-title">{selectedScheduleDateLabel} 일정</div>
              {homeScheduleState.loading ? (
                <div className="home-inline-empty">일정을 불러오는 중...</div>
              ) : homeScheduleState.error ? (
                <div className="home-inline-empty">일정을 불러오지 못했습니다.</div>
              ) : selectedScheduleItems.length === 0 ? (
                <div className="home-inline-empty">선택한 날짜의 일정이 없습니다.</div>
              ) : (
                <div className="home-inline-stack">
                  {selectedScheduleItems.slice(0, 5).map((item) => {
                    const patientLabel = getPatientLabel(item.patient_id);
                    const title = item.title || "일정";
                    return (
                      <div key={item.id} className="home-inline-row">
                        <span className="home-inline-time">{formatClockTime(item.scheduled_at)}</span>
                        <span className="home-inline-main">
                          {isCaregiverRole ? `[${patientLabel}] ${title}` : title}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </section>

        <div className="home-side-stack">
          <a className="card home-info-card home-core-card home-core-link-card" href="/app/medication-check">
            <div className="card-body">
              <h6 className="card-title fw-semibold">
                {isCaregiverRole ? "💊 복약 확인 필요" : "💊 오늘 복약 일정"}
              </h6>
              <div className="home-kpi-list">
                <div className="home-kpi-item">
                  <span className="home-kpi-label">{isCaregiverRole ? "확인 필요 복약자" : "오늘 복약 횟수"}</span>
                  <span className="home-kpi-value">
                    {isCaregiverRole ? `${caregiverNeedCheckPatientCount}명` : `${medicationItems.length}회`}
                  </span>
                </div>
                <div className="home-kpi-item">
                  <span className="home-kpi-label">{isCaregiverRole ? "미복약/지연" : "다음 복약 시간"}</span>
                  <span className="home-kpi-value">
                    {isCaregiverRole ? `${caregiverMissedCount}건` : nextMedicationItem ? formatClockTime(nextMedicationItem.scheduled_at) : "일정 없음"}
                  </span>
                </div>
                <div className="home-kpi-item">
                  <span className="home-kpi-label">{isCaregiverRole ? "오늘 복약 건수" : "완료/미완료"}</span>
                  <span className="home-kpi-value">
                    {isCaregiverRole ? `${medicationItems.length}건` : `${takenMedicationCount}/${takenMedicationCount + remainingMedicationCount}`}
                  </span>
                </div>
              </div>

              <div className="home-inline-list mt-3">
                <div className="home-inline-title">{isCaregiverRole ? "오늘 확인 항목" : "하루 복약 목록"}</div>
                {homeMedicationState.loading ? (
                  <div className="home-inline-empty">복약 상태를 불러오는 중...</div>
                ) : homeMedicationState.error ? (
                  <div className="home-inline-empty">복약 상태를 불러오지 못했습니다.</div>
                ) : limitedMedicationSections.length === 0 ? (
                  <div className="home-inline-empty">오늘 복약 일정이 없습니다.</div>
                ) : (
                  <div className="home-inline-stack">
                    {limitedMedicationSections.map((section) => (
                      <div key={section.meal_label} className="home-inline-meal-group">
                        <div className="home-inline-meal-title">{section.meal_label}</div>
                        <div className="home-inline-stack">
                          {section.rows.map((row) => (
                            <div key={row.id} className="home-inline-row">
                              <span className="home-inline-time">{row.time_label}</span>
                              <span className="home-inline-main home-inline-main-wrap">{row.main_label}</span>
                              <span className={`home-med-status status-${row.status}`}>{intakeStatusLabel(row.status)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </a>

          <a className="card home-info-card home-core-card home-core-link-card" href="/app/caregiver">
            <div className="card-body">
              <h6 className="card-title fw-semibold">{isCaregiverRole ? "🔔 알림/리마인드" : "🔔 새로운 알림"}</h6>
              {homeNotificationsState.loading ? (
                <div className="home-info-note">알림을 불러오는 중...</div>
              ) : homeNotificationsState.error ? (
                <div className="home-info-note">알림을 불러오지 못했습니다.</div>
              ) : homeNotificationItems.length === 0 ? (
                <div className="home-info-note">최근 알림이 없습니다.</div>
              ) : (
                <div className="home-notification-list">
                  {homeNotificationItems.map((item) => (
                    <div key={item.id} className={`home-notification-item ${item.read_at ? "" : "unread"}`}>
                      <div className="home-notification-head">
                        <strong>{item.title || "알림"}</strong>
                        {!item.read_at && <span className="home-notification-badge">미확인</span>}
                      </div>
                      <div className="home-notification-body">
                        {item.body || item.message || "상세 알림은 알림센터에서 확인하세요."}
                      </div>
                      <div className="home-notification-time">{formatDateTime(item.created_at || item.sent_at)}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </a>
        </div>
      </div>
    </AppLayout>
  );
}

export default App;
