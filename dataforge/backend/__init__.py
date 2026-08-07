"""DataForge V2 backend — modular monolith.

Planes:
- core:         config, security, identifiers
- db:           system of record (SQLAlchemy)
- events:       event bus (in-memory default, NATS optional)
- storage:      object store (local FS default, S3 optional)
- intelligence: embeddings, vector index, knowledge graph, LLM router
- services:     bounded-context business logic
- agents:       typed, policy-bound autonomous agents
- pipelines:    event-driven dataset pipeline engine
- workers:      task queue abstraction (local async default, Celery optional)
- api:          FastAPI /v1 control plane
"""

__version__ = "2.0.0"
