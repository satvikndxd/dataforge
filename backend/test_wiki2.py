import requests
import json
def wiki_search(topic, num=5):
    url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={topic}&utf8=&format=json"
    headers = {"User-Agent": "DataForgeBot/1.0"}
    r = requests.get(url, headers=headers)
    return r.json()
print(json.dumps(wiki_search("Artificial Intelligence"), indent=2)[:500])
