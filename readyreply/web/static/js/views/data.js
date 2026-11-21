import { api } from "../api.js";
import { busy, h, show, toast } from "../dom.js";
import { errorText, t } from "../i18n.js";

const DEMOS = ["soda", "salon", "hardware"];

export function renderData(root) {
  const report = h("div", { id: "import-report", "aria-live": "polite" });
  const file = h("input", { type: "file", accept: ".csv,text/csv", "aria-label": t("data.choose_file") });
  show(root, h("section", { class: "panel" },
    h("h1", {}, t("data.demo_title")), h("p", { class: "muted" }, t("data.demo_intro")),
    h("div", { class: "demo-grid" }, DEMOS.map((kind) => h("button", {
      class: "button demo", type: "button", "data-demo": kind,
      onClick: (e) => busy(e.currentTarget, () => loadDemo(kind)),
    }, t(`demo.${kind}`)))),
    h("h2", {}, t("data.csv_title")), h("p", { class: "muted" }, t("data.csv_intro")),
    h("div", { class: "row wrap" },
      h("button", { class: "button secondary", type: "button",
        onClick: (e) => busy(e.currentTarget, exportCsv) }, t("data.export")),
      file,
      h("button", { class: "button", type: "button",
        onClick: (e) => busy(e.currentTarget, () => importCsv(file, report)) }, t("data.import"))),
    report));
}

async function loadDemo(kind) {
  try {
    await api.post(`/api/demo/${kind}`, { mode: "empty_only" });
  } catch (error) {
    if (error.code !== "demo.confirm_replace") throw error;
    if (!window.confirm(t("data.confirm_replace"))) return;
    await api.post(`/api/demo/${kind}`, { mode: "replace" });
  }
  toast(t("data.demo_loaded"));
  window.location.hash = "#/search";
}

async function exportCsv() {
  const blob = await api.get("/api/csv/export");
  const link = h("a", { href: URL.createObjectURL(blob), download: "ready-reply-answers.csv" });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}

async function importCsv(input, target) {
  const [file] = input.files;
  if (!file) { toast(t("data.choose_file"), "warn"); return; }
  try {
    const result = await api.upload("/api/csv/import", file);
    show(target, h("p", { class: "ok" }, t("data.imported", { count: result.imported })),
      result.rejected.length ? h("ul", { class: "errors" }, result.rejected.map((row) =>
        h("li", {}, t("data.row_error", { line: row.line, reason: errorText(row.code) })))) : null);
  } catch (error) {
    show(target, h("p", { class: "form-error" }, errorText(error.code)));
  }
}
