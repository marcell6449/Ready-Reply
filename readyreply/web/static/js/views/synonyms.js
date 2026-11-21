import { api } from "../api.js";
import { busy, field, h, show, toast } from "../dom.js";
import { errorText, t } from "../i18n.js";

export async function renderSynonyms(root) {
  const { groups } = await api.get("/api/synonyms");
  const rows = groups.map((group) => group.join(", "));
  const list = h("div", { class: "stack" });
  const redraw = () => show(list, rows.map((text, index) => h("div", { class: "row synonym" },
    field(t("synonyms.group", { number: index + 1 }), h("input", {
      value: text, onInput: (event) => { rows[index] = event.target.value; },
    })),
    h("button", { class: "button small danger", type: "button",
      onClick: () => { rows.splice(index, 1); redraw(); } }, t("common.delete")))));
  redraw();
  const error = h("p", { class: "form-error", role: "alert" });
  const submit = h("button", { class: "button", type: "submit" }, t("common.save"));
  show(root, h("form", { class: "panel", onSubmit: (event) => {
    event.preventDefault();
    busy(submit, () => save(rows).catch((e) => { error.textContent = errorText(e.code); }));
  } },
  h("h1", {}, t("synonyms.title")), h("p", { class: "muted" }, t("synonyms.intro")), list,
  h("button", { class: "button secondary", type: "button",
    onClick: () => { rows.push(""); redraw(); } }, t("synonyms.add")),
  error, submit));
}

async function save(rows) {
  const groups = rows.map((text) => text.split(",").map((term) => term.trim()).filter(Boolean))
    .filter((group) => group.length);
  await api.put("/api/synonyms", { groups });
  toast(t("synonyms.saved"));
}
