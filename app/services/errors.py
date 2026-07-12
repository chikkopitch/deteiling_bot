class DomainError(Exception):
    pass


class SlotUnavailableError(DomainError):
    pass


class InvalidTransitionError(DomainError):
    pass


class AccessDeniedError(DomainError):
    pass
