"""Tests for the GitHub management agent.

Focus areas:
- input validation (repository URLs, usernames),
- ``_github_request`` error mapping (timeout, network failure, rate limit,
  auth failure, not found, malformed payloads),
- action behaviour with mocked HTTP responses,
- the protocol handler: invalid actions and unexpected exceptions must
  produce an ERROR-type response and never raise.

All HTTP traffic is intercepted by monkeypatching ``main.SESSION.request``;
no real network calls are performed.
"""

import asyncio
import html
import types

import pytest
import requests

import main
from main import (
    INVALID_ACTION_TEMPLATE,
    GitHubRepoRequest,
    REQUEST_TIMEOUT_SECONDS,
    compare_repositories,
    create_issue,
    get_readme,
    get_repo_details,
    get_user_info,
    handle_github_repo_request,
    list_issues,
    parse_repo_full_name,
    validate_username,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeResponse:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(self, status_code=200, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.content = text.encode() if text else (b"{}" if json_data is not None else b"")
        self.headers = headers or {}

    def json(self):
        if self._json_data is None:
            raise ValueError("No JSON could be decoded")
        return self._json_data


class FakeContext:
    """Captures outgoing messages instead of sending them over the network."""

    def __init__(self):
        self.sent = []
        self.logger = types.SimpleNamespace(
            info=lambda *a, **k: None,
            error=lambda *a, **k: None,
        )

    async def send(self, recipient, message):
        self.sent.append((recipient, message))


def mock_http(monkeypatch, responder):
    """Route every request through ``responder(method, url, **kwargs)``."""

    def fake_request(method, url, **kwargs):
        return responder(method, url, **kwargs)

    monkeypatch.setattr(main.SESSION, "request", fake_request)


def run_handler(msg):
    """Run the async protocol handler and return the sent UAgentResponse."""
    ctx = FakeContext()
    sender = "agent://sender"
    asyncio.run(handle_github_repo_request(ctx, sender, msg))
    assert len(ctx.sent) == 1, "handler must send exactly one response"
    recipient, response = ctx.sent[0]
    assert recipient == sender
    return response


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestParseRepoFullName:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("https://github.com/octocat/Hello-World", "octocat/Hello-World"),
            ("github.com/octocat/Hello-World.git", "octocat/Hello-World"),
            ("https://github.com/octocat/Hello-World/", "octocat/Hello-World"),
            ("owner/repo", "owner/repo"),
            ("  owner/repo  ", "owner/repo"),
            ("owner_name/repo.name", "owner_name/repo.name"),
        ],
    )
    def test_valid_inputs(self, raw, expected):
        assert parse_repo_full_name(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        ["", "   ", None, "just-a-name", "https://github.com/onlyowner/"],
    )
    def test_invalid_inputs(self, raw):
        with pytest.raises(ValueError):
            parse_repo_full_name(raw)

    def test_invalid_input_message_is_actionable(self):
        with pytest.raises(ValueError) as excinfo:
            parse_repo_full_name("notaurl")
        assert "owner/repo" in str(excinfo.value)


class TestValidateUsername:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("octocat", "octocat"),
            ("https://github.com/octocat", "octocat"),
            ("https://github.com/octocat/", "octocat"),
        ],
    )
    def test_valid_inputs(self, raw, expected):
        assert validate_username(raw) == expected

    @pytest.mark.parametrize("raw", ["", "   ", None, "-badstart", "double--hyphen"])
    def test_invalid_inputs(self, raw):
        with pytest.raises(ValueError):
            validate_username(raw)


# ---------------------------------------------------------------------------
# _github_request error mapping
# ---------------------------------------------------------------------------


