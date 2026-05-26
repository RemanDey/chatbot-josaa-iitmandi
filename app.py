import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Callable

from cache import get_cached, set_cached
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
import requests
from twilio.twiml.messaging_response import MessagingResponse
from google import genai
from google.genai import types
import random
import hardcoded_responses
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
# - AI_BACKEND_URL: Aryan RAG backend URL used as grounded context for Gemini.
# - HOISTED_FRONTEND_URL: Optional front-end location for links returned to users.
# - BOT_TOKEN: Telegram bot token. Only required if using the Telegram webhook.
AI_BACKEND_URL = os.getenv(
    "AI_BACKEND_URL", "https://aryanraj1092-iitmandi-bot.hf.space/api/chat"
)
HOISTED_FRONTEND_URL = os.getenv(
        "HOISTED_FRONTEND_URL", "https://chatbot-josaa-iitmandi.onrender.com/"
)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN","remandey")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# Create Flask app instance. When running under gunicorn, use the module name
# target `app:app` so the WSGI server can import this object.
API_KEY_1 = os.getenv("GOOGLE_API_KEY_1","reman_dey")
API_KEY_2 = os.getenv("GOOGLE_API_KEY_2","remn_dey_2")
API_KEY_3 = os.getenv("GOOGLE_API_KEY_3","remn_dey_3")
API_KEY_4 = os.getenv("GOOGLE_API_KEY_4","remn_dey_4")
API_KEY_FALLBACK = os.getenv("GOOGLE_API_KEY","remn_dey_fallback")
GROQ_API_KEY = os.getenv("GROQ_API_KEY","remn_groq")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY","remn_mistral")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY","remn_cerebras")
GOOGLE_MODEL = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")
FALLBACK_PROVIDER_ORDER = os.getenv(
    "FALLBACK_PROVIDER_ORDER", "google,groq,cerebras,mistral"
)
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

# Default IP-based limits protect public web/debug-adjacent traffic from bursts
# while keeping the backend dependency-free for Render's simple deployment model.
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per hour"],
    storage_uri="memory://",
)

# Cap concurrent Gemini waits so slow upstream calls cannot exhaust the gevent
# worker indefinitely; requests get a graceful fallback after 30 seconds.
GENAI_TIMEOUT_SECONDS = 30
RAG_TIMEOUT_SECONDS = 15
CHAT_COMPLETIONS_TIMEOUT_SECONDS = 20
GENAI_TIMEOUT_REPLY = "I'm taking too long to respond right now. Please try again in a moment."
GENAI_ERROR_REPLY = "Something went wrong. Please try again."
_executor = ThreadPoolExecutor(max_workers=10)


def _whatsapp_sender_key():
    # Limit by WhatsApp sender so one noisy number cannot consume every IP quota.
    return request.values.get("From") or get_remote_address()


def _telegram_chat_key():
    # Limit by Telegram chat_id because many webhook calls can share one proxy IP.
    telegram_data = request.get_json(silent=True) or {}
    chat_id = telegram_data.get("message", {}).get("chat", {}).get("id")
    return str(chat_id or get_remote_address())


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
@limiter.limit("10 per minute", key_func=_telegram_chat_key)
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

        # Reuse the same AI path as web/WhatsApp so Telegram gets caching,
        # timeout handling, and consistent JoSAA answers.
        ai_reply = generate_ai_response(cleaned_prompt)

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
@limiter.limit("10 per minute", key_func=_whatsapp_sender_key)
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


@app.route("/health", methods=["GET"])
def health():
    """Return a minimal probe response for Render/load balancer health checks."""
    return jsonify({"status": "ok", "timestamp": int(time.time())}), 200


