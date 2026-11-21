import { api, setCsrf } from "./api.js";
import { h, show, toast } from "./dom.js";
import { errorText, loadTranslations, otherLocale, setLocale, t } from "./i18n.js";
import { isAdmin, state } from "./state.js";
import { renderAnswerEditor, renderAnswerList } from "./views/answers.js";
import { renderLogin, renderSetup } from "./views/auth.js";
import { renderBusiness } from "./views/business.js";
import { renderData } from "./views/data.js";
import { renderPhone } from "./views/phone.js";
import { onQueryInput, recordNow, renderSearch } from "./views/search.js";
import { renderStats } from "./views/stats.js";
import { renderSynonyms } from "./views/synonyms.js";
import { renderUnanswered } from "./views/unanswered.js";
import { renderUsers } from "./views/users.js";

const view = () => document.getElementById("view");
const LARGE_TEXT_KEY = "rr.largeText";

const ROUTES = {
  search: { render: renderSearch, admin: false, icon: "🔎" },
  unanswered: { render: renderUnanswered, admin: false, icon: "❓" },
  answers: { render: renderAnswerList, admin: true, icon: "💬" },
  business: { render: renderBusiness, admin: true, icon: "🏪" },
  synonyms: { render: renderSynonyms, admin: true, icon: "🔁", more: true },
  stats: { render: renderStats, admin: true, icon: "📊", more: true },
  users: { render: renderUsers, admin: true, icon: "👥", more: true },
  data: { render: renderData, admin: true, icon: "📦", more: true },
  phone: { render: renderPhone, admin: true, icon: "📱", more: true },
  more: { render: renderMore, admin: true, icon: "☰", mobileOnly: true },
};

function allowedRoutes() {
  return Object.entries(ROUTES).filter(([, route]) => isAdmin() || !route.admin);
}

function renderMore(root) {
  show(root, h("nav", { class: "panel more" }, h("h1", {}, t("nav.more")),
    allowedRoutes().filter(([, r]) => r.more).map(([name, r]) =>
      h("a", { class: "more-link", href: `#/${name}` }, `${r.icon} ${t(`nav.${name}`)}`))));
}

function renderNav(active) {
  const nav = document.getElementById("nav");
  nav.hidden = false;
  show(nav, allowedRoutes().map(([name, route]) => h("a", {
    href: `#/${name}`,
    class: `nav-link${route.more ? " more-item" : ""}${route.mobileOnly ? " mobile-only" : ""}`,
    "aria-current": name === active ? "page" : null,
  }, h("span", { class: "nav-icon", "aria-hidden": "true" }, route.icon),
  h("span", { class: "nav-text" }, t(`nav.${name}`)))));
}

async function route() {
  if (!state.me) return;
  const [name = "search", detail] = window.location.hash.replace(/^#\/?/, "").split("/");
  const known = ROUTES[name] && (isAdmin() || !ROUTES[name].admin) ? name : "search";
  renderNav(known);
  // Each navigation renders into a fresh element, so a slow render from the previous
  // screen lands in a detached node instead of overwriting the current one.
  const target = h("div", { class: "route" });
  view().replaceChildren(target);
  try {
    if (known === "answers" && detail) await renderEditor(target, detail);
    else await ROUTES[known].render(target);
  } catch (error) {
    if (error.status !== 401) toast(errorText(error.code), "warn");
  }
  if (known !== "search") window.scrollTo(0, 0);
}

function renderEditor(target, detail) {
  const prefill = state.pendingQuestion || {};
  state.pendingQuestion = null;
  return renderAnswerEditor(target, detail === "new" ? null : detail, prefill);
}

async function onSignedIn(me) {
  state.me = me;
  setCsrf(me.csrf_token);
  document.body.classList.add("signed-in");
  document.getElementById("searchbar").hidden = false;
  document.getElementById("logout").hidden = false;
  state.variables = await api.get("/api/variables");
  const input = document.getElementById("search-input");
  input.value = state.query;
  await route();
  if (window.matchMedia("(min-width: 720px)").matches) input.focus();
}

function onSignedOut(event) {
  state.me = null;
  document.body.classList.remove("signed-in");
  document.getElementById("nav").hidden = true;
  document.getElementById("searchbar").hidden = true;
  document.getElementById("logout").hidden = true;
  renderLogin(view(), onSignedIn, event.detail);
}

function wireSearchBar() {
  const input = document.getElementById("search-input");
  input.addEventListener("input", () => {
    if (!window.location.hash.startsWith("#/search") && window.location.hash) {
      window.location.hash = "#/search";
    }
    onQueryInput(input.value);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") recordNow();
    if (event.key === "Escape") { input.value = ""; onQueryInput("", { immediate: true }); }
  });
}

function applyChromeTexts() {
  document.title = t("app.name");
  document.getElementById("brand").textContent = t("app.name");
  const input = document.getElementById("search-input");
  input.placeholder = t("search.placeholder");
  input.setAttribute("aria-label", t("search.placeholder"));
  const lang = document.getElementById("lang-toggle");
  lang.textContent = otherLocale().toUpperCase();
  lang.setAttribute("aria-label", t("settings.language"));
  document.getElementById("text-size").setAttribute("aria-label", t("settings.large_text"));
  document.getElementById("logout").textContent = t("auth.logout");
}

function wireSettings() {
  document.getElementById("lang-toggle").addEventListener("click", () => {
    setLocale(otherLocale());
    applyChromeTexts();
    if (state.me) route(); else window.location.reload();
  });
  document.getElementById("text-size").addEventListener("click", () => {
    const large = document.documentElement.classList.toggle("large-text");
    try { localStorage.setItem(LARGE_TEXT_KEY, large ? "1" : ""); } catch { /* private mode */ }
  });
  document.getElementById("logout").addEventListener("click", async () => {
    await api.post("/api/auth/logout");
    window.dispatchEvent(new CustomEvent("rr:signed-out", { detail: "auth.logged_out" }));
  });
}

function restoreLargeText() {
  try {
    if (localStorage.getItem(LARGE_TEXT_KEY)) document.documentElement.classList.add("large-text");
  } catch { /* private mode */ }
}

async function boot() {
  restoreLargeText();
  const status = await api.get("/api/setup/status");
  await loadTranslations(status.locale);
  setCsrf(status.csrf_token);
  applyChromeTexts();
  wireSettings();
  wireSearchBar();
  window.addEventListener("hashchange", route);
  window.addEventListener("rr:signed-out", onSignedOut);
  if (status.needs_setup) {
    renderSetup(view(), onSignedIn);
    return;
  }
  try {
    await onSignedIn(await api.get("/api/auth/me"));
  } catch {
    // The signed-out event already showed the login form.
  }
}

boot();
