from enum import Enum


class ThreadStatus(str, Enum):
    ACTIVE = "active"
    WAITING_MANAGER = "waiting_manager"
    MANUAL = "manual"
    CLOSED = "closed"
