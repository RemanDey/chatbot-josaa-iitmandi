import os
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash
from dotenv import load_dotenv
import requests
from twilio.twiml.messaging_response import MessagingResponse
from google import genai
from google.genai import types
import random
# Basic module-level documentation:
"""
Lightweight Flask webhook service for integrating WhatsApp/Telegram with an
external AI backend. Routes include:
 - /whatsapp : Twilio/Twilio-Proxy POST webhook (Twilio-style form fields)
 - /telegram : Telegram webhook receiver for bot mentions
 - /app      : JSON HTTP API for browser-based testing
 - /debug    : Developer debug UI (protected by a simple session login)
 - /         : Simple web UI

The `/debug` endpoint provides a password-protected developer console used
to verify frontend↔backend connectivity. It includes an interactive prompt
input that POSTs to `/app`, measures response time, stores a local request
history in the browser, computes basic timing statistics (avg/median/min/max),
and renders a response-time chart (Chart.js via CDN). Access is controlled by
session cookies; set `FLASK_SECRET_KEY` to secure sessions and `DEBUG_PASSWORD`
to change the debug password (defaults to `debugpass` for local testing).

This file intentionally keeps the runtime small and framework-agnostic so it
is easy to deploy behind a WSGI server (gunicorn/uvicorn) in production.

Security and production notes:
 - Do NOT store secrets in source control; use environment variables or a
     secrets manager provided by your cloud provider.
 - Validate and sanitize incoming webhook payloads where possible.
 - Use TLS/HTTPS in production and configure the platform’s secret verification
     (Meta webhook verify token / Telegram bot secure settings / Twilio auth).
 - The `/debug` UI is intended for local development or secured staging
     environments only. Do NOT expose `/debug` to the public internet without
     additional access controls (VPN, firewall rules, or stronger auth).
"""

# Load environment variables from a local .env file when developing locally.
# In production, runtime environment should provide these values securely.
load_dotenv()

# Configuration (read from environment in production deployments):
# - AI_BACKEND_URL: URL of the AI service used to generate responses. Required.
# - HOISTED_FRONTEND_URL: Optional front-end location for links returned to users.
# - BOT_TOKEN: Telegram bot token. Only required if using the Telegram webhook.
AI_BACKEND_URL = "https://aryanraj1092-iitmandi-bot.hf.space/api/chat"
HOISTED_FRONTEND_URL = os.getenv(
        "HOISTED_FRONTEND_URL", "https://chatbot-josaa-iitmandi.onrender.com/"
)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# Create Flask app instance. When running under gunicorn, use the module name
# target `app:app` so the WSGI server can import this object.
API_KEY_1 = os.getenv("GOOGLE_API_KEY_1")
API_KEY_2 = os.getenv("GOOGLE_API_KEY_2")
API_KEY_3 = os.getenv("GOOGLE_API_KEY_3")
API_KEY_4 = os.getenv("GOOGLE_API_KEY_4")
#API_KEY_5 = os.getenv("GOOGLE_API_KEY_5")


grounding_tool = types.Tool(
    google_search=types.GoogleSearch()
)

config = types.GenerateContentConfig(
    tools=[grounding_tool],
    system_instruction="""You are a helpful assistant for answering questions about IIT Mandi and JOSAA admissions. 
    Visit IIT Mandi official Website and Use the Google Search tool to find up-to-date information when needed, and provide clear, concise answers to user queries.
    You must adhere to these strict formatting rules:
    - Never return a dense wall of text.
    - Use bold text (**key phrase**) at the start of lines to create visual anchors.
    - Use bullet points for features/lists, and numbered lists ONLY for sequential steps.
    - Keep responses informative and pointwise, even for complex queries. If the answer is not known, say "I don't know" instead of making up information.
    
    """
)
app = Flask(__name__)

# Session / debug configuration
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me-in-prod")
DEBUG_PASSWORD = os.getenv("DEBUG_PASSWORD", "debugpass")


def _debug_is_authenticated():
    return bool(session.get("debug_auth"))


