import { api, setCsrf } from "../api.js";
import { busy, field, h, show } from "../dom.js";
import { errorText, t } from "../i18n.js";

const SETUP_FORM = {
  title: "setup.title", intro: "setup.intro", submit: "setup.submit",
  passwordAutocomplete: "new-password", usernameHint: "auth.username_hint", passwordHint: "auth.password_hint",
};
const LOGIN_FORM = {
  title: "login.title", intro: "login.intro", submit: "login.submit",
  passwordAutocomplete: "current-password", usernameHint: null, passwordHint: null,
};

function credentialsForm(options, onSubmit) {
  const username = h("input", { name: "username", autocomplete: "username", required: true, maxlength: 32 });
  const password = h("input", { name: "password", type: "password", required: true,
    autocomplete: options.passwordAutocomplete, maxlength: 128 });
  const error = h("p", { class: "form-error", role: "alert" });
  const submit = h("button", { class: "button", type: "submit" }, t(options.submit));
  const form = h("form", { class: "panel auth-panel", onSubmit: (event) => {
    event.preventDefault();
    busy(submit, () => onSubmit(username.value, password.value).catch((e) => {
      error.textContent = errorText(e.code);
    }));
  } },
  h("h1", {}, t(options.title)), h("p", { class: "muted" }, t(options.intro)),
  field(t("auth.username"), username, options.usernameHint && t(options.usernameHint)),
  field(t("auth.password"), password, options.passwordHint && t(options.passwordHint)),
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
  show(root, credentialsForm(SETUP_FORM,
    (username, password) => signIn("/api/setup", username, password, onSignedIn)));
}

export function renderLogin(root, onSignedIn, reason) {
  const form = credentialsForm(LOGIN_FORM,
    (username, password) => signIn("/api/auth/login", username, password, onSignedIn));
  if (reason === "auth.session_expired") {
    form.insertBefore(h("p", { class: "warning" }, t("login.expired")), form.children[1]);
  }
  show(root, form);
}
