"""Тесты ограничителя частоты запросов."""

from app.rate_limit import RateLimiter


def test_allows_requests_under_limit() -> None:
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        allowed, _ = limiter.allow("1.1.1.1")
        assert allowed is True


def test_blocks_requests_over_limit() -> None:
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    limiter.allow("1.1.1.1")
    limiter.allow("1.1.1.1")

    allowed, retry_after = limiter.allow("1.1.1.1")
    assert allowed is False
    assert retry_after > 0


def test_limits_are_per_key() -> None:
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.allow("a")[0] is True
    assert limiter.allow("a")[0] is False
    assert limiter.allow("b")[0] is True


def test_reset_clears_history() -> None:
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    limiter.allow("a")
    limiter.reset()
    assert limiter.allow("a")[0] is True
