import { api } from "../api.js";
import { busy, field, h, show, toast } from "../dom.js";
import { errorText, t } from "../i18n.js";
import { state } from "../state.js";

export async function renderUsers(root) {
  const users = await api.get("/api/users");
  show(root, h("section", { class: "panel" },
    h("h1", {}, t("users.title")), h("p", { class: "muted" }, t("users.intro")),
    h("ul", { class: "list" }, users.map((user) => userRow(root, user))),
    newUserForm(root)));
}

function roleSelect(value) {
  return h("select", { "aria-label": t("users.role") },
    ["staff", "admin"].map((role) => h("option", { value: role, selected: role === value },
      t(`role.${role}`))));
}

function userRow(root, user) {
  const role = roleSelect(user.role);
  role.value = user.role;
  const active = h("input", { type: "checkbox", checked: user.active });
  const password = h("input", { type: "password", autocomplete: "new-password",
    placeholder: t("users.new_password"), "aria-label": t("users.new_password") });
  const save = h("button", { class: "button small", type: "button", onClick: (e) => busy(e.currentTarget,
    () => update(root, user, { role: role.value, active: active.checked, new_password: password.value || null })) },
  t("common.save"));
  return h("li", { class: "list-row" },
    h("div", { class: "list-main" }, h("strong", {}, user.username),
      user.username === state.me.username ? h("span", { class: "chip" }, t("users.you")) : null),
    h("div", { class: "row wrap" }, role,
      h("label", { class: "inline" }, active, t("users.active")), password, save,
      h("button", { class: "button small danger", type: "button",
        onClick: (e) => busy(e.currentTarget, () => remove(root, user)) }, t("common.delete"))));
}

async function update(root, user, changes) {
  try {
    await api.put(`/api/users/${user.id}`, changes);
    toast(t("users.saved"));
    await renderUsers(root);
  } catch (error) {
    toast(errorText(error.code), "warn");
  }
}

async function remove(root, user) {
  if (!window.confirm(t("users.confirm_delete", { name: user.username }))) return;
  try {
    await api.del(`/api/users/${user.id}`);
    await renderUsers(root);
  } catch (error) {
    toast(errorText(error.code), "warn");
  }
}

function newUserForm(root) {
  const username = h("input", { required: true, maxlength: 32, autocomplete: "off" });
  const password = h("input", { type: "password", required: true, autocomplete: "new-password" });
  const role = roleSelect("staff");
  const error = h("p", { class: "form-error", role: "alert" });
  const submit = h("button", { class: "button", type: "submit" }, t("users.create"));
  return h("form", { class: "subpanel", onSubmit: (event) => {
    event.preventDefault();
    busy(submit, async () => {
      try {
        await api.post("/api/users", { username: username.value, password: password.value, role: role.value });
        await renderUsers(root);
      } catch (e) { error.textContent = errorText(e.code); }
    });
  } },
  h("h2", {}, t("users.new")),
  field(t("auth.username"), username, t("auth.username_hint")),
  field(t("auth.password"), password, t("auth.password_hint")),
  field(t("users.role"), role), error, submit);
}
