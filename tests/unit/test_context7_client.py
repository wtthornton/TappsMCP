"""Unit tests for knowledge/context7_client.py — Context7 API client."""

from __future__ import annotations

import pytest

from tapps_mcp.knowledge.context7_client import Context7Client


class TestExtractContent:
    def test_string_data(self):
        assert Context7Client._extract_content("hello") == "hello"

    def test_dict_with_content(self):
        data = {"content": "# Docs"}
        assert Context7Client._extract_content(data) == "# Docs"

    def test_dict_with_snippets(self):
        data = {
            "snippets": [
                {"content": "Some text", "codeList": ["print('hello')"]},
                {"content": "More text"},
            ]
        }
        result = Context7Client._extract_content(data)
        assert "print('hello')" in result
        assert "Some text" in result
        assert "More text" in result

    def test_empty_dict(self):
        assert Context7Client._extract_content({}) == ""

    def test_list_data(self):
        assert Context7Client._extract_content([1, 2, 3]) == ""

    def test_none_snippets(self):
        data = {"snippets": None}
        assert Context7Client._extract_content(data) == ""

    def test_empty_snippets(self):
        data = {"snippets": []}
        assert Context7Client._extract_content(data) == ""

    def test_snippet_with_only_code(self):
        data = {"snippets": [{"codeList": ["x = 1", "y = 2"]}]}
        result = Context7Client._extract_content(data)
        assert "x = 1" in result
        assert "y = 2" in result

    def test_snippet_with_empty_code(self):
        data = {"snippets": [{"codeList": ["", "   "]}]}
        result = Context7Client._extract_content(data)
        assert result == ""

    def test_non_dict_snippet_skipped(self):
        data = {"snippets": ["not a dict", 42]}
        assert Context7Client._extract_content(data) == ""


class TestContext7ClientInit:
    def test_default_init(self):
        client = Context7Client()
        assert client._api_key is None
        assert "context7.com" in client._base_url

    def test_custom_base_url(self):
        client = Context7Client(base_url="https://custom.api.com/")
        assert client._base_url == "https://custom.api.com"

    @pytest.mark.asyncio
    async def test_close_no_client(self):
        client = Context7Client()
        await client.close()  # Should not raise
