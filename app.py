import os
import requests
from flask import Flask, request, jsonify, render_template
from google import genai
from dotenv import load_dotenv
from google.genai import types

load_dotenv()

app = Flask(__name__)

# Environment Variables
# ACCESS_TOKEN = os.environ.get("WA_ACCESS_TOKEN")
# PHONE_NUMBER_ID = os.environ.get("WA_PHONE_NUMBER_ID")
# VERIFY_TOKEN = os.environ.get("WA_VERIFY_TOKEN")

# # Initialize LLM Client (OpenAI example)
# ai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# # QWEN model configuration (hypertuned qwen-b). If provided, the app will
# # prefer calling the QWEN endpoint using these env vars. Otherwise it falls
# # back to the existing OpenAI client.
# QWEN_API_URL = os.environ.get("QWEN_API_URL")
# QWEN_API_KEY = os.environ.get("QWEN_API_KEY")
# QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen-b-hypertuned")
client=genai.Client(api_key=os.environ.get("API"))
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Handles the initial handshake validation from Meta."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    
    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            print("Webhook verified successfully!")
            return challenge, 200
        return "Verification failed", 403
    return "Missing parameters", 400


@app.route("/", methods=["GET"])
def index():
    """Renders the web app frontend."""
    return render_template("index.html")


@app.route("/webhook", methods=["POST"])
def receive_message():
    """Handles incoming message events from users."""
    data = request.json
    
    # Drill down into the Meta JSON payload structure
    if data.get("object") == "whatsapp_business_account":
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                
                if messages:
                    message = messages[0]
                    sender_phone = message.get("from") # Customer phone number
                    
                    # Verify it's a standard text message
                    if message.get("type") == "text":
                        user_text = message["text"]["body"]
                        print(f"Received message from {sender_phone}: {user_text}")
                        
                        # 1. Generate text from AI
                        ai_reply = generate_ai_response(user_text)
                        
                        # 2. Send the reply back to the user
                        send_whatsapp_message(sender_phone, ai_reply)
                        
        return "EVENT_RECEIVED", 200
    return "Not Found", 404


def generate_ai_response(prompt):
    """Sends the user's message to an LLM for processing and returns the reply."""
    if prompt=="ps":
        return "Reman Loves To Solve PS:)hehe"
    elif "reman" in prompt.lower():
        return "Reman Dey is My Creator!!!MY GODDDDDDDDDDD!!! visit his god damn portfolio at remandey.github.io/my-portfolio . ANd he is too fond of solving his PS :)"
    else:
        response=client.models.generate_content(
            model='gemini-2.5-flash',
            config=types.GenerateContentConfig(system_instruction="You are the official IIT Mandi JosAA councillor. Your task is to provide helpful and accurate information about the JosAA program. You should answer questions related to the application process, eligibility criteria, important dates, and any other relevant information about JosAA. Always provide clear and concise responses to assist users in understanding the JosAA program better. You must have proper knowledge about the courses offered at IIT Mandi from the website https://academics.iitmandi.ac.in/degreeprograms and the admission process. If you don't know the answer to a question, it's better to say 'I don't know' rather than providing incorrect information. Always be polite and helpful in your responses.", temperature=0.7, max_output_tokens=2048),
            contents=prompt,
        )
        return response.text

@app.route("/app", methods=["POST"])
def web_app_response():
    """Handles web-hosted app requests and returns a JSON response."""
    data = request.json or {}
    prompt = data.get("prompt") or request.args.get("prompt")
    if not prompt:
        return jsonify({"error": "Missing prompt."}), 400
    #FOR DEBUGGING
    #print(prompt)
    reply = generate_ai_response(prompt)
    return jsonify({"prompt": prompt, "reply": reply})


def send_whatsapp_message(to_phone, reply_text):
    """Sends a text response via Meta's Graph API."""
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": reply_text
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()


if __name__ == "__main__":
   
    port = int(os.environ.get("PORT", 5000))
    

    app.run(host="0.0.0.0", port=port)
