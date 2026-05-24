# IIT MANDI JOSAA CHATBOT

A Flask-based chatbot that receives incoming messages from Twilio-proxied WhatsApp, supports optional Telegram bot mentions, and forwards prompts to an external AI backend.

## Features
- Webhook endpoint for Twilio-based WhatsApp message events (`/whatsapp`)
- Optional Telegram mention handler (`/telegram`)
- Browser-accessible `/app` endpoint for local JSON testing
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
```

Note: `AI_BACKEND_URL` is currently configured directly in `app.py`.

## Local Development

Run the Flask app locally:

```bash
python app.py
```

The app will listen on `http://0.0.0.0:5000` by default.

### Notes for development

- Keep secrets out of source control. Use a `.env` file locally and set real
  secrets in your cloud provider's environment variables when deploying.
- If you modify `app.py`, run the app in a dedicated virtual environment to
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
- `static/` - static assets for the frontend

## Authors
Made by Reman Dey and Aryan Raj
