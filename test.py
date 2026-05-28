import requests

url = 'https://aryanraj1092-iitmandi-bot.hf.space/api/chat'
headers = {
    'accept': 'application/json',
    'Authorization': 'Bearer iitmandiaxyz@1092',
    'Content-Type': 'application/json'
}
data = {
    "query": "my rank is 3000 in jee advanced. what branch can i get in iit mandi?",
    "history": []
}

response = requests.post(url, headers=headers, json=data)
print(response.json()["answer"])