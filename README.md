# Udyam Digital: a small business goes digital in one sitting

**Team NeuralNinjas (IIITD) · YTL Hackathon 2026 · Enterprise Track A**

Udyam Digital is a phone web app for **Accel Business**, the case's fictional telecom operator. A shop, clinic or
small factory owner chats with an AI advisor in their own language. They get a bundle of internet, phone and digital
services at one clear monthly price, verify their business with instant KYC, and track installation. They never
wait for a salesperson's visit or a PDF quote.

| Today (sales-led, Apr–Jun 2026 data) | With the app |
|---|---|
| A sales visit to discover needs, then 3–5 days for a PDF quote | A 2-minute chat and an instant, itemised price |
| KYC papers collected in person or by email | Document photos read on the spot, checked against GST and Udyam registries |
| 17.6 days from lead to activation, 3 status calls per customer | A tracker with a ready-by date for each product |
| 7.4% of leads activate; about Rs 15,000 to win each customer | Target: 15%+ and under Rs 6,000 (see [success metrics](#success-metrics)) |

All businesses, people, documents and numbers come from the synthetic hackathon dataset. "Accel Business" is fictional.

---

## Run it

You need **Docker**. Nothing else.

```bash
cp .env.example .env          # then fill in the values below
docker build -t udyam-digital .
docker run --env-file .env -p 7860:7860 -v udyam-state:/app/state udyam-digital
```

Open **http://localhost:7860**. On a phone on the same Wi-Fi, use `http://<your-computer-ip>:7860`.

| Setting in `.env` | Needed? | What it does |
|---|---|---|
| `GROQ_API_KEY` | Optional | Turns on the AI advisor (free key from console.groq.com). Without it the advisor runs in guided mode with the same questions, rules and prices. |
| `APP_STATE_KEY` | Recommended | Encrypts saved applications so progress survives a restart. Make one with `python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"` |
| `BACKOFFICE_KEY` | For the back office | Any secret word; opens the staff view at `/#/office` |
| `PARTNER_KEYS` | Optional | Logins for channel partners, e.g. `RAJ01=some-key` |
| `OTP_MODE` | Leave as `demo` | Shows the mobile verification code on screen. `sms` sends real texts (MSG91 or Twilio, see `.env.example`). |

`docs/DEPLOY.md` explains how to host it free on Hugging Face Spaces.

---

## A 5-minute demo

1. **Chat.** Pick a language (English, हिंदी, मराठी, ગુજરાતી, தமிழ், తెలుగు, ಕನ್ನಡ). When asked for a GST number, type
   `27XUIXG0767D1ZP`. The app finds *Ganesh Woodcraft, Nagpur* in the GST registry and fills in the name and city.
   Answer a few questions by tapping or typing (or by voice in English and Hindi).
2. **Plan.** See the recommended bundle with a reason for each product. You can:
   - switch extras on and off;
   - pick Basic / Recommended / Full;
   - choose 12 or 24 months for a lower price, or pay 3, 6 or 12 months ahead;
   - compare the price with what you pay today.

   First-time customers get a welcome offer on setup. Because this is a factory, the plan offers a call from a specialist.
3. **Negotiate.** Back in the chat, type "this is too expensive". The first answer shows cheaper ways to pay (no
   discount yet). Insist and you get 5%, then 10%, then a salesperson's call. The limits come from
   `backend/app/pricing_settings.json`.
4. **Accept.** Verify a mobile number. In demo mode the code is shown on screen. The order is signed with that
   code (e-sign demo).
5. **Consent and KYC.** Agree to the purposes listed on the consent screen. Then either:
   - upload `data/kyc_documents/K03_*.png` (four photos); or
   - use **Get it from DigiLocker (demo)** for the GST and Udyam certificates, and upload only the address proof and ID.

   The decision is instant: PASS. Try `K01` (cancelled GST), `K04` (blurred photo) or `K11` (old electricity bill)
   to see each kind of problem caught.
6. **Tracker.** Each product has its own ready-by date: SIMs 1 day, fibre 5, firewall 10.
7. **Back office.** Open `http://localhost:7860/#/office` and enter your `BACKOFFICE_KEY`. You'll see:
   - the success-metrics table and the live funnel;
   - leads to call first, ranked by the conversion predictor;
   - applications that need a person;
   - **Mark live** for each product, and the access log.
8. **Partner.** Start a chat from `http://localhost:7860/?ref=RAJ01&assisted=1`. The owner sees "Raj Telecom is
   helping you". Sign in to the back office with Raj Telecom's `PARTNER_KEYS` key and you see only that referral,
   with no documents or ID numbers.

---

## What the case asked for, and where it is

| Case requirement | What we built | Code |
|---|---|---|
| **AI advisor**: asks about the business and recommends a bundle in plain language | Chat in 7 languages, voice in English and Hindi. The AI understands free text; a rules engine picks products and checks every catalogue rule. Extras are ranked by what similar past customers bought. | `backend/app/advisor/`, `recommend.py`, `bundles.py`, `similar.py`, `voice.py` |
| **Quote and checkout**: one transparent monthly price, add-ons the owner can toggle | Itemised price with GST shown separately, including on the setup fee. Three tiers, contract-length pricing, setup spread over 6 or 12 months, pay-ahead billing, welcome offer, chat negotiation with a hard floor. | `quote.py`, `negotiate.py`, `frontend/src/screens/Plan.jsx` |
| **Smart KYC**: document upload with extraction and validation, mock GSTIN/Udyam lookups, a clear consent screen | Local OCR (photos never leave our server). Straightens tilted photos, repairs common OCR misreads, runs 30+ checks against the registries. Owners without GST need only address proof and ID. DigiLocker demo. Matches all 12 applicants in our answer key. | `backend/app/kyc/`, `Consent.jsx`, `Documents.jsx` |
| **Tracker**: an order status the owner can check instead of calling support | Timeline from accepted → signed → consent → documents → verified → installation → all live. Each product has its own ready-by date. | `tracker.py`, `Tracker.jsx` |
| *Stretch:* voice or WhatsApp front end | Voice answers in English and Hindi. The owner checks the text before sending, and the GST number is always typed, never spoken. | `voice.py`, `Chat.jsx` |
| *Stretch:* back office for leads the advisor could not close | Callbacks and hand-offs (price, leased lines, factories, 5+ sites, a chat that keeps failing, help with GST registration), each with a summary of the owner's answers. | `handoff.py`, `BackOffice.jsx` |
| *Stretch:* propensity score for which leads to call | Logistic regression on the 5,000 past leads: AUC 0.754 on leads it never saw, top 10% activate 2.7× more often than average. Language is left out on purpose, for fairness. | `predictor.py` |

### The five key questions
- **Which segments, which bundles:** micro shops get a cheap entry plan (fibre, or 5G AirFiber where fibre can't reach, plus one or
  two mobile lines); offices get email and security, with backup as an extra; chains and factories go to a specialist. The defaults come from what
  the 368 activated customers bought.
- **Discovery without a salesperson:** the chat, in the owner's language, with tap-to-answer options.
- **Near-instant, DPDP-compliant KYC:** registry lookups, local OCR, consent first, masking, short retention (see [Privacy](#privacy-and-security)).
- **Field force and partners:** partner referral links keep the partner's commission, and assisted mode supports a
  partner sitting with the owner. Partners get a limited back-office login. Hard cases go to the business team
  instead of competing with it.
- **Success metrics:** see the next section.

### Success metrics
Shown live in the back office (`metrics.py`). "Before" is computed from `smb_leads.csv`.

| Metric | Before | Pilot target (2 quarters) |
|---|---|---|
| Lead → activation | 7.4% | 15% or more |
| Days from first contact to live | 17.6 | under 5 (fibre and AirFiber plans) |
| Cost to win a customer | ~Rs 15,100 | under Rs 6,000 on app-led sales |
| Status calls from the customer | 3.0 | under 0.5 |
| Customers leaving within 6 months | 15.2% | 20–30% lower |

---

## How it works

```
 Phone web app (React)  ──────►  FastAPI backend (one Docker container)
  chat · plan · consent           ├─ advisor/      conversation: fixed questions, AI reads free text
  documents · tracker             ├─ recommend.py  rules engine: eligible bundle from the 25-product catalogue
  back office (/#/office)         ├─ quote.py      prices, GST, contracts, offers, floor
                                  ├─ kyc/          local OCR → field parsing → registry checks → decision
                                  ├─ tracker.py    per-product install dates
                                  ├─ predictor.py  which leads to call first
                                  └─ store.py      encrypted applications, retention, access log
                                          │
                          Groq (chat AI + speech-to-text): only the current message, ID numbers removed
```

**The AI talks, the rules decide.** The AI only (1) pulls facts out of what the owner types and (2) explains
the finished bundle in the owner's language. The questions, the products, the quantities and every price come from
deterministic code checked against the catalogue (city tier, minimum staff and sites, GST requirement, product
dependencies). A recommendation can't break a rule, and the same answers always give the same plan. If the AI
is down or rate-limited, the chat carries on in guided mode.

---

## Privacy and security

Designed for India's Digital Personal Data Protection Act, 2023:

- **Consent first.** KYC starts only after the owner ticks named purposes. The consent text version and time are
  recorded. Offers and news are a separate opt-in, unticked by default and switchable off at any time.
- **Data minimisation.**
  - The AI gets only the current message, with GST, Udyam, PAN, phone, Aadhaar and email numbers and the business
    name removed. It never sees the chat history.
  - The chat transcript is never stored.
  - Owners are told an AI reads their replies, and voice recordings are never stored.
- **Photos never leave our server.** OCR runs locally. Each photo is read in memory and discarded; only the fields
  needed are kept.
- **Masking.** ID numbers are masked on every screen and in every log (`27XUI******D1ZP`).
- **Encryption.** Saved applications and the access log are encrypted and signed (Fernet: AES plus HMAC).
- **Retention.**
  - Unfinished applications are deleted 72 hours after the last activity.
  - Accepted orders are kept for 365 days.
  - Document details are deleted as soon as every service is live; only the KYC result is kept.
  - Owners can delete everything at any time.
- **Least privilege.** Partners see only their own referrals, never documents, KYC evidence, GST or phone numbers.
  Every back-office view, including refused logins, is recorded in the access log.

---

## Tests

All tests run inside Docker, because the pinned OCR runtime has no wheel for macOS:

```bash
docker run --rm -v "$PWD":/src -w /src --user root udyam-digital \
  sh -c "pip install -q pytest httpx; python -m pytest -q -p no:cacheprovider"
```

| What | Result |
|---|---|
| Unit and API tests: rules, quotes, KYC answer key, consent, privacy, negotiation, voice, partners, tracker | 448 passed |
| 26 owner personas in 7 languages, typed in their own words (`python scripts/eval_advisor.py scripted`) | 26 / 26 |
| 12 KYC applicants (K01–K12) against our answer key (`tests/kyc_answer_key.csv`) | 12 / 12 |

`docs/TESTING.md` lists what each test covers and what the tests found and fixed.

---

## Project layout

```
backend/app/           FastAPI app (main.py) and all business logic
  advisor/             chat flow, free-text parsing in 7 languages, AI calls
  kyc/                 OCR, document parsing, registry lookups, checks, DigiLocker demo
  i18n/                every screen and chat text in 7 languages
  pricing_settings.json  discount limits, welcome offer, pay-ahead savings
  partners.json        demo channel partners
frontend/              React + Vite phone app (served by the backend after the Docker build)
data/                  the hackathon dataset: catalogue, 5,000 leads, mock registries, 47 KYC images
tests/                 pytest suite and the KYC answer key
scripts/               persona evaluation, KYC stress tests, end-to-end smoke test
analysis/              results from the scripts
docs/                  DEPLOY.md (hosting), TESTING.md (test details)
accel-business-ui/     the design kit the app's screens were built from
```

## Limits of the prototype

- KYC lookups, DigiLocker and e-sign run against the mock registries. Production would use DigiLocker, a licensed
  KYC vendor and Aadhaar e-sign.
- Real SMS codes work through MSG91 or Twilio, but Indian SMS needs a DLT-registered template. Judging uses demo mode.
- Payment is not taken in the app.
- Voice is on for English and Hindi only. The other 5 languages are translated but not yet tested with speech.
- The non-English texts were written by the team and still need a review by native speakers.
