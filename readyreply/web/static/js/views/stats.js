import { api } from "../api.js";
import { h, show } from "../dom.js";
import { t } from "../i18n.js";

export async function renderStats(root) {
  const stats = await api.get("/api/stats");
  show(root, h("section", { class: "panel" },
    h("h1", {}, t("stats.title")),
    h("div", { class: "tiles" },
      tile(t("stats.answers"), stats.total_answers), tile(t("stats.copies"), stats.total_copies)),
    h("h2", {}, t("stats.top_copied")),
    ranking(stats.top_copied.map((item) => [item.title, item.copies])),
    h("h2", {}, t("stats.top_unanswered")),
    ranking(stats.top_unanswered.map((item) => [item.text, item.times_searched]))));
}

function tile(label, value) {
  return h("div", { class: "tile" }, h("span", { class: "tile-value" }, value), h("span", {}, label));
}

function ranking(rows) {
  if (!rows.length) return h("p", { class: "muted" }, t("stats.empty"));
  return h("ol", { class: "ranking" },
    rows.map(([label, count]) => h("li", {}, h("span", {}, label), h("strong", {}, count))));
}
