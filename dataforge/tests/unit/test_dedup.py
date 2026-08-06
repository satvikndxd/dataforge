from backend.services.dedup import (
    Deduplicator,
    canonical_url,
    content_hash,
    minhash_signature,
    minhash_similarity,
)


def test_content_hash_normalizes():
    assert content_hash("Hello,  World!") == content_hash("hello world")
    assert content_hash("alpha") != content_hash("beta")


def test_canonical_url_strips_tracking():
    a = canonical_url("https://www.example.com/page/?utm_source=x&id=1")
    b = canonical_url("https://example.com/page?id=1")
    assert a == b


def test_minhash_similarity():
    words = [f"token{i}" for i in range(60)]
    text = " ".join(words)
    near_words = list(words)
    near_words[30] = "changed"          # 1 of 60 words differs -> high Jaccard
    near = " ".join(near_words)
    far = "completely different content about databases and pipelines " * 10
    assert minhash_similarity(minhash_signature(text), minhash_signature(text)) == 1.0
    assert minhash_similarity(minhash_signature(text), minhash_signature(near)) > 0.6
    assert minhash_similarity(minhash_signature(text), minhash_signature(far)) < 0.3


def test_deduplicator_layers():
    d = Deduplicator()
    base = " ".join(f"word{i}" for i in range(80))

    first = d.check_and_add("r1", base, url="https://example.com/a")
    assert not first.is_duplicate

    exact = d.check_and_add("r2", base.upper(), url="https://other.com/b")
    assert exact.is_duplicate and exact.method == "exact"

    by_url = d.check_and_add("r3", "totally different words entirely here now",
                             url="https://www.example.com/a?utm_source=feed")
    assert by_url.is_duplicate and by_url.method == "url"

    near_text = base.replace("word40", "edited")  # 1 of 80 words differs
    near = d.check_and_add("r4", near_text, url="https://x.com/c")
    assert near.is_duplicate and near.method == "near"

    fresh = d.check_and_add("r5", "an unrelated corpus about marine biology and reefs " * 8,
                            url="https://y.com/d")
    assert not fresh.is_duplicate
