// Fetch wrapper: sends the CSRF header and turns error responses into ApiError.

let csrfToken = "";

export class ApiError extends Error {
  constructor(status, code) {
    super(code);
    this.status = status;
    this.code = code;
  }
}

export function setCsrf(token) {
  csrfToken = token || "";
}

async function parse(response) {
  if (response.status === 204) return null;
  const type = response.headers.get("content-type") || "";
  if (type.includes("application/json")) return response.json();
  return response.blob();
}

export async function request(method, url, body, contentType = "application/json") {
  const headers = { "x-csrf-token": csrfToken };
  const options = { method, headers, credentials: "same-origin" };
  if (body !== undefined) {
    headers["content-type"] = contentType;
    options.body = contentType === "application/json" ? JSON.stringify(body) : body;
  }
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new ApiError(0, "network.offline");
  }
  const data = await parse(response);
  if (!response.ok) throw failure(response.status, data);
  return data;
}

function failure(status, data) {
  const error = new ApiError(status, data?.code || "error.generic");
  if (status === 401) {
    window.dispatchEvent(new CustomEvent("rr:signed-out", { detail: error.code }));
  }
  return error;
}

export const api = {
  get: (url) => request("GET", url),
  post: (url, body = {}) => request("POST", url, body),
  put: (url, body) => request("PUT", url, body),
  del: (url) => request("DELETE", url),
  upload: (url, file) => request("POST", url, file, "text/csv"),
};
