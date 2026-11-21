import { api, setCsrf } from "../api.js";
import { busy, field, h, show } from "../dom.js";
import { errorText, t } from "../i18n.js";

function credentialsForm(titleKey, introKey, submitKey, onSubmit) {
  const username = h("input", { name: "username", autocomplete: "username", required: true, maxlength: 32 });
  const password = h("input", { name: "password", type: "password", required: true,
    autocomplete: introKey === "setup.intro" ? "new-password" : "current-password", maxlength: 128 });
  const error = h("p", { class: "form-error", role: "alert" });
  const submit = h("button", { class: "button", type: "submit" }, t(submitKey));
  const form = h("form", { class: "panel auth-panel", onSubmit: (event) => {
    event.preventDefault();
    busy(submit, () => onSubmit(username.value, password.value).catch((e) => {
      error.textContent = errorText(e.code);
    }));
  } },
  h("h1", {}, t(titleKey)), h("p", { class: "muted" }, t(introKey)),
  field(t("auth.username"), username, introKey === "setup.intro" ? t("auth.username_hint") : null),
  field(t("auth.password"), password, introKey === "setup.intro" ? t("auth.password_hint") : null),
  error, submit);
  return form;
}

async function signIn(url, username, password, onSignedIn) {
  const status = await api.get("/api/setup/status");
  setCsrf(status.csrf_token);
  const me = await api.post(url, { username, password });
  setCsrf(me.csrf_token);
  onSignedIn(me);
}

export function renderSetup(root, onSignedIn) {
  show(root, credentialsForm("setup.title", "setup.intro", "setup.submit",
    (username, password) => signIn("/api/setup", username, password, onSignedIn)));
}

export function renderLogin(root, onSignedIn, reason) {
  const form = credentialsForm("login.title", "login.intro", "login.submit",
    (username, password) => signIn("/api/auth/login", username, password, onSignedIn));
  if (reason === "auth.session_expired") {
    form.insertBefore(h("p", { class: "warning" }, t("login.expired")), form.children[1]);
  }
  show(root, form);
}
