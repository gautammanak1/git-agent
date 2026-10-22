# git-agent

A [Fetch.ai uAgents](https://fetch.ai) agent that manages GitHub repositories
through natural-language requests. It answers with accessible, semantic HTML
that renders safely in chat clients that support HTML (such as ASI:One or the
Agentverse), and degrades to plain text elsewhere.

## Features

- **13 repository actions** — details, issues, README, commits, branches,
  contributors, repository comparison, collaborators (add/remove), starring,
  and user profiles.
- **Robust error handling** — every failure path returns a clear, actionable
  message instead of crashing the agent: timeouts, network failures, rate
  limits, invalid tokens, missing resources, and malformed payloads are all
  mapped to human-readable text with the appropriate `ERROR` response type.
- **Accessible output** — semantic HTML (`h3`, `ul`/`li`, tables with
  `scope` attributes, descriptive links) and `html.escape`d user data, so
  injected markup is displayed as text, never executed.
- **Optional authentication** — write actions require a GitHub personal
  access token supplied through environment variables; read actions work
  without one.

## Supported actions

| Action | Description | Requires token |
| --- | --- | --- |
| `get_details` | Repository metadata (stars, forks, issues, language, license, topics) | No |
| `create_issue` | Open a new issue (`issue_title` required) | Yes (`GITHUB_TOKEN_ISSUE`) |
| `list_issues` | Open issues (pull requests are filtered out) | No |
| `get_readme` | Repository README, truncated to 6000 characters | No |
| `compare` | Compare stars/forks/issues/watchers of two repositories | No |
| `add_collaborator` | Grant repository access to a user | Yes (`GITHUB_TOKEN_DETAILS`) |
| `remove_collaborator` | Revoke repository access | Yes (`GITHUB_TOKEN_DETAILS`) |
| `get_commits` | Recent commits (short SHA + first line of the message) | No |
| `get_branches` | List branches | No |
| `list_contributors` | Top contributors | No |
| `star_repo` | Star the repository | Yes (`GITHUB_TOKEN_DETAILS`) |
| `unstar_repo` | Unstar the repository | Yes (`GITHUB_TOKEN_DETAILS`) |
| `get_user_info` | Public profile of a GitHub user plus their repositories | No |

Unsupported or misspelled actions receive an explicit error message listing
every supported action.

## Requirements

- Python 3.9+
- A GitHub personal access token (only for write actions) with the
  `repo` scope

## Installation

```bash
git clone https://github.com/gautammanak1/git-agent.git
cd git-agent
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Configuration

The agent reads two optional environment variables:

| Variable | Used by | Purpose |
| --- | --- | --- |
| `GITHUB_TOKEN_DETAILS` | `add_collaborator`, `remove_collaborator`, `star_repo`, `unstar_repo` | Token for collaborator and starring actions |
| `GITHUB_TOKEN_ISSUE` | `create_issue` | Token for creating issues |

Without a token, the corresponding actions return a clear error explaining
which variable to set. Read-only actions never require a token.

```bash
# Windows (cmd)
set GITHUB_TOKEN_ISSUE=ghp_your_token_here

# macOS / Linux
export GITHUB_TOKEN_ISSUE=ghp_your_token_here
```

## Running the agent

```bash
python main.py
```

## Error handling

All GitHub traffic goes through a single request helper that maps every
failure to an actionable message:

- **Timeouts** — the agent waits at most 20 seconds per request and reports
  the limit when exceeded.
- **Network failures** — DNS or connection problems return "Could not reach
  the GitHub API" instead of a traceback.
- **Rate limiting** — 403/429 responses with an exhausted quota are
  reported explicitly.
- **Authentication** — invalid tokens produce a dedicated 401 message.
- **Missing resources** — 404 responses name the resource that was not
  found (for example, `Not found (404): repository 'a/b'`).
- **Malformed payloads** — non-JSON responses are handled gracefully.
- **Unexpected exceptions** — the protocol handler never raises; it logs
  and returns an `ERROR`-typed response.

Input validation rejects malformed repository URLs and usernames up front
with instructions on the accepted format (`owner/repo` or a full GitHub URL).

## Accessibility

- Semantic HTML: headings, unordered lists, and tables with
  `scope="col"` / `scope="row"` headers.
- All user-controlled data is escaped with `html.escape`, preventing HTML
  injection from repository names, topics, README contents, and issue titles.
- Links are descriptive (the repository name), never bare URLs.
- Error messages are complete sentences that state what failed and how to
  fix it.

## Testing

The test suite (51 tests) covers input validation, the HTTP error mapping,
every action, and the protocol handler. All HTTP traffic is mocked — no real
API calls are performed.

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -v
```

## License

MIT — see the repository for details.