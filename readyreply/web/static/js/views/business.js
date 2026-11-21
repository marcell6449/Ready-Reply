import { api } from "../api.js";
import { busy, field, h, show, toast } from "../dom.js";
import { errorText, t, variableLabel } from "../i18n.js";
import { state } from "../state.js";

export async function renderBusiness(root) {
  state.variables = await api.get("/api/variables");
  const rows = state.variables.map((v) => ({ ...v }));
  const list = h("div", { class: "stack" });
  const redraw = () => show(list, rows.map((row, index) => variableEditor(row, () => {
    rows.splice(index, 1);
    redraw();
  })));
  redraw();
  const error = h("p", { class: "form-error", role: "alert" });
  const submit = h("button", { class: "button", type: "submit" }, t("common.save"));
  show(root, h("form", { class: "panel", onSubmit: (event) => {
    event.preventDefault();
    busy(submit, () => save(rows).catch((e) => { error.textContent = errorText(e.code); }));
  } },
  h("h1", {}, t("business.title")), h("p", { class: "muted" }, t("business.intro")),
  list,
  h("button", { class: "button secondary", type: "button", onClick: () => {
    rows.push({ key: "", label: "", value: "", builtin: false });
    redraw();
  } }, t("business.add")),
  error, submit));
}

function variableEditor(row, onRemove) {
  const bind = (name) => (event) => { row[name] = event.target.value; };
  const value = h("textarea", { rows: 2, maxlength: 2000, value: row.value, onInput: bind("value") });
  if (row.builtin) {
    return h("div", { class: "variable" }, field(`${variableLabel(row)}  {${row.key}}`, value));
  }
  return h("fieldset", { class: "variable custom" },
    h("legend", {}, t("business.custom")),
    field(t("business.label"), h("input", { maxlength: 60, value: row.label, onInput: bind("label") })),
    field(t("business.key"), h("input", { maxlength: 40, value: row.key, onInput: bind("key"),
      pattern: "[a-z][a-z0-9_]*" }), t("business.key_hint")),
    field(t("business.value"), value),
    h("button", { class: "button small danger", type: "button", onClick: onRemove }, t("common.delete")));
}

async function save(rows) {
  state.variables = await api.put("/api/variables", rows);
  toast(t("business.saved"));
}
