
# GitHub Repository Management Agent

This GitHub Repository Management Agent enables users to interact with GitHub repositories, offering features such as retrieving repository details, creating issues, comparing repositories, listing issues, and fetching the README content. It uses the Fetch.ai uAgents framework to manage these interactions asynchronously.

## 📌 Features

- **Get Repository Details**: Retrieve essential information such as name, description, stars, forks, and open issues for any GitHub repository.
- **Create Issues**: Quickly create new issues in a specified repository, providing both a title and body for the issue.
- **Compare Repositories**: Compare two repositories by analyzing their descriptions, stars, forks, and open issues.
- **List Issues**: View all open issues in a repository, with titles and issue numbers.
- **Fetch README Content**: Retrieve and display the content of a repository's README file.

## 🛠️ Setup Instructions

1. **Clone the Repository**:

   ```bash
   git clone https://github.com/your_username/github-agent
   cd github-agent
   ```

2. **Install Dependencies**:
   Make sure you have Python installed. Then, install the required packages.

   ```bash
   pip install requests uagents
   ```

3. **Configure GitHub API Tokens**:
   Replace the placeholders in the code (`GITHUB_TOKEN_DETAILS` and `GITHUB_TOKEN_ISSUE`) with your actual GitHub API tokens for authenticating requests.

4. **Run the Agent**:

   ```bash
   python your_script_name.py
   ```

5. **Agent Protocols**:
   The agent uses a protocol to handle different types of requests (e.g., retrieving repository details, creating issues). Each request follows the `GitHubRepoRequest` model and sends a response using `UAgentResponse`.

## 🧑‍💼 Business Model

This agent could be monetized as an API service to help developers or teams manage GitHub repositories more efficiently. Potential clients include:

- **Development Teams**: Automate repository management tasks such as issue tracking and documentation updates.
- **Project Managers**: Use the agent to compare project metrics, like stars and forks, when evaluating open-source projects.
- **Education & Training**: Teaching GitHub workflows to new developers with automated assistance.
  
## 📖 Usage

### Example Commands

Below are examples for each command, detailing the inputs and the responses generated by the agent:

1. **Get Repository Details**

   ```python
   # Send a request to get details of a repository
   agent.send_message({
       "repo_url": "https://github.com/user/repo",
       "action": "get_details"
   })
   ```

2. **Create Issue**

   ```python
   # Create a new issue in the specified repository
   agent.send_message({
       "repo_url": "https://github.com/user/repo",
       "action": "create_issue",
       "issue_title": "Bug Report",
       "issue_body": "Detailed description of the issue..."
   })
   ```

3. **Compare Repositories**

   ```python
   # Compare metrics between two repositories
   agent.send_message({
       "repo_url": "https://github.com/user/repo1",
       "action": "compare",
       "compare_repo_url": "https://github.com/user/repo2"
   })
   ```

4. **List Issues**

   ```python
   # List all issues in a specified repository
   agent.send_message({
       "repo_url": "https://github.com/user/repo",
       "action": "list_issues"
   })
   ```

5. **Fetch README Content**

   ```python
   # Fetch and decode the README content from the repository
   agent.send_message({
       "repo_url": "https://github.com/user/repo",
       "action": "get_readme"
   })
   ```

## 🤝 Contributing

Feel free to fork this repository, submit pull requests, or raise issues for any bugs or enhancements. Contributions are always welcome!

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

This README template provides a well-rounded guide to understanding, configuring, and using the GitHub Repository Management Agent. Let me know if you’d like further customization or specific adjustments