# Accel Business – Udyam Digital · UI kit

React 18 + Vite, plain CSS with custom properties, one component per file, Lucide icons only.
"Accel Business" is a fictional brand.

```
npm install
npm run dev        # demo: Chat → Plan → Documents → Tracker, language + dark mode in the header
npm run build
```

## Tokens

`src/styles/tokens.css` has every colour, type size, spacing step, radius, shadow and motion value.

- Light is the default. Dark follows the OS unless `<html data-theme="light|dark">` is set.
- Type sizes are in rem, so layouts survive 200% text size.
- Devanagari: `:lang(hi)` and `:lang(mr)` switch to Noto Sans Devanagari with line-height 1.6.
  Set `lang` on the screen root (see `PlanScreen`).
- `prefers-reduced-motion` sets every duration to 0.

Changes from the brief, all for WCAG AA:

| Token | Brief | Kit | Why |
|---|---|---|---|
| `--color-brand` | #E0443A | #D23B32 | white button text 4.2 → 4.8:1 |
| `--color-danger` | #C62828 | #B4183D | stays visibly different from the brand red |
| `--color-success` | #1A9E5C | #157F4A | passes as text |
| `--color-warning` | #C27C0E | #915800 | passes as text |
| Marigold as text | #F2A900 | `--color-accent-ink` #7A4E00 | Marigold is a fill only |

In dark mode, primary buttons use dark text on #FF6B5E.

## Components (`src/components`)

| File | What it is |
|---|---|
| `Button` | primary, secondary, plain, destructive, trust; `href` renders a link |
| `Chip`, `ChipGroup` | tap-to-answer chips; `numeric` for 1 · 3 · 5 · 10 · 20 |
| `SegmentedControl` | radio group with arrow-key support |
| `Switch` | iOS-style switch (`role="switch"`) |
| `Checkbox` | labelled row with hint; never pre-ticked |
| `TextField`, `NumberField` | label, hint, error; stepper for counts |
| `ChatBubble` | `from="assistant" | "owner" | "hint"` |
| `TypingIndicator` | three dots, announced as status |
| `ProductCard` | name, quantity, one-line reason, monthly price |
| `ToggleRow` | extra with price and switch; whole row is the target |
| `PriceBar` | sticky monthly total, GST shown separately, setup, contract, go-live |
| `PriceBreakdown` | native `<details>` "How is this price worked out?" |
| `UploadTile` | `state="empty" | "reading" | "read" | "retake"` |
| `FieldPreviewList` | what we read, with `masked` values |
| `StatusBadge` | Approved / Retake / Review / Rejected / Incomplete, icon + word |
| `DecisionCard` | outcome, what happens next, one action |
| `Timeline` | done / now / todo steps |
| `BottomSheet` | `<dialog>`-based, so focus and Esc come from the browser |
| `Toast` | auto-dismissing status message |
| `ProgressIndicator` | slim bar + "3 of 8" (pass `formatLabel` for Hindi/Marathi) |
| `LanguageSwitcher` | header pill + sheet with English / हिंदी / मराठी |
| `AppHeader` | sticky frosted header, solid fallback |
| `EmptyState` | illustration slot + title + action |
| `Note` | info / warn / ok / trust explanation |
| `BrandMark` | the fictional mark |

`src/screens` shows four of them composed: `ChatScreen`, `PlanScreen` (live totals, English + Hindi copy in
`src/i18n/plan.js`), `DocumentsScreen` (simulated reading), `TrackerScreen` (all four decisions).

`src/lib/format.js`: `formatINR` (₹1,23,456), `withGST`, `maskId`. Mask IDs on the server as well.

## Placeholders to replace

- Security cameras (₹398) and WhatsApp Business setup (₹149) prices are samples; the clinic bundle prices come from the brief.
- Dates, names, order numbers and the 72-hour window in copy are demo data.
- The design canvas has the remaining screens (home, consent, camera, e-sign, payment, booking, help, privacy, partner mode, system states, back office) to build from these components.
