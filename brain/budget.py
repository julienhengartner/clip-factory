"""Kostenbremse: Jeder kostenpflichtige Aufruf muss hier vorbei.

- Ohne BBOB_ALLOW_PAID_APIS=true wird jeder Aufruf blockiert.
- Pro Tag sind höchstens `max_paid_calls_per_day` Aufrufe erlaubt.
- Jeder genehmigte Aufruf wird in api_usage protokolliert.
"""
from __future__ import annotations

from config import Settings
from core.errors import BudgetExceededError, PaidApiNotAllowedError, PublishingNotAllowedError
from brain.memory import Memory


class BudgetGuard:
    def __init__(self, settings: Settings, memory: Memory):
        self.settings = settings
        self.memory = memory

    def authorize_paid_call(self, provider: str, operation: str, units: float = 1) -> None:
        if not self.settings.allow_paid_apis:
            raise PaidApiNotAllowedError(
                f"Kostenpflichtiger Aufruf {provider}.{operation} blockiert (BBOB_ALLOW_PAID_APIS ist nicht 'true').")
        used = self.memory.paid_calls_today()
        if used >= self.settings.max_paid_calls_per_day:
            raise BudgetExceededError(
                f"Tageslimit für kostenpflichtige Aufrufe erreicht ({used}/{self.settings.max_paid_calls_per_day}).")
        self.memory.record_api_call(provider, operation, units)

    def require_publishing_allowed(self, platform: str) -> None:
        if not self.settings.allow_publishing:
            raise PublishingNotAllowedError(
                f"Veröffentlichung auf {platform} blockiert (BBOB_ALLOW_PUBLISHING ist nicht 'true').")
