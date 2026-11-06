"""Lightweight NLP layer for MedOps AI.

Everything here runs offline with the standard library and has no model download,
so no ticket text leaves the hospital network. An optional LLM hook (see
`app/nlp/narrative.py`) is the only component that can call out, and only when the
operator configures it.
"""
