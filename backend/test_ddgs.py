from duckduckgo_search import DDGS
with DDGS() as ddgs:
    print(list(ddgs.text("Artificial Intelligence", max_results=2)))
