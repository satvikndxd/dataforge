import requests
from bs4 import BeautifulSoup
import urllib.parse
url = "https://html.duckduckgo.com/html/?q=recent+advancements+in+ai"
headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36"}
resp = requests.get(url, headers=headers)
soup = BeautifulSoup(resp.text, 'html.parser')
# duckduckgo's html page uses a.result__url for URLs
results = []
for a in soup.find_all('a', class_='result__url'):
    href = a.get('href', '')
    if href.startswith('//duckduckgo.com/l/?uddg='):
        actual_url = urllib.parse.unquote(href.split('uddg=')[1].split('&')[0])
        results.append(actual_url)
print(results)
