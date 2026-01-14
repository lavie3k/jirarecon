#!/usr/bin/env python3

import argparse
from email import parser
import requests
import re
import os
import sys
import json
import warnings
from urllib3.exceptions import InsecureRequestWarning
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from concurrent.futures import ThreadPoolExecutor, as_completed
from textwrap3 import wrap

# Import local modules
try:
    from rules import custom_rules
    from keywords import search_keywords
    from truffleHogRegexes.regexChecks import regexes
    from jira2markdown import convert as jira_convert
except ImportError as e:
    print(f"Error importing local modules: {e}")
    sys.exit(1)

# Rich imports for UI
try:
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    from rich.markdown import Markdown
    from rich.syntax import Syntax
except ImportError:
    print("Please install 'rich' library: pip install rich")
    sys.exit(1)

# Suppress InsecureRequestWarning
warnings.simplefilter('ignore', InsecureRequestWarning)

# Initialize Rich Console
console = Console(force_terminal=True)

results = {}

def print_banner():
    banner_text = r"""
     ██╗██╗██████╗  █████╗ ██████╗ ███████╗ ██████╗ ██████╗ ███╗   ██╗
     ██║██║██╔══██╗██╔══██╗██╔══██╗██╔════╝██╔════╝██╔══██╗████╗  ██║
     ██║██║██████╔╝███████║██████╔╝█████╗  ██║     ██║  ██║██╔██╗ ██║
██   ██║██║██╔══██╗██╔══██║██╔══██╗██╔══╝  ██║     ██║  ██║██║╚██╗██║
╚█████╔╝██║██║  ██║██║  ██║██║  ██║███████╗╚██████╗╚██████╔╝██║ ╚████║
 ╚════╝ ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝
    """
    panel = Panel(
        Text(banner_text, justify="center", style="bold cyan"),
        title="[bold white]Jirarecon[/bold white]",
        subtitle="[italic white]by @lavie3k[/italic white]",
        border_style="bright_blue",
        padding=(1, 2)
    )
    console.print(panel)

def get_output_directory(url, service_type):
    """
    Extract domain name from URL and create organized folder structure.
    Returns: FileDownload/{service_type}/{domain}/
    """
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path
    domain = domain.replace('www.', '')
    domain = domain.split(':')[0]
    base_dir = "FileDownload"
    service_dir = service_type.capitalize()  # Jira or Confluence
    output_dir = os.path.join(base_dir, service_dir, domain)
    os.makedirs(output_dir, exist_ok=True)
    return output_dir

