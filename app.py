import os
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import requests

# Load environment variables from a local .env file for development.
# In production, these values should be provided securely by the runtime environment.
load_dotenv()

# Required configuration values for Meta / WhatsApp and the AI backend.
# VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
# PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
# ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
AI_BACKEND_URL ="https://chatbot-josaa-backend-api.onrender.com/api/chat"

app = Flask(__name__)

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Handle Meta webhook verification requests.

    Meta sends a GET request to confirm the webhook endpoint. The callback
    should return the provided challenge only when the verify token is valid.

    Troubleshooting:
    - If verification fails, confirm VERIFY_TOKEN matches Meta's webhook config.
    - If request lacks hub.mode or hub.challenge, check the Meta callback URL.
    """
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode and token and mode == "subscribe":
        if token == VERIFY_TOKEN:
            return challenge, 200
        return "Verification failed", 403

    return "Missing parameters", 400


@app.route("/", methods=["GET"])
def index():
    """Render the web frontend."""
    return render_template("index.html")


@app.route("/webhook", methods=["POST"])
def receive_message():
    """Handle incoming WhatsApp events and reply to user text messages.

    Troubleshooting:
    - Confirm the incoming payload is from a valid WhatsApp business account.
    - If no response is sent, inspect whether messages is empty or message type != text.
    - Log the raw webhook body in production for debugging delivery issues.
    """
    data = request.get_json(silent=True) or {}

    if data.get("object") != "whatsapp_business_account":
        return "Not Found", 404

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])

            if not messages:
                continue

            message = messages[0]
            sender_phone = message.get("from")

            if message.get("type") != "text":
                continue

            user_text = message["text"]["body"]

            # Generate the AI response and send it back over WhatsApp.
            ai_reply = generate_ai_response(user_text)
            send_whatsapp_message(sender_phone, ai_reply)

    return "EVENT_RECEIVED", 200


def generate_ai_response(prompt):
    """Query the AI backend and return the text reply.

    Troubleshooting:
    - Verify AI_BACKEND_URL is reachable from this service.
    - If response.raise_for_status() triggers, inspect backend logs and status code.
    """
    if prompt == "ps":
        return "Reman Loves To Solve PS:)hehe"

    if "reman" in prompt.lower():
        return (
            "Reman Dey is My Creator!!!MY GODDDDDDDDDDD!!! "
            "visit his god damn portfolio at remandey.github.io/my-portfolio . "
            "ANd he is too fond of solving his PS :)"
        )

    payload = {"query": prompt}
    response = requests.post(AI_BACKEND_URL, json=payload)
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


def send_whatsapp_message(to_phone, reply_text):
    """Send a WhatsApp text message through Meta Graph API.

    Troubleshooting:
    - Verify PHONE_NUMBER_ID and ACCESS_TOKEN are set and valid.
    - If Graph API returns an error, inspect the JSON response and API permissions.
    - If messages are not delivered, confirm WhatsApp business account configuration.
    """
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "text",
        "text": {"preview_url": False, "body": reply_text},
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
