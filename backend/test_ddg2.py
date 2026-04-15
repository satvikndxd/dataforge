import requests
from bs4 import BeautifulSoup
import urllib.parse
url = "https://html.duckduckgo.com/html/?q=recent+advancements+in+ai"
headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
resp = requests.get(url, headers=headers)
soup = BeautifulSoup(resp.text, 'html.parser')
results = []
for div in soup.find_all('div', class_='result__body'):
    title_a = div.find('a', class_='result__a')
    url_a = div.find('a', class_='result__url')
    if not title_a or not url_a: continue
    
    title = title_a.get_text(strip=True)
    href = url_a.get('href', '')
    if href.startswith('//duckduckgo.com/l/?uddg='):
        actual_url = urllib.parse.unquote(href.split('uddg=')[1].split('&')[0])
    else: actual_url = href
    
    if "duckduckgo.com" in actual_url or "bing.com/aclick" in actual_url: continue
    print(f"[{title}]({actual_url})")
