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
  // ref: a partner's referral code from the link (/?ref=RAJ01); assisted: the partner is sitting with the owner
  start: (language, ref = null, assisted = false) => call("POST", "/applications", { language, ref, assisted }),
  send: (id, msg) => call("POST", `/applications/${id}/message`, msg),
  switchProduct: (id, product_id, on) => call("POST", `/applications/${id}/addons`, { product_id, on }),
  plan: (id, choice = {}) => call("POST", `/applications/${id}/plan`, choice),   // tier, contract, setup spread
  salesCallback: (id, body) => call("POST", `/applications/${id}/sales-callback`, body),
  // mobile number with a one-time code: save progress / required to accept; continue on another phone
  phoneSend: (id, phone) => call("POST", `/applications/${id}/phone`, { phone }),
  phoneVerify: (id, code, marketing) => call("POST", `/applications/${id}/phone/verify`, { code, marketing }),
  resumeSend: (phone, lang) => call("POST", "/resume", { phone, lang }),
  resumeVerify: (phone, code, lang) => call("POST", "/resume/verify", { phone, code, lang }),
  accept: (id) => call("POST", `/applications/${id}/accept`),
  consent: (id, purposes) => call("POST", `/applications/${id}/consent`, { purposes }),
  upload: (id, docType, file) => {
    const form = new FormData();
    form.append("file", file);
    return call("POST", `/applications/${id}/documents/${docType}`, form);
  },
  digilocker: (id, docType) => call("POST", `/applications/${id}/documents/${docType}/digilocker`),   // demo
  udyamNumber: (id, number) => call("POST", `/applications/${id}/udyam-number`, { number }),
  checkKyc: (id) => call("POST", `/applications/${id}/kyc`),
  status: (id) => call("GET", `/applications/${id}`),
  erase: (id) => call("DELETE", `/applications/${id}`),
  marketing: (id, on) => call("POST", `/applications/${id}/marketing`, { on }),
  backoffice: (key) => call("GET", "/backoffice/applications", undefined, { "x-admin-key": key }),   // staff only
  officeStats: (key) => call("GET", "/backoffice/stats", undefined, { "x-admin-key": key }),
  officeCustomers: (key) => call("GET", "/backoffice/customers", undefined, { "x-admin-key": key }),
  officeLeads: (key) => call("GET", "/backoffice/leads?limit=60", undefined, { "x-admin-key": key }),
  officeMe: (key) => call("GET", "/backoffice/me", undefined, { "x-admin-key": key }),          // staff or partner
  officeAccessLog: (key) => call("GET", "/backoffice/access-log", undefined, { "x-admin-key": key }),
  officeInstalled: (key, ref, productId) =>
    call("POST", `/backoffice/applications/${ref}/installed`, { product_id: productId }, { "x-admin-key": key }),
};
