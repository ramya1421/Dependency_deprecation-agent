class CircuitOpenError(Exception):
    """Raised when a request is refused because the circuit for its source is open."""

    def __init__(self, source: str) -> None:
        super().__init__(f"circuit open for source {source!r}")
        self.source = source


class OfflineCacheMissError(Exception):
    """Raised in offline mode when a request has no usable cache entry."""

    def __init__(self, url: str) -> None:
        super().__init__(f"offline mode: no cache entry for {url!r}")
        self.url = url
