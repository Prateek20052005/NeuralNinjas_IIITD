// Screen text comes from the backend (one set of language files for the whole app).
import { useEffect, useState } from "react";
import { api } from "./api.js";

const cache = {};

export function useStrings(lang) {
  const [strings, setStrings] = useState(cache[lang] || null);
  useEffect(() => {
    if (cache[lang]) return setStrings(cache[lang]);
    let live = true;
    api.strings(lang).then((s) => {
      cache[lang] = s;
      if (live) setStrings(s);
    }).catch(() => live && setStrings({}));
    return () => { live = false; };
  }, [lang]);
  return (key, params = {}) => {
    const text = strings?.[key] ?? "";
    return text.replace(/\{(\w+)\}/g, (_, k) => (params[k] ?? `{${k}}`));
  };
}

const LOCALE = { en: "en-IN", hi: "hi-IN", mr: "mr-IN" };

export const rupees = (n) => new Intl.NumberFormat("en-IN").format(n);

export const longDate = (iso, lang) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(LOCALE[lang] || "en-IN", { day: "numeric", month: "long", year: "numeric" });
