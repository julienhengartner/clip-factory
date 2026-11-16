"""Gemeinsame Basis aller Agenten.

Jeder Agent bekommt denselben AgentContext (Einstellungen, Gedächtnis, Kostenbremse, HTTP-Client,
Token-Speicher) und kommuniziert ausschliesslich über klar typisierte Methoden mit dem Brain Agent.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from brain.budget import BudgetGuard
from brain.memory import Memory
from config import Settings
from core.logging import get_logger
from integrations.token_store import TokenStore


@dataclass
class AgentContext:
    settings: Settings
    memory: Memory
    budget: BudgetGuard
    http: httpx.Client
    tokens: TokenStore


class Agent:
    name = "agent"

    def __init__(self, ctx: AgentContext):
        self.ctx = ctx
        self.s = ctx.settings
        self.memory = ctx.memory
        self.log = get_logger(self.name)

    def event(self, level: str, message: str, video_id: str | None = None) -> None:
        self.memory.log(level, self.name, message, video_id=video_id)
        getattr(self.log, "warning" if level == "warning" else "error" if level == "error" else "info")(message)
