import { api } from "../api.js";
import { h, show } from "../dom.js";
import { t } from "../i18n.js";

export async function renderPhone(root) {
  const { url } = await api.get("/api/system/lan");
  show(root, h("section", { class: "panel center" },
    h("h1", {}, t("phone.title")), h("p", { class: "muted" }, t("phone.intro")),
    h("img", { class: "qr", src: "/api/system/qr.svg", alt: t("phone.qr_alt"), width: 240, height: 240 }),
    h("p", { class: "url" }, url),
    h("p", { class: "muted small" }, t("phone.same_wifi"))));
}