def generate_ai_response(prompt):
    """Query the AI backend and return the text reply.

    Troubleshooting:
    - Verify AI_BACKEND_URL is reachable from this service.
    - If response.raise_for_status() triggers, inspect backend logs and status code.
    """
    # Quick, deterministic responses used during local development and demos.
    normalized_prompt = re.sub(r"[^a-z0-9\s]", " ", prompt.lower())
    prompt_words = normalized_prompt.split()
    chat_word_map = {
        "r": "are",
        "u": "you",
        "ur": "your",
        "urs": "yours",
        "ya": "you",
        "ge": "btech in general engineering",
        "ep": "btech in engineering physics",
        "ee": "btech in electrical engineering",
        "cse": "btech in computer science and engineering",
        "mnc": "btech in mathematics and computing",
        "vlsi": "btech in microelectronics and vlsi",
        "ce": "btech in civil engineering",
        "mse": "btech in material science and engineering"
    }
    normalized_words = [chat_word_map.get(word, word) for word in prompt_words]
    normalized_prompt = " ".join(normalized_words)
    prompt_word_count = len(normalized_words)

    identity_exact = {
        "who are you",
        "who r you",
        "what are you",
        "what is your name",
        "what s your name",
        "whats your name",
        "what is you name",
        "whats you name",
        "tell me about yourself",
        "introduce yourself",
        "what should i call you",
    }
    identity_contains = {
        "your name",
        "about yourself",
        "are you gemini",
        "are you google",
        "built by google",
        "trained by google",
        "who made you",
    }
    if (
        normalized_prompt in identity_exact
        or (
            prompt_word_count <= 12
            and any(phrase in normalized_prompt for phrase in identity_contains)
        )
    ):
        return "I am chat bot JoSAAssist for IIT Mandi JosAA Counselling."

    if prompt == "ps":
        return "Reman Loves To Solve PS:)hehe"
    if " hi " in prompt.lower() or " hello " in prompt.lower():
        return "Hello! I'm JoSAAssist, your IIT Mandi admissions assistant. How can I help you today?"
    if " reman " in prompt.lower() or prompt.lower().startswith("reman") or prompt.lower().endswith("reman"):
        return (
            "Reman Dey, a 2nd Year Engineering Physics student at IIT Mandi, made this bot frontend and the Whatsapp and Telegram integrations."
            "He is a technology enthusiast and aspiring engineer with interests in robotics, embedded systems, artificial intelligence, and computational modeling." 
            "He has worked on projects involving ESP8266-based rover systems, ROS-controlled robots, and AI weather prediction frameworks such as GenCast."
            "Visit his portfolio at remandey.github.io/my-portfolio . "
        )

    # Cache after deterministic shortcuts so repeated admissions questions reuse
    # a processed answer without changing demo/debug special cases.
    cached_reply = get_cached(prompt)
    if cached_reply is not None:
        return cached_reply
    #generating hardcodede responses
    hardcoded_router = hardcoded_responses.hardcoded_responses("triggers.json")
    hardcoded_reply, bypassed = hardcoded_router.process_prompt(prompt)
    if bypassed:
        return format_api_response(hardcoded_reply)
    # payload = {"query": prompt}


    # response = requests.post(AI_BACKEND_URL, json=payload)
    # processessed_reply = format_ai_response(response)
    raw_reply = generate_api_response(prompt)
    processessed_reply = format_api_response(raw_reply)
    # Avoid caching transient upstream failures, otherwise a single timeout could
    # serve the same apology for a common question for the full one-hour TTL.
    if processessed_reply not in {GENAI_TIMEOUT_REPLY, GENAI_ERROR_REPLY}:
        set_cached(prompt, processessed_reply)
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


def _call_aryan_rag(prompt):
    # Aryan's RAG backend supplies JoSAA-specific context; Gemini then blends it
    # with search-grounded reasoning into one answer instead of competing replies.
    response = requests.post(
        AI_BACKEND_URL,
        json={"query": prompt},
        timeout=RAG_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return format_ai_response(response)


def _build_combined_prompt(prompt):
    """Build a single prompt with optional RAG context."""
    rag_answer = ""
    try:
        rag_answer = _call_aryan_rag(prompt)
    except Exception as e:
        app.logger.warning("Aryan RAG backend unavailable: %s", e)

    if rag_answer:
        combined_prompt = (
            "User question:\n"
            f"{prompt}\n\n"
            "Aryan RAG answer/context:\n"
            f"{rag_answer}\n\n"
            "Create one combined JoSAAssist answer. Use Aryan RAG as grounded "
            "admissions context, use Google Search when fresher official IIT "
            "Mandi or JoSAA information is needed, resolve conflicts clearly, "
            "and keep the response concise and pointwise."
        )
    return combined_prompt if rag_answer else prompt


def _extract_chat_completion_text(data):
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("No choices in provider response")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        for chunk in content:
            if isinstance(chunk, dict) and isinstance(chunk.get("text"), str):
                text_parts.append(chunk["text"])
        if text_parts:
            return "\n".join(text_parts)

    raise RuntimeError("Provider response did not include textual content")


def _call_google_genai(combined_prompt):
    available_keys = [
        k for k in [API_KEY_1, API_KEY_2, API_KEY_3, API_KEY_4, API_KEY_FALLBACK] if k
    ]
    if not available_keys:
        raise RuntimeError("Missing GOOGLE_API_KEY / GOOGLE_API_KEY_1..4")

    key = random.choice(available_keys)
    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model=GOOGLE_MODEL,
        contents=combined_prompt,
        config=config,
    )
    return response.text or ""


