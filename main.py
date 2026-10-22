"""GitHub Repository Management Agent.

A Fetch.ai uAgents-based agent that talks to the GitHub REST API.

Design notes:
- Every outbound HTTP call goes through ``_github_request`` which adds
  timeouts, consistent error mapping (auth, rate limit, not found, network
  failures, malformed payloads) and token handling.
- All user/API supplied values are HTML-escaped before being embedded in
  responses, and responses use semantic HTML (headings, lists, tables with
  ``scope`` attributes) so screen readers can navigate them.
- Actions run in a thread executor so the blocking ``requests`` calls never
  stall the agent's event loop, and the message handler never raises.
- GitHub tokens are read from environment variables instead of being
  hard-coded in source.
"""

import asyncio
import functools
import html
import os
import re
from typing import Any, Optional, Tuple

import requests
from uagents import Agent, Context, Field, Model, Protocol
from ai_engine import UAgentResponse, UAgentResponseType

GITHUB_API_URL = "https://api.github.com"

# Timeouts keep a hung GitHub API from blocking the executor pool forever.
REQUEST_TIMEOUT_SECONDS = 20
# READMEs can be huge; truncate before returning them in a chat message.
README_MAX_CHARS = 6000
# GitHub usernames: 1-39 chars, alphanumerics and single internal hyphens.
GITHUB_USERNAME_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$"
)
REPO_FULL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

# Tokens come from the environment so secrets never live in source code.
GITHUB_TOKEN_DETAILS = os.environ.get("GITHUB_TOKEN_DETAILS", "")
GITHUB_TOKEN_ISSUE = os.environ.get("GITHUB_TOKEN_ISSUE", "")

# Shared session: reuses connection pools for faster repeated calls.
SESSION = requests.Session()

agent = Agent()
github_protocol = Protocol(name="GitHubRepoProtocol")


class GitHubRepoRequest(Model):
    repo_url: Optional[str] = Field(
        default=None,
        description=(
            "The GitHub repository, e.g. 'https://github.com/owner/repo' or "
            "'owner/repo'."
        ),
    )
    action: str = Field(
        description=(
            "Action to perform. Supported: get_details, create_issue, "
            "list_issues, get_readme, compare, add_collaborator, "
            "remove_collaborator, get_commits, get_branches, "
            "list_contributors, star_repo, unstar_repo, get_user_info."
        ),
    )
    issue_title: Optional[str] = Field(
        default=None, description="Title of the issue if action is 'create_issue'."
    )
    issue_body: Optional[str] = Field(
        default=None, description="Body of the issue if action is 'create_issue'."
    )
    collaborator_username: Optional[str] = Field(
        default=None,
        description="Username of the collaborator to add or remove.",
    )
    compare_repo_url: Optional[str] = Field(
        default=None,
        description="The URL of the second repository for comparison.",
    )
    user_info: Optional[str] = Field(
        default=None,
        description=(
            "GitHub username (or profile URL) to fetch user details for."
        ),
    )


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------


def parse_repo_full_name(repo_url: str) -> str:
    """Normalize a repository URL or 'owner/repo' shorthand to 'owner/repo'.

    Raises ValueError with an actionable message when the input cannot be
    interpreted; the message is surfaced to the caller as the response.
    """
    if not repo_url or not str(repo_url).strip():
        raise ValueError(
            "A repository URL is required (e.g. 'https://github.com/owner/repo' "
            "or 'owner/repo')."
        )
    value = str(repo_url).strip()
    if "github.com" in value:
        value = value.split("github.com", 1)[1]
    value = value.strip("/:").strip()
    if value.endswith(".git"):
        value = value[:-4]
    parts = [part for part in value.split("/") if part]
    if len(parts) < 2:
        raise ValueError(
            f"Could not determine 'owner/repo' from '{repo_url}'. Provide a "
            "GitHub repository URL or an 'owner/repo' pair."
        )
    full_name = f"{parts[0]}/{parts[1]}"
    if not REPO_FULL_NAME_PATTERN.match(full_name):
        raise ValueError(
            f"'{repo_url}' does not look like a valid GitHub repository reference."
        )
    return full_name


