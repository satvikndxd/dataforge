from googlesearch import search
results = list(search("Artificial Intelligence advancements 2024", num_results=5, advanced=True))
for r in results:
    print(r.title, " | ", r.url)
