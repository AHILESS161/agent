"""Тесты ограничения частоты запросов.

Лимитер защищает вход (подбор пароля) и загрузку файлов
(исчерпание дискового пространства).
"""

from __future__ import annotations

from app.api.middleware.rate_limit import (
    DEFAULT_RULE,
    RULES,
    RateLimiter,
    Rule,
    _rule_for,
)


class TestRateLimiter:
    def test_allows_requests_within_limit(self):
        limiter = RateLimiter()
        rule = Rule(limit=3, window=60)
        for _ in range(3):
            allowed, _ = limiter.check("client-a", rule, now=100.0)
            assert allowed

    def test_blocks_request_over_limit(self):
        limiter = RateLimiter()
        rule = Rule(limit=2, window=60)
        limiter.check("client-a", rule, now=100.0)
        limiter.check("client-a", rule, now=100.0)

        allowed, retry_after = limiter.check("client-a", rule, now=100.0)
        assert not allowed
        assert retry_after > 0

    def test_window_slides_and_releases_quota(self):
        limiter = RateLimiter()
        rule = Rule(limit=1, window=60)
        limiter.check("client-a", rule, now=100.0)

        assert not limiter.check("client-a", rule, now=120.0)[0]
        # Окно прошло — квота снова доступна.
        assert limiter.check("client-a", rule, now=161.0)[0]

    def test_clients_are_counted_independently(self):
        limiter = RateLimiter()
        rule = Rule(limit=1, window=60)
        assert limiter.check("client-a", rule, now=100.0)[0]
        assert limiter.check("client-b", rule, now=100.0)[0]

    def test_retry_after_is_at_least_one_second(self):
        limiter = RateLimiter()
        rule = Rule(limit=1, window=60)
        limiter.check("k", rule, now=100.0)
        _, retry_after = limiter.check("k", rule, now=159.9)
        assert retry_after >= 1


class TestRuleSelection:
    def test_login_has_stricter_limit_than_default(self):
        assert _rule_for("/api/v1/auth/login").limit < DEFAULT_RULE.limit

    def test_registration_has_strict_limit(self):
        assert _rule_for("/api/v1/auth/register").limit <= 5

    def test_longest_matching_prefix_wins(self):
        rule = _rule_for("/api/v1/auth/login/json")
        assert rule == RULES["/api/v1/auth/login"]

    def test_unknown_path_uses_default(self):
        assert _rule_for("/api/v1/something/else") == DEFAULT_RULE
