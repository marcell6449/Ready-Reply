// Copy text. Phones open the app over http://192.168.x.x, which is not a secure context,
// so navigator.clipboard is missing there: fall back to a hidden textarea.

export async function copyText(text) {
  if (window.isSecureContext && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Permission denied: try the fallback below.
    }
  }
  return legacyCopy(text);
}

function legacyCopy(text) {
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.className = "offscreen";
  document.body.append(area);
  area.select();
  area.setSelectionRange(0, text.length);
  try {
    return document.execCommand("copy");
  } finally {
    area.remove();
  }
}
