import { api } from "../api.js";
import { copyText } from "../clipboard.js";
import { h, show, toast } from "../dom.js";
import { errorText, t, variableLabel } from "../i18n.js";
import { isAdmin, state } from "../state.js";

const SEARCH_DELAY_MS = 120;
const RECORD_AFTER_MS = 1500;
let searchTimer = 0;
let recordTimer = 0;
let latestRequest = 0;

export function renderSearch(root) {
  show(root, h("section", { class: "results", id: "results", "aria-live": "polite" }));
  runSearch(state.query);
}

export function onQueryInput(query) {
  state.query = query;
  clearTimeout(searchTimer);
  clearTimeout(recordTimer);
  searchTimer = setTimeout(() => runSearch(query), SEARCH_DELAY_MS);
}

export function searchNow(query) {
  state.query = query;
  clearTimeout(searchTimer);
  clearTimeout(recordTimer);
  runSearch(query);
}

async function runSearch(query) {
  const requestId = ++latestRequest;
  const results = await api.get(`/api/search?q=${encodeURIComponent(query)}`);
  const list = document.getElementById("results");
  if (requestId !== latestRequest || !list) return;
  if (results.length) {
    show(list, results.map(card));
  } else {
    show(list, emptyState(query));
    scheduleRecord(query);
  }
}

function scheduleRecord(query) {
  if (!query.trim()) return;
  recordTimer = setTimeout(() => recordUnanswered(query), RECORD_AFTER_MS);
}

export function recordNow() {
  const list = document.getElementById("results");
  if (list?.dataset.empty === "true") {
    clearTimeout(recordTimer);
    recordUnanswered(state.query);
  }
}

async function recordUnanswered(query) {
  try {
    await api.post("/api/unanswered", { query });
    const note = document.getElementById("recorded-note");
    if (note) note.textContent = t("search.recorded");
  } catch {
    // Too short to record: nothing to tell the user.
  }
}

function emptyState(query) {
  const list = document.getElementById("results");
  list.dataset.empty = query.trim() ? "true" : "false";
  if (!query.trim()) return libraryEmpty();
  return h("div", { class: "empty" },
    h("p", { class: "empty-title" }, t("search.no_results", { query })),
    h("p", { id: "recorded-note", class: "muted" }),
    isAdmin() ? h("a", { class: "button secondary", href: "#/unanswered" }, t("search.see_unanswered")) : null);
}

function libraryEmpty() {
  return h("div", { class: "empty" },
    h("p", { class: "empty-title" }, t("search.library_empty")),
    isAdmin()
      ? h("div", { class: "row" },
        h("a", { class: "button", href: "#/data" }, t("search.import_whatsapp")),
        h("a", { class: "button secondary", href: "#/answers/new" }, t("answers.new")))
      : h("p", { class: "muted" }, t("search.ask_admin")));
}

function card(result) {
  const { answer, preview } = result;
  return h("article", { class: "card", "data-answer-id": answer.id },
    h("header", { class: "card-head" },
      h("h2", { class: "card-title" }, answer.title),
      answer.category ? h("span", { class: "chip" }, answer.category) : null),
    preview.text !== null
      ? h("p", { class: "card-text" }, preview.text)
      : missingWarning(preview.missing),
    h("div", { class: "card-actions" }, copyButton(answer, preview)));
}

function missingWarning(missing) {
  const byKey = Object.fromEntries(state.variables.map((v) => [v.key, variableLabel(v)]));
  const labels = missing.map((key) => byKey[key] || key).join(", ");
  return h("div", { class: "warning", role: "note" },
    h("p", {}, t("copy.missing", { labels })),
    isAdmin() ? h("a", { href: "#/business" }, t("copy.fill_in")) : h("p", {}, t("copy.ask_admin")));
}

function copyButton(answer, preview) {
  const blocked = preview.text === null;
  return h("button", {
    class: blocked ? "button copy blocked" : "button copy",
    type: "button",
    "aria-disabled": blocked ? "true" : "false",
    onClick: (event) => onCopy(event.currentTarget, answer, preview),
  }, t("copy.button"));
}

async function onCopy(button, answer, preview) {
  if (preview.text === null) {
    toast(t("copy.blocked"), "warn");
    return;
  }
  // Copy first, inside the click, so phones allow it. Then record the use.
  const copied = await copyText(preview.text);
  toast(copied ? t("copy.done") : t("copy.failed"), copied ? "ok" : "warn");
  button.classList.add("done");
  setTimeout(() => button.classList.remove("done"), 1200);
  try {
    await api.post(`/api/answers/${answer.id}/copy`);
  } catch (error) {
    if (error.status !== 401) toast(errorText(error.code), "warn");
  }
}
