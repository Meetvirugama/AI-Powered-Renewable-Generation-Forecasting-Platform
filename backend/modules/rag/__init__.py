"""Regulatory RAG copilot.

Submodules are imported lazily by their consumers rather than re-exported here:
`embed` pulls in a 2.2 GB model on first use, and `backend.modules.factory`
relies on `from backend.modules.rag.copilot import RAGCopilot` raising ImportError
to fall back to the mock. Eager re-exports would defeat both.
"""