class TestGithubRequest:
    def test_success_returns_parsed_json(self, monkeypatch):
        mock_http(
            monkeypatch,
            lambda m, u, **k: FakeResponse(200, {"full_name": "a/b"}),
        )
        ok, payload = main._github_request("GET", "https://api.github.com/x")
        assert ok is True
        assert payload == {"full_name": "a/b"}

    def test_timeout(self, monkeypatch):
        def responder(method, url, **kwargs):
            raise requests.exceptions.Timeout()

        mock_http(monkeypatch, responder)
        ok, payload = main._github_request("GET", "https://api.github.com/x")
        assert ok is False
        assert f"did not respond within {REQUEST_TIMEOUT_SECONDS} seconds" in payload

    def test_network_failure(self, monkeypatch):
        def responder(method, url, **kwargs):
            raise requests.exceptions.ConnectionError("boom")

        mock_http(monkeypatch, responder)
        ok, payload = main._github_request("GET", "https://api.github.com/x")
        assert ok is False
        assert "Could not reach the GitHub API" in payload

    def test_rate_limit(self, monkeypatch):
        mock_http(
            monkeypatch,
            lambda m, u, **k: FakeResponse(
                403, {"message": "API rate limit exceeded"},
                headers={"X-RateLimit-Remaining": "0"},
            ),
        )
        ok, payload = main._github_request("GET", "https://api.github.com/x")
        assert ok is False
        assert "rate limit" in payload.lower()

    def test_403_without_rate_limit_is_generic(self, monkeypatch):
        mock_http(
            monkeypatch,
            lambda m, u, **k: FakeResponse(
                403, {"message": "forbidden"}, headers={"X-RateLimit-Remaining": "42"}
            ),
        )
        ok, payload = main._github_request("GET", "https://api.github.com/x")
        assert ok is False
        assert "HTTP 403" in payload
        assert "forbidden" in payload

    def test_401_invalid_token(self, monkeypatch):
        mock_http(
            monkeypatch,
            lambda m, u, **k: FakeResponse(401, {"message": "Bad credentials"}),
        )
        ok, payload = main._github_request(
            "GET", "https://api.github.com/x", token="bad"
        )
        assert ok is False
        assert "401 Unauthorized" in payload

    def test_404_uses_resource_description(self, monkeypatch):
        mock_http(
            monkeypatch,
            lambda m, u, **k: FakeResponse(404, {"message": "Not Found"}),
        )
        ok, payload = main._github_request(
            "GET", "https://api.github.com/x", resource="repository 'a/b'"
        )
        assert ok is False
        assert "Not found (404): repository 'a/b'" in payload

    def test_malformed_json_on_success_status(self, monkeypatch):
        mock_http(
            monkeypatch,
            lambda m, u, **k: FakeResponse(200, None, text="<html>gateway</html>"),
        )
        ok, payload = main._github_request("GET", "https://api.github.com/x")
        assert ok is True
        assert payload == "<html>gateway</html>"

    def test_generic_error_includes_status_and_detail(self, monkeypatch):
        mock_http(
            monkeypatch,
            lambda m, u, **k: FakeResponse(500, {"message": "server oops"}),
        )
        ok, payload = main._github_request("GET", "https://api.github.com/x")
        assert ok is False
        assert "HTTP 500" in payload and "server oops" in payload

    def test_token_is_sent_when_configured(self, monkeypatch):
        captured = {}

        def responder(method, url, **kwargs):
            captured.update(kwargs)
            return FakeResponse(200, {})

        mock_http(monkeypatch, responder)
        main._github_request("GET", "https://api.github.com/x", token="t0ken")
        assert captured["headers"]["Authorization"] == "token t0ken"


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


class TestGetRepoDetails:
    def test_renders_semantic_html(self, monkeypatch):
        mock_http(
            monkeypatch,
            lambda m, u, **k: FakeResponse(
                200,
                {
                    "full_name": "octo/<b>at</b>",
                    "description": "A repo",
                    "stargazers_count": 5,
                    "forks_count": 1,
                    "open_issues_count": 2,
                    "language": "Python",
                    "license": {"name": "MIT"},
                    "topics": ["x<script>", "y"],
                    "html_url": "https://github.com/octo/x",
                },
            ),
        )
        result = get_repo_details("octo/x")
        # Construct expected strings via html.escape so assertions stay valid
        # regardless of any HTML-entity decoding applied to this file.
        assert f"<h3>octo/{html.escape('<b>at</b>')}</h3>" in result
        assert f"<li>{html.escape('x<script>')}</li>" in result
        assert "<strong>Stars:</strong> 5" in result
        assert result.startswith("<h3>")

    def test_invalid_url_returns_error_string(self, monkeypatch):
        result = get_repo_details("not a repo")
        assert result.startswith("Error:")
        mock_http(monkeypatch, lambda m, u, **k: pytest.fail("no HTTP expected"))

    def test_api_error_is_propagated(self, monkeypatch):
        mock_http(monkeypatch, lambda m, u, **k: FakeResponse(404, {"message": "Not Found"}))
        result = get_repo_details("ghost/missing")
        assert "Error: Not found (404)" in result


