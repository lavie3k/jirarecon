# jirarecon

**jirarecon** (formerly jirarecon) is a powerful Jira Secrets Hunter and Reconnaissance tool designed to scan Jira instances for sensitive information and secrets. It supports authentication via username/password or Personal Access Token (PAT) and features a modern, rich terminal interface.

**Author**: @lavie3k

---

## Features

*   **Multi-mode Authentication**: Login using standard Basic Auth (Username/Password) or Jira Personal Access Tokens (Bearer Auth).
*   **Keyword Search**: Search for specific keywords either globally across all accessible projects or within a specific project.
*   **Secret Scanning**: Automatically analyzes found issues (descriptions and comments) using a set of regex rules (TruffleHog based + custom rules) to find potential secrets like API keys, passwords, and tokens.
*   **Bulk Download**: Download found issues as Markdown files, including attachments.
*   **Rich UI**: Beautiful terminal output with progress bars, tables, and formatted logs using the `rich` library.
*   **Pagination**: Robust handling of large result sets with pagination support.
*   **Project Enumeration**: List all available projects and their IDs.
*   **Issue Viewer**: View detailed content of a single issue directly in the terminal without downloading.

## Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/lavie3k/jirarecon.git
    cd jirarecon
    ```

2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

```bash
python jirarecon.py [OPTIONS]
```

### Authentication

**Using Username & Password:**
```bash
python jirarecon.py -u https://jira.example.com -U username -P password [OPTIONS]
```

**Using Personal Access Token:**
```bash
python jirarecon.py -u https://jira.example.com -T <YOUR_TOKEN> [OPTIONS]
```

### Key Commands

| Option | Description | Example |
| :--- | :--- | :--- |
| `-u`, `--url` | Jira Instance URL (Required) | `-u https://jira.example.com` |
| `-k`, `--keyword` | Keyword to search (can use multiple) | `-k password -k "access key"` |
| `-s`, `--search-project`| Search for keywords only within a specific project | `-s PROJECT_KEY -k password` |
| `-da`, `--download-all` | Download **all** found issues (from search or list) as Markdown | `--download-all` |
| `-l`, `--list-projects` | List all available projects | `-l` |
| `-li`, `--list-issues` | List issues in a specific project | `-li PROJECT_KEY` |
| `-vi`, `--view-issue` | View details of a specific issue | `-vi PROJECT-123` |

### Examples

**1. Scan specifically for "password" and "token" globally:**
```bash
python jirarecon.py -u https://jira.target.com -T <TOKEN> -k password -k token
```

**2. List all issues in project "DEV" and download them all:**
```bash
python jirarecon.py -u https://jira.target.com -T <TOKEN> -li DEV --download-all
```
*Note: This will fetch all issues in the project, skip the keyword search phase, download them to `issues/DEV_XXX.md`, and then scan them for secrets.*

**3. Search for "aws_key" in project "OPS" and download matches:**
```bash
python jirarecon.py -u https://jira.target.com -T <TOKEN> -s OPS -k aws_key --download-all
```

**4. View a single issue in the terminal:**
```bash
python jirarecon.py -u https://jira.target.com -T <TOKEN> -vi OPS-101
```

## Output

*   **Secrets**: Secrets found during analysis are displayed in a table at the end of the run.
*   **Downloaded Issues**: If `--download-all` or `-di` is used, issues are saved in the `issues/` directory, organized by issue key.
*   **Logs**: You can save the output to a file using `-o <filename>`.
