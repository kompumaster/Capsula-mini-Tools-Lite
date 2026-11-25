"""Оркестратор колонки VK Капсула Мини."""

from micro_agent.agent import Agent
from micro_agent.config import Config
from micro_agent.core.events import Event
from micro_agent.core.loop import Loop, Scheduler
from micro_agent.core.state import StateMachine
from micro_agent.settings import Settings

__version__ = "0.1.26"

__all__ = [
    "Agent",
    "Config",
    "Event",
    "Loop",
    "Scheduler",
    "Settings",
    "StateMachine",
    "__version__",
]
