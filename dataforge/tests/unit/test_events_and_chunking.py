from backend.events.bus import EventBus, subject_matches
from backend.events.schemas import Event
from backend.services.chunking import chunk_text


def test_subject_matching():
    assert subject_matches(">", "pipeline.started")
    assert subject_matches("pipeline.*", "pipeline.started")
    assert subject_matches("pipeline.stage.*", "pipeline.stage.completed")
    assert not subject_matches("pipeline.*", "agent.run.started")


def test_bus_fanout_and_handlers(app):
    bus = EventBus()
    seen = []
    bus.add_handler("test.*", lambda e: seen.append(e.event_type))
    sub = bus.subscribe("test.>")
    bus.emit("test.alpha", tenant_id="org_x", payload={"n": 1})
    bus.emit("other.beta", tenant_id="org_x")
    assert seen == ["test.alpha"]
    event = sub.q.get_nowait()
    assert event.event_type == "test.alpha"
    assert sub.q.empty()


def test_event_envelope_wire_format():
    e = Event(event_type="extraction.completed", tenant_id="org_1", payload={"x": 1})
    wire = e.to_wire()
    assert wire["event_type"] == "extraction.completed"
    assert wire["schema_version"] == "1.0"
    assert wire["event_id"].startswith("evt_")


def test_chunking_respects_budget_and_overlap():
    text = "\n\n".join(f"Paragraph {i}. " + ("Content sentence with several words. " * 8)
                       for i in range(20))
    chunks = chunk_text(text, target_tokens=120, overlap_tokens=10)
    assert len(chunks) > 3
    assert all(c.token_estimate <= 400 for c in chunks)
    assert [c.position for c in chunks] == list(range(len(chunks)))


def test_chunking_preserves_headings():
    text = "# Introduction\n\n" + ("Intro sentence goes here. " * 30) + \
           "\n\n# Methods\n\n" + ("Methods sentence goes here. " * 30)
    chunks = chunk_text(text, target_tokens=80)
    headings = {c.meta.get("heading") for c in chunks if c.meta.get("heading")}
    assert "Introduction" in headings or "Methods" in headings


def test_chunking_empty():
    assert chunk_text("") == []