def _call_openai_compatible_chat(*, endpoint, api_key, model, combined_prompt):
    if not api_key:
        raise RuntimeError("Missing API key")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": config.system_instruction},
            {"role": "user", "content": combined_prompt},
        ],
        "temperature": 0.2,
    }
    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=CHAT_COMPLETIONS_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _extract_chat_completion_text(response.json())


def _call_groq(combined_prompt):
    return _call_openai_compatible_chat(
        endpoint="https://api.groq.com/openai/v1/chat/completions",
        api_key=GROQ_API_KEY,
        model=GROQ_MODEL,
        combined_prompt=combined_prompt,
    )


def _call_cerebras(combined_prompt):
    return _call_openai_compatible_chat(
        endpoint="https://api.cerebras.ai/v1/chat/completions",
        api_key=CEREBRAS_API_KEY,
        model=CEREBRAS_MODEL,
        combined_prompt=combined_prompt,
    )


def _call_mistral(combined_prompt):
    return _call_openai_compatible_chat(
        endpoint="https://api.mistral.ai/v1/chat/completions",
        api_key=MISTRAL_API_KEY,
        model=MISTRAL_MODEL,
        combined_prompt=combined_prompt,
    )


def _available_provider_callables():
    provider_map: dict[str, Callable[[str], str]] = {
        "google": _call_google_genai,
        "groq": _call_groq,
        "cerebras": _call_cerebras,
        "mistral": _call_mistral,
    }
    return provider_map


def _provider_chain():
    provider_map = _available_provider_callables()
    providers = []
    for name in [p.strip().lower() for p in FALLBACK_PROVIDER_ORDER.split(",") if p.strip()]:
        if name in provider_map and name not in providers:
            providers.append(name)
    if not providers:
        providers = ["google", "groq", "cerebras", "mistral"]
    return providers


def _call_with_provider_fallback(prompt):
    combined_prompt = _build_combined_prompt(prompt)
    providers = _provider_chain()
    provider_map = _available_provider_callables()
    errors = []

    for provider in providers:
        try:
            reply = provider_map[provider](combined_prompt).strip()
            if reply:
                app.logger.info("LLM provider success: %s", provider)
                return reply
            raise RuntimeError("Empty response text")
        except Exception as e:
            errors.append(f"{provider}: {e}")
            app.logger.warning("LLM provider failed (%s): %s", provider, e)

    raise RuntimeError("All providers failed -> " + " | ".join(errors))


def generate_api_response(prompt):
    """Generate a response for API requests from Google GenAI.

    This function can be used to centralize any logic that should apply to
    both webhook and API responses, such as logging, metrics, or special
    formatting.
    """
    # Keep external LLM calls in a worker thread so we can enforce a hard timeout.
    future = _executor.submit(_call_with_provider_fallback, prompt)
    try:
        return future.result(timeout=GENAI_TIMEOUT_SECONDS)
    except FuturesTimeout:
        future.cancel()
        app.logger.warning("LLM timeout after %s seconds", GENAI_TIMEOUT_SECONDS)
        return GENAI_TIMEOUT_REPLY
    except Exception as e:
        app.logger.error("LLM error: %s", e)
        return GENAI_ERROR_REPLY

@app.route("/app", methods=["POST"])
@limiter.limit("20 per minute")
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
