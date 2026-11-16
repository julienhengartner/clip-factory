class FactoryError(Exception):
    """Basisklasse für erwartbare Fehler der Videofabrik."""


class NotConfiguredError(FactoryError):
    """Eine Integration ist nicht eingerichtet (fehlende Zugangsdaten/Freigaben)."""

    def __init__(self, service: str, missing: list[str]):
        self.service = service
        self.missing = missing
        super().__init__(f"{service} nicht eingerichtet – es fehlt: {', '.join(missing)}")


class PaidApiNotAllowedError(FactoryError, PermissionError):
    pass


class BudgetExceededError(FactoryError):
    pass


class PublishingNotAllowedError(FactoryError, PermissionError):
    pass


class InsufficientMaterialError(FactoryError):
    """Zu wenig verifiziertes Material für ein Video von mindestens 60 Sekunden."""


class ExternalApiError(FactoryError):
    def __init__(self, service: str, message: str, status: int | None = None, code: str | None = None):
        self.service, self.status, self.code = service, status, code
        super().__init__(f"{service}: {message}" + (f" (HTTP {status})" if status else "") + (f" [{code}]" if code else ""))
