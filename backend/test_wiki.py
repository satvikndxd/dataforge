import requests
import json
def wiki_search(topic, num=5):
    url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={topic}&utf8=&format=json"
    r = requests.get(url)
    return r.json()
print(json.dumps(wiki_search("Artificial Intelligence"), indent=2))
