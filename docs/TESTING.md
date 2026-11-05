# How we test Udyam Digital

The judges run 15 live advisor scenarios and a KYC answer key. We built our own versions of both, plus
tests for phone photos and failures. Everything below can be re-run with one command.

| What | Command | Result (4 Nov 2026) |
|---|---|---|
| Unit and API tests (rules, quotes, KYC answer key, consent, privacy, failures, negotiation, voice) | `.venv/Scripts/python -m pytest -q` | 417 passed |
| 26 owner personas in 7 languages, AI switched off (backup mode) | `python scripts/eval_advisor.py scripted` | 26 / 26 |
| 11 hardest personas with the real AI (Groq, free tier) | `python scripts/eval_advisor.py ai <names>` | 11 / 11, ~4.1K tokens per chat (2 Nov, before the new languages) |
| Phone-like photos of 12 KYC documents | `python scripts/stress_kyc.py K03 K07 K10` | see below |
| Whole journey against the running server or Docker container | `python scripts/smoke_http.py` | chat -> quote -> consent -> 4 photos -> PASS -> delete |

Set `PYTHONIOENCODING=utf-8` on Windows so Hindi and Marathi print.

## Advisor personas (`scripts/eval_advisor.py`)

Each persona answers the question on screen in its own typed words (no button taps): English, Hindi, Marathi,
Hinglish, Devanagari digits ("१५"), number words ("about twenty five"), a GSTIN that belongs to someone else,
cancelled and suspended GSTINs, a typo GSTIN, a town not in our data, questions in the middle of the chat,
everything in the first message, and nonsense ("asdf", "what's the weather?").

Every conversation is checked for:
- finishing without asking the same question 3 times in a row
- a bundle that passes every catalogue rule (city tier, size, GST, dependencies) and a valid quote
- every "yes" need in the bundle or explained in a note; no product the owner said "no" to
- the right business kind, city, staff, sites and GST status
- every message in the owner's language, with no product codes or field names

What the tests found and what we changed:
| Found | Fix |
|---|---|
| Backup mode (AI down or rate-limited) got stuck when the owner typed "kirana store" instead of tapping | Code reads kind of business (EN/HI/MR/Hinglish keywords) and the city inside a sentence |
| "about twenty five" read as 5 | Tens + ones number words |
| The AI read "मेरी दवाई की दुकान है" (my medicine shop) as a clinic | The owner's own words decide the kind of business; the AI is the backup |
| The AI sometimes ignored a plain "no GST" ("नाही", "none") | Plain answers to the GST question never go to the AI |
| An unclear answer repeated the question with no explanation | Short hint first ("Please answer yes or no") |
| A Hindi chat showed one English note from the AI | AI text in the wrong language is replaced by our translated template |
| Extras switched on at quantity 1 while the card showed x8 | Extras switch on at the suggested quantity |
| Double taps and very long pastes | Taps on an old question are ignored; messages are cut at 500 characters |

## Phone photos (`scripts/stress_kyc.py`)

Each specimen is turned into 10 phone-like copies: tilted 5 and 12 degrees, sideways, upside down, JPEG
quality 30, 900 px wide, dark and noisy, a shadow across it, keystone (photo taken at an angle), and on a
table with background around it. We compare the fields read with those from the clean image.

| Photo | Document type found | Fields same as clean image | Before today's fixes (8 docs) |
|---|---|---|---|
| Tilted 5 degrees | 12 / 12 | 96% | 96% |
| Tilted 12 degrees | 12 / 12 | 96% | 92% |
| Sideways | 12 / 12 | 100% | 0% |
| Upside down | 12 / 12 | 100% | 4% |
| JPEG quality 30 | 12 / 12 | 85% | 79% |
| 900 px wide | 12 / 12 | 99% | 96% |
| Dark and noisy | 12 / 12 | 97% | 96% |
| Shadow across it | 12 / 12 | 99% | 71% |
| Keystone | 12 / 12 | 94% | 92% |
| On a table | 12 / 12 | 93% | 90% |

Documents: all four for K03, K07 and K10 (120 photos). About 3 s per photo on a laptop CPU; a sideways photo
takes 2-3 reads (up to about 9 s). The remaining differences are spacing in names (ignored by the checks) and
values the checks don't use; one consumer number was misread on the extreme JPEG-30 copy.

Fixes from this test:
- Sideways and upside-down photos are turned the right way up and read again (title near the top, text boxes
  wider than tall). Before: 0% of fields, and the app wrongly said "read successfully".
- Shadows are evened out before the pink watermark is removed. Before: shadowed GST/Udyam numbers were lost.
- A labelled box with ink in it but no text read is read again, enlarged. If it still can't be read, the owner
  is asked to retake the photo. An empty box (K01's planted blank Udyam number) is still a REJECT.
- Watermark letters run into an ID ("…7183141NO") are dropped. Extra digits are kept, and a GSTIN is only
  trimmed if its checksum passes, so a tampered number still fails.

## Failure cases (`tests/test_robustness.py`)

AI failing mid-chat, AI returning junk, AI stating a price or asking its own question, empty and giant messages,
unknown slots, double taps, empty / huge / non-image uploads, KYC with nothing uploaded, and 20 owners chatting
at the same time. The owner never sees an error from the AI: the chat carries on in backup mode.

## Review of the new features (4 Nov 2026)

After price negotiation, plan tiers, four more languages and voice were added, we checked them by running the
code, not just reading it. What we found and changed:

| Found | Fix |
|---|---|
| "haan na", "chahiye na" (Hinglish for "yes, of course") were read as **no**, because "na" is also Gujarati for no | "na" means no only when the answer starts with it ("na", "na bhai"); "chahiye", "pahije", "zaroor" count as yes |
| An owner without GST passed KYC with a bill for one business and an ID for another | Without GST or Udyam, the bill names the business and the ID must match it, otherwise a person reviews it |
| The GST certificate tile was hidden for owners with no GST or a cancelled GST, so K01's "GST cancelled" could not be shown | The tile is always shown: optional when the owner has no GST, required (and checked against the registry) when the GSTIN is cancelled or suspended |
| Any contract length was accepted (1000 months was saved and accepted) | Only the lengths shown on screen (and setup over 1, 6 or 12 months) are accepted |
| A salesperson callback could be requested after accepting, dated with the real date instead of the app's date; "Accept" twice was recorded twice | Callback only for an open quote, dated like the rest of the app; a second "Accept" changes nothing |
| The AI's price filter knew "rupee" only in English, Hindi and Marathi | Rupee words and short forms added for Gujarati, Tamil, Telugu and Kannada |
| With no AI key, voice said "not available in this language" | It now says voice is switched off (the mic button is hidden anyway) |
