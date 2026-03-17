"""
Client Bot Package.
Handles communication with end-users via AI agents, RAG, and workflows.
"""
from .router import process_client_update

__all__ = ["process_client_update"]
