import requests
from uagents import Agent, Context, Protocol, Model, Field
from ai_engine import UAgentResponse, UAgentResponseType
import base64

agent = Agent()

GITHUB_API_URL = "https://api.github.com"
GITHUB_TOKEN_DETAILS = ""
GITHUB_TOKEN_ISSUE = ""
github_protocol = Protocol(name="GitHubRepoProtocol")
class GitHubRepoRequest(Model):
    repo_url: str = Field(description="The URL of the GitHub repository.")
    action: str = Field(description="Action to perform: 'get_details', 'create_issue', 'compare', 'list_issues', 'get_readme'.")
    issue_title: str = Field(default=None, description="Title of the issue if action is 'create_issue'.")
    issue_body: str = Field(default=None, description="Body of the issue if action is 'create_issue'.")
    compare_repo_url: str = Field(default=None, description="The URL of the second repository for comparison.")
def get_repo_details(repo_url: str) -> dict:
    repo_name = repo_url.split("github.com/")[-1]
    headers = {"Authorization": f"token {GITHUB_TOKEN_DETAILS}"}
    response = requests.get(f"{GITHUB_API_URL}/repos/{repo_name}", headers=headers)

    if response.status_code == 200:
        return response.json()
    return {"error": f"Failed to fetch repository details: {response.json().get('message')}"}
def create_issue(repo_url: str, title: str, body: str) -> dict:
    repo_name = repo_url.split("github.com/")[-1]
    headers = {"Authorization": f"token {GITHUB_TOKEN_ISSUE}"}
    data = {"title": title, "body": body}
    response = requests.post(f"{GITHUB_API_URL}/repos/{repo_name}/issues", headers=headers, json=data)

    if response.status_code == 201:
        return {"message": "Issue created successfully."}
    return {"error": f"Failed to create issue: {response.json().get('message')}"}
def compare_repos(repo_url1: str, repo_url2: str) -> str:
    repo1_details = get_repo_details(repo_url1)
    repo2_details = get_repo_details(repo_url2)
    
    if "error" in repo1_details:
        return repo1_details["error"]
    if "error" in repo2_details:
        return repo2_details["error"]

    comparison = (
        f"Comparison of Repositories:\n\n"
        f"Repo 1 - {repo1_details['name']}:\n"
        f"- Description: {repo1_details['description']}\n"
        f"- Stars: {repo1_details['stargazers_count']}\n"
        f"- Forks: {repo1_details['forks_count']}\n"
        f"- Open Issues: {repo1_details['open_issues_count']}\n\n"
        f"Repo 2 - {repo2_details['name']}:\n"
        f"- Description: {repo2_details['description']}\n"
        f"- Stars: {repo2_details['stargazers_count']}\n"
        f"- Forks: {repo2_details['forks_count']}\n"
        f"- Open Issues: {repo2_details['open_issues_count']}\n"
    )

    return comparison
def list_issues(repo_url: str) -> str:
    repo_name = repo_url.split("github.com/")[-1]
    headers = {"Authorization": f"token {GITHUB_TOKEN_DETAILS}"}
    response = requests.get(f"{GITHUB_API_URL}/repos/{repo_name}/issues", headers=headers)

    if response.status_code == 200:
        issues = response.json()
        if not issues:
            return "No issues found in the repository."
        issue_list = "\n".join([f"- #{issue['number']}: {issue['title']}" for issue in issues])
        return f"Issues in {repo_name}:\n{issue_list}"
    return f"Failed to list issues: {response.json().get('message')}"
def get_readme(repo_url: str) -> str:
    repo_name = repo_url.split("github.com/")[-1]
    headers = {"Authorization": f"token {GITHUB_TOKEN_DETAILS}"}
    response = requests.get(f"{GITHUB_API_URL}/repos/{repo_name}/readme", headers=headers)

    if response.status_code == 200:
        readme_data = response.json()
        readme_content = base64.b64decode(readme_data['content']).decode('utf-8')
        return f"README Content:\n\n{readme_content}"
    return f"Failed to fetch README: {response.json().get('message')}"
@github_protocol.on_message(model=GitHubRepoRequest, replies={UAgentResponse})
async def handle_github_repo_request(ctx: Context, sender: str, msg: GitHubRepoRequest):
    ctx.logger.info(f"Received GitHub repo request for URL: '{msg.repo_url}', Action: '{msg.action}'")

    if msg.action == "get_details":
        repo_info = get_repo_details(msg.repo_url)
        if "error" in repo_info:
            message = repo_info["error"]
        else:
            message = (
                f"Repository Details:\n"
                f"- Name: {repo_info['name']}\n"
                f"- Description: {repo_info['description']}\n"
                f"- Stars: {repo_info['stargazers_count']}\n"
                f"- Forks: {repo_info['forks_count']}\n"
                f"- Open Issues: {repo_info['open_issues_count']}\n"
            )
    elif msg.action == "create_issue" and msg.issue_title and msg.issue_body:
        result = create_issue(msg.repo_url, msg.issue_title, msg.issue_body)
        message = result.get("message", result.get("error"))

    elif msg.action == "compare" and msg.compare_repo_url:
        message = compare_repos(msg.repo_url, msg.compare_repo_url)

    elif msg.action == "list_issues":
        message = list_issues(msg.repo_url)

    elif msg.action == "get_readme":
        message = get_readme(msg.repo_url)

    else:
        message = "Invalid action or missing required fields."
    ctx.logger.info(f"Sending message to {sender}: {message}")
    await ctx.send(sender, UAgentResponse(message=message, type=UAgentResponseType.FINAL))
agent.include(github_protocol, publish_manifest=True)

if __name__ == "__main__":
    agent.run()
