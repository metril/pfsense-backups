"""Shared package used by both the worker and the web service.

Contains canonical settings, filesystem paths, DB engine/models, Fernet-based
credential encryption, and Pydantic schemas for IPC + API payloads. Both
services import from here; nothing here may import from `worker` or `web`.
"""
