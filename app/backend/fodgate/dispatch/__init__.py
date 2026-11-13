"""Dispatch: the always-on agent that hands work to a roster of people and takes their Reports back.

spec/dispatch.md is the specification. The split that keeps the hard rules intact:
- `dispatcher.py`, `tasks.py`, `timers.py`, `roster.py`: ordinary code. Routing, timers, Escalation, the HOLD alert.
- `agent.py`: the Haiku tool loop. It can route and write text. It has no tool that records a Confirmation.
- `commands.py`: the only module that calls the Workflow's Confirmation methods, always as the signed-in person.
"""
from .dispatcher import Dispatcher

__all__ = ["Dispatcher"]
