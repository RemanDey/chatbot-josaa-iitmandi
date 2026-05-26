# IIT MANDI JOSAA CHATBOT

A Flask-based chatbot that receives incoming messages from Twilio-proxied WhatsApp, supports optional Telegram bot mentions, and forwards prompts to an external AI backend.

## Features
- Webhook endpoint for Twilio-based WhatsApp message events (`/whatsapp`)
- Optional Telegram mention handler (`/telegram`)
- Browser-accessible `/app` endpoint for local JSON testing
- Developer debug UI at `/debug` with authenticated access, timing statistics, request history and a response-time chart
- Minimal Flask app suitable for deployment with `gunicorn`

## Requirements
- Python 3.10+
- `pip` package manager
- `requirements.txt`

## Installation

1. Create a virtual environment:
   ```bash
   python -m venv venv
   ```
2. Activate the environment:
   - Windows:
     ```powershell
     .\venv\Scripts\Activate.ps1
     ```
   - macOS / Linux:
     ```bash
     source venv/bin/activate
     ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Environment Variables

Create a `.env` file in the project root or set these variables in your deployment environment:

```env
PORT=5000
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
HOISTED_FRONTEND_URL=https://your-frontend.example.com/
# Optional / Debug UI (use only in development or behind a secure network)
FLASK_SECRET_KEY=replace-with-a-random-secret
DEBUG_PASSWORD=your_debug_password
# LLM providers (Google + fallbacks)
GOOGLE_API_KEY=your_google_key
GROQ_API_KEY=your_groq_key
CEREBRAS_API_KEY=your_cerebras_key
MISTRAL_API_KEY=your_mistral_key
# Optional model overrides
GOOGLE_MODEL=gemini-2.5-flash
GROQ_MODEL=llama-3.1-8b-instant
CEREBRAS_MODEL=gpt-oss-120b
MISTRAL_MODEL=mistral-small-latest
# Optional fallback order
FALLBACK_PROVIDER_ORDER=google,groq,cerebras,mistral
```

Notes:
- `AI_BACKEND_URL` is currently set inside `app.py`. You can move it into an environment variable if you prefer.
- `FLASK_SECRET_KEY` is used to secure session cookies for the `/debug` login. Set a long random value in production.
- LLM fallback uses providers in `FALLBACK_PROVIDER_ORDER` and skips to the next provider if one fails.

## Local Development

Run the Flask app locally:

```bash
python app.py
```

The app will listen on `http://0.0.0.0:5000` by default.

### Debug UI (`/debug`)

- Visit `http://localhost:5000/debug`. The endpoint is protected by a simple password form.
- Default password: `debugpass` (if `DEBUG_PASSWORD` is not set). Change `DEBUG_PASSWORD` before exposing the UI.
- Features of the debug page:
  - Send a prompt to the `/app` endpoint and view the JSON reply.
  - Response-time measurement (ms) for each request.
  - Local request history (stored in your browser's `localStorage`) — click an item to repopulate the prompt.
  - Statistics panel showing Requests, Average, Median, Min, and Max response times.
  - Line chart of recent response times (Chart.js is loaded from CDN).
  - "Copy curl" button to copy a ready-made curl command for reproduction.

Security note: the debug UI is intended for local development or secured staging environments only. Do not expose it to the public internet without additional protections.

### Notes for development

- Keep secrets out of source control. Use a `.env` file locally and set real
  secrets in your cloud provider's environment variables when deploying.
- If you modify `app.py` or the templates, run the app in a dedicated virtual environment to
  avoid dependency conflicts.

## Production Deployment

Use `gunicorn` to run the app in production:

```bash
gunicorn --bind 0.0.0.0:$PORT app:app
```

## Render Deployment

For Render deployment, ensure your service is configured as a Python web service and your `Start Command` is:

```bash
gunicorn --bind 0.0.0.0:$PORT app:app
```

Set the same environment variables in the Render dashboard.

## Security & Operational Notes

- Validate webhook requests when using Twilio to receive WhatsApp messages.
- Use TLS/HTTPS in production and configure your reverse proxy to handle TLS termination.
- Limit Telegram webhook access and verify incoming updates if possible.
- Monitor service health for the AI backend service.

## Integration Points

- WhatsApp/Twilio: The `/whatsapp` endpoint expects Twilio-style form data with
  `Body` and `From` fields.
- Telegram: If enabled, set `TELEGRAM_BOT_TOKEN` and configure your bot webhook
  to point to `https://<your-host>/telegram`.

## Troubleshooting

- "AI backend unavailable": check that the AI backend URL in `app.py` is reachable from the host running this app.
- Webhook not triggering: confirm the external webhook URL is reachable and your platform (Twilio or Telegram) is configured with the correct callback.
- 500-level errors: inspect application logs and only enable debug mode locally.

## Project Structure

- `app.py` - main Flask app and webhook handlers
- `requirements.txt` - Python package requirements
- `templates/index.html` - web UI template for local testing
- `templates/debug.html` - developer debug UI with timing/stats/chart
- `static/` - static assets for the frontend

## Authors
Made by Reman Dey and Aryan Raj
