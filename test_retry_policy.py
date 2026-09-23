#!/usr/bin/env python3
"""
Fail-fast API retry policy tests -- no real API calls, mocks
generation.client.messages.create() directly.

Verifies:
  - Retryable errors (429, 5xx, network) retry with exponential backoff
    and succeed once the transient error clears.
  - Non-retryable errors (400, 401, 403) raise NonRetryableAPIError on
    the FIRST attempt -- no retry, no sleep.
  - A retryable error that never clears exhausts MAX_API_RETRIES and
    still ends in NonRetryableAPIError (a rate limit/outage that hasn't
    cleared after several backoff attempts won't clear for the next
    question either -- see generation.py's NonRetryableAPIError docstring).

Every assertion here is a hard failure (raises AssertionError), not a
caught-and-logged warning -- see STATUS.md's note on tests that must fail
loudly rather than swallowing exceptions.
"""

import unittest.mock as mock
import anthropic
import generation as g


def _api_error(cls, status_code, message):
    return cls(message, response=mock.MagicMock(status_code=status_code, headers={}), body=None)


def test_retryable_error_retries_then_succeeds():
    print("\n=== Retryable (429): retries with backoff, then succeeds ===")
    call_count = {"n": 0}

    def flaky_then_ok(**kwargs):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise _api_error(anthropic.RateLimitError, 429, "rate limited")
        return "SUCCESS"

    with mock.patch.object(g.client.messages, "create", side_effect=flaky_then_ok), \
         mock.patch("time.sleep") as mock_sleep:
        result = g._call_claude_with_retry(model="x", max_tokens=1, messages=[], system="")

    assert result == "SUCCESS", result
    assert call_count["n"] == 3, f"expected 3 calls, got {call_count['n']}"
    assert mock_sleep.call_count == 2, f"expected 2 sleeps, got {mock_sleep.call_count}"
    delays = [c.args[0] for c in mock_sleep.call_args_list]
    assert delays[1] > delays[0], f"backoff should increase: {delays}"
    print(f"  ✓ retried {call_count['n']} times, backoff delays {[round(d, 2) for d in delays]}")


def test_non_retryable_400_fails_immediately():
    print("\n=== Non-retryable (400, credit balance too low): no retry ===")
    call_count = {"n": 0}

    def always_400(**kwargs):
        call_count["n"] += 1
        raise _api_error(anthropic.BadRequestError, 400, "credit balance too low")

    with mock.patch.object(g.client.messages, "create", side_effect=always_400), \
         mock.patch("time.sleep") as mock_sleep:
        try:
            g._call_claude_with_retry(model="x", max_tokens=1, messages=[], system="")
            raise AssertionError("expected NonRetryableAPIError, got no exception")
        except g.NonRetryableAPIError as e:
            assert isinstance(e.original, anthropic.BadRequestError)

    assert call_count["n"] == 1, f"must not retry a 400, got {call_count['n']} calls"
    assert mock_sleep.call_count == 0, "must not sleep/backoff on a non-retryable error"
    print(f"  ✓ {call_count['n']} call, no sleep, raised NonRetryableAPIError wrapping BadRequestError")


def test_non_retryable_401_fails_immediately():
    print("\n=== Non-retryable (401, bad API key): no retry ===")

    def always_401(**kwargs):
        raise _api_error(anthropic.AuthenticationError, 401, "invalid x-api-key")

    with mock.patch.object(g.client.messages, "create", side_effect=always_401) as m, \
         mock.patch("time.sleep") as mock_sleep:
        try:
            g._call_claude_with_retry(model="x", max_tokens=1, messages=[], system="")
            raise AssertionError("expected NonRetryableAPIError, got no exception")
        except g.NonRetryableAPIError as e:
            assert isinstance(e.original, anthropic.AuthenticationError)

    assert m.call_count == 1, f"must not retry a 401, got {m.call_count} calls"
    assert mock_sleep.call_count == 0
    print(f"  ✓ {m.call_count} call, no sleep, raised NonRetryableAPIError wrapping AuthenticationError")


def test_non_retryable_403_fails_immediately():
    print("\n=== Non-retryable (403, permission denied): no retry ===")

    def always_403(**kwargs):
        raise _api_error(anthropic.PermissionDeniedError, 403, "permission denied")

    with mock.patch.object(g.client.messages, "create", side_effect=always_403) as m, \
         mock.patch("time.sleep") as mock_sleep:
        try:
            g._call_claude_with_retry(model="x", max_tokens=1, messages=[], system="")
            raise AssertionError("expected NonRetryableAPIError, got no exception")
        except g.NonRetryableAPIError as e:
            assert isinstance(e.original, anthropic.PermissionDeniedError)

    assert m.call_count == 1, f"must not retry a 403, got {m.call_count} calls"
    assert mock_sleep.call_count == 0
    print(f"  ✓ {m.call_count} call, no sleep, raised NonRetryableAPIError wrapping PermissionDeniedError")


def test_exhausted_retries_on_persistent_5xx_aborts():
    print("\n=== Persistent 5xx: exhausts MAX_API_RETRIES, then aborts ===")

    def always_500(**kwargs):
        raise _api_error(anthropic.InternalServerError, 500, "server error")

    with mock.patch.object(g.client.messages, "create", side_effect=always_500) as m, \
         mock.patch("time.sleep") as mock_sleep:
        try:
            g._call_claude_with_retry(model="x", max_tokens=1, messages=[], system="")
            raise AssertionError("expected NonRetryableAPIError, got no exception")
        except g.NonRetryableAPIError as e:
            assert isinstance(e.original, anthropic.InternalServerError)

    assert m.call_count == g.MAX_API_RETRIES, f"expected {g.MAX_API_RETRIES} attempts, got {m.call_count}"
    assert mock_sleep.call_count == g.MAX_API_RETRIES - 1
    print(f"  ✓ {m.call_count}/{g.MAX_API_RETRIES} attempts, then aborted with NonRetryableAPIError")


def test_generate_question_does_not_retry_nonretryable_api_error():
    print("\n=== generate_question(): NonRetryableAPIError skips the question-level retry loop ===")
    from unittest.mock import MagicMock

    gen = g.QuestionGenerator.__new__(g.QuestionGenerator)
    gen.topic = "test"
    gen.kb = MagicMock()
    archetype = MagicMock()
    archetype.marking_pattern = {"typical_total_marks": 3}
    gen.kb.get_archetype.return_value = archetype

    call_count = {"n": 0}

    def raise_nonretryable(*args, **kwargs):
        call_count["n"] += 1
        raise g.NonRetryableAPIError(RuntimeError("credit balance too low"))

    with mock.patch.object(gen, "_call_claude", side_effect=raise_nonretryable):
        try:
            gen.generate_question("some_archetype", marks=3, max_retries=3)
            raise AssertionError("expected NonRetryableAPIError to propagate")
        except g.NonRetryableAPIError:
            pass

    assert call_count["n"] == 1, (
        f"generate_question's own retry loop (max_retries=3) must NOT retry a "
        f"NonRetryableAPIError -- got {call_count['n']} calls, expected 1"
    )
    print(f"  ✓ _call_claude invoked {call_count['n']} time (not retried across generate_question's 3 attempts)")


if __name__ == "__main__":
    test_retryable_error_retries_then_succeeds()
    test_non_retryable_400_fails_immediately()
    test_non_retryable_401_fails_immediately()
    test_non_retryable_403_fails_immediately()
    test_exhausted_retries_on_persistent_5xx_aborts()
    test_generate_question_does_not_retry_nonretryable_api_error()
    print("\n✓ ALL RETRY POLICY TESTS PASSED")