@app.route("/debug/login", methods=["GET", "POST"])
def debug_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == DEBUG_PASSWORD:
            session["debug_auth"] = True
            return redirect(url_for("debug"))
        flash("Invalid password", "error")
    return render_template("login.html")


@app.route("/debug/logout", methods=["GET"])
def debug_logout():
    session.pop("debug_auth", None)
    return redirect(url_for("debug_login"))


@app.route("/debug", methods=["GET"])
def debug():
    if not _debug_is_authenticated():
        return redirect(url_for("debug_login"))
    # The debug UI (templates/debug.html) uses the browser to POST to `/app`
    # and displays the response. This page is intentionally lightweight.
    return render_template("debug.html")

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
        return "OK", 200

    message = telegram_data.get("message")
    if not message:
        return "OK", 200

    chat_id = message.get("chat", {}).get("id")
    incoming_text = message.get("text", "")

    app.logger.info("Telegram message received from chat_id=%s", chat_id)

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
            response = requests.post(TELEGRAM_API_URL, json=payload, timeout=5)
            response.raise_for_status()
        except Exception:
            pass

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

    # Optionally, implement mention/group logic here to avoid noisy replies.
    cleaned_prompt = incoming_msg


    ai_reply = f"JOSAA-ChatBot: {generate_ai_response(cleaned_prompt)}"
    twilio_response = MessagingResponse()
    twilio_response.message(ai_reply)

    return str(twilio_response)

@app.route("/", methods=["GET"])
def index():
    """Render the web frontend."""
    return render_template("index.html")

@app.route("/about", methods=["GET"])
def about():
    """Render the about page."""
    return render_template("about.html")


def generate_ai_response(prompt):
    """Query the AI backend and return the text reply.

    Troubleshooting:
    - Verify AI_BACKEND_URL is reachable from this service.
    - If response.raise_for_status() triggers, inspect backend logs and status code.
    """
    # Quick, deterministic responses used during local development and demos.
    if prompt == "ps":
        return "Reman Loves To Solve PS:)hehe"
    if " hi " in prompt.lower() or " hello " in prompt.lower():
        return "Hello! I'm JoSAAssist, your IIT Mandi admissions assistant. How can I help you today?"
    if " reman " in prompt.lower():
        return (
            "Reman Dey, a 2nd Year Engineering Physics student at IIT Mandi, made this bot frontend and the Whatsapp and Telegram integrations."
            "He is a technology enthusiast and aspiring engineer with interests in robotics, embedded systems, artificial intelligence, and computational modeling. He has worked on projects involving ESP8266-based rover systems, ROS-controlled robots, and AI weather prediction frameworks such as GenCast."
            "Visit his portfolio at remandey.github.io/my-portfolio . "
        )

    # payload = {"query": prompt}


    # response = requests.post(AI_BACKEND_URL, json=payload)
    # processessed_reply = format_ai_response(response)
    raw_reply = generate_api_response(prompt)
    processessed_reply = format_api_response(raw_reply)
    return processessed_reply

def format_ai_response(raw_response):
    """Format the raw AI response for better readability.

    This is a placeholder for any post-processing you might want to do on the
    AI's output before sending it back to users. For example, you could add
    markdown formatting, handle special tokens, or truncate long responses.
    """
    data = raw_response.json()
    processed_response = data["answer"]
    return processed_response
def format_api_response(raw_response):
    """Format the raw API response from Google GenAI.

    This function can be used to apply any necessary transformations to the
    response text, such as markdown formatting, truncation, or handling of
    special tokens returned by the model.
    """
    # For this example, we simply return the text as-is, but you could add
    # additional formatting logic here if needed.
    clean_response = raw_response.replace("*","")
    return clean_response
def generate_api_response(prompt):
    """Generate a response for API requests from Google GenAI.

    This function can be used to centralize any logic that should apply to
    both webhook and API responses, such as logging, metrics, or special
    formatting.
    """
    key=random.choice([API_KEY_1, API_KEY_2, API_KEY_3, API_KEY_4])
    client = genai.Client(api_key=key)
    response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt,
    config=config,
    )

    return response.text
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
    app.run(host="0.0.0.0", port=port,debug=True)
