const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });

/** ₹1,23,456 — Indian digit grouping, no decimals. */
export function formatINR(amount) {
  return '₹' + inr.format(Math.round(amount));
}

export const GST_RATE = 0.18;

/** Monthly subtotal, GST and total, rounded the way the bill shows them. */
export function withGST(subtotal, rate = GST_RATE) {
  const gst = Math.round(subtotal * rate);
  return { subtotal, gst, total: subtotal + gst };
}

/**
 * Mask an ID, keeping `head` and `tail` characters: 27XUI4321A1ZP → 27XUI******1ZP.
 * Always mask on the server too; this is for display only.
 */
export function maskId(value, head = 5, tail = 3) {
  if (!value) return '';
  const s = String(value);
  if (s.length <= head + tail) return s;
  return s.slice(0, head) + '*'.repeat(Math.max(6, s.length - head - tail)).slice(0, 6) + s.slice(-tail);
}
