class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


class ProviderError(Exception):
    """Only sanitized, application-authored messages may be placed here."""
    def __init__(self, code="X_UNAVAILABLE", status=503, definitive=False, retry_at=None):
        self.code = code
        self.status = status
        self.definitive = definitive
        self.retry_at = retry_at
        super().__init__(code)
