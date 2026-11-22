import { api } from "../api.js";
import { busy, h, show, toast } from "../dom.js";
import { errorText, t } from "../i18n.js";
import { whatsappSection } from "./whatsapp.js";

export function renderData(root) {
  const report = h("div", { id: "import-report", "aria-live": "polite" });
  const file = h("input", { type: "file", id: "csv-file", accept: ".csv,text/csv", "aria-label": t("data.choose_file") });
  show(root, whatsappSection(), h("section", { class: "panel spaced" },
    h("h2", {}, t("data.csv_title")), h("p", { class: "muted" }, t("data.csv_intro")),
    h("div", { class: "row wrap" },
      h("button", { class: "button secondary", type: "button",
        onClick: (e) => busy(e.currentTarget, exportCsv) }, t("data.export")),
      file,
      h("button", { class: "button", type: "button",
        onClick: (e) => busy(e.currentTarget, () => importCsv(file, report)) }, t("data.import"))),
    report));
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
