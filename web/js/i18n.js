export const LOCALES = [
  ["bg", "Български"], ["cs", "Čeština"], ["da", "Dansk"], ["de", "Deutsch"],
  ["el", "Ελληνικά"], ["en", "English"], ["es", "Español"], ["et", "Eesti"],
  ["fi", "Suomi"], ["fr", "Français"], ["ga", "Gaeilge"], ["hr", "Hrvatski"],
  ["hu", "Magyar"], ["it", "Italiano"], ["lt", "Lietuvių"], ["lv", "Latviešu"],
  ["mt", "Malti"], ["nl", "Nederlands"], ["pl", "Polski"], ["pt", "Português"],
  ["ro", "Română"], ["sk", "Slovenčina"], ["sl", "Slovenščina"], ["sv", "Svenska"],
  ["ru", "Русский"], ["zh-Hans", "简体中文"], ["ja", "日本語"], ["ar", "العربية"],
  ["uk", "Українська"], ["no", "Norsk"],
];

const STORAGE_KEY = "talktome.locale";
let currentLocale = "en";
let fallback = {};
let messages = {};

function supported(code) {
  return LOCALES.some(([locale]) => locale === code);
}

function browserLocale() {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored && supported(stored)) return stored;
  for (const requested of navigator.languages || [navigator.language]) {
    if (supported(requested)) return requested;
    const base = requested.split("-")[0];
    if (supported(base)) return base;
  }
  return "en";
}

async function loadMessages(locale) {
  const response = await fetch(`/master-data/i18n/${locale}.json`, {cache: "no-store"});
  if (!response.ok) throw new Error(`Unable to load locale ${locale}`);
  return response.json();
}

export function translate(key, params = {}) {
  const template = messages[key] ?? fallback[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_match, name) => String(params[name] ?? `{${name}}`));
}

export function formatDateTime(value) {
  return new Intl.DateTimeFormat(currentLocale, {
    year: "numeric", month: "numeric", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).format(new Date(value));
}

function applyTranslations() {
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = translate(element.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
    element.setAttribute("aria-label", translate(element.dataset.i18nAriaLabel));
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    element.setAttribute("placeholder", translate(element.dataset.i18nPlaceholder));
  });
  document.querySelectorAll("[data-i18n-tooltip]").forEach((element) => {
    element.dataset.tooltip = translate(element.dataset.i18nTooltip);
  });
}

function renderLanguageOptions(query = "") {
  const list = document.querySelector("#language-options");
  const normalized = query.trim().toLocaleLowerCase();
  list.replaceChildren();
  const matches = LOCALES.filter(([code, name]) => `${code} ${name}`.toLocaleLowerCase().includes(normalized));
  if (!matches.length) {
    const empty = document.createElement("p");
    empty.className = "language-empty";
    empty.textContent = translate("language.noResults");
    list.append(empty);
    return;
  }
  for (const [code, nativeName] of matches) {
    const option = document.createElement("button");
    option.type = "button";
    option.role = "option";
    option.className = "language-option";
    option.dataset.locale = code;
    option.setAttribute("aria-selected", String(code === currentLocale));
    const name = document.createElement("strong");
    name.textContent = nativeName;
    const localeCode = document.createElement("span");
    localeCode.textContent = code;
    option.append(name, localeCode);
    option.addEventListener("click", async () => {
      await setLocale(code);
      document.querySelector("#language-dialog").close();
    });
    list.append(option);
  }
}

export async function setLocale(locale) {
  const selected = supported(locale) ? locale : "en";
  messages = selected === "en" ? fallback : await loadMessages(selected);
  currentLocale = selected;
  localStorage.setItem(STORAGE_KEY, selected);
  document.documentElement.lang = selected;
  document.documentElement.dir = selected === "ar" ? "rtl" : "ltr";
  document.querySelector("[data-dialog='language-dialog']").textContent = selected.toUpperCase();
  applyTranslations();
  renderLanguageOptions(document.querySelector("#language-search").value);
  document.dispatchEvent(new CustomEvent("talktome:localechange", {detail: {locale: selected}}));
}

export async function initializeI18n() {
  fallback = await loadMessages("en");
  const search = document.querySelector("#language-search");
  search.addEventListener("input", () => renderLanguageOptions(search.value));
  search.addEventListener("keydown", (event) => {
    const options = [...document.querySelectorAll("#language-options [role=option]")];
    if (event.key === "Escape") {
      search.value = "";
      renderLanguageOptions();
      return;
    }
    if (event.key === "ArrowDown" && options.length) {
      event.preventDefault();
      options[0].focus();
    }
  });
  await setLocale(browserLocale());
}
