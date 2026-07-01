"""Reset context-local engine state between tests.

The engine keeps policy, mode, context, and trace in `contextvars`, which persist
across tests within pytest's single thread. This autouse fixture gives each test
a clean slate so one test's policy can't leak into the next."""

import pytest

from amanai import clear_context, clear_tool_policy, reset, set_mode


@pytest.fixture(autouse=True)
def _reset_engine_state():
    clear_tool_policy()
    set_mode("enforce")
    clear_context()
    reset()
    yield
    clear_tool_policy()
    set_mode("enforce")
    clear_context()
    reset()
