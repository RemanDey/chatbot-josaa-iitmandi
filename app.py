import os
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import requests
from twilio.twiml.messaging_response import MessagingResponse
# Load environment variables from a local .env file for development.
# In production, these values should be provided securely by the runtime environment.
load_dotenv()

# Required configuration values for Meta / WhatsApp and the AI backend.
# VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
# PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
# ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
AI_BACKEND_URL = ""
HOISTED_FRONTEND_URL = "https://chatbot-josaa-iitmandi.onrender.com/"
app = Flask(__name__)

@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    # 1. Grab the incoming message and the sender's details from Twilio's payload
    incoming_msg = request.values.get('Body', '').strip()
    sender = request.values.get('From', '')
    
    print(f"Message from {sender}: {incoming_msg}")
    
    # 2. Optional Group Logic: Only reply if the bot is explicitly mentioned
    # (Since it's in a group, you don't want it replying to *every* sentence)
    if "@bot" not in incoming_msg.lower():
        return "", 200 # Ignore the message but return a clean success status

    # Clean the trigger word out of the prompt
    cleaned_prompt = incoming_msg.lower().replace("@bot", "").strip()

    # 3. Get the AI's response
    ai_reply = f"AI Response to '{cleaned_prompt}'"  # Placeholder for actual AI response

    # 4. Use Twilio's TwiML to send the response back
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
