// Thin wrapper over the FastAPI backend. Errors carry the server's message (already in the owner's language).

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function call(method, path, body) {
  const opts = { method, headers: {} };
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(`/api${path}`, opts);
  } catch {
    throw new ApiError("offline", 0);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "";
    throw new ApiError(detail, res.status);
  }
  return data;
}

export const api = {
  strings: (lang) => call("GET", `/i18n/${lang}`),
  consentText: (lang) => call("GET", `/consent/${lang}`),
  catalogue: () => call("GET", "/catalogue"),
  start: (language) => call("POST", "/applications", { language }),
  send: (id, msg) => call("POST", `/applications/${id}/message`, msg),
  switchProduct: (id, product_id, on) => call("POST", `/applications/${id}/addons`, { product_id, on }),
  accept: (id) => call("POST", `/applications/${id}/accept`),
  consent: (id, purposes) => call("POST", `/applications/${id}/consent`, { purposes }),
  upload: (id, docType, file) => {
    const form = new FormData();
    form.append("file", file);
    return call("POST", `/applications/${id}/documents/${docType}`, form);
  },
  udyamNumber: (id, number) => call("POST", `/applications/${id}/udyam-number`, { number }),
  checkKyc: (id) => call("POST", `/applications/${id}/kyc`),
  status: (id) => call("GET", `/applications/${id}`),
  erase: (id) => call("DELETE", `/applications/${id}`),
};
