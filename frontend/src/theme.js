export const DARK_MODE_STORAGE_KEY = "dark_mode";

const normalizeDarkModeValue = (value) => {
  if (value === true || value === 1) return true;
  if (typeof value !== "string") return false;
  const normalized = value.trim().toLowerCase();
  return normalized === "1" || normalized === "true";
};

export const getStoredDarkMode = () => {
  if (typeof window === "undefined") return false;
  return normalizeDarkModeValue(window.localStorage.getItem(DARK_MODE_STORAGE_KEY));
};

export const applyDarkMode = (enabled) => {
  const isDarkMode = !!enabled;

  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-bs-theme", isDarkMode ? "dark" : "light");
    document.body.classList.toggle("theme-dark", isDarkMode);
  }

  if (typeof window !== "undefined") {
    window.localStorage.setItem(DARK_MODE_STORAGE_KEY, isDarkMode ? "1" : "0");
  }
};