class TestCreateIssue:
    def test_missing_token_is_rejected(self, monkeypatch):
        monkeypatch.setattr(main, "GITHUB_TOKEN_ISSUE", "")
        result = create_issue("a/b", "Title", "Body")
        assert "GITHUB_TOKEN_ISSUE" in result

    def test_missing_title_is_rejected(self, monkeypatch):
        monkeypatch.setattr(main, "GITHUB_TOKEN_ISSUE", "t")
        result = create_issue("a/b", "  ", "Body")
        assert result.startswith("Error:")
        assert "issue_title" in result

    def test_success_returns_link(self, monkeypatch):
        monkeypatch.setattr(main, "GITHUB_TOKEN_ISSUE", "t")

        def responder(method, url, **kwargs):
            assert method == "POST"
            assert kwargs["json"] == {"title": "T", "body": "B"}
            return FakeResponse(201, {"number": 7, "html_url": "https://github.com/a/b/issues/7"})

        mock_http(monkeypatch, responder)
        result = create_issue("a/b", "T", "B")
        assert "Issue #7 created" in result
        assert 'href="https://github.com/a/b/issues/7"' in result


class TestListIssues:
    def test_filters_pull_requests(self, monkeypatch):
        payload = [
            {"number": 1, "title": "Real issue", "html_url": "u1"},
            {"number": 2, "title": "PR", "html_url": "u2", "pull_request": {"url": "x"}},
        ]
        mock_http(monkeypatch, lambda m, u, **k: FakeResponse(200, payload))
        result = list_issues("a/b")
        assert "Real issue" in result
        assert "PR" not in result

    def test_no_issues_message(self, monkeypatch):
        mock_http(monkeypatch, lambda m, u, **k: FakeResponse(200, []))
        result = list_issues("a/b")
        assert "No open issues" in result


class TestGetReadme:
    def test_truncates_long_readmes(self, monkeypatch):
        long_text = "x" * (main.README_MAX_CHARS + 500)
        mock_http(monkeypatch, lambda m, u, **k: FakeResponse(200, None, text=long_text))
        result = get_readme("a/b")
        assert "truncated" in result
        # The escaped body must not exceed the cap.
        body = result.split("<pre>", 1)[1].split("</pre>", 1)[0]
        assert len(body) <= main.README_MAX_CHARS

    def test_escapes_html_in_readme(self, monkeypatch):
        mock_http(monkeypatch, lambda m, u, **k: FakeResponse(200, None, text="<script>alert(1)</script>"))
        result = get_readme("a/b")
        assert "<script>alert(1)</script>" not in result
        assert html.escape("<script>alert(1)</script>") in result


class TestCompareRepositories:
    def test_missing_second_repo_is_rejected(self):
        result = compare_repositories("a/b", None)
        assert result.startswith("Error:")
        assert "compare_repo_url" in result

    def test_renders_comparison_table(self, monkeypatch):
        responses = {
            "https://api.github.com/repos/a/b": {"stargazers_count": 10, "forks_count": 2,
                                                 "open_issues_count": 3, "subscribers_count": 4},
            "https://api.github.com/repos/c/d": {"stargazers_count": 20, "forks_count": 5,
                                                 "open_issues_count": 6, "subscribers_count": 7},
        }

        def responder(method, url, **kwargs):
            return FakeResponse(200, responses[url])

        mock_http(monkeypatch, responder)
        result = compare_repositories("a/b", "c/d")
        assert "<table>" in result
        assert '<th scope="col">Metric</th>' in result
        assert "<td>10</td><td>20</td>" in result

    def test_second_repo_failure_propagates(self, monkeypatch):
        responses = {
            "https://api.github.com/repos/a/b": FakeResponse(200, {"stargazers_count": 1}),
            "https://api.github.com/repos/c/d": FakeResponse(404, {"message": "Not Found"}),
        }

        def responder(method, url, **kwargs):
            return responses[url]

        mock_http(monkeypatch, responder)
        result = compare_repositories("a/b", "c/d")
        assert "Error: Not found (404)" in result


