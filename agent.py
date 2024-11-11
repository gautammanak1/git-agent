import requests
from uagents import Agent, Context, Protocol, Model, Field
from ai_engine import UAgentResponse, UAgentResponseType


agent = Agent()


GITHUB_API_URL = "https://api.github.com"

GITHUB_TOKEN_DETAILS = ""
GITHUB_TOKEN_ISSUE = ""


github_protocol = Protocol(name="GitHubRepoProtocol")


class GitHubRepoRequest(Model):
    repo_url: str = Field(description="The URL of the GitHub repository.")
    action: str = Field(description="Action to perform, e.g., 'get_details', 'create_issue', 'list_issues', 'get_readme', 'add_collaborator', 'remove_collaborator', 'get_commits', 'get_branches', 'list_contributors', 'star_repo', 'unstar_repo', 'get_user_info'.")
    issue_title: str = Field(default=None, description="Title of the issue if action is 'create_issue'.")
    issue_body: str = Field(default=None, description="Body of the issue if action is 'create_issue'.")
    collaborator_username: str = Field(default=None, description="Username of the collaborator to add or remove.")
    compare_repo_url: str = Field(default=None, description="The URL of the second repository for comparison.")
    user_info: str = Field(default=None, description="GitHub username to fetch user details, like repositories, most used languages, followers, etc.")


def get_repo_details(repo_url: str) -> str:
    repo_name = repo_url.split("github.com/")[-1]
    headers = {"Authorization": f"token {GITHUB_TOKEN_DETAILS}"}
    response = requests.get(f"{GITHUB_API_URL}/repos/{repo_name}", headers=headers)
    return str(response.json()) if response.status_code == 200 else f"Error: {response.json().get('message')}"


def create_issue(repo_url: str, title: str, body: str) -> str:
    repo_name = repo_url.split("github.com/")[-1]
    headers = {"Authorization": f"token {GITHUB_TOKEN_ISSUE}"}
    data = {"title": title, "body": body}
    response = requests.post(f"{GITHUB_API_URL}/repos/{repo_name}/issues", headers=headers, json=data)
    return "Issue created successfully." if response.status_code == 201 else f"Error: {response.json().get('message')}"


def add_collaborator(repo_url: str, username: str) -> str:
    repo_name = repo_url.split("github.com/")[-1]
    headers = {"Authorization": f"token {GITHUB_TOKEN_DETAILS}"}
    response = requests.put(f"{GITHUB_API_URL}/repos/{repo_name}/collaborators/{username}", headers=headers)
    return "Collaborator added successfully." if response.status_code == 201 else f"Error: {response.json().get('message')}"

def remove_collaborator(repo_url: str, username: str) -> str:
    repo_name = repo_url.split("github.com/")[-1]
    headers = {"Authorization": f"token {GITHUB_TOKEN_DETAILS}"}
    response = requests.delete(f"{GITHUB_API_URL}/repos/{repo_name}/collaborators/{username}", headers=headers)
    return "Collaborator removed successfully." if response.status_code == 204 else f"Error: {response.json().get('message')}"


def list_commits(repo_url: str) -> str:
    repo_name = repo_url.split("github.com/")[-1]
    headers = {"Authorization": f"token {GITHUB_TOKEN_DETAILS}"}
    response = requests.get(f"{GITHUB_API_URL}/repos/{repo_name}/commits", headers=headers)
    if response.status_code == 200:
        commits = response.json()
        return "<br>".join([f"Commit: {commit['sha']} - {commit['commit']['message']}" for commit in commits])
    return f"Error: {response.json().get('message')}"

def get_branches(repo_url: str) -> str:
    repo_name = repo_url.split("github.com/")[-1]
    headers = {"Authorization": f"token {GITHUB_TOKEN_DETAILS}"}
    response = requests.get(f"{GITHUB_API_URL}/repos/{repo_name}/branches", headers=headers)
    if response.status_code == 200:
        branches = response.json()
        return "<br>".join([branch['name'] for branch in branches])
    return f"Error: {response.json().get('message')}"


def get_user_info(username: str) -> str:
    if "github.com/" in username:
        username = username.split("github.com/")[-1] 

    headers = {"Authorization": f"token {GITHUB_TOKEN_DETAILS}"}
    response = requests.get(f"{GITHUB_API_URL}/users/{username}", headers=headers)
    if response.status_code == 200:
        user_info = response.json()
        repos_response = requests.get(f"{GITHUB_API_URL}/users/{username}/repos", headers=headers)
        user_info["repositories"] = repos_response.json() if repos_response.status_code == 200 else []
        
        response_message = f"""
        <h3>GitHub User Info: {user_info['login']}</h3>
        <ul>
            <li><strong>Name:</strong> {user_info.get('name', 'N/A')}</li>
            <li><strong>Company:</strong> {user_info.get('company', 'N/A')}</li>
            <li><strong>Location:</strong> {user_info.get('location', 'N/A')}</li>
            <li><strong>Bio:</strong> {user_info.get('bio', 'N/A')}</li>
            <li><strong>Followers:</strong> {user_info.get('followers', 'N/A')}</li>
            <li><strong>Following:</strong> {user_info.get('following', 'N/A')}</li>
            <li><strong>Public Repos:</strong> {user_info.get('public_repos', 'N/A')}</li>
            <li><strong>Twitter:</strong> @{user_info.get('twitter_username', 'N/A')}</li>
            <li><strong>GitHub Profile:</strong> <a href="{user_info['html_url']}">Visit Profile</a></li>
        </ul>
        <h4>Repositories:</h4>
        <ul>
        """
        for repo in user_info["repositories"]:
            response_message += f'<li><a href="{repo["html_url"]}">{repo["name"]}</a></li>'
        
        response_message += "</ul>"
        
        return response_message
    return f"Error: {response.json().get('message')}"


@github_protocol.on_message(model=GitHubRepoRequest, replies={UAgentResponse})
async def handle_github_repo_request(ctx: Context, sender: str, msg: GitHubRepoRequest):
    ctx.logger.info(f"Received GitHub repo request for URL: '{msg.repo_url}', Action: '{msg.action}'")


    actions = {
        "get_details": lambda: get_repo_details(msg.repo_url),
        "create_issue": lambda: create_issue(msg.repo_url, msg.issue_title, msg.issue_body),
        "add_collaborator": lambda: add_collaborator(msg.repo_url, msg.collaborator_username),
        "remove_collaborator": lambda: remove_collaborator(msg.repo_url, msg.collaborator_username),
        "get_commits": lambda: list_commits(msg.repo_url),
        "get_branches": lambda: get_branches(msg.repo_url),
        "get_user_info": lambda: get_user_info(msg.user_info),  
    }

    response = actions.get(msg.action, lambda: "Invalid action or missing required fields.")()
    

    response = str(response)


    ctx.logger.info(f"Sending message to {sender}: {response}")
    await ctx.send(sender, UAgentResponse(message=response, type=UAgentResponseType.FINAL))


agent.include(github_protocol, publish_manifest=True)

if __name__ == "__main__":
    agent.run()
