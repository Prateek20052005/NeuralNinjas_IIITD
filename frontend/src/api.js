// Thin wrapper over the FastAPI backend. Errors carry the server's message (already in the owner's language).

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function call(method, path, body, headers = {}) {
  const opts = { method, headers: { ...headers } };
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
  health: () => call("GET", "/health"),
  voice: (id, audio) => {   // a spoken answer -> its text, for the owner to check before sending
    const form = new FormData();
    const ext = (audio.type.split(";")[0].split("/")[1] || "webm").replace("x-", "");
    form.append("file", audio, `answer.${ext}`);
    return call("POST", `/applications/${id}/voice`, form);
  },
  consentText: (lang) => call("GET", `/consent/${lang}`),
  catalogue: () => call("GET", "/catalogue"),
  start: (language) => call("POST", "/applications", { language }),
  send: (id, msg) => call("POST", `/applications/${id}/message`, msg),
  switchProduct: (id, product_id, on) => call("POST", `/applications/${id}/addons`, { product_id, on }),
  plan: (id, choice = {}) => call("POST", `/applications/${id}/plan`, choice),   // tier, contract, setup spread
  priceRequest: (id) => call("POST", `/applications/${id}/price-request`),
  salesCallback: (id, body) => call("POST", `/applications/${id}/sales-callback`, body),
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
  backoffice: (key) => call("GET", "/backoffice/applications", undefined, { "x-admin-key": key }),   // staff only
};