class TestGetUserInfo:
    def test_happy_path(self, monkeypatch):
        def responder(method, url, **kwargs):
            if url == "https://api.github.com/users/octocat":
                return FakeResponse(200, {"login": "octocat", "name": "The Octocat",
                                          "html_url": "https://github.com/octocat",
                                          "followers": 1, "following": 2, "public_repos": 3})
            if url.startswith("https://api.github.com/users/octocat/repos"):
                return FakeResponse(200, [{"name": "repo1", "html_url": "r1", "stargazers_count": 9}])
            return FakeResponse(404, {})

        mock_http(monkeypatch, responder)
        result = get_user_info("octocat")
        assert "GitHub user: octocat" in result
        assert "repo1" in result

    def test_repo_list_failure_is_graceful(self, monkeypatch):
        def responder(method, url, **kwargs):
            if url == "https://api.github.com/users/octocat":
                return FakeResponse(200, {"login": "octocat"})
            if url.startswith("https://api.github.com/users/octocat/repos"):
                return FakeResponse(500, {"message": "oops"})
            return FakeResponse(404, {})

        mock_http(monkeypatch, responder)
        result = get_user_info("octocat")
        assert "Repository list is unavailable" in result

    def test_invalid_username_rejected(self, monkeypatch):
        result = get_user_info("bad--name")
        assert result.startswith("Error:")


# ---------------------------------------------------------------------------
# Protocol handler
# ---------------------------------------------------------------------------


class TestHandler:
    def test_invalid_action_returns_error_type(self):
        msg = GitHubRepoRequest(action="does_not_exist")
        response = run_handler(msg)
        assert response.type == main.UAgentResponseType.ERROR
        assert "does_not_exist" in response.message
        assert response.message == INVALID_ACTION_TEMPLATE.format(
            action="does_not_exist",
            supported=", ".join(sorted([
                "add_collaborator", "compare", "create_issue", "get_branches",
                "get_commits", "get_details", "get_readme", "get_user_info",
                "list_contributors", "list_issues", "remove_collaborator",
                "star_repo", "unstar_repo",
            ])),
        )

    def test_action_error_maps_to_error_type(self, monkeypatch):
        # Invalid repo URL -> action returns "Error: ..." -> ERROR response type.
        msg = GitHubRepoRequest(action="get_details", repo_url="bogus")
        response = run_handler(msg)
        assert response.type == main.UAgentResponseType.ERROR
        assert response.message.startswith("Error:")

    def test_success_maps_to_final_type(self, monkeypatch):
        mock_http(
            monkeypatch,
            lambda m, u, **k: FakeResponse(200, {"full_name": "a/b"}),
        )
        msg = GitHubRepoRequest(action="get_details", repo_url="a/b")
        response = run_handler(msg)
        assert response.type == main.UAgentResponseType.FINAL
        assert "<h3>a/b</h3>" in response.message

    def test_unexpected_exception_returns_error_response(self, monkeypatch):
        def responder(method, url, **kwargs):
            raise RuntimeError("simulated internal bug")

        mock_http(monkeypatch, responder)
        msg = GitHubRepoRequest(action="get_details", repo_url="a/b")
        response = run_handler(msg)
        assert response.type == main.UAgentResponseType.ERROR
        assert "unexpected error" in response.message

    def test_get_user_info_without_repo_url_does_not_crash(self, monkeypatch):
        def responder(method, url, **kwargs):
            if url == "https://api.github.com/users/octocat":
                return FakeResponse(200, {"login": "octocat"})
            return FakeResponse(200, [])

        mock_http(monkeypatch, responder)
        msg = GitHubRepoRequest(action="get_user_info", user_info="octocat")
        response = run_handler(msg)
        assert response.type == main.UAgentResponseType.FINAL
        assert "octocat" in response.message