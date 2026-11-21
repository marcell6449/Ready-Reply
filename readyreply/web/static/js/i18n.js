// All visible text comes from i18n/translations.json.

const STORAGE_KEY = "rr.locale";
const LOCALES = ["es", "en"];
let catalog = {};
let locale = "es";

export async function loadTranslations(serverDefault) {
  const response = await fetch("/static/i18n/translations.json");
  catalog = await response.json();
  locale = readSaved() || serverDefault || "es";
  document.documentElement.lang = locale;
}

function readSaved() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return LOCALES.includes(saved) ? saved : null;
  } catch {
    return null;
  }
}

export function currentLocale() {
  return locale;
}

export function otherLocale() {
  return LOCALES.find((code) => code !== locale);
}

export function setLocale(code) {
  locale = code;
  document.documentElement.lang = code;
  try {
    localStorage.setItem(STORAGE_KEY, code);
  } catch {
    // Private mode: the choice lasts until the page is closed.
  }
}

export function t(key, params = {}) {
  const text = catalog[locale]?.[key] ?? catalog.es?.[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match));
}

export function errorText(code) {
  const key = `error.${code}`;
  const text = t(key);
  return text === key ? t("error.generic") : text;
}

export function variableLabel(variable) {
  return variable.builtin ? t(`var.${variable.key}`) : variable.label || variable.key;
}
