import { api } from "../api.js";
import { copyText } from "../clipboard.js";
import { busy, field, h, show, toast } from "../dom.js";
import { currentLocale, errorText, t } from "../i18n.js";
import { isAdmin, state } from "../state.js";

export async function renderUnanswered(root) {
  const questions = await api.get("/api/unanswered");
  show(root, h("section", { class: "panel" },
    h("h1", {}, t("unanswered.title")), h("p", { class: "muted" }, t("unanswered.intro")),
    questions.length ? h("ul", { class: "list" }, questions.map((q) => questionRow(root, q)))
      : h("p", { class: "empty-title" }, t("unanswered.empty")),
    h("div", { id: "ai-panel" })));
}

function questionRow(root, question) {
  return h("li", { class: "list-row" },
    h("div", { class: "list-main" }, h("strong", {}, question.text),
      h("span", { class: "count" }, t("unanswered.times", { count: question.times_searched }))),
    isAdmin() ? h("div", { class: "row" },
      h("button", { class: "button small", type: "button", onClick: () => createFor(question) },
        t("unanswered.create")),
      h("button", { class: "button small secondary", type: "button",
        onClick: (e) => busy(e.currentTarget, () => suggest(question)) }, t("ai.suggest")),
      h("button", { class: "button small danger", type: "button",
        onClick: (e) => busy(e.currentTarget, () => dismiss(root, question)) }, t("unanswered.dismiss")))
      : null);
}

function createFor(question, body = "") {
  state.pendingQuestion = { questionId: question.id, title: question.text, body };
  window.location.hash = "#/answers/new";
}

async function dismiss(root, question) {
  await api.del(`/api/unanswered/${question.id}`);
  await renderUnanswered(root);
}

async function suggest(question) {
  const panel = document.getElementById("ai-panel");
  show(panel, h("p", { class: "muted", role: "status" }, t("ai.generating")));
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    const result = await api.post("/api/ai/suggest", { question_id: question.id, locale: currentLocale() });
    show(panel, result.kind === "draft" ? draftPanel(question, result) : manualPanel(question, result));
  } catch (error) {
    show(panel, h("p", { class: "form-error" }, errorText(error.code)));
  }
}

function reviewArea(text) {
  return h("textarea", { rows: 6, maxlength: 4000, value: text, "aria-label": t("ai.review") });
}

function useButton(question, area) {
  return h("button", { class: "button", type: "button", onClick: () => {
    if (!area.value.trim()) { toast(t("ai.paste_first"), "warn"); return; }
    createFor(question, area.value);
  } }, t("ai.use"));
}

function draftPanel(question, result) {
  const area = reviewArea(result.text);
  return h("section", { class: "ai-box" },
    h("h2", {}, t("ai.draft_title")), h("p", { class: "muted" }, t("ai.review_hint")),
    field(t("ai.review"), area), useButton(question, area));
}

function manualPanel(question, result) {
  const area = reviewArea("");
  const promptBox = h("textarea", { rows: 6, readonly: true, value: result.prompt });
  return h("section", { class: "ai-box" },
    result.notice ? h("p", { class: "warning" }, t(result.notice)) : null,
    h("h2", {}, t("ai.manual_title")), h("p", { class: "muted" }, t("ai.manual_steps")),
    field(t("ai.prompt"), promptBox),
    h("div", { class: "row" },
      h("button", { class: "button secondary", type: "button", onClick: async () => {
        toast((await copyText(result.prompt)) ? t("copy.done") : t("copy.failed"));
      } }, t("ai.copy_prompt")),
      result.open_url ? h("a", { class: "button secondary", href: result.open_url,
        target: "_blank", rel: "noopener noreferrer" }, t("ai.open_chat")) : null),
    field(t("ai.paste"), area), useButton(question, area));
}
