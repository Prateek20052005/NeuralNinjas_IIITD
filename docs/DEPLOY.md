# Running and hosting the app

Everything here is free. The secrets are the Groq API key and the `APP_STATE_KEY` that encrypts saved applications;
neither is ever put in the code or the image.

## 1. On your own computer (Docker)

```bash
docker build -t udyam-digital .
docker run --env-file .env -p 7860:7860 -v udyam-state:/app/state udyam-digital
```

Open http://localhost:7860 (on a phone on the same Wi-Fi: http://<your-computer-ip>:7860).
Without a `GROQ_API_KEY` in `.env` the advisor still works in guided (scripted) mode.
The `udyam-state` volume keeps owners' applications (encrypted with `APP_STATE_KEY`) across restarts and rebuilds, for
`RETENTION_HOURS` (72) after the last activity. Without `APP_STATE_KEY` they are kept in memory only.
One-time codes run in demo mode (`OTP_MODE=demo`): the code is shown on screen, as there is no SMS provider yet.

## 2. Free public link: Hugging Face Spaces

Free "CPU basic" Spaces have 2 vCPU and 16 GB RAM, enough for the local OCR. A Space sleeps after
about 48 hours without visitors; the first visit after that takes a minute to wake it.

1. Create a free account at https://huggingface.co (you do this yourself).
2. **New Space** -> name it, e.g. `udyam-digital` -> SDK **Docker** -> template **Blank** -> **Create Space**.
3. In the Space: **Settings -> Variables and secrets**
   - **New secret**: `GROQ_API_KEY` = your key (secrets are hidden and never shown in logs)
   - **New variable**: `LLM_PROVIDER` = `groq`, `LLM_MODEL` = `openai/gpt-oss-120b`, `APP_TODAY` = `2026-07-15`
   - Optional secret `BACKOFFICE_KEY` to switch on the back-office list.
4. Upload the code. The Space is a git repository:
   ```bash
   git clone https://huggingface.co/spaces/<your-name>/udyam-digital space
   ```
   Copy into `space/`: `Dockerfile`, `.dockerignore`, `backend/`, `frontend/` (without `node_modules` and
   `dist`), `data/*.csv`. **Do not copy `.env`.** Add this block at the very top of `space/README.md`:
   ```yaml
   ---
   title: Accel Business - Udyam Digital
   emoji: 📶
   colorFrom: red
   colorTo: gray
   sdk: docker
   app_port: 7860
   ---
   ```
   Then `git add . && git commit -m "Deploy" && git push` (use a Hugging Face access token as the password).
5. The Space builds the Docker image (about 5 minutes) and shows the app at
   `https://<your-name>-udyam-digital.hf.space`.

## Settings reference

| Name | Where | Meaning |
|---|---|---|
| `GROQ_API_KEY` | secret | Groq key for the AI advisor; empty = guided mode |
| `LLM_PROVIDER` | variable | `groq` |
| `LLM_MODEL` | variable | default `openai/gpt-oss-120b` |
| `APP_TODAY` | variable | date used for document checks (`2026-07-15` per the case) |
| `RETENTION_HOURS` | variable | idle applications are deleted after this many hours (default 72) |
| `BACKOFFICE_KEY` | secret | turns on `/api/backoffice/applications` (send it as header `x-admin-key`) |
| `PORT` | variable | set by the Dockerfile to 7860 |
