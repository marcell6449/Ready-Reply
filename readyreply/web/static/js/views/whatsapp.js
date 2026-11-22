import { api } from "../api.js";
import { busy, field, h, show, toast } from "../dom.js";
import { errorText, t, variableLabel } from "../i18n.js";
import { state } from "../state.js";

// Import answers from chats the owner exported from WhatsApp. Everything runs on this computer.
const BASE64_CHUNK = 0x8000;
let selectedFiles = [];

export function whatsappSection() {
  const preview = h("div", { id: "chat-preview", "aria-live": "polite" });
  const input = h("input", { type: "file", id: "chat-files", multiple: true, class: "visually-hidden",
    accept: ".txt,.zip,text/plain,application/zip" });
  input.addEventListener("change", () => analyze([...input.files], preview));
  return h("section", { class: "panel" },
    h("h1", {}, t("chats.title")), h("p", { class: "muted" }, t("chats.intro")),
    h("ol", { class: "steps" }, ["chats.step_export", "chats.step_send", "chats.step_drop"].map(
      (key) => h("li", {}, t(key)))),
    dropZone(input, preview), preview);
}

function dropZone(input, preview) {
  const zone = h("label", { class: "dropzone", for: "chat-files" },
    h("strong", {}, t("chats.drop")), h("span", { class: "muted" }, t("chats.drop_hint")), input);
  zone.addEventListener("dragover", (event) => { event.preventDefault(); zone.classList.add("over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("over"));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("over");
    analyze([...event.dataTransfer.files], preview);
  });
  return zone;
}

function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let start = 0; start < bytes.length; start += BASE64_CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(start, start + BASE64_CHUNK));
  }
  return btoa(binary);
}

async function payload(files) {
  return Promise.all(files.map(async (file) => ({
    name: file.name, content_base64: toBase64(await file.arrayBuffer()),
  })));
}

async function analyze(files, target, businessSender = null) {
  if (!files.length) return;
  selectedFiles = files;
  show(target, h("p", { class: "muted", role: "status" }, t("chats.reading", { count: files.length })));
  try {
    const body = { files: await payload(files), business_sender: businessSender };
    show(target, previewView(await api.post("/api/whatsapp/analyze", body), target));
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    show(target, h("p", { class: "form-error" }, errorText(error.code)));
  }
}

function senderPicker(preview, target) {
  const select = h("select", { "aria-label": t("chats.business_sender") },
    preview.senders.map((name) => h("option", { value: name, selected: name === preview.business_sender }, name)));
  select.addEventListener("change", () => analyze(selectedFiles, target, select.value));
  return field(t("chats.business_sender"), select, t("chats.business_sender_hint"));
}

function checkbox(checked) {
  return h("input", { type: "checkbox", checked });
}

function detailRows(details) {
  const byKey = Object.fromEntries(state.variables.map((v) => [v.key, v]));
  return details.map((detail) => {
    const box = checkbox(!detail.current);
    const label = byKey[detail.key] ? variableLabel(byKey[detail.key]) : detail.key;
    const current = detail.current ? h("span", { class: "muted small" }, t("chats.current", { value: detail.current })) : null;
    return { detail, box, element: h("label", { class: "pick" }, box,
      h("span", {}, h("strong", {}, `${label}: `), detail.value, current)) };
  });
}

function answerRows(answers) {
  return answers.map((answer) => {
    const box = checkbox(!answer.exists);
    const title = h("input", { value: answer.question, maxlength: 120, "aria-label": t("answers.field_title") });
    const body = h("textarea", { rows: 3, maxlength: 4000, value: answer.reply, "aria-label": t("answers.field_body") });
    const meta = h("span", { class: "muted small" }, t("chats.times", { count: answer.times_asked }),
      answer.exists ? h("span", { class: "chip" }, t("chats.exists")) : null);
    return { box, title, body, element: h("div", { class: "pick-card" }, h("label", { class: "pick" }, box, meta), title, body) };
  });
}

function questionRows(questions) {
  return questions.map((question) => {
    const box = checkbox(true);
    return { question, box, element: h("label", { class: "pick" }, box,
      h("span", {}, question.question, " ", h("span", { class: "muted small" }, t("chats.times", { count: question.times_asked })))) };
  });
}

function group(titleKey, rows) {
  if (!rows.length) return null;
  return h("div", { class: "stack" }, h("h2", {}, t(titleKey, { count: rows.length })), rows.map((row) => row.element));
}

function previewView(preview, target) {
  const rows = { details: detailRows(preview.details), answers: answerRows(preview.answers),
    questions: questionRows(preview.unanswered) };
  const save = h("button", { class: "button", type: "button",
    onClick: (event) => busy(event.currentTarget, () => saveAll(rows, target)) }, t("chats.save_all"));
  return h("div", { class: "stack chat-preview" },
    h("p", { class: "linked" }, t("chats.found", { answers: preview.answers.length,
      questions: preview.unanswered.length, details: preview.details.length })),
    preview.skipped_files ? h("p", { class: "warning" }, t("chats.skipped", { count: preview.skipped_files })) : null,
    senderPicker(preview, target),
    group("chats.details_title", rows.details), group("chats.answers_title", rows.answers),
    group("chats.questions_title", rows.questions), save);
}

function selection(rows) {
  const kept = (list) => list.filter((row) => row.box.checked);
  return {
    details: Object.fromEntries(kept(rows.details).map((row) => [row.detail.key, row.detail.value])),
    answers: kept(rows.answers).map((row) => ({ title: row.title.value, category: "WhatsApp", body: row.body.value, tags: [] })),
    questions: kept(rows.questions).map((row) => row.question),
  };
}

async function saveAll(rows, target) {
  try {
    const result = await api.post("/api/whatsapp/import", selection(rows));
    state.variables = await api.get("/api/variables");
    toast(t("chats.saved"));
    show(target, h("div", { class: "stack" },
      h("p", { class: "linked" }, t("chats.result", result)),
      h("div", { class: "row" },
        h("a", { class: "button", href: "#/search" }, t("welcome.start")),
        h("a", { class: "button secondary", href: "#/answers" }, t("nav.answers")),
        h("a", { class: "button secondary", href: "#/unanswered" }, t("nav.unanswered")))));
  } catch (error) {
    toast(errorText(error.code), "warn");
  }
}
