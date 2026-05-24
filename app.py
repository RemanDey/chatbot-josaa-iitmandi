import os
import logging
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import requests
from twilio.twiml.messaging_response import MessagingResponse

# Basic module-level documentation:
"""
Lightweight Flask webhook service for integrating WhatsApp/Telegram with an
external AI backend. Routes include:
 - /whatsapp : Twilio/Twilio-Proxy POST webhook (Twilio-style form fields)
 - /telegram : Telegram webhook receiver for bot mentions
 - /app      : JSON HTTP API for browser-based testing
 - /         : Simple web UI

This file intentionally keeps the runtime small and framework-agnostic so it
is easy to deploy behind a WSGI server (gunicorn/uvicorn) in production.

Security and production notes:
 - Do NOT store secrets in source control; use environment variables or a
     secrets manager provided by your cloud provider.
 - Validate and sanitize incoming webhook payloads where possible.
 - Use TLS/HTTPS in production and configure the platform’s secret verification
     (Meta webhook verify token / Telegram bot secure settings / Twilio auth).
"""

# Initialize basic logging so container logs include useful information.
logging.basicConfig(level=logging.INFO)

# Load environment variables from a local .env file when developing locally.
# In production, runtime environment should provide these values securely.
load_dotenv()

# Configuration (read from environment in production deployments):
# - AI_BACKEND_URL: URL of the AI service used to generate responses. Required.
# - HOISTED_FRONTEND_URL: Optional front-end location for links returned to users.
# - BOT_TOKEN: Telegram bot token. Only required if using the Telegram webhook.
AI_BACKEND_URL = os.getenv("AI_BACKEND_URL", "")
HOISTED_FRONTEND_URL = os.getenv(
        "HOISTED_FRONTEND_URL", "https://chatbot-josaa-iitmandi.onrender.com/"
)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# Create Flask app instance. When running under gunicorn, use the module name
# target `app:app` so the WSGI server can import this object.
app = Flask(__name__)
@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    """Receive Telegram webhook POSTs from the Bot API.

    Expected payload: standard Telegram update containing `message` and `text`.
    This handler only replies when the bot is explicitly mentioned to avoid
    noisy replies in group chats. Replace the hard-coded mention with your bot
    username or implement a more robust mention check.
    """

    telegram_data = request.get_json(silent=True) or {}

    # Basic defensive checks to avoid KeyError on malformed payloads.
    if not telegram_data:
        logging.debug("telegram_webhook: empty payload")
        return "OK", 200

    message = telegram_data.get("message")
    if not message:
        logging.debug("telegram_webhook: non-message update received")
        return "OK", 200

    chat_id = message.get("chat", {}).get("id")
    incoming_text = message.get("text", "")

    logging.info("Received Telegram message from %s: %s", chat_id, incoming_text)

    # Trigger Condition: only reply if the bot is @-mentioned. This prevents
    # the bot from replying to every message in a group.
    if "@josaa_iitmandi_bot" in incoming_text:
        cleaned_prompt = incoming_text.replace("@josaa_iitmandi_bot", "").strip()

        # TODO: replace placeholder reply with the real AI call (generate_ai_response)
        ai_reply = f"Reman and Aryan's hehe  Response to '{cleaned_prompt}'"

        payload = {
            "chat_id": chat_id,
            "text": ai_reply,
            # Reply to the same message to keep context in group chats
            "reply_to_message_id": message.get("message_id"),
        }

        # Fire-and-forget: we don't fail the webhook if Telegram call fails,
        # but in production you may want to check the response and retry.
        try:
            requests.post(TELEGRAM_API_URL, json=payload, timeout=5)
        except Exception:
            logging.exception("Failed to send reply to Telegram")

    return "OK", 200

@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    """Handle incoming messages forwarded via Twilio's webhook.

    Twilio will POST form-encoded values such as `Body` and `From`. This
    endpoint builds a TwiML response to return text messages back through
    Twilio. In production, validate Twilio signatures to ensure requests are
    authentic: https://www.twilio.com/docs/usage/security.
    """

    incoming_msg = request.values.get("Body", "").strip()
    sender = request.values.get("From", "")

    logging.info("Message from %s: %s", sender, incoming_msg)

    # Optionally, implement mention/group logic here to avoid noisy replies.
    cleaned_prompt = incoming_msg

    # TODO: integrate with AI backend. Currently returns a placeholder reply.
    ai_reply = f"Reman and Aryan's hehe  Response to '{cleaned_prompt}'"

    twilio_response = MessagingResponse()
    twilio_response.message(ai_reply)

    return str(twilio_response)

@app.route("/", methods=["GET"])
def index():
    """Render the web frontend."""
    return render_template("index.html")



def generate_ai_response(prompt):
    """Query the AI backend and return the text reply.

    Troubleshooting:
    - Verify AI_BACKEND_URL is reachable from this service.
    - If response.raise_for_status() triggers, inspect backend logs and status code.
    """
    # Quick, deterministic responses used during local development and demos.
    if prompt == "ps":
        return "Reman Loves To Solve PS:)hehe"

    if "reman" in prompt.lower():
        return (
            "Reman Dey is My Creator!!!MY GODDDDDDDDDDD!!! "
            "visit his portfolio at remandey.github.io/my-portfolio . "
            "ANd he is too fond of solving his PS :)"
        )

    # In production ensure `AI_BACKEND_URL` is set. Failing early with a clear
    # error message helps debugging in container logs.
    if not AI_BACKEND_URL:
        logging.error("AI_BACKEND_URL is not configured")
        return "AI backend unavailable"

    payload = {"query": prompt}
    try:
        response = requests.post(AI_BACKEND_URL, json=payload, timeout=8)
        response.raise_for_status()
        return response.text
    except requests.RequestException:
        logging.exception("Error contacting AI backend")
        return "Sorry, I couldn't get a response from the AI service."


@app.route("/app", methods=["POST"])
def web_app_response():
    """Return a JSON response for browser-based requests.

    Troubleshooting:
    - Ensure requests include a JSON body with the prompt key.
    - If prompt is missing, check the front-end form or AJAX payload.
    """
    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt") or request.args.get("prompt")

    if not prompt:
        return jsonify({"error": "Missing prompt."}), 400

    reply = generate_ai_response(prompt)
    return jsonify({"prompt": prompt, "reply": reply})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
