import { api, setCsrf } from "../api.js";
import { field, h, show, submitForm } from "../dom.js";
import { t } from "../i18n.js";

const SETUP_FORM = {
  title: "setup.title", intro: "setup.intro", submit: "setup.submit",
  passwordAutocomplete: "new-password", usernameHint: "auth.username_hint", passwordHint: "auth.password_hint",
};
const LOGIN_FORM = {
  title: "login.title", intro: "login.intro", submit: "login.submit",
  passwordAutocomplete: "current-password", usernameHint: null, passwordHint: null,
};

function credentialsForm(options, onSubmit, extraFields = []) {
  const username = h("input", { name: "username", autocomplete: "username", required: true, maxlength: 32 });
  const password = h("input", { name: "password", type: "password", required: true,
    autocomplete: options.passwordAutocomplete, maxlength: 128 });
  return submitForm({
    className: "panel auth-panel",
    submitLabel: t(options.submit),
    onSubmit: () => onSubmit({ username: username.value, password: password.value }),
  },
  h("h1", {}, t(options.title)), h("p", { class: "muted" }, t(options.intro)),
  field(t("auth.username"), username, options.usernameHint && t(options.usernameHint)),
  field(t("auth.password"), password, options.passwordHint && t(options.passwordHint)),
  extraFields);
}

async function signIn(url, body, onSignedIn) {
  const status = await api.get("/api/setup/status");
  setCsrf(status.csrf_token);
  const me = await api.post(url, body);
  setCsrf(me.csrf_token);
  onSignedIn(me);
}

export function renderSetup(root, onSignedIn) {
  const whatsapp = h("input", { name: "whatsapp", type: "tel", inputmode: "tel", autocomplete: "tel",
    maxlength: 40, placeholder: "8888-1234" });
  const afterSetup = (me) => {
    window.location.hash = "#/welcome";
    onSignedIn(me);
  };
  show(root, credentialsForm(SETUP_FORM,
    (credentials) => signIn("/api/setup", { ...credentials, whatsapp: whatsapp.value }, afterSetup),
    [field(t("setup.whatsapp"), whatsapp, t("setup.whatsapp_hint"))]));
}

export function renderLogin(root, onSignedIn, reason) {
  const form = credentialsForm(LOGIN_FORM,
    (credentials) => signIn("/api/auth/login", credentials, onSignedIn));
  if (reason === "auth.session_expired") {
    form.insertBefore(h("p", { class: "warning" }, t("login.expired")), form.children[1]);
  }
  show(root, form);
}