def validate_username(username: Optional[str]) -> str:
    """Validate a GitHub username (accepts profile URLs too)."""
    if not username or not str(username).strip():
        raise ValueError("A GitHub username is required for this action.")
    username = str(username).strip()
    if "github.com/" in username:
        username = username.split("github.com/")[-1].strip("/")
    if not GITHUB_USERNAME_PATTERN.match(username):
        raise ValueError(f"'{username}' is not a valid GitHub username.")
    return username


def _handles_input_errors(func):
    """Convert input-validation ValueErrors into readable 'Error: ...' strings."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as exc:
            return f"Error: {exc}"

    return wrapper


# ---------------------------------------------------------------------------
# GitHub API helper with centralized error handling
# ---------------------------------------------------------------------------


def _error_detail(response) -> str:
    """Best-effort extraction of an error message from a GitHub response."""
    try:
        payload = response.json()
    except ValueError:
        detail = (response.text or "").strip()
        return detail[:200] if detail else "no additional details were provided"
    if isinstance(payload, dict) and payload.get("message"):
        return str(payload["message"])[:200]
    return "no additional details were provided"


def _github_request(
    method: str,
    url: str,
    *,
    token: str = "",
    json_body: Optional[dict] = None,
    expected: Tuple[int, ...] = (200,),
    extra_headers: Optional[dict] = None,
    want_text: bool = False,
    resource: Optional[str] = None,
) -> Tuple[bool, Any]:
    """Perform one GitHub API call and map failures to readable messages.

    Returns ``(ok, payload)``: on success ``payload`` is the parsed JSON body
    (or the raw text when ``want_text`` is set); on failure it is an
    'Error: ...' message that is safe to send back to the user as-is.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    if extra_headers:
        headers.update(extra_headers)

    try:
        response = SESSION.request(
            method, url, headers=headers, json=json_body, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except requests.exceptions.Timeout:
        return False, (
            f"Error: The GitHub API did not respond within "
            f"{REQUEST_TIMEOUT_SECONDS} seconds. Please try again later."
        )
    except requests.exceptions.RequestException:
        return False, (
            "Error: Could not reach the GitHub API. Check your network "
            "connection and try again."
        )

    if response.status_code in expected:
        if want_text:
            return True, response.text
        if not response.content:
            return True, {}
        try:
            return True, response.json()
        except ValueError:
            # Success status but unexpected body: still hand back something.
            return True, response.text

    if response.status_code in (403, 429) and response.headers.get(
        "X-RateLimit-Remaining"
    ) == "0":
        return False, (
            "Error: The GitHub API rate limit has been exceeded. Configure a "
            "GitHub token via GITHUB_TOKEN_DETAILS (or wait for the limit to "
            "reset) and try again."
        )
    if response.status_code == 401:
        return False, (
            "Error: GitHub rejected the configured token (401 Unauthorized). "
            "Verify that the token is valid and has not expired."
        )
    if response.status_code == 404:
        target = resource or url
        return False, (
            f"Error: Not found (404): {target}. Verify that it exists and "
            "that your token has access to it."
        )

    return False, (
        f"Error: GitHub API returned HTTP {response.status_code}: "
        f"{_error_detail(response)}"
    )


# ---------------------------------------------------------------------------
# Response formatting helpers (accessibility: semantic, escaped HTML)
# ---------------------------------------------------------------------------


def _format_repo_details(data: dict) -> str:
    """Render repository details as a screen-reader friendly summary."""
    full_name = str(data.get("full_name", "Unknown repository"))
    description = data.get("description") or "No description provided."
    license_name = (data.get("license") or {}).get("name") or "None"
    topics = data.get("topics") or []
    topics_html = (
        "".join(f"<li>{html.escape(str(topic))}</li>" for topic in topics)
        or "<li>None</li>"
    )
    profile_url = str(data.get("html_url", ""))
    link = (
        f'<p><a href="{html.escape(profile_url)}">Open {html.escape(full_name)} '
        "on GitHub</a></p>"
        if profile_url
        else ""
    )
    return (
        f"<h3>{html.escape(full_name)}</h3>"
        f"<p>{html.escape(str(description))}</p>"
        "<ul>"
        f"<li><strong>Stars:</strong> {data.get('stargazers_count', 0)}</li>"
        f"<li><strong>Forks:</strong> {data.get('forks_count', 0)}</li>"
        f"<li><strong>Open issues:</strong> {data.get('open_issues_count', 0)}</li>"
        f"<li><strong>Primary language:</strong> "
        f"{html.escape(str(data.get('language') or 'N/A'))}</li>"
        f"<li><strong>License:</strong> {html.escape(str(license_name))}</li>"
        "</ul>"
        "<h4>Topics</h4>"
        f"<ul>{topics_html}</ul>"
        f"{link}"
    )


# ---------------------------------------------------------------------------
# Action implementations
# ---------------------------------------------------------------------------


@_handles_input_errors
def get_repo_details(repo_url: str) -> str:
    repo = parse_repo_full_name(repo_url)
    ok, payload = _github_request(
        "GET",
        f"{GITHUB_API_URL}/repos/{repo}",
        token=GITHUB_TOKEN_DETAILS,
        resource=f"repository '{repo}'",
    )
    if not ok:
        return payload
    return _format_repo_details(payload)


@_handles_input_errors
def create_issue(repo_url: str, title: Optional[str], body: Optional[str]) -> str:
    if not GITHUB_TOKEN_ISSUE:
        return (
            "Error: Creating issues requires authentication. Set the "
            "GITHUB_TOKEN_ISSUE environment variable and restart the agent."
        )
    if not title or not str(title).strip():
        raise ValueError(
            "An issue title is required for the 'create_issue' action (send "
            "it in the 'issue_title' field)."
        )
    repo = parse_repo_full_name(repo_url)
    ok, payload = _github_request(
        "POST",
        f"{GITHUB_API_URL}/repos/{repo}/issues",
        token=GITHUB_TOKEN_ISSUE,
        json_body={"title": str(title), "body": str(body or "")},
        expected=(201,),
        resource=f"repository '{repo}'",
    )
    if not ok:
        return payload
    number = payload.get("number", "?") if isinstance(payload, dict) else "?"
    issue_url = payload.get("html_url", "") if isinstance(payload, dict) else ""
    link = (
        f' <a href="{html.escape(str(issue_url))}">View issue #{number}</a>'
        if issue_url
        else ""
    )
    return f"Issue #{number} created successfully in {html.escape(repo)}.{link}"


@_handles_input_errors
def list_issues(repo_url: str) -> str:
    repo = parse_repo_full_name(repo_url)
    ok, payload = _github_request(
        "GET",
        f"{GITHUB_API_URL}/repos/{repo}/issues?state=open&per_page=30",
        token=GITHUB_TOKEN_DETAILS,
        resource=f"issues of '{repo}'",
    )
    if not ok:
        return payload
    if not isinstance(payload, list):
        return f"Error: Unexpected response while listing issues of {html.escape(repo)}."
    # The issues endpoint also returns pull requests; filter them out.
    issues = [i for i in payload if isinstance(i, dict) and "pull_request" not in i]
    if not issues:
        return f"No open issues found in {html.escape(repo)}."
    items = "".join(
        f"<li>#{issue.get('number', '?')} "
        f'<a href="{html.escape(str(issue.get("html_url", "")))}">'
        f"{html.escape(str(issue.get('title') or 'untitled'))}</a></li>"
        for issue in issues
    )
    return f"<h3>Open issues in {html.escape(repo)}</h3><ul>{items}</ul>"


@_handles_input_errors
def get_readme(repo_url: str) -> str:
    repo = parse_repo_full_name(repo_url)
    ok, payload = _github_request(
        "GET",
        f"{GITHUB_API_URL}/repos/{repo}/readme",
        token=GITHUB_TOKEN_DETAILS,
        extra_headers={"Accept": "application/vnd.github.raw+json"},
        want_text=True,
        resource=f"README of '{repo}'",
    )
    if not ok:
        return payload
    text = (payload or "").strip()
    if not text:
        return f"The README of {html.escape(repo)} is empty."
    note = ""
    if len(text) > README_MAX_CHARS:
        text = text[:README_MAX_CHARS]
        note = (
            f"<p>(Preview truncated to the first {README_MAX_CHARS} "
            "characters.)</p>"
        )
    return (
        f"<h3>README of {html.escape(repo)}</h3>{note}"
        f"<pre>{html.escape(text)}</pre>"
    )


@_handles_input_errors
def compare_repositories(
    repo_url: str, compare_repo_url: Optional[str]
) -> str:
    if not compare_repo_url or not str(compare_repo_url).strip():
        raise ValueError(
            "A second repository is required for the 'compare' action (send "
            "it in the 'compare_repo_url' field)."
        )
    first = parse_repo_full_name(repo_url)
    second = parse_repo_full_name(compare_repo_url)
    ok_a, data_a = _github_request(
        "GET",
        f"{GITHUB_API_URL}/repos/{first}",
        token=GITHUB_TOKEN_DETAILS,
        resource=f"repository '{first}'",
    )
    if not ok_a:
        return data_a
    ok_b, data_b = _github_request(
        "GET",
        f"{GITHUB_API_URL}/repos/{second}",
        token=GITHUB_TOKEN_DETAILS,
        resource=f"repository '{second}'",
    )
    if not ok_b:
        return data_b
    metrics = [
        ("Stars", "stargazers_count"),
        ("Forks", "forks_count"),
        ("Open issues", "open_issues_count"),
        ("Watchers", "subscribers_count"),
    ]
    rows = ""
    for label, key in metrics:
        rows += (
            f'<tr><th scope="row">{label}</th>'
            f"<td>{data_a.get(key, 'N/A')}</td>"
            f"<td>{data_b.get(key, 'N/A')}</td></tr>"
        )
    return (
        f"<h3>Comparing {html.escape(first)} with {html.escape(second)}</h3>"
        "<table><thead><tr>"
        '<th scope="col">Metric</th>'
        f'<th scope="col">{html.escape(first)}</th>'
        f'<th scope="col">{html.escape(second)}</th>'
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )


@_handles_input_errors
def add_collaborator(repo_url: str, username: Optional[str]) -> str:
    if not GITHUB_TOKEN_DETAILS:
        return (
            "Error: Managing collaborators requires a GitHub token with "
            "repository administration permissions. Set the "
            "GITHUB_TOKEN_DETAILS environment variable and restart the agent."
        )
    user = validate_username(username)
    repo = parse_repo_full_name(repo_url)
    ok, payload = _github_request(
        "PUT",
        f"{GITHUB_API_URL}/repos/{repo}/collaborators/{user}",
        token=GITHUB_TOKEN_DETAILS,
        expected=(201, 204),
        resource=f"repository '{repo}' or user '{user}'",
    )
    if not ok:
        return payload
    return (
        f"Collaborator '{html.escape(user)}' added to {html.escape(repo)} "
        "(or they already had access; GitHub sent an invitation if one was "
        "required)."
    )


@_handles_input_errors
def remove_collaborator(repo_url: str, username: Optional[str]) -> str:
    if not GITHUB_TOKEN_DETAILS:
        return (
            "Error: Managing collaborators requires a GitHub token with "
            "repository administration permissions. Set the "
            "GITHUB_TOKEN_DETAILS environment variable and restart the agent."
        )
    user = validate_username(username)
    repo = parse_repo_full_name(repo_url)
    ok, payload = _github_request(
        "DELETE",
        f"{GITHUB_API_URL}/repos/{repo}/collaborators/{user}",
        token=GITHUB_TOKEN_DETAILS,
        expected=(204,),
        resource=f"repository '{repo}' or user '{user}'",
    )
    if not ok:
        return payload
    return (
        f"Collaborator '{html.escape(user)}' removed from {html.escape(repo)}."
    )


@_handles_input_errors
def list_commits(repo_url: str) -> str:
    repo = parse_repo_full_name(repo_url)
    ok, payload = _github_request(
        "GET",
        f"{GITHUB_API_URL}/repos/{repo}/commits?per_page=10",
        token=GITHUB_TOKEN_DETAILS,
        resource=f"commit history of '{repo}'",
    )
    if not ok:
        return payload
    if not isinstance(payload, list) or not payload:
        return f"No commits found for {html.escape(repo)}."
    items = ""
    for commit in payload[:10]:
        if not isinstance(commit, dict):
            continue
        sha = str(commit.get("sha", ""))[:7] or "unknown"
        commit_info = commit.get("commit") or {}
        lines = str(commit_info.get("message", "")).splitlines()
        message = lines[0] if lines else "no commit message"
        author_login = (commit.get("author") or {}).get("login")
        author = author_login or (commit_info.get("author") or {}).get(
            "name", "unknown"
        )
        items += (
            f"<li><code>{html.escape(sha)}</code> - "
            f"{html.escape(message)} ({html.escape(str(author))})</li>"
        )
    return f"<h3>Latest commits in {html.escape(repo)}</h3><ul>{items}</ul>"


@_handles_input_errors
def get_branches(repo_url: str) -> str:
    repo = parse_repo_full_name(repo_url)
    ok, payload = _github_request(
        "GET",
        f"{GITHUB_API_URL}/repos/{repo}/branches?per_page=100",
        token=GITHUB_TOKEN_DETAILS,
        resource=f"branches of '{repo}'",
    )
    if not ok:
        return payload
    if not isinstance(payload, list):
        return f"Error: Unexpected response while listing branches of {html.escape(repo)}."
    names = [
        str(branch.get("name", ""))
        for branch in payload
        if isinstance(branch, dict)
    ]
    names = [name for name in names if name]
    if not names:
        return f"No branches found in {html.escape(repo)}."
    items = "".join(f"<li>{html.escape(name)}</li>" for name in names)
    return f"<h3>Branches in {html.escape(repo)}</h3><ul>{items}</ul>"


@_handles_input_errors
def list_contributors(repo_url: str) -> str:
    repo = parse_repo_full_name(repo_url)
    ok, payload = _github_request(
        "GET",
        f"{GITHUB_API_URL}/repos/{repo}/contributors?per_page=10",
        token=GITHUB_TOKEN_DETAILS,
        resource=f"contributors of '{repo}'",
    )
    if not ok:
        return payload
    if not isinstance(payload, list) or not payload:
        return f"No contributor data available for {html.escape(repo)} yet."
    items = ""
    for contributor in payload[:10]:
        if not isinstance(contributor, dict):
            continue
        name = (
            contributor.get("login")
            or contributor.get("name")
            or "anonymous"
        )
        profile_url = str(contributor.get("html_url", ""))
        contributions = contributor.get("contributions", 0)
        entry = (
            f'<a href="{html.escape(profile_url)}">{html.escape(str(name))}</a>'
            if profile_url
            else html.escape(str(name))
        )
        items += f"<li>{entry} - {contributions} contributions</li>"
    return f"<h3>Top contributors of {html.escape(repo)}</h3><ul>{items}</ul>"


@_handles_input_errors
def star_repo(repo_url: str) -> str:
    if not GITHUB_TOKEN_DETAILS:
        return (
            "Error: Starring a repository requires a GitHub token. Set the "
            "GITHUB_TOKEN_DETAILS environment variable and restart the agent."
        )
    repo = parse_repo_full_name(repo_url)
    ok, payload = _github_request(
        "PUT",
        f"{GITHUB_API_URL}/user/starred/{repo}",
        token=GITHUB_TOKEN_DETAILS,
        expected=(204,),
        resource=f"repository '{repo}'",
    )
    if not ok:
        return payload
    return f"Starred {html.escape(repo)}."


@_handles_input_errors
def unstar_repo(repo_url: str) -> str:
    if not GITHUB_TOKEN_DETAILS:
        return (
            "Error: Unstarring a repository requires a GitHub token. Set the "
            "GITHUB_TOKEN_DETAILS environment variable and restart the agent."
        )
    repo = parse_repo_full_name(repo_url)
    ok, payload = _github_request(
        "DELETE",
        f"{GITHUB_API_URL}/user/starred/{repo}",
        token=GITHUB_TOKEN_DETAILS,
        expected=(204,),
        resource=f"repository '{repo}'",
    )
    if not ok:
        return payload
    return f"Removed the star from {html.escape(repo)}."


@_handles_input_errors
def get_user_info(username: Optional[str]) -> str:
    user = validate_username(username)
    ok, payload = _github_request(
        "GET",
        f"{GITHUB_API_URL}/users/{user}",
        token=GITHUB_TOKEN_DETAILS,
        resource=f"user '{user}'",
    )
    if not ok:
        return payload

    ok_repos, repos = _github_request(
        "GET",
        f"{GITHUB_API_URL}/users/{user}/repos?per_page=10&sort=updated",
        token=GITHUB_TOKEN_DETAILS,
    )
    if ok_repos and isinstance(repos, list):
        repo_items = ""
        for repo in repos[:10]:
            if not isinstance(repo, dict):
                continue
            repo_items += (
                f'<li><a href="{html.escape(str(repo.get("html_url", "")))}">'
                f"{html.escape(str(repo.get('name') or 'unknown'))}</a> - "
                f"{repo.get('stargazers_count', 0)} stars</li>"
            )
    else:
        repo_items = "<li>Repository list is unavailable right now.</li>"

    login = str(payload.get("login", user))
    profile_url = str(payload.get("html_url", ""))
    profile_link = (
        f'<a href="{html.escape(profile_url)}">Open {html.escape(login)} '
        "profile on GitHub</a>"
        if profile_url
        else "Profile link unavailable."
    )
    twitter = (
        f"@{payload['twitter_username']}"
        if payload.get("twitter_username")
        else "N/A"
    )
    return (
        f"<h3>GitHub user: {html.escape(login)}</h3>"
        "<ul>"
        f"<li><strong>Name:</strong> {html.escape(str(payload.get('name') or 'N/A'))}</li>"
        f"<li><strong>Company:</strong> {html.escape(str(payload.get('company') or 'N/A'))}</li>"
        f"<li><strong>Location:</strong> {html.escape(str(payload.get('location') or 'N/A'))}</li>"
        f"<li><strong>Bio:</strong> {html.escape(str(payload.get('bio') or 'N/A'))}</li>"
        f"<li><strong>Followers:</strong> {payload.get('followers', 0)}</li>"
        f"<li><strong>Following:</strong> {payload.get('following', 0)}</li>"
        f"<li><strong>Public repositories:</strong> {payload.get('public_repos', 0)}</li>"
        f"<li><strong>Twitter:</strong> {html.escape(twitter)}</li>"
        f"<li><strong>Profile:</strong> {profile_link}</li>"
        "</ul>"
        "<h4>Recently updated repositories</h4>"
        f"<ul>{repo_items}</ul>"
    )


# ---------------------------------------------------------------------------
# Protocol handler
# ---------------------------------------------------------------------------

INVALID_ACTION_TEMPLATE = "Error: Unsupported action '{action}'. Supported actions: {supported}."


@github_protocol.on_message(model=GitHubRepoRequest, replies={UAgentResponse})
async def handle_github_repo_request(ctx: Context, sender: str, msg: GitHubRepoRequest):
    action = getattr(msg, "action", "") or ""
    repo_url = getattr(msg, "repo_url", None)
    ctx.logger.info(
        f"Received GitHub repo request: action='{action}', repo_url='{repo_url}'"
    )

    actions = {
        "get_details": lambda: get_repo_details(repo_url),
        "create_issue": lambda: create_issue(
            repo_url, getattr(msg, "issue_title", None), getattr(msg, "issue_body", None)
        ),
        "compare": lambda: compare_repositories(
            repo_url, getattr(msg, "compare_repo_url", None)
        ),
        "list_issues": lambda: list_issues(repo_url),
        "get_readme": lambda: get_readme(repo_url),
        "add_collaborator": lambda: add_collaborator(
            repo_url, getattr(msg, "collaborator_username", None)
        ),
        "remove_collaborator": lambda: remove_collaborator(
            repo_url, getattr(msg, "collaborator_username", None)
        ),
        "get_commits": lambda: list_commits(repo_url),
        "get_branches": lambda: get_branches(repo_url),
        "list_contributors": lambda: list_contributors(repo_url),
        "star_repo": lambda: star_repo(repo_url),
        "unstar_repo": lambda: unstar_repo(repo_url),
        "get_user_info": lambda: get_user_info(getattr(msg, "user_info", None)),
    }

    action_fn = actions.get(action)
    if action_fn is None:
        response = INVALID_ACTION_TEMPLATE.format(
            action=action, supported=", ".join(sorted(actions))
        )
        response_type = UAgentResponseType.ERROR
    else:
        try:
            # ``requests`` is blocking; run it in the default executor so the
            # agent's event loop stays responsive to other messages.
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, action_fn)
            response_type = (
                UAgentResponseType.ERROR
                if str(response).startswith("Error")
                else UAgentResponseType.FINAL
            )
        except Exception as exc:  # never let a bug kill the message loop
            ctx.logger.error(f"Unhandled error while executing '{action}': {exc}")
            response = (
                "Error: An unexpected error occurred while processing your "
                "request. Please try again later."
            )
            response_type = UAgentResponseType.ERROR

    response = str(response)
    ctx.logger.info(
        f"Sending response to {sender} (type={response_type}, "
        f"{len(response)} chars)"
    )
    await ctx.send(sender, UAgentResponse(message=response, type=response_type))


agent.include(github_protocol, publish_manifest=True)

if __name__ == "__main__":
    agent.run()