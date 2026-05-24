# IIT MANDI JOSAA CHATBOT

A Flask-based chatbot that forwards user text to an AI backend and returns replies using Meta's WhatsApp Business API.

## Features
- Webhook endpoint for WhatsApp message events
- AI response generation via an external backend API
- Browser-accessible `/app` endpoint for local testing
- Production-ready configuration with environment variables
- Deployment support via `gunicorn`

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
VERIFY_TOKEN=your_meta_webhook_verify_token
PHONE_NUMBER_ID=your_whatsapp_phone_number_id
ACCESS_TOKEN=your_meta_graph_api_access_token
AI_BACKEND_URL=http://127.0.0.1:8000/api/chat
PORT=5000

# Optional / Integration variables
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
HOISTED_FRONTEND_URL=https://your-frontend.example.com/
```

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

- Validate webhook requests:
   - For Twilio: validate the Twilio signature on incoming requests.
   - For Telegram: limit the webhook endpoint to Telegram IP ranges or verify
      requests when possible.
- Use TLS/HTTPS in production and configure your WAF or reverse proxy to
   handle TLS termination.
- Monitor logs and configure health checks for the AI backend service.

## Integration Points

- WhatsApp (Meta): The webhook handler expects to receive messages via Twilio
   or your chosen WhatsApp integration. Ensure your `ACCESS_TOKEN` and
   `PHONE_NUMBER_ID` are set and valid.
- Telegram: If you enable Telegram handling, set `TELEGRAM_BOT_TOKEN` and
   configure your bot's webhook to point to `https://<your-host>/telegram`.

## Troubleshooting

- "AI backend unavailable": check that `AI_BACKEND_URL` is configured and the
   backend is reachable from the host running this app.
- Webhook not triggering: confirm external webhook URL is reachable and your
   platform (Twilio/Meta/Telegram) is configured with the correct callback.
- 500-level errors: inspect the container logs for tracebacks and enable
   DEBUG only in local development.

## Debugging and Troubleshooting

- Check webhook verification by ensuring `VERIFY_TOKEN` matches the Meta webhook setup.
- Confirm `PHONE_NUMBER_ID` and `ACCESS_TOKEN` are valid for the WhatsApp Business account.
- Verify the AI backend at `AI_BACKEND_URL` is reachable and responding correctly.
- Inspect logs for non-200 responses from Meta Graph API and from the AI backend.

## Project Structure

- `app.py` - main Flask app and webhook handlers
- `requirements.txt` - Python package requirements
- `templates/index.html` - web UI template for local testing
- `static/` - static assets for the frontend

## Notes

This repository also includes a `rag-backend/` folder with a separate RAG backend implementation and its own `requirements.txt`.
