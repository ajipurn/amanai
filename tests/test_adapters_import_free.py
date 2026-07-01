"""Zero-dependency guard (spec 0001): the SDK and adapters import with no framework
installed, and framework adapters raise a helpful ImportError when their framework
is missing. This runs in the CI env, which has no langchain/crewai installed."""

import importlib

import pytest


def test_core_and_adapter_imports_need_no_framework():
    for mod in ("amanai", "amanai.adapters", "amanai.adapters.openai"):
        assert importlib.import_module(mod) is not None


def test_guard_mcp_call_is_the_generalized_funnel():
    from amanai import guard_mcp_call, guard_tool_call

    assert guard_mcp_call is guard_tool_call


def _langchain_installed():
    return importlib.util.find_spec("langchain_core") is not None


def _crewai_installed():
    return importlib.util.find_spec("crewai") is not None


@pytest.mark.skipif(_langchain_installed(), reason="langchain-core is installed")
def test_langchain_adapter_raises_helpful_import_error():
    from amanai.adapters.langchain import guard_langchain_tool

    with pytest.raises(ImportError) as e:
        guard_langchain_tool(object())
    assert "langchain-core" in str(e.value)


@pytest.mark.skipif(_crewai_installed(), reason="crewai is installed")
def test_crewai_adapter_raises_helpful_import_error():
    from amanai.adapters.crewai import guard_crewai_tool

    with pytest.raises(ImportError) as e:
        guard_crewai_tool(object())
    assert "crewai" in str(e.value)
