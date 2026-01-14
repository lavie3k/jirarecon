# Jirarecon

## Introduction

**Jirarecon** is a powerful and versatile reconnaissance tool designed for security professionals and researchers. It enables efficient scanning and analysis of Jira and Confluence instances to uncover sensitive information, secrets, and other critical data. With its modern terminal interface and robust feature set, Jirarecon simplifies the process of identifying vulnerabilities and extracting valuable insights.

**Author**: @lavie3k

---

## Features

- **Multi-Mode Authentication**: Supports Basic Auth (Username/Password) and Personal Access Tokens (PAT) for secure access.
- **Keyword Search**: Search for specific keywords across all projects or within a specific project/space.
- **Secret Scanning**: Detect secrets like API keys, passwords, and tokens using regex-based rules (TruffleHog + custom rules).
- **Bulk Download**: Download issues or Confluence pages as Markdown files, including attachments.
- **URL and IP Extraction**: Extract URLs and IP addresses from Jira issues or Confluence pages.
- **Rich Terminal Interface**: Beautifully formatted output with progress bars, tables, and logs using the `rich` library.
- **Project and Space Enumeration**: List all available Jira projects or Confluence spaces.
- **Pagination Support**: Handles large datasets with robust pagination.
- **Detailed Issue/Page Viewer**: View content directly in the terminal.
- **Download All Pages**: Download all pages in a specific Confluence space or across all spaces.
- **Customizable Threads**: Adjust the number of threads for faster processing.

---

## Installation

### Prerequisites

- Python 3.8+
- `pip` (Python package manager)

### Installation Steps

1. Clone the repository:
    ```bash
    git clone https://github.com/lavie3k/jirarecon.git
    cd jirarecon
    ```

2. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### Usage

Run the tool with the following command:
```bash
python jirarecon.py [SERVICE] [OPTIONS]
```

Where `[SERVICE]` is either `jira` or `confluence`.

#### Jira Mode

| Option | Description | Example |
|--------|-------------|---------|
| `-u`, `--url` | Jira instance URL (required). | `-u https://jira.example.com` |
| `-U`, `--username` | Jira username. | `-U username` |
| `-P`, `--password` | Jira password. | `-P password` |
| `-T`, `--token` | Personal Access Token. | `-T <TOKEN>` |
| `-l`, `--list-projects` | List all Jira projects. | `-l` |
| `-li`, `--list-issues` | List issues in a specific project. | `-li PROJECT_KEY` |
| `-vi`, `--view-issue` | View details of a specific issue. | `-vi ISSUE_KEY` |
| `-di`, `--download-issue` | Download a specific issue as Markdown. | `-di ISSUE_KEY` |
| `-da`, `--download-all` | Download all found issues. | `-da` |
| `-eu`, `--extract-urls` | Extract URLs from issues. | `-eu` |
| `-s`, `--search-project` | Search for keywords in a specific project. | `-s PROJECT_KEY -k keyword` |
| `-k`, `--keyword` | Keyword(s) to search. | `-k password -k token` |
| `-o`, `--out` | Output file for results. | `-o results.txt` |

#### Confluence Mode

| Option | Description | Example |
|--------|-------------|---------|
| `-u`, `--url` | Confluence instance URL (required). | `-u https://confluence.example.com` |
| `-U`, `--username` | Confluence username. | `-U username` |
| `-P`, `--password` | Confluence password. | `-P password` |
| `-T`, `--token` | Personal Access Token. | `-T <TOKEN>` |
| `-l`, `--list-spaces` | List all Confluence spaces. | `-l` |
| `-lp`, `--list-pages` | List pages in a specific space. | `-lp SPACE_KEY` |
| `-dp`, `--download-page` | Download a specific page. | `-dp PAGE_ID` |
| `-da`, `--download-all` | Download all pages in a space or all spaces. | `-da` |
| `-eu`, `--extract-urls` | Extract URLs from pages. | `-eu` |
| `-k`, `--keyword` | Keyword(s) to search. | `-k secret` |
| `--search` | Trigger search with default keywords. | `--search` |
| `-o`, `--out` | Output file for results. | `-o results.txt` |

---

## Detailed Usage Examples

### Jira Reconnaissance

1. **List all Jira projects:**
    ```bash
    python jirarecon.py jira -u https://jira.example.com -T <TOKEN> -l
    ```

2. **Search for keywords in a specific project:**
    ```bash
    python jirarecon.py jira -u https://jira.example.com -T <TOKEN> -s PROJECT_KEY -k password -k token
    ```

3. **Extract URLs from all issues in a project:**
    ```bash
    python jirarecon.py jira -u https://jira.example.com -T <TOKEN> -li PROJECT_KEY -eu
    ```

4. **Download all issues as Markdown files:**
    ```bash
    python jirarecon.py jira -u https://jira.example.com -T <TOKEN> -da
    ```

### Confluence Reconnaissance

1. **List all Confluence spaces:**
    ```bash
    python jirarecon.py confluence -u https://confluence.example.com -l
    ```

2. **List pages in a specific space:**
    ```bash
    python jirarecon.py confluence -u https://confluence.example.com -lp SPACE_KEY
    ```

3. **Download all pages in a specific space:**
    ```bash
    python jirarecon.py confluence -u https://confluence.example.com -lp SPACE_KEY -da
    ```

4. **Extract URLs from all pages in all spaces:**
    ```bash
    python jirarecon.py confluence -u https://confluence.example.com -eu
    ```

---

## Recon Modules

### Jira Reconnaissance
- **Project Enumeration**: List all accessible Jira projects.
- **Issue Analysis**: Search for keywords, extract URLs, and scan for secrets in Jira issues.
- **Bulk Download**: Save issues as Markdown files for offline analysis.

### Confluence Reconnaissance
- **Space Enumeration**: List all accessible Confluence spaces.
- **Page Analysis**: Extract URLs, IPs, and scan for sensitive data in Confluence pages.
- **Bulk Download**: Save pages and attachments for offline analysis.

---

## Licensing

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

For more information, visit the [GitHub repository](https://github.com/lavie3k/jirarecon).
