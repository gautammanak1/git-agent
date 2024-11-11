
# GitHub Repository Management Agent

This GitHub Repository Management Agent enables users to efficiently manage GitHub repositories through automated interactions. Using the Fetch.ai `uAgents` framework, this agent provides asynchronous features for retrieving repository details, managing collaborators, creating and listing issues, comparing repositories, fetching README content, and more. It’s designed for developers, project managers, and educators looking to simplify and automate repository tasks.

## 📌 Features

The GitHub Repository Management Agent includes the following core functionalities:

1. **Get Repository Details**  
   Retrieve essential information about any GitHub repository, including its name, description, stars, forks, and open issues count.

2. **Create Issues**  
   Quickly create new issues in a specified repository by providing a title and body for the issue.

3. **Compare Repositories**  
   Compare two repositories based on metrics like stars, forks, and open issues, helping users evaluate and benchmark open-source projects.

4. **List Issues**  
   View all open issues in a repository, displaying titles and issue numbers for easy tracking.

5. **Fetch README Content**  
   Retrieve and display the content of a repository's README file, offering insight into project details and setup instructions.

6. **Add Collaborator**  
   Add a collaborator to a repository by providing their GitHub username, allowing them access to contribute.

7. **Remove Collaborator**  
   Remove a collaborator from a repository using their GitHub username to revoke their access.

8. **List Commits**  
   Retrieve recent commits in the specified repository, providing a snapshot of recent changes and contributors.

9. **Get Branches**  
   Retrieve a list of all branches in the repository, helpful for tracking parallel development work.

10. **Get User Info**  
    Fetch detailed information about a GitHub user, including their public repositories, followers, and other profile data.

## 🛠️ Setup Instructions

Follow these steps to set up and run the GitHub Repository Management Agent.

### Prerequisites

- **Python 3.8+**: Ensure Python is installed on your system.

### Installation

1. **Clone the Repository**

   ```bash
   git clone https://github.com/your_username/github-agent
   cd github-agent
   ```

2. **Install Dependencies**
   Install the necessary packages using pip:

   ```bash
   pip install requests uagents
   ```

3. **Configure GitHub API Tokens**
   Replace placeholders in the code (`GITHUB_TOKEN_DETAILS` and `GITHUB_TOKEN_ISSUE`) with your actual GitHub API tokens to authenticate requests to GitHub.

### Running the Agent

Start the agent by running the main script:

```bash
python your_script_name.py
```

## 🧑‍💼 Business Model

This agent can be monetized as a service to assist developers and project teams in managing GitHub repositories. Potential clients and use cases include:

- **Development Teams**: Automate repository management tasks, such as issue tracking and documentation updates.
- **Project Managers**: Use the agent to compare project metrics, like stars and forks, when evaluating or benchmarking open-source projects.
- **Education & Training**: Teach GitHub workflows and project management to new developers through automated, hands-on assistance.

## 📖 Usage

Each feature is accessible via specific actions sent in the `GitHubRepoRequest` model. Below are examples of usage for each feature, detailing the inputs and expected responses.

### Example Commands

1. **Get Repository Details**

   ```python
   request = GitHubRepoRequest(repo_url="https://github.com/user/repo", action="get_details")
   ```

   Retrieves the name, description, stars, forks, and open issues count of the specified repository.

2. **Create Issue**

   ```python
   request = GitHubRepoRequest(repo_url="https://github.com/user/repo", action="create_issue", issue_title="Bug Report", issue_body="Detailed description of the issue...")
   ```

   Creates a new issue in the specified repository, with a custom title and description.

3. **Compare Repositories**

   ```python
   request = GitHubRepoRequest(repo_url="https://github.com/user/repo1", action="compare", compare_repo_url="https://github.com/user/repo2")
   ```

   Compares metrics like stars, forks, and open issues between two repositories.

4. **List Issues**

   ```python
   request = GitHubRepoRequest(repo_url="https://github.com/user/repo", action="list_issues")
   ```

   Lists all open issues in the specified repository, displaying each issue’s title and number.

5. **Fetch README Content**

   ```python
   request = GitHubRepoRequest(repo_url="https://github.com/user/repo", action="get_readme")
   ```

   Fetches and displays the README content of the specified repository.

6. **Add Collaborator**

   ```python
   request = GitHubRepoRequest(repo_url="https://github.com/user/repo", action="add_collaborator", collaborator_username="username")
   ```

   Adds a collaborator to the specified repository by GitHub username.

7. **Remove Collaborator**

   ```python
   request = GitHubRepoRequest(repo_url="https://github.com/user/repo", action="remove_collaborator", collaborator_username="username")
   ```

   Removes a collaborator from the specified repository using their GitHub username.

8. **List Commits**

   ```python
   request = GitHubRepoRequest(repo_url="https://github.com/user/repo", action="get_commits")
   ```

   Lists recent commits in the specified repository, showing commit messages and timestamps.

9. **Get Branches**

   ```python
   request = GitHubRepoRequest(repo_url="https://github.com/user/repo", action="get_branches")
   ```

   Retrieves a list of all branches in the specified repository.

10. **Get User Info**

    ```python
    request = GitHubRepoRequest(action="get_user_info", user_info="username")
    ```

    Fetches detailed information about a specified GitHub user, including their public repositories, followers, and other profile details.

## Agent Protocols

The agent processes different requests by following specific protocols for each action. Each request is handled using the `GitHubRepoRequest` model and sends a response back using `UAgentResponse`, ensuring smooth interaction with the GitHub API.

## 🤝 Contributing

Contributions are welcome! If you want to contribute:

1. **Fork the repository**
2. **Create a new branch** with a descriptive name
3. **Make your changes**
4. **Submit a pull request** with a summary of your changes

Please raise any issues for bugs or suggested enhancements.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---
