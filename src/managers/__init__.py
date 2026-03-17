"""
Manager Bot Package.
Handles ticket notifications and manager replies.
"""
from .router import process_manager_update

__all__ = ["process_manager_update"]
