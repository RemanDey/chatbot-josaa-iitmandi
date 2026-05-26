import requests

# 1. Define the API endpoint URL for the Hugging Face Space
url = "https://aryanraj1092-iitmandi-bot.hf.space/api/chat"

# 2. Set the headers (Include the Bearer API Key)
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer iitmandiaxyz@1092"  # Note: If they changed the API_KEY secret on HF, replace this token
}

# 3. Create the payload (must match FastAPI's ChatRequest schema: query & history)
payload = {
    "query": "number of courses offered in iit mandi?",  # Your question to the chatbot
    "history": []  # Keep empty for a new chat session
}

try:
    # 4. Send the POST request
    print("Sending query to chatbot...")
    response = requests.post(url, json=payload, headers=headers)

    # 5. Handle the response
    if response.status_code == 200:
        response_data = response.json()
        print("\n--- Answer ---")
        print(response_data.get("answer"))
        
        print("\n--- Sources Cited ---")
        sources = response_data.get("sources", [])
        if sources:
            for source in sources:
                print(f"- Index {source['index']}: {source['source']}")
        else:
            print("No sources cited.")
    else:
        print(f"\nError: Failed with status code {response.status_code}")
        print("Response detail:", response.text)

except Exception as e:
    print(f"\nAn error occurred while connecting: {e}")