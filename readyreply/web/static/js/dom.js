// Safe DOM building: text is always inserted as text nodes, never parsed as HTML.

export function h(tag, props = {}, ...children) {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(props)) {
    setProp(element, name, value);
  }
  appendChildren(element, children);
  return element;
}

function setProp(element, name, value) {
  if (value === undefined || value === null || value === false) return;
  if (name.startsWith("on")) {
    element.addEventListener(name.slice(2).toLowerCase(), value);
  } else if (name === "class") {
    element.className = value;
  } else if (name === "value" || name === "checked" || name === "disabled") {
    element[name] = value;
  } else {
    element.setAttribute(name, value === true ? "" : String(value));
  }
}

function appendChildren(element, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    element.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function show(container, ...children) {
  container.replaceChildren();
  appendChildren(container, children);
}

const TOAST_MS = 2200;
let toastTimer = 0;

export function toast(message, kind = "ok") {
  const region = document.getElementById("toast");
  region.textContent = message;
  region.dataset.kind = kind;
  region.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => region.classList.remove("visible"), TOAST_MS);
}

export function field(labelText, input, hint) {
  return h("label", { class: "field" }, h("span", { class: "field-label" }, labelText), input,
    hint ? h("span", { class: "field-hint" }, hint) : null);
}

// Disables the button while the action runs, so a double click cannot submit twice.
export async function busy(button, action) {
  if (button.disabled) return undefined;
  button.disabled = true;
  try {
    return await action();
  } finally {
    button.disabled = false;
  }
}