def request_session(proxy=None):
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    if proxy:
        session.proxies = {'http': 'http://'+proxy, 'https': 'http://'+proxy}
        session.verify = False
    retries = Retry(total=5, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session

def login(url, username=None, password=None, token=None, proxy=None, service='jira'):
    req = request_session(proxy)
    if service == 'confluence':
        myself_urls = [f"{url}/rest/api/user/current", f"{url}/wiki/rest/api/user/current"]
    else:
        myself_urls = [f"{url}/rest/api/2/myself"]
    headers = {'Content-Type': 'application/json'}
    auth_method = "Token" if token else f"Basic ({username})"
    with console.status(f"[bold green]Logging in to {service.capitalize()} with {auth_method}...[/bold green]", spinner="dots"):
        try:
            if token:
                headers['Authorization'] = f"Bearer {token}"
            response = None
            success = False
            for endpoint in myself_urls:
                try:
                    if token:
                         response = req.get(endpoint, headers=headers)
                    else:
                         response = req.get(endpoint, auth=(username, password), headers=headers)
                    if response.status_code == 200:
                        success = True
                        break
                except:
                    continue
            if success and response:
                user_display = username if username else "Token User"
                try:
                    user_data = response.json()
                    if 'displayName' in user_data:
                        user_display = user_data['displayName']
                except:
                    pass
                console.print(f"[bold green][+] Successfully logged in as {user_display}[/bold green]")
                if token:
                    req.headers.update({'Authorization': f"Bearer {token}"})
                else:
                    req.auth = (username, password)
                return req
            else:
                last_code = response.status_code if response else "Unknown"
                last_text = response.text if response else "Connection Error"
                console.print(f"[bold red][-] Login failed with status code: {last_code}[/bold red]")
                console.print(f"[red]Response: {last_text}[/red]")
                sys.exit(1)
        except Exception as e:
            console.print(f"[bold red][-] Login error: {str(e)}[/bold red]")
            sys.exit(1)

def list_projects(url, req):
    projects_url = f"{url}/rest/api/2/project"
    try:
        with console.status("[cyan]Fetching projects...[/cyan]"):
            response = req.get(projects_url)
        if response.status_code == 200:
            projects = response.json()
            table = Table(title=f"Jira Projects ({len(projects)})", box=box.ROUNDED, show_lines=True)
            table.add_column("Project Key", style="cyan", no_wrap=True)
            table.add_column("Project Name", style="magenta")
            table.add_column("Project ID", style="green")
            for project in projects:
                table.add_row(
                    project.get('key', ''),
                    project.get('name', ''),
                    project.get('id', '')
                )
            console.print(table)
            return projects
        else:
            console.print(f"[red][-] Failed to fetch projects: {response.status_code}[/red]")
            return []
    except Exception as e:
        console.print(f"[red][-] Error fetching projects: {e}[/red]")
        return []

def extract_urls_and_ips(text):
    if not text:
        return [], []

    # Regex to capture http/https URLs
    url_pattern = re.compile(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[-\w._~:/?#[\]@!$&\'()*+,;=]*)?')
    urls = url_pattern.findall(str(text))

    # Regex to capture IP addresses
    ip_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
    ips = ip_pattern.findall(str(text))

    return urls, ips

def collect_urls_and_ips(fetched_data):
    all_urls = set()
    all_ips = set()
    console.print(f"[bold cyan]Extracting URLs and IPs from {len(fetched_data)} items...[/bold cyan]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Extracting...[/cyan]", total=len(fetched_data))

        for item_id, data in fetched_data.items():
            progress.update(task, advance=1)
            description = str(data.get("description", "") or "")
            comments = str(data.get("comments", "") or "")
            urls, ips = extract_urls_and_ips(description + " " + comments)
            all_urls.update(urls)
            all_ips.update(ips)

    return sorted(list(all_urls)), sorted(list(all_ips))

def save_urls_and_ips(urls, ips, filename, domain, mode):
    try:
        # Create directory structure based on domain and mode
        base_dir = "FileDownload"
        mode_dir = mode.capitalize()  # Jira or Confluence
        output_dir = os.path.join(base_dir, mode_dir, domain)
        os.makedirs(output_dir, exist_ok=True)

        # Save the file in the appropriate directory
        file_path = os.path.join(output_dir, filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("# Extracted URLs\n")
            f.write("\n".join(urls))
            f.write("\n\n# Extracted IPs\n")
            f.write("\n".join(ips))
        console.print(f"[bold green][+] Successfully saved {len(urls)} URLs and {len(ips)} IPs to {file_path}[/bold green]")
    except Exception as e:
        console.print(f"[red][-] Error saving URLs and IPs: {e}[/red]")

def extract_urls_from_text(text):
    if not text:
        return []
    url_pattern = re.compile(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[-\w._~:/?#[\]@!$&\'()*+,;=]*)?')
    return url_pattern.findall(str(text))

def collect_urls(fetched_data):
    all_urls = set()
    console.print(f"[bold cyan]Extracting URLs from {len(fetched_data)} issues...[/bold cyan]")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
        task = progress.add_task("[cyan]Extracting...[/cyan]", total=len(fetched_data))
        for issue_id, data in fetched_data.items():
            if data.get("description"):
                urls = extract_urls_from_text(data["description"])
                all_urls.update(urls)
            if data.get("comments"):
                for comment in data["comments"]:
                    urls = extract_urls_from_text(comment)
                    all_urls.update(urls)
            progress.advance(task)
    return sorted(list(all_urls))

def save_urls(urls, filename):
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write('\n'.join(urls))
        console.print(f"[bold green][+] Successfully saved {len(urls)} URLs to {filename}[/bold green]")
    except Exception as e:
        console.print(f"[red][-] Error saving URLs: {e}[/red]")

def list_project_issues(url, req, project_id):
    jql_query = f'project = "{project_id}"'
    url_endpoint = f"{url}/rest/api/2/search"
    start_at = 0
    max_results = 100
    all_issues = []
    try:
        with console.status(f"[cyan]Fetching issues for {project_id}...[/cyan]") as status:
            while True:
                params = {'jql': jql_query, 'startAt': start_at, 'maxResults': max_results, 'fields': 'key,summary,status'}
                response = req.get(url_endpoint, params=params)
                if response.status_code == 200:
                    json_response = response.json()
                    issues = json_response.get('issues', [])
                    if not issues:
                        break
                    all_issues.extend(issues)
                    start_at += len(issues)
                    status.update(f"[cyan]Fetching issues for {project_id} (Found {len(all_issues)})...[/cyan]")
                    if start_at >= json_response.get('total', 0):
                        break
                else:
                    console.print(f"[red][-] Failed to fetch issues: {response.status_code}[/red]")
                    break
        if all_issues:
            table = Table(title=f"Issues in {project_id} ({len(all_issues)})", box=box.ROUNDED)
            table.add_column("Issue Key", style="cyan", no_wrap=True)
            table.add_column("Summary", style="white")
            table.add_column("Status", style="yellow")
            for issue in all_issues[:500]:
                table.add_row(
                    issue.get('key', ''),
                    issue.get('fields', {}).get('summary', ''),
                    issue.get('fields', {}).get('status', {}).get('name', '')
                )
            if len(all_issues) > 500:
                table.add_row("...", f"... {len(all_issues)-500} more issues ...", "...")
            console.print(table)
            return all_issues
        else:
             return []
    except Exception as e:
        console.print(f"[red][-] Error fetching issues: {e}[/red]")
        return []

def search_project_keywords(url, req, project_id, keywords=None):
    if keywords is None:
        keywords = search_keywords
    console.print(f"[bold cyan][+] Searching in project {project_id} with {len(keywords)} keywords...[/bold cyan]")
    found_issues = []
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
        task = progress.add_task(f"[cyan]Searching...[/cyan]", total=len(keywords))
        for keyword in keywords:
            progress.update(task, description=f"[cyan]Searching: {keyword}[/cyan]")
            jql_query = f'project = "{project_id}" AND text ~ "{keyword}"'
            url_endpoint = f"{url}/rest/api/2/search"
            params = {'jql': jql_query, 'startAt': 0, 'maxResults': 10000, 'fields': 'key,summary,description,comment'}
            try:
                response = req.get(url_endpoint, params=params)
                if response.status_code == 200:
                    json_response = response.json()
                    issues = json_response.get('issues', [])
                    for issue in issues:
                        issue_key = issue.get('key', '')
                        if issue_key not in [item['key'] for item in found_issues]:
                            found_issues.append({
                                'key': issue_key,
                                'summary': issue.get('fields', {}).get('summary', ''),
                                'keyword': keyword,
                                'description': issue.get('fields', {}).get('description', ''),
                                'comments': [c.get('body', '') for c in issue.get('fields', {}).get('comment', {}).get('comments', [])]
                            })
            except Exception as e:
                console.print(f"[red]Error with keyword '{keyword}': {e}[/red]")
            progress.advance(task)
    if found_issues:
        table = Table(title=f"Methods Found ({len(found_issues)})", box=box.ROUNDED)
        table.add_column("Issue Key", style="cyan")
        table.add_column("Summary", style="white")
        table.add_column("Matched Keyword", style="green")
        for item in found_issues:
            table.add_row(item['key'], item['summary'], item['keyword'])
        console.print(table)
    else:
        console.print("[yellow]No issues found matching keywords.[/yellow]")
    return found_issues

def view_issue_details(url, req, issue_key):
    url_endpoint = f"{url}/rest/api/2/issue/{issue_key}"
    try:
        response = req.get(url_endpoint)
        if response.status_code == 200:
            issue = response.json()
            fields = issue.get('fields', {})
            console.print(Panel(f"[bold white]{fields.get('summary', '')}[/bold white]", title=f"Issue: {issue_key}", style="cyan"))
            grid = Table.grid(padding=1)
            grid.add_column(style="bold cyan", justify="right")
            grid.add_column(style="white")
            grid.add_row("Status:", fields.get('status', {}).get('name', 'N/A'))
            grid.add_row("Priority:", fields.get('priority', {}).get('name', 'N/A'))
            grid.add_row("Assignee:", fields.get('assignee', {}).get('displayName', 'N/A'))
            grid.add_row("Reporter:", fields.get('reporter', {}).get('displayName', 'N/A'))
            grid.add_row("Created:", fields.get('created', 'N/A'))
            grid.add_row("Updated:", fields.get('updated', 'N/A'))
            console.print(Panel(grid, title="Details", border_style="blue"))
            description = fields.get('description', '') or 'N/A'
            console.print(Panel(Markdown(description if description != 'N/A' else '_No description_'), title="Description", border_style="green"))
            comments = fields.get('comment', {}).get('comments', [])
            if comments:
                console.print(f"[bold]Comments ({len(comments)}):[/bold]")
                for idx, comment in enumerate(comments, 1):
                    author = comment.get('author', {}).get('displayName', 'Unknown')
                    date = comment.get('created', '')
                    body = comment.get('body', '')
                    console.print(Panel(body, title=f"#{idx} {author} - {date}", border_style="white", expand=False))
            else:
                console.print("[italic]No comments[/italic]")
        else:
            console.print(f"[red]Failed to fetch issue: {response.status_code}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")

def post_process_markdown(text):
    if not text:
        return text
    text = text.replace('{**}', '`')
    text = re.sub(r'<br\s*/?>', '\n', text)
    return text

def download_issue_to_markdown(url, req, issue_key, quiet=False):
    url_endpoint = f"{url}/rest/api/2/issue/{issue_key}"
    try:
        response = req.get(url_endpoint)
        if response.status_code == 200:
            issue = response.json()
            fields = issue.get('fields', {})
            sanitized_key = issue_key.replace('/', '_')
            base_output_dir = get_output_directory(url, 'jira')
            issue_dir = os.path.join(base_output_dir, sanitized_key)
            os.makedirs(issue_dir, exist_ok=True)
            markdown_content = f"# {issue_key}: {fields.get('summary', '')}\n\n"
            markdown_content += "## Information\n\n"
            markdown_content += f"- **Status**: {fields.get('status', {}).get('name', 'N/A')}\n"
            markdown_content += f"- **Priority**: {fields.get('priority', {}).get('name', 'N/A')}\n"
            markdown_content += f"- **Assignee**: {fields.get('assignee', {}).get('displayName', 'N/A')}\n"
            markdown_content += f"- **Reporter**: {fields.get('reporter', {}).get('displayName', 'N/A')}\n"
            markdown_content += f"- **Created**: {fields.get('created', 'N/A')}\n"
            markdown_content += f"- **Updated**: {fields.get('updated', 'N/A')}\n\n"
            markdown_content += "## Description\n\n"
            description = fields.get('description', '') or 'N/A'
            converted_desc = jira_convert(description)
            markdown_content += post_process_markdown(converted_desc) + "\n\n"
            markdown_content += "## Comments\n\n"
            comments = fields.get('comment', {}).get('comments', [])
            if comments:
                for idx, comment in enumerate(comments, 1):
                    author = comment.get('author', {}).get('displayName', 'Unknown')
                    created = comment.get('created', '')
                    body = comment.get('body', '')
                    converted_body = jira_convert(body)
                    markdown_content += f"### Comment {idx} - {author} ({created})\n\n"
                    markdown_content += post_process_markdown(converted_body) + "\n\n"
            else:
                markdown_content += "No comments\n\n"
            attachments = fields.get('attachment', [])
            if attachments:
                markdown_content += "## Attachments\n\n"
                for attachment in attachments:
                    filename = attachment.get('filename', 'unknown')
                    content_url = attachment.get('content', '')
                    markdown_content += f"- [{filename}]({content_url})\n"
                    try:
                        if not quiet:
                            console.print(f"[cyan]Downloading attachment: {filename}[/cyan]")
                        file_response = req.get(content_url)
                        if file_response.status_code == 200:
                            file_path = os.path.join(issue_dir, filename)
                            with open(file_path, 'wb') as f:
                                f.write(file_response.content)
                            if not quiet:
                                console.print(f"[green]Saved: {file_path}[/green]")
                    except Exception as e:
                        console.print(f"[red]Error downloading {filename}: {e}[/red]")
                markdown_content += "\n"
            markdown_file = os.path.join(issue_dir, f"{sanitized_key}.md")
            with open(markdown_file, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            if not quiet:
                console.print(f"[bold green]Issue saved to: {markdown_file}[/bold green]")
        else:
            console.print(f"[red]Failed to fetch issue: {response.status_code}[/red]")
    except Exception as e:
        console.print(f"[red]Error downloading issue: {e}[/red]")

def search_keyword(url, keyword, req):
    url_endpoint = f"{url}/rest/api/2/search"
    jql_query = f'text ~ "{keyword}"'
    start_at = 0
    max_results = 100
    found = []
    while True:
        params = {'jql': jql_query, 'startAt': start_at, 'maxResults': max_results, 'fields': 'key'}
        try:
            response = req.get(url_endpoint, params=params)
            if response.status_code != 200:
                break
            data = response.json()
            if "issues" in data:
                batch = [item["key"] for item in data["issues"]]
                if not batch:
                    break
                found.extend(batch)
                start_at += len(batch)
                if start_at >= data.get("total", 0):
                    break
            else:
                break
        except Exception:
            break
    return found

def fetch_issue_data(url, issue_id, req):
    url_endpoint = f"{url}/rest/api/2/issue/{issue_id}"
    params = {'fields': ['summary', 'description', 'comment', 'created', 'updated']}
    details = {"summary": "N/A", "description": "", "comments": []}
    try:
        response = req.get(url_endpoint, params=params)
        data = response.json()
        details["summary"] = data.get("fields", {}).get("summary", "N/A")
        details["description"] = data.get("fields", {}).get("description", "")
        if "comment" in data.get("fields", {}):
            details["comments"] = [c["body"] for c in data["fields"]["comment"]["comments"]]
    except:
        pass
    return issue_id, details

def display_scanned_issues(fetched_data):
    if not fetched_data:
        return
    table = Table(title=f"Scanned Issues ({len(fetched_data)})", box=box.ROUNDED, show_lines=True)
    table.add_column("Issue Key", style="cyan", no_wrap=True)
    table.add_column("Summary", style="white")
    for issue_id, data in fetched_data.items():
        table.add_row(issue_id, data.get("summary", "N/A"))
    console.print(table)
    console.print("\n")

def flatten_list(array):
    return [element for items in array for element in items]

def check_credentials(fetched_data):
    rules = regexes.copy()
    rules.update(custom_rules)
    compiled_rules = {}
    for rule_name, pattern_str in rules.items():
        try:
            compiled_rules[rule_name] = re.compile(pattern_str)
        except re.error:
            continue
    analyzed_results = {}
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
        task = progress.add_task("[green]Scanning...[/green]", total=len(fetched_data))
        for issue_id, data in fetched_data.items():
            output = {}
            description = data["description"]
            comments = data["comments"]
            d_match = []
            c_match = []
            for rule_name, pattern in compiled_rules.items():
                if description:
                    d_match.extend(pattern.findall(str(description), re.UNICODE))
                for comment in comments:
                    if comment:
                        c_match.extend(pattern.findall(str(comment), re.UNICODE))
            if d_match or c_match:
                output["description"] = list(set(d_match))
                output["comments"] = list(set(c_match))
                analyzed_results[issue_id] = output
            progress.advance(task)
    return analyzed_results

def display_results(results, save, out=None):
    if not results:
        console.print("[yellow]No secrets found in the scanned issues.[/yellow]")
        return
    table = Table(title="Secrets Found", box=box.ROUNDED, show_lines=True)
    table.add_column("Issue ID", style="cyan", no_wrap=True)
    table.add_column("Description Matches", style="red")
    table.add_column("Comment Matches", style="magenta")
    log_output = []
    for issue_id, data in results.items():
        desc_matches = data["description"]
        comm_matches = data["comments"]
        desc_str = "\n".join(desc_matches) if desc_matches else "--"
        comm_str = "\n".join(comm_matches) if comm_matches else "--"
        display_desc = desc_str[:500] + "..." if len(desc_str) > 500 else desc_str
        display_comm = comm_str[:500] + "..." if len(comm_str) > 500 else comm_str
        table.add_row(issue_id, display_desc, display_comm)
        if save:
            log_output.append(f"Issue: {issue_id}\nDescription Matches: {desc_str}\nComment Matches: {comm_str}\n" + "-"*40)
    console.print(table)
    console.print(f"[bold green][+] Total Issues with Secrets: {len(results)}[/bold green]")
    if save and out:
        with open(out, "w", encoding="utf-8") as f:
            f.write("Jirarecon Scan Results\n====================\n\n")
            f.write("\n\n".join(log_output))
        console.print(f"[green]Results saved to {out}[/green]")

# ---------------- Confluence helpers (patched to avoid multiple live displays) ----------------

def _silent_status(enabled=True):
    if not enabled:
        class _Dummy:
            def __enter__(self): return None
            def __exit__(self, exc_type, exc, tb): return False
        return _Dummy()
    return console.status("")

def sanitize_filename(name):
    safe = re.sub(r'[\\/*?:"<>|]', "", name or "").strip()
    safe = safe.replace('\n', ' ').replace('\r', ' ')
    return safe[:200] if len(safe) > 200 else safe

def list_confluence_spaces(url, req, silent=False):
    url_endpoint = f"{url}/rest/api/space"
    try:
        ctx = _silent_status(not silent)
        with ctx:
            response = req.get(url_endpoint, params={'limit': 500})
        if response.status_code == 200:
            data = response.json()
            spaces = data.get('results', [])
            if not silent:
                table = Table(title=f"Confluence Spaces ({len(spaces)})", box=box.ROUNDED)
                table.add_column("Key", style="cyan")
                table.add_column("Name", style="white")
                table.add_column("Type", style="yellow")
                for space in spaces:
                    table.add_row(space.get('key'), space.get('name'), space.get('type'))
                console.print(table)
            return spaces
        else:
            if not silent:
                console.print(f"[red]Failed to fetch spaces: {response.status_code}[/red]")
            return []
    except Exception as e:
        if not silent:
            console.print(f"[red]Error fetching spaces: {e}[/red]")
        return []

def list_space_pages(url, req, space_key, silent=False):
    url_endpoint = f"{url}/rest/api/content"
    params = {'spaceKey': space_key, 'limit': 500, 'type': 'page'}
    try:
        ctx = _silent_status(not silent)
        with ctx:
            response = req.get(url_endpoint, params=params)
        if response.status_code == 200:
            data = response.json()
            pages = data.get('results', [])
            if not silent:
                table = Table(title=f"Pages in {space_key} ({len(pages)})", box=box.ROUNDED)
                table.add_column("ID", style="cyan")
                table.add_column("Title", style="white")
                for page in pages:
                    table.add_row(page.get('id'), page.get('title'))
                console.print(table)
            return pages
        else:
            if not silent:
                console.print(f"[red]Failed to fetch pages: {response.status_code}[/red]")
            return []
    except Exception as e:
        if not silent:
            console.print(f"[red]Error fetching pages: {e}[/red]")
        return []

def list_all_space_pages(url, req):
    """
    Liệt kê tất cả spaces và gom toàn bộ pages của từng space, tránh lỗi nhiều live display.
    """
    pages = []
    spaces = list_confluence_spaces(url, req, silent=True) or []
    if not spaces:
        return pages
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
        task = progress.add_task("[cyan]Fetching pages across all spaces...[/cyan]", total=len(spaces))
        for sp in spaces:
            space_key = sp.get('key')
            if not space_key:
                progress.advance(task)
                continue
            ps = list_space_pages(url, req, space_key, silent=True) or []
            pages.extend(ps)
            progress.advance(task)
    return pages

def download_confluence_page(url, req, page_id):
    """
    Lưu page theo cấu trúc:
    - Nếu có attachment: FileDownload/Confluence/<domain>/<SPACE_KEY>/<Title>/<Title>.md + attachments
    - Nếu không: FileDownload/Confluence/<domain>/<SPACE_KEY>/<Title>.md
    """
    url_endpoint = f"{url}/rest/api/content/{page_id}"
    params = {'expand': 'body.storage,version,space'}
    try:
        response = req.get(url_endpoint, params=params)
        if response.status_code == 200:
            data = response.json()
            title = data.get('title', 'Untitled')
            space_key = data.get('space', {}).get('key', 'UNKNOWN_SPACE')
            body = data.get('body', {}).get('storage', {}).get('value', '')
            safe_title = sanitize_filename(title)
            base_output_dir = get_output_directory(url, 'confluence')
            space_dir = os.path.join(base_output_dir, space_key)
            os.makedirs(space_dir, exist_ok=True)

            # Check attachments
            att_url = f"{url}/rest/api/content/{page_id}/child/attachment"
            att_resp = req.get(att_url)
            attachments = []
            if att_resp.status_code == 200:
                att_data = att_resp.json()
                attachments = att_data.get('results', []) or []

            if attachments:
                # Create folder per page
                page_dir = os.path.join(space_dir, safe_title)
                os.makedirs(page_dir, exist_ok=True)
                md_path = os.path.join(page_dir, f"{safe_title}.md")
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(f"# {title}\n\n")
                    f.write(body)
                console.print(f"[green]Saved page to {md_path}[/green]")

                console.print(f"[cyan]--> Downloading {len(attachments)} attachments...[/cyan]")
                for att in attachments:
                    fname = sanitize_filename(att.get('title', 'unknown'))
                    durl = f"{url}{att.get('_links', {}).get('download', '')}"
                    try:
                        d_resp = req.get(durl)
                        if d_resp.status_code == 200:
                            with open(os.path.join(page_dir, fname), 'wb') as outf:
                                outf.write(d_resp.content)
                    except:
                        pass
                console.print(f"[green]Attachments saved under {page_dir}[/green]")
            else:
                # Save single MD directly under space folder
                md_path = os.path.join(space_dir, f"{safe_title}.md")
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(f"# {title}\n\n")
                    f.write(body)
                console.print(f"[green]Saved page to {md_path}[/green]")
        else:
            console.print(f"[red]Failed to fetch page: {response.status_code}[/red]")
    except Exception as e:
        console.print(f"[red]Error downloading page: {e}[/red]")

def search_confluence(url, req, keywords):
    url_endpoint = f"{url}/rest/api/content/search"
    found = []
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
        task = progress.add_task("[cyan]Searching Confluence...[/cyan]", total=len(keywords))
        for kw in keywords:
            cql = f'text ~ "{kw}"'
            params = {'cql': cql, 'limit': 50}
            try:
                response = req.get(url_endpoint, params=params)
                if response.status_code == 200:
                    results = response.json().get('results', [])
                    for res in results:
                        found.append({
                            'title': res.get('title'),
                            'id': res.get('id'),
                            'type': res.get('type'),
                            'keyword': kw
                        })
            except:
                pass
            progress.advance(task)
    if found:
        table = Table(title=f"Confluence Search Results ({len(found)})", box=box.ROUNDED)
        table.add_column("ID", style="cyan")
        table.add_column("Title", style="white")
        table.add_column("Type", style="yellow")
        table.add_column("Match", style="green")
        for item in found:
            table.add_row(item['id'], item['title'], item['type'], item['keyword'])
        console.print(table)
    else:
        console.print("[yellow]No results found.[/yellow]")
    return found

def fetch_confluence_page_data(url, page_id, req):
    """
    Fetch Confluence page content and attachments, including space key for structuring if needed.
    """
    url_endpoint = f"{url}/rest/api/content/{page_id}"
    params = {'expand': 'body.storage,version,space'}
    details = {"title": "N/A", "body": "", "attachments": [], "space_key": "UNKNOWN_SPACE"}
    try:
        response = req.get(url_endpoint, params=params)
        if response.status_code == 200:
            data = response.json()
            details["title"] = data.get('title', 'N/A')
            details["body"] = data.get('body', {}).get('storage', {}).get('value', '')
            details["space_key"] = data.get('space', {}).get('key', 'UNKNOWN_SPACE')
            att_url = f"{url}/rest/api/content/{page_id}/child/attachment"
            att_resp = req.get(att_url)
            if att_resp.status_code == 200:
                att_data = att_resp.json()
                attachments = att_data.get('results', [])
                if attachments:
                    for att in attachments:
                        details["attachments"].append({
                            'filename': att.get('title', 'unknown'),
                            'content_url': f"{url}{att.get('_links', {}).get('download', '')}"
                        })
    except:
        pass
    return page_id, details

def collect_confluence_urls(fetched_data):
    """
    Extract URLs and IPs from Confluence pages.
    Returns: (list of URLs, list of IPs)
    """
    all_urls = set()
    all_ips = set()
    console.print(f"[bold cyan]Extracting URLs and IPs from {len(fetched_data)} pages...[/bold cyan]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Extracting...[/cyan]", total=len(fetched_data))

        for page_id, data in fetched_data.items():
            progress.update(task, advance=1)
            urls, ips = extract_urls_and_ips(data.get("body", ""))
            all_urls.update(urls)
            all_ips.update(ips)

    return sorted(list(all_urls)), sorted(list(all_ips))

# ============ NEW: Confluence bulk download helpers ============

def _domain_from_url(url: str) -> str:
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc or "confluence"
    except:
        return "confluence"

def _build_paths(root_out: str, domain: str, space_key: str, title: str, has_attachments: bool):
    safe_space = sanitize_filename(space_key or "UNKNOWN_SPACE")
    safe_title = sanitize_filename(title or "untitled")
    base_space = os.path.join(root_out, "Confluence", domain, safe_space)
    if has_attachments:
        page_dir = os.path.join(base_space, safe_title)
        md_path = os.path.join(page_dir, f"{safe_title}.md")
        attachments_dir = page_dir
    else:
        page_dir = base_space
        md_path = os.path.join(page_dir, f"{safe_title}.md")
        attachments_dir = None
    return {"page_dir": page_dir, "md_path": md_path, "attachments_dir": attachments_dir}

def _download_single_page(session, base_url: str, page_id: str, out_root: str, console_log=False):
    # Reuse fetch_confluence_page_data to get title/space/attachments
    pid, details = fetch_confluence_page_data(base_url, page_id, session)
    title = details.get("title") or f"page-{page_id}"
    space_key = details.get("space_key") or "UNKNOWN_SPACE"
    attachments = details.get("attachments") or []
    has_attachments = len(attachments) > 0

    domain = _domain_from_url(base_url)
    paths = _build_paths(out_root, domain, space_key, title, has_attachments)
    os.makedirs(paths["page_dir"], exist_ok=True)

    # Write markdown
    md_content = f"# {title}\n\n" + (details.get("body") or "")
    with open(paths["md_path"], "w", encoding="utf-8") as f:
        f.write(md_content)

    # Download attachments if any
    if has_attachments:
        for att in attachments:
            fname = sanitize_filename(att.get("filename", "unknown"))
            durl = att.get("content_url", "")
            if not durl:
                continue
            try:
                r = session.get(durl)
                if r.status_code == 200:
                    with open(os.path.join(paths["attachments_dir"], fname), "wb") as outf:
                        outf.write(r.content)
            except:
                pass

    if console_log:
        console.log(f"Saved: [{space_key}] {title}")

def download_space_pages(session, base_url: str, space_key: str, out_root: str, console_inst: Console):
    pages = list_space_pages(base_url, session, space_key, silent=True) or []
    if not pages:
        console_inst.log(f"No pages found in space {space_key}")
        return

    total = len(pages)
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TaskProgressColumn(), console=console_inst, transient=True
    ) as progress:
        task = progress.add_task(f"Downloading {total} pages from {space_key}…", total=total)
        for p in pages:
            pid = p.get("id")
            if not pid:
                progress.advance(task, 1)
                continue
            try:
                _download_single_page(session, base_url, pid, out_root, console_log=False)
            except Exception as e:
                console_inst.log(f"[red]Failed[/red] page {pid} in {space_key}: {e}")
            finally:
                progress.advance(task, 1)

def download_all_spaces_pages(session, base_url: str, out_root: str, console_inst: Console):
    spaces = list_confluence_spaces(base_url, session, silent=True) or []
    if not spaces:
        console_inst.log("No spaces found.")
        return

    pages_by_space = {}
    total = 0
    # Preload to determine progress total, keep inner calls silent
    for sp in spaces:
        sk = sp.get("key") or "UNKNOWN_SPACE"
        try:
            ps = list_space_pages(base_url, session, sk, silent=True) or []
        except Exception as e:
            console_inst.log(f"[yellow]Skip space[/yellow] {sk}: {e}")
            ps = []
        pages_by_space[sk] = ps
        total += len(ps)

    if total == 0:
        console_inst.log("No pages found across spaces.")
        return

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TaskProgressColumn(), console=console_inst, transient=True
    ) as progress:
        task = progress.add_task(f"Downloading {total} pages from {len(pages_by_space)} spaces…", total=total)
        for sk, pages in pages_by_space.items():
            for p in pages:
                pid = p.get("id")
                if not pid:
                    progress.advance(task, 1)
                    continue
                try:
                    _download_single_page(session, base_url, pid, out_root, console_log=False)
                except Exception as e:
                    console_inst.log(f"[red]Failed[/red] page {pid} in {sk}: {e}")
                finally:
                    progress.advance(task, 1)

# ================== End NEW helpers ==================

def handle_jira(args):
    url = args.url.rstrip('/')
    proxy = args.proxy
    if proxy:
        console.print(f"[yellow][+] Using proxy: {proxy}[/yellow]")
    session = login(url, args.username, args.password, args.token, proxy, service='jira')
    if args.list_projects and not args.extract_urls:
        list_projects(url, session)
        return
    keywords_to_search = args.keyword if args.keyword else search_keywords
    found_issue_keys = set()
    if args.extract_urls:
        console.print("[bold blue]Mode: URL and IP Extraction[/bold blue]")
        if args.list_issues:
            console.print(f"[cyan]Scope: Single Project ({args.list_issues})[/cyan]")
            issues = list_project_issues(url, session, args.list_issues)
            if issues:
                found_issue_keys.update([issue['key'] for issue in issues])
        else:
            console.print("[cyan]Scope: All Projects[/cyan]")
            projects = list_projects(url, session)
            if projects:
                for proj in projects:
                    p_key = proj.get('key')
                    if p_key:
                        issues = list_project_issues(url, session, p_key)
                        if issues:
                            found_issue_keys.update([issue['key'] for issue in issues])
        console.print(f"[bold green][+] Identified {len(found_issue_keys)} issues for URL extraction[/bold green]")
        if not found_issue_keys:
            return
        console.print("[+] Fetching Issue Details for extraction...")
        fetched_data_map = {}
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[magenta]Downloading issues...[/magenta]", total=len(found_issue_keys))
            with ThreadPoolExecutor(max_workers=args.threads) as executor:
                future_to_id = {executor.submit(fetch_issue_data, url, iid, session): iid for iid in found_issue_keys}
                for future in as_completed(future_to_id):
                    try:
                        iid, details = future.result()
                        fetched_data_map[iid] = details
                    except Exception:
                        pass
                    progress.advance(task)
        extracted_urls, extracted_ips = collect_urls_and_ips(fetched_data_map)
        console.print(f"[+] Found {len(extracted_urls)} unique URLs and {len(extracted_ips)} unique IPs")
        # Extract domain from URL
        from urllib.parse import urlparse
        parsed_url = urlparse(args.url)
        domain = parsed_url.netloc or parsed_url.path
        domain = domain.replace('www.', '').split(':')[0]  # Clean domain

        if args.out:
            output_file = args.out
        else:
            output_file = "extracted_data.txt"

        save_urls_and_ips(extracted_urls, extracted_ips, output_file, domain, "jira")
        return
    if args.list_issues:
        issues = list_project_issues(url, session, args.list_issues)
        if args.download_all and issues:
            found_issue_keys.update([issue['key'] for issue in issues])
            args.keyword = [] 
            args.search_project = None
        else:
            return
    if args.view_issue:
        view_issue_details(url, session, args.view_issue)
        return
    if args.download_issue:
        download_issue_to_markdown(url, session, args.download_issue)
        return
    if args.search_project:
        if args.keyword:
             console.print(f"[+] Using custom keywords: {', '.join(args.keyword)}")
        else:
             console.print(f"[+] Using default keywords ({len(search_keywords)} keywords)")
        project_results = search_project_keywords(url, session, args.search_project, keywords_to_search)
        found_issue_keys.update([item['key'] for item in project_results])
    else:
        if args.keyword:
            console.print(f"[+] Using custom keywords: {', '.join(args.keyword)}")
        else:
            console.print(f"[+] Using default keywords ({len(search_keywords)} keywords)")
        console.print(f"[+] Initiating search across all projects with {args.threads} threads...")
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
            task = progress.add_task("[cyan]Searching keywords...[/cyan]", total=len(keywords_to_search))
            with ThreadPoolExecutor(max_workers=args.threads) as executor:
                future_to_kw = {executor.submit(search_keyword, url, kw, session): kw for kw in keywords_to_search}
                for future in as_completed(future_to_kw):
                    try:
                        keys = future.result()
                        found_issue_keys.update(keys)
                    except Exception:
                        pass
                    progress.advance(task)
    console.print(f"[bold green][+] Search returned {len(found_issue_keys)} unique tickets[/bold green]")
    if not found_issue_keys:
        return
    if args.download_all:
        console.print(f"[+] Downloading {len(found_issue_keys)} issues to 'issues/' directory...")
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
            task = progress.add_task("[cyan]Downloading issues...[/cyan]", total=len(found_issue_keys))
            with ThreadPoolExecutor(max_workers=args.threads) as executor:
                future_to_id = {executor.submit(download_issue_to_markdown, url, session, iid, True): iid for iid in found_issue_keys}
                for future in as_completed(future_to_id):
                    progress.advance(task)
        console.print("[bold green][+] Download complete.[/bold green]")
    console.print("[+] Fetching Issue Details...")
    fetched_data_map = {}
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
        task = progress.add_task("[magenta]Downloading issues...[/magenta]", total=len(found_issue_keys))
        with ThreadPoolExecutor(max_workers=args.threads) as executor:
            future_to_id = {executor.submit(fetch_issue_data, url, iid, session): iid for iid in found_issue_keys}
            for future in as_completed(future_to_id):
                try:
                    iid, details = future.result()
                    fetched_data_map[iid] = details
                except Exception:
                    pass
                progress.advance(task)
    display_scanned_issues(fetched_data_map)
    console.print(f"[bold cyan]Analyzing {len(fetched_data_map)} issues for secrets...[/bold cyan]")
    results = check_credentials(fetched_data_map)
    console.print("\n[bold white]Scan Compete.[/bold white]\n")
    display_results(results, args.out is not None, args.out)

def handle_confluence(args):
    url = args.url.rstrip('/')
    proxy = args.proxy
    if proxy:
        console.print(f"[yellow][+] Using proxy: {proxy}[/yellow]")
    session = None
    if args.username and args.password:
        session = login(url, args.username, args.password, None, proxy, service='confluence')
    elif args.token:
        session = login(url, None, None, args.token, proxy, service='confluence')
    else:
        session = request_session(proxy)

    # Download all pages in a specific space or all spaces
    if args.download_all:
        console.print("[bold blue]Mode: Download All Pages[/bold blue]")
        fetched_data_map = {}
        page_list = []

        if args.list_pages:
            space_key = args.list_pages
            console.print(f"[cyan]Scope: Single Space ({space_key})[/cyan]")
            page_list = list_space_pages(url, session, space_key, silent=False) or []
        else:
            console.print("[cyan]Scope: All Spaces[/cyan]")
            spaces = list_confluence_spaces(url, session, silent=True) or []
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
                task = progress.add_task("[cyan]Collecting pages from all spaces...[/cyan]", total=len(spaces))
                for sp in spaces:
                    skey = sp.get('key')
                    if skey:
                        ps = list_space_pages(url, session, skey, silent=True) or []
                        page_list.extend(ps)
                    progress.advance(task)

        console.print(f"[bold green][+] Identified {len(page_list)} pages for download[/bold green]")
        if not page_list:
            return

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
            task = progress.add_task("[magenta]Downloading pages...[/magenta]", total=len(page_list))
            threads = getattr(args, 'threads', 10) or 10
            with ThreadPoolExecutor(max_workers=threads) as executor:
                future_to_id = {
                    executor.submit(download_confluence_page, url, session, p.get('id')): p.get('id')
                    for p in page_list if p.get('id')
                }
                for future in as_completed(future_to_id):
                    try:
                        future.result()
                    except Exception as e:
                        console.print(f"[red][-] Error downloading page: {e}[/red]")
                    progress.advance(task)

        console.print("[bold green][+] Download complete.[/bold green]")
        return

    # Existing functionality for extracting URLs
    if args.extract_urls:
        console.print("[bold blue]Mode: URL and IP Extraction[/bold blue]")
        fetched_data_map = {}
        page_list = []
        if args.list_pages:
            space_key = args.list_pages
            console.print(f"[cyan]Scope: Single Space ({space_key})[/cyan]")
            page_list = list_space_pages(url, session, space_key, silent=False) or []
        else:
            console.print("[cyan]Scope: All Spaces[/cyan]")
            spaces = list_confluence_spaces(url, session, silent=True) or []
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
                task = progress.add_task("[cyan]Collecting pages from all spaces...[/cyan]", total=len(spaces))
                for sp in spaces:
                    skey = sp.get('key')
                    if skey:
                        ps = list_space_pages(url, session, skey, silent=True) or []
                        page_list.extend(ps)
                    progress.advance(task)

        console.print(f"[bold green][+] Identified {len(page_list)} pages for URL extraction[/bold green]")
        if not page_list:
            return

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
            task = progress.add_task("[magenta]Downloading pages...[/magenta]", total=len(page_list))
            threads = getattr(args, 'threads', 10) or 10
            with ThreadPoolExecutor(max_workers=threads) as executor:
                future_to_id = {
                    executor.submit(fetch_confluence_page_data, url, p.get('id'), session): p.get('id')
                    for p in page_list if p.get('id')
                }
                for future in as_completed(future_to_id):
                    try:
                        pid, details = future.result()
                        fetched_data_map[pid] = details
                    except Exception:
                        pass
                    progress.advance(task)

        extracted_urls, extracted_ips = collect_confluence_urls(fetched_data_map)
        console.print(f"[+] Found {len(extracted_urls)} unique URLs and {len(extracted_ips)} unique IPs")

        # Extract domain from URL
        from urllib.parse import urlparse
        parsed_url = urlparse(args.url)
        domain = parsed_url.netloc or parsed_url.path
        domain = domain.replace('www.', '').split(':')[0]  # Clean domain

        if args.out:
            output_file = args.out
        else:
            output_file = "extracted_data.txt"

        save_urls_and_ips(extracted_urls, extracted_ips, output_file, domain, "confluence")
        return

    # List/show modes
    if args.list_spaces:
        list_confluence_spaces(url, session, silent=False)
        return
    if args.list_pages:
        list_space_pages(url, session, args.list_pages, silent=False)
        return
    if args.download_page:
        download_confluence_page(url, session, args.download_page)
        return

    # Search mode
    keywords = args.keyword if args.keyword else search_keywords
    if args.search or args.keyword:
        search_confluence(url, session, keywords)

def main():
    print_banner()
    parser = argparse.ArgumentParser(description='Jirarecon - Jira & Confluence Security Reconnaissance', add_help=False)
    subparsers = parser.add_subparsers(dest='command', help='Service to recon')
    parser.add_argument('-h', '--help', action='store_true', help='Show this help message and exit')

    jira_parser = subparsers.add_parser('jira', help='Jira reconnaissance', add_help=False)
    jira_parser.add_argument('-h', '--help', action='store_true', help='Show this help message and exit')
    jira_parser.add_argument('-u', '--url', help='Jira instance URL')
    jira_parser.add_argument('-U', '--username', help='Jira username')
    jira_parser.add_argument('-P', '--password', help='Jira password')
    jira_parser.add_argument('-T', '--token', help='Personal Access Token')
    jira_parser.add_argument('-p', '--proxy', help='Proxy (e.g., 127.0.0.1:8080)')

    jira_parser.add_argument('-t', '--threads', default=10, type=int, help='Threads (default: 10)')

    jira_parser.add_argument('-l', '--list-projects', action='store_true', help='List all projects')
    jira_parser.add_argument('-li', '--list-issues', metavar='PROJECT_ID', help='List issues in a project')
    jira_parser.add_argument('-vi', '--view-issue', metavar='ISSUE_KEY', help='View issue details')
    jira_parser.add_argument('-di', '--download-issue', metavar='ISSUE_KEY', help='Download issue as markdown')
    jira_parser.add_argument('-da', '--download-all', action='store_true', help='Download all found issues')
    jira_parser.add_argument('-eu', '--extract-urls', action='store_true', help='Extract URLs from issues')
    jira_parser.add_argument('-s', '--search-project', metavar='PROJECT_ID', help='Search in specific project')
    jira_parser.add_argument('-k', '--keyword', metavar='KEYWORD', action='append', help='Keyword to search')
    jira_parser.add_argument('-o', '--out', help='Output file')
    
    conf_parser = subparsers.add_parser('confluence', help='Confluence reconnaissance', add_help=False)
    conf_parser.add_argument('-h', '--help', action='store_true', help='Show this help message and exit')
    conf_parser.add_argument('-u', '--url', help='Confluence instance URL')
    conf_parser.add_argument('-U', '--username', help='Username')
    conf_parser.add_argument('-P', '--password', help='Password')
    conf_parser.add_argument('-T', '--token', help='Personal Access Token')
    conf_parser.add_argument('-p', '--proxy', help='Proxy')
    conf_parser.add_argument('-t', '--threads', default=10, type=int, help='Threads (default: 10)')
    conf_parser.add_argument('-l', '--list-spaces', action='store_true', help='List all spaces (projects)')
    conf_parser.add_argument('-lp', '--list-pages', metavar='SPACE_KEY', help='List pages in a space')
    conf_parser.add_argument('-dp', '--download-page', metavar='PAGE_ID', help='Download page content & attachments')
    conf_parser.add_argument('-ds', "--download-space", type=str, help="Download all pages in a specific Confluence space (SPACE_KEY)")
    conf_parser.add_argument('-da',"--download-all", action="store_true", help="Download all Confluence pages in all spaces")
    conf_parser.add_argument('-k', '--keyword', metavar='KEYWORD', action='append', help='Keyword to search')
    conf_parser.add_argument('--search', action='store_true', help='Trigger search with default keywords if no -k provided')

    conf_parser.add_argument('-eu', '--extract-urls', action='store_true', help='Extract URLs from pages')

    conf_parser.add_argument('-o', '--out', help='Output file')
    conf_parser.add_argument("--output-dir", type=str, default="FileDownload", help="Root output folder")

    if len(sys.argv) == 1:
        print(parser.format_help())
        sys.stdout.flush()
        sys.exit(1)

    if '-h' in sys.argv or '--help' in sys.argv:
        if 'jira' in sys.argv:
            print(jira_parser.format_help())
        elif 'confluence' in sys.argv:
            print(conf_parser.format_help())
        else:
            print(parser.format_help())
        sys.stdout.flush()
        sys.exit(0)

    try:
        args, unknown = parser.parse_known_args()
    except Exception as e:
        console.print(f"[red]Error parsing arguments: {e}[/red]")
        sys.exit(1)

    if not args.command:
        print(parser.format_help())
        sys.stdout.flush()
        sys.exit(1)

    if args.command == 'jira':
        if not (args.token or (args.username and args.password)):
            console.print("[bold red]Error: You must provide either a Token (-T) OR Username (-U) and Password (-P).[/bold red]")
            sys.exit(1)
        if not args.url:
            console.print("[bold red]Error: Jira URL (-u) is required.[/bold red]")
            print(jira_parser.format_help())
            sys.stdout.flush()
            sys.exit(1)
        if not (args.list_projects or args.list_issues or args.view_issue or 
                args.download_issue or args.download_all or args.extract_urls or 
                args.search_project or args.keyword):
             print(jira_parser.format_help())
             sys.stdout.flush()
             sys.exit(1)
        handle_jira(args)

    elif args.command == 'confluence':
        if not args.url:
            console.print("[bold red]Error: Confluence URL (-u) is required.[/bold red]")
            print(conf_parser.format_help())
            sys.stdout.flush()
            sys.exit(1)
        if not (args.list_spaces or args.list_pages or args.download_page or 
                args.keyword or args.search or args.extract_urls or
                args.download_all or args.download_space):
             print(conf_parser.format_help())
             sys.stdout.flush()
             sys.exit(1)
        handle_confluence(args)

if __name__ == "__main__":
    main()
