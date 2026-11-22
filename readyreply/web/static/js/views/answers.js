import { api } from "../api.js";
import { busy, field, h, show, submitForm, toast } from "../dom.js";
import { t, variableLabel } from "../i18n.js";
import { state } from "../state.js";

const PLACEHOLDER = /\{\{|\}\}|\{([a-z][a-z0-9_]{0,39})\}/g;

export async function renderAnswerList(root) {
  const answers = await api.get("/api/answers");
  show(root, h("section", { class: "panel" },
    h("div", { class: "panel-head" }, h("h1", {}, t("answers.title")),
      h("a", { class: "button", href: "#/answers/new" }, t("answers.new"))),
    answers.length ? h("ul", { class: "list" }, answers.map((a) => answerRow(root, a)))
      : h("p", { class: "muted" }, t("answers.empty"))));
}

function answerRow(root, answer) {
  return h("li", { class: "list-row" },
    h("div", { class: "list-main" }, h("strong", {}, answer.title),
      answer.category ? h("span", { class: "chip" }, answer.category) : null),
    h("div", { class: "row" },
      h("a", { class: "button small secondary", href: `#/answers/${answer.id}` }, t("common.edit")),
      h("button", { class: "button small secondary", type: "button",
        onClick: (e) => busy(e.currentTarget, () => duplicate(root, answer)) }, t("answers.duplicate")),
      h("button", { class: "button small danger", type: "button",
        onClick: (e) => busy(e.currentTarget, () => remove(root, answer)) }, t("common.delete"))));
}

async function duplicate(root, answer) {
  const copy = await api.post(`/api/answers/${answer.id}/duplicate`);
  toast(t("answers.duplicated", { title: copy.title }));
  await renderAnswerList(root);
}

async function remove(root, answer) {
  if (!window.confirm(t("answers.confirm_delete", { title: answer.title }))) return;
  await api.del(`/api/answers/${answer.id}`);
  toast(t("answers.deleted"));
  await renderAnswerList(root);
}

export async function renderAnswerEditor(root, answerId, prefill = {}) {
  const answers = answerId ? await api.get("/api/answers") : [];
  const current = answers.find((a) => String(a.id) === String(answerId)) || prefill;
  show(root, editorForm(answerId, editorInputs(current), prefill.questionId));
  root.querySelector("input[name=title]").focus();
}

function editorForm(answerId, inputs, questionId) {
  const usage = h("p", { class: "field-hint", id: "variable-usage" });
  const updateUsage = () => describeUsage(usage, inputs.body.value);
  inputs.body.addEventListener("input", updateUsage);
  updateUsage();
  return submitForm({
    submitLabel: t("common.save"),
    onSubmit: () => save(answerId, inputs, questionId),
    extraActions: [h("a", { class: "button secondary", href: "#/answers" }, t("common.cancel"))],
  },
  h("h1", {}, answerId ? t("answers.edit_title") : t("answers.new_title")),
  field(t("answers.field_title"), inputs.title),
  field(t("answers.field_category"), inputs.category),
  field(t("answers.field_body"), inputs.body, t("answers.body_hint")),
  variableButtons(inputs.body, updateUsage), usage,
  field(t("answers.field_tags"), inputs.tags, t("answers.tags_hint")));
}

function editorInputs(current) {
  return {
    title: h("input", { name: "title", required: true, maxlength: 120, value: current.title || "" }),
    category: h("input", { name: "category", maxlength: 60, value: current.category || "" }),
    body: h("textarea", { name: "body", required: true, rows: 6, maxlength: 4000, value: current.body || "" }),
    tags: h("input", { name: "tags", value: (current.tags || []).join(", ") }),
  };
}

function variableButtons(textarea, onChange) {
  return h("div", { class: "chips", "aria-label": t("answers.insert_variable") },
    state.variables.map((variable) => h("button", {
      type: "button", class: "chip-button",
      onClick: () => { insertAtCursor(textarea, `{${variable.key}}`); onChange(); },
    }, `+ ${variableLabel(variable)}`)));
}

function insertAtCursor(textarea, text) {
  const start = textarea.selectionStart ?? textarea.value.length;
  const end = textarea.selectionEnd ?? start;
  textarea.setRangeText(text, start, end, "end");
  textarea.focus();
}

function describeUsage(target, body) {
  const byKey = Object.fromEntries(state.variables.map((v) => [v.key, v]));
  const keys = [...new Set([...body.matchAll(PLACEHOLDER)].map((m) => m[1]).filter(Boolean))];
  const parts = keys.map((key) => {
    const variable = byKey[key];
    if (!variable) return t("answers.var_unknown", { key });
    return variable.value.trim() ? `✓ ${variableLabel(variable)}` : t("answers.var_empty", { label: variableLabel(variable) });
  });
  target.textContent = parts.length ? `${t("answers.uses")} ${parts.join(" · ")}` : "";
}

async function save(answerId, inputs, questionId) {
  const payload = {
    title: inputs.title.value,
    category: inputs.category.value,
    body: inputs.body.value,
    tags: inputs.tags.value.split(","),
  };
  if (answerId) await api.put(`/api/answers/${answerId}`, payload);
  else if (questionId) await api.post(`/api/unanswered/${questionId}/answer`, payload);
  else await api.post("/api/answers", payload);
  toast(t("answers.saved"));
  window.location.hash = questionId ? "#/unanswered" : "#/answers";
}
