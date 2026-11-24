from global_library_mcp.web.server import RateLimiter


def test_rate_limiter_allows_up_to_limit_then_blocks():
    limiter = RateLimiter(limit_per_minute=3)
    assert [limiter.allow("10.0.0.1") for _ in range(3)] == [True, True, True]
    assert limiter.allow("10.0.0.1") is False
    assert limiter.allow("10.0.0.2") is True


def test_rate_limiter_window_expires():
    limiter = RateLimiter(limit_per_minute=1)
    clock = {"now": 1000.0}
    limiter._now = lambda: clock["now"]
    assert limiter.allow("10.0.0.1") is True
    assert limiter.allow("10.0.0.1") is False
    clock["now"] += 61.0
    assert limiter.allow("10.0.0.1") is True
