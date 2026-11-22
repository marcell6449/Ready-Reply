import { h, show } from "../dom.js";
import { t } from "../i18n.js";
import { state } from "../state.js";

// Shown right after registration: confirms the WhatsApp number and lists the next steps.
const STEPS = [
  { text: "welcome.step_business", links: [["welcome.go_business", "#/business"]] },
  { text: "welcome.step_answers",
    links: [["welcome.create_answer", "#/answers/new"], ["welcome.try_demo", "#/data"]] },
  { text: "welcome.step_phone", links: [["welcome.open_phone", "#/phone"]] },
  { text: "welcome.step_whatsapp", links: [["welcome.start", "#/search"]] },
];

function numberStatus() {
  const phone = state.variables.find((variable) => variable.key === "phone")?.value.trim();
  if (!phone) return h("p", { class: "muted" }, t("welcome.number_missing"));
  return h("p", { class: "linked", role: "status" },
    h("span", { class: "linked-check", "aria-hidden": "true" }, "✓"),
    h("span", {}, t("welcome.number_linked", { number: phone })));
}

function step({ text, links }) {
  return h("li", { class: "step" }, h("p", {}, t(text)),
    h("div", { class: "row" }, links.map(([label, href], index) =>
      h("a", { class: index === 0 ? "button small" : "button small secondary", href }, t(label)))));
}

export function renderWelcome(root) {
  show(root, h("section", { class: "panel welcome" },
    h("h1", {}, t("welcome.title")), numberStatus(),
    h("h2", {}, t("welcome.steps_title")),
    h("ol", { class: "steps" }, STEPS.map(step))));
}
