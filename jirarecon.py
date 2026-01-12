#!/usr/bin/env python3

import argparse
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
console = Console()

# Global variable for results, though we will try to keep it local where possible
# Keeping these for compatibility if needed, but refactoring main logic to be cleaner
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

def login(url, username=None, password=None, token=None, proxy=None):
    req = request_session(proxy)
    myself_url = f"{url}/rest/api/2/myself"
    headers = {'Content-Type': 'application/json'}
    
    auth_method = "Token" if token else f"Basic ({username})"
    
    with console.status(f"[bold green]Logging in with {auth_method}...[/bold green]", spinner="dots"):
        try:
            if token:
                headers['Authorization'] = f"Bearer {token}"
                response = req.get(myself_url, headers=headers)
            else:
                response = req.get(myself_url, auth=(username, password), headers=headers)
                
            if response.status_code == 200:
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
                console.print(f"[bold red][-] Login failed with status code: {response.status_code}[/bold red]")
                console.print(f"[red]Response: {response.text}[/red]")
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

def extract_urls_from_text(text):
    if not text:
        return []
    # Regex to capture http/https URLs
    url_pattern = re.compile(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[-\w._~:/?#[\]@!$&\'()*+,;=]*)?')
    return url_pattern.findall(str(text))

def collect_urls(fetched_data):
    all_urls = set()
    console.print(f"[bold cyan]Extracting URLs from {len(fetched_data)} issues...[/bold cyan]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Extracting...[/cyan]", total=len(fetched_data))
        
        for issue_id, data in fetched_data.items():
            # Check description
            if data.get("description"):
                urls = extract_urls_from_text(data["description"])
                all_urls.update(urls)
            
            # Check comments
            if data.get("comments"):
                for comment in data["comments"]:
                    urls = extract_urls_from_text(comment)
                    all_urls.update(urls)
                    
            progress.advance(task)
            
    return sorted(list(all_urls))

def save_urls(urls, filename):
    try:
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
            
            # Show only first 500 rows to avoid cluttering terminal if list is huge
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
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
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
            
            # Grid for details
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
    # Implementation remains similar but with richer output logs
    url_endpoint = f"{url}/rest/api/2/issue/{issue_key}"
    try:
        response = req.get(url_endpoint)
        if response.status_code == 200:
            issue = response.json()
            fields = issue.get('fields', {})
            
            sanitized_key = issue_key.replace('/', '_')
            issue_dir = os.path.join('issues', sanitized_key)
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

# Optimization: Search function returns data instead of modifying global list
def search_keyword(url, keyword, req):
    url_endpoint = f"{url}/rest/api/2/search"
    jql_query = f'text ~ "{keyword}"'
    start_at = 0
    max_results = 100
    found = []
    
    while True:
        params = {
            'jql': jql_query, 
            'startAt': start_at, 
            'maxResults': max_results, 
            'fields': 'key'
        }
        try:
            response = req.get(url_endpoint, params=params)
            if response.status_code != 200:
                # console.print(f"[red]Search failed for {keyword}: {response.status_code}[/red]")
                break
                
            data = response.json()
            if "issues" in data:
                batch = [item["key"] for item in data["issues"]]
                if not batch:
                    break
                found.extend(batch)
                start_at += len(batch)
                
                # Check if we've fetched all results
                if start_at >= data.get("total", 0):
                    break
            else:
                break
        except Exception:
            break
            
    return found

# Optimization: Fetch function returns data
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
    # Original logic optimized with precompiled regexes
    # console.print(f"[bold cyan]Analyzing {len(fetched_data)} issues for secrets...[/bold cyan]")
    
    rules = regexes.copy()
    rules.update(custom_rules)
    
    # Precompile regexes
    compiled_rules = {}
    for rule_name, pattern_str in rules.items():
        try:
            compiled_rules[rule_name] = re.compile(pattern_str)
        except re.error:
            continue

    analyzed_results = {}
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
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
            
            # If matches found, add to results
            if d_match or c_match:
                output["description"] = list(set(d_match)) # De-duplicate
                output["comments"] = list(set(c_match))    # De-duplicate
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
    
    # Prepare data for generic logging
    log_output = []
    
    for issue_id, data in results.items():
        desc_matches = data["description"]
        comm_matches = data["comments"]
        
        desc_str = "\n".join(desc_matches) if desc_matches else "--"
        comm_str = "\n".join(comm_matches) if comm_matches else "--"
        
        # Truncate for display if too long
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

def main():
    print_banner()
    
    argparser = argparse.ArgumentParser(description='Jirarecon, Jira Secrets Hunter')
    argparser.add_argument('-u', '--url', help = 'jira instance url', required = True)
    argparser.add_argument('-U', '--username', help = 'jira username')
    argparser.add_argument('-P', '--password', help = 'jira password')
    argparser.add_argument('-T', '--token', help = 'jira personal access token')
    argparser.add_argument('-t', '--threads', default = 10, help = 'default: 10', type = int)
    argparser.add_argument('-o', '--out', help = 'file to save output to')
    argparser.add_argument('-p', '--proxy', help = 'proxy to use, eg: 127.0.0.1:8080')
    argparser.add_argument('-l', '--list-projects', action='store_true', help = 'list all jira projects')
    argparser.add_argument('-li','--list-issues', metavar = 'project_id', help = 'list all issues in a project')
    argparser.add_argument('-vi','--view-issue', metavar = 'issue_key', help = 'view detailed content of an issue')
    argparser.add_argument('-di','--download-issue', metavar = 'issue_key', help = 'download issue as markdown')
    argparser.add_argument('-da','--download-all', action='store_true', help = 'download all found issues as markdown')
    argparser.add_argument('-eu', '--extract-urls', action='store_true', help = 'extract URLs from issues (use with -li for specific project, or default to all projects)')
    argparser.add_argument('-s','--search-project', metavar = 'project_id', help = 'search for keywords in a specific project')
    argparser.add_argument('-k', '--keyword', metavar = 'keyword', action='append', help = 'specific keyword to search')
    
    args = argparser.parse_args()
    
    # Validate authentication arguments
    if args.token:
        pass
    elif args.username and args.password:
        pass
    else:
        console.print("[bold red]Error: You must provide either a Token (-T) OR Username (-U) and Password (-P).[/bold red]")
        sys.exit(1)
    
    url = args.url.rstrip('/')
    
    proxy = args.proxy
    if proxy:
        console.print(f"[yellow][+] Using proxy: {proxy}[/yellow]")
        
    session = login(url, args.username, args.password, args.token, proxy)
    
    if args.list_projects and not args.extract_urls:
        list_projects(url, session)
        return
        
    keywords_to_search = args.keyword if args.keyword else search_keywords
    
    found_issue_keys = set()
    
    # URL Extraction Mode
    if args.extract_urls:
        console.print("[bold blue]Mode: URL Extraction[/bold blue]")
        
        # 1. Determine Scope
        if args.list_issues:
            # Single Project Scope
            console.print(f"[cyan]Scope: Single Project ({args.list_issues})[/cyan]")
            issues = list_project_issues(url, session, args.list_issues)
            if issues:
                found_issue_keys.update([issue['key'] for issue in issues])
        else:
            # All Projects Scope
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

        # 2. Fetch Details
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
                    
        # 3. Extract URLs
        extracted_urls = collect_urls(fetched_data_map)
        console.print(f"[+] Found {len(extracted_urls)} unique URLs")
        
        # 4. Save
        output_file = args.out if args.out else "extracted_urls.txt"
        save_urls(extracted_urls, output_file)
        
        return

    if args.list_issues:
        issues = list_project_issues(url, session, args.list_issues)
        if args.download_all and issues:
            found_issue_keys.update([issue['key'] for issue in issues])
            # Skip search phase since we already have the target keys
            args.keyword = [] # Clear keywords to avoid search phase
            args.search_project = None
        else:
            return
        
    if args.view_issue:
        view_issue_details(url, session, args.view_issue)
        return
        
    if args.download_issue:
        download_issue_to_markdown(url, session, args.download_issue)
        return
    
    # Phase 1: Search
    if args.search_project:
        if args.keyword:
             console.print(f"[+] Using custom keywords: {', '.join(args.keyword)}")
        else:
             console.print(f"[+] Using default keywords ({len(search_keywords)} keywords)")
        
        project_results = search_project_keywords(url, session, args.search_project, keywords_to_search)
        found_issue_keys.update([item['key'] for item in project_results])
        
    else:
        # Global Search
        if args.keyword:
            console.print(f"[+] Using custom keywords: {', '.join(args.keyword)}")
        else:
            console.print(f"[+] Using default keywords ({len(search_keywords)} keywords)")
            
        console.print(f"[+] Initiating search across all projects with {args.threads} threads...")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
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
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Downloading issues...[/cyan]", total=len(found_issue_keys))
            
            with ThreadPoolExecutor(max_workers=args.threads) as executor:
                future_to_id = {executor.submit(download_issue_to_markdown, url, session, iid, True): iid for iid in found_issue_keys}
                for future in as_completed(future_to_id):
                    progress.advance(task)
        console.print("[bold green][+] Download complete.[/bold green]")

    # Phase 2: Fetch
    console.print("[+] Fetching Issue Details...")
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
    
    # NEW: Display the list of all scanned issues
    display_scanned_issues(fetched_data_map)
                
    # Phase 3: Analyze
    console.print(f"[bold cyan]Analyzing {len(fetched_data_map)} issues for secrets...[/bold cyan]")
    results = check_credentials(fetched_data_map)
    
    # Phase 4: Display
    console.print("\n[bold white]Scan Compete.[/bold white]\n")
    display_results(results, args.out is not None, args.out)

if __name__ == "__main__":
    main()
