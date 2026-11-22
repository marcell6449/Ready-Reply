import { api } from "../api.js";
import { h, show, toast } from "../dom.js";
import { currentLocale, errorText, t } from "../i18n.js";
import { state } from "../state.js";

// Shows that chats saved in the watched folders are imported by themselves.
const REFRESH_MS = 10000;

function historyLine(record) {
  const when = new Date(record.imported_at).toLocaleString(currentLocale());
  const text = record.error
    ? t("auto.ignored", { reason: errorText(record.error) })
    : t("auto.imported", record);
  return h("li", {}, h("span", { class: "muted small" }, when), " ", text);
}

function content(status) {
  if (!status.enabled) return [h("p", { class: "muted" }, t("auto.disabled"))];
  return [
    h("p", { class: "linked" }, t("auto.enabled")),
    h("p", {}, t("auto.how")),
    h("ul", { class: "folders" }, status.folders.map((folder) => h("li", {}, h("code", {}, folder)))),
    h("h2", {}, t("auto.history")),
    status.recent.length
      ? h("ul", { class: "history" }, status.recent.map(historyLine))
      : h("p", { class: "muted" }, t("auto.none_yet")),
  ];
}

async function refresh(card, previousCount) {
  const status = await api.get("/api/whatsapp/auto");
  show(card, h("h1", {}, t("auto.title")), content(status));
  if (previousCount !== null && status.recent.length > previousCount) {
    toast(t("auto.new_chat"));
    state.variables = await api.get("/api/variables");
  }
  return status.recent.length;
}

export function autoImportCard() {
  const card = h("section", { class: "panel", id: "auto-import" }, h("p", { class: "muted" }, "…"));
  let count = null;
  const tick = async () => {
    if (!document.body.contains(card) && count !== null) {
      clearInterval(timer);
      return;
    }
    count = await refresh(card, count).catch(() => count);
  };
  const timer = setInterval(tick, REFRESH_MS);
  tick();
  return card;
}
