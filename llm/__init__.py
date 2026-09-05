"""
llm/__init__.py
---------------
Shared exceptions for the LLM layer.
"""

from __future__ import annotations


class LLMOutputError(Exception):
    """
    Raised when the Groq API returns a response that does not match
    the expected JSON schema (missing keys, wrong types, etc.).
    """
