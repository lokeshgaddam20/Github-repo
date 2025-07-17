import os
import sys
import subprocess
import shutil
import json
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from dotenv import load_dotenv
import csv
import time

load_dotenv()

token = os.getenv('API_TOKEN_GITHUB_DNB_MAIN')
API_URL = "https://api.github.com/graphql"

if not token:
    raise Exception("GitHub token not found. Please set the token environment variable.")

HEADERS = {
    "Authorization": f"bearer {token}",
    "Content-Type": "application/json"
}

# Rate limiting
RATE_LIMIT_DELAY = 0.1  # seconds between requests

# Fetches Pull Request statistics
PR_METRICS_QUERY = """
query pullRequestMetrics($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    totalPRs: pullRequests {
      totalCount
    }
    openPRs: pullRequests(states: [OPEN]) {
      totalCount
    }
    closedPRs: pullRequests(states: [CLOSED]) {
      totalCount
    }
    mergedPRs: pullRequests(states: [MERGED]) {
      totalCount
    }
    draftPRs: pullRequests(first: 100, states: [OPEN]) {
      nodes {
        isDraft
      }
    }
    recentPRsForReviews: pullRequests(last: 100, states: [MERGED, CLOSED]) {
      nodes {
        reviews(first: 50) {
          totalCount
          nodes {
            state
          }
        }
      }
    }
  }
}
"""

# Fetches commit history for contributor analysis.
REPO_STATS_QUERY = """
query repoStats($owner: String!, $name: String!, $since: GitTimestamp!) {
  repository(owner: $owner, name: $name) {
    totalCommits: defaultBranchRef {
      target {
        ... on Commit {
          history {
            totalCount
          }
        }
      }
    }
    yearlyCommits: defaultBranchRef {
      target {
        ... on Commit {
          history(since: $since) {
            totalCount
          }
        }
      }
    }
  }
}
"""

# Fetches commit history for contributor analysis.
COMMIT_HISTORY_QUERY = """
query commitHistory($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    createdAt
    defaultBranchRef {
      target {
        ... on Commit {
          history(first: 100, after: $cursor) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              committedDate
              additions
              deletions
              author {
                user {
                  login
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

# Fetches recent pull requests to count contributions per author
PRS_BY_AUTHOR_QUERY = """
query prAuthors($owner: String!, $name: String!, $cursor: String) {
    repository(owner: $owner, name: $name) {
        pullRequests(first: 100, after: $cursor, orderBy: {field: CREATED_AT, direction: DESC}) {
            pageInfo {
                hasNextPage
                endCursor
            }
            nodes {
                author {
                    login
                }
            }
        }
    }
}
"""

def run_query(query, variables):
    """Executes a GraphQL query and returns the data with rate limiting."""
    time.sleep(RATE_LIMIT_DELAY)  # Simple rate limiting
    
    try:
        response = requests.post(API_URL, headers=HEADERS, json={'query': query, 'variables': variables})
        response.raise_for_status()
        result = response.json()
        
        if 'errors' in result:
            raise Exception(f"GraphQL query failed: {result['errors']}")
        
        return result.get('data', {})
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        raise

def count_lines_in_file(file_path):
    """Count non-empty lines in a file."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            return sum(1 for line in file if line.strip())
    except:
        return 0

def is_code_file(file_path):
    """Check if a file is a code file based on extension and location."""
    skip_patterns = ['.git/', '__pycache__', 'node_modules', '.venv', 'dist', 'build']
    file_str = str(file_path)
    
    for pattern in skip_patterns:
        if pattern in file_str:
            return False
    
    code_extensions = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp', '.h', '.hpp',
        '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.scala', '.sh',
        '.html', '.css', '.scss', '.xml', '.json', '.yaml', '.yml', '.sql',
        '.md', '.txt', '.dockerfile'
    }
    
    return (file_path.suffix.lower() in code_extensions or 
            file_path.name.lower() in ['makefile', 'dockerfile'])

def calculate_loc(repo_path):
    """Calculate lines of code and file statistics."""
    print("Calculating LOC and files...")
    total_lines = 0
    file_count = 0
    file_stats = {}
    
    for file_path in Path(repo_path).rglob('*'):
        if file_path.is_file() and is_code_file(file_path):
            lines = count_lines_in_file(file_path)
            if lines > 0:
                relative_path = str(file_path.relative_to(repo_path))
                file_stats[relative_path] = lines
                total_lines += lines
                file_count += 1
    
    return total_lines, file_count, file_stats

def calculate_review_metrics(data):
    """Calculate review metrics from PR data."""
    recent_prs = data.get('recentPRsForReviews', {}).get('nodes', [])
    
    reviewed_pr_count = 0
    total_reviews = 0
    total_approvals = 0
    total_change_requests = 0
    
    for pr in recent_prs:
        reviews_data = pr.get('reviews', {})
        if reviews_data and reviews_data['totalCount'] > 0:
            reviewed_pr_count += 1
            total_reviews += reviews_data['totalCount']
            for review in reviews_data.get('nodes', []):
                if review['state'] == 'APPROVED':
                    total_approvals += 1
                elif review['state'] == 'CHANGES_REQUESTED':
                    total_change_requests += 1

    reviews_per_pr = (total_reviews / reviewed_pr_count) if reviewed_pr_count > 0 else 0
    approval_rate = (total_approvals / total_reviews) if total_reviews > 0 else 0
    change_requests_rate = (total_change_requests / total_reviews) if total_reviews > 0 else 0

    return {
        "reviews_per_pr": round(reviews_per_pr, 2),
        "approval_rate": round(approval_rate, 2),
        "change_requests_rate": round(change_requests_rate, 2)
    }

def get_pull_request_metrics(owner, repo):
    """Fetches and processes pull request metrics."""
    variables = {"owner": owner, "name": repo}
    data = run_query(PR_METRICS_QUERY, variables)
    
    if not data or 'repository' not in data:
        return {}
    
    repo_data = data['repository']
    
    # Count draft PRs
    draft_count = 0
    for pr in repo_data.get('draftPRs', {}).get('nodes', []):
        if pr.get('isDraft'):
            draft_count += 1
    
    # Calculate review metrics
    review_metrics = calculate_review_metrics(repo_data)
    
    return {
        "total": repo_data.get('totalPRs', {}).get('totalCount', 0),
        "open": repo_data.get('openPRs', {}).get('totalCount', 0),
        "closed": repo_data.get('closedPRs', {}).get('totalCount', 0),
        "merged": repo_data.get('mergedPRs', {}).get('totalCount', 0),
        "draft": draft_count,
        **review_metrics
    }

def get_repo_stats(owner, repo):
    """Fetches overall repository statistics, including yearly commits."""
    variables = {
        "owner": owner,
        "name": repo,
        "since": (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
    }
    data = run_query(REPO_STATS_QUERY, variables)
    return data.get("repository", {})

def get_contributor_metrics(owner, repo, max_pages=10):
    """
    Fetches and processes contributor metrics based on recent commit activity.
    Fixed version with proper error handling and pagination.
    """
    contributors = defaultdict(lambda: {'commits': 0, 'additions': 0, 'deletions': 0})
    commit_counts_by_year = defaultdict(int)
    active_30_days = set()
    active_90_days = set()
    
    now_utc = datetime.now(timezone.utc)
    since_30 = now_utc - timedelta(days=30)
    since_90 = now_utc - timedelta(days=90)

    # Process commit history
    cursor = None
    pages_fetched = 0
    
    while pages_fetched < max_pages:
        try:
            variables = {"owner": owner, "name": repo, "cursor": cursor}
            data = run_query(COMMIT_HISTORY_QUERY, variables)
            
            if not data or 'repository' not in data:
                break
                
            repo_data = data['repository']
            if not repo_data or not repo_data.get('defaultBranchRef') or not repo_data['defaultBranchRef'].get('target'):
                break
            
            history = repo_data['defaultBranchRef']['target']['history']
            
            # Process commits
            for commit in history.get('nodes', []):
                if commit.get('author') and commit['author'].get('user'):
                    username = commit['author']['user']['login']
                    contributors[username]['commits'] += 1
                    contributors[username]['additions'] += commit.get('additions', 0)
                    contributors[username]['deletions'] += commit.get('deletions', 0)
                    
                    # Track activity periods
                    committed_date = datetime.fromisoformat(commit['committedDate'].replace('Z', '+00:00'))
                    if committed_date > since_30:
                        active_30_days.add(username)
                    if committed_date > since_90:
                        active_90_days.add(username)
                    
                    # Count commits by year
                    year = committed_date.year
                    commit_counts_by_year[year] += 1
            
            # Check for more pages
            page_info = history.get('pageInfo', {})
            if not page_info.get('hasNextPage'):
                break
                
            cursor = page_info.get('endCursor')
            pages_fetched += 1
            
            print(f"  ... fetched page {pages_fetched}, cursor: {cursor}")
            
        except Exception as e:
            print(f"Error fetching commit history: {e}")
            break

    # Format the final output
    sorted_contributors = sorted(contributors.items(), key=lambda item: item[1]['commits'], reverse=True)
    
    all_contributors = [
        {
            "username": user, 
            "commit_count": stats["commits"],
            "additions": stats["additions"],
            "deletions": stats["deletions"]
        } 
        for user, stats in sorted_contributors
    ]

    return {
        "total_contributors": len(contributors),
        "active_30_days": len(active_30_days),
        "active_90_days": len(active_90_days),
        "contributors": all_contributors[:10],  # Top 10 contributors
        "yearly_commits": dict(sorted(commit_counts_by_year.items())),
    }

def clone_repo(owner, repo, token, temp_dir):
    """Clone a repository to a temporary directory."""
    https_url = f"https://{owner}:{token}@github.com/{owner}/{repo}.git"
    
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    
    try:
        result = subprocess.run(
            ["git", "clone", https_url, temp_dir], 
            capture_output=True, 
            text=True, 
            check=True,
            timeout=300  # 5 minute timeout
        )
        return temp_dir
    except subprocess.CalledProcessError as e:
        print(f"Error cloning repo {owner}/{repo}: {e.stderr}")
        return None
    except subprocess.TimeoutExpired:
        print(f"Timeout cloning repo {owner}/{repo}")
        return None

def process_repo(repo_line, token):
    """Process a single repository"""
    repo_line = repo_line.strip()
    if not repo_line:
        return None
    
    try:
        owner, repo = repo_line.split('/')
    except ValueError:
        print(f"Error: Invalid format '{repo_line}', use 'owner/repo'")
        return None
    
    # Use thread ID for unique temp directory
    thread_id = threading.current_thread().ident
    temp_dir = f"temp_repo_{thread_id}"
    
    try:
        print(f"Processing {owner}/{repo}...")

        print("  Fetching pull request metrics...")
        pr_metrics = get_pull_request_metrics(owner, repo)
        
        print("  Fetching contributor metrics...")
        contributor_metrics = get_contributor_metrics(owner, repo)
        
        print("  Fetching overall repository statistics...")
        repo_stats = get_repo_stats(owner, repo)
        
        print("  Cloning repository for LOC analysis...")
        repo_path = clone_repo(owner, repo, token, temp_dir)
        if not repo_path:
            return {
                "repository": f"{owner}/{repo}",
                "error": "Failed to clone repository"
            }

        total_lines, file_count, file_stats = calculate_loc(repo_path)

        result = {
            "repository": f"{owner}/{repo}",
            "total_files": file_count,
            "total_lines": total_lines,
            "total_commits": repo_stats.get("totalCommits", {}).get("target", {}).get("history", {}).get("totalCount", 0),
            "yearly_commits": repo_stats.get("yearlyCommits", {}).get("target", {}).get("history", {}).get("totalCount", 0),
            "total_contributors": contributor_metrics.get("total_contributors", 0),
            "active_30_days": contributor_metrics.get("active_30_days", 0),
            "active_90_days": contributor_metrics.get("active_90_days", 0),
            "pr_total": pr_metrics.get("total", 0),
            "pr_open": pr_metrics.get("open", 0),
            "pr_closed": pr_metrics.get("closed", 0),
            "pr_merged": pr_metrics.get("merged", 0),
            "pr_draft": pr_metrics.get("draft", 0),
            "reviews_per_pr": pr_metrics.get("reviews_per_pr", 0),
            "approval_rate": pr_metrics.get("approval_rate", 0),
            "change_requests_rate": pr_metrics.get("change_requests_rate", 0),
        }

        print(f"  Completed {owner}/{repo}")
        return result
        
    except Exception as e:
        print(f"Error processing {owner}/{repo}: {str(e)}")
        return {
            "repository": f"{owner}/{repo}",
            "error": str(e)
        }
    finally:
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"Warning: Could not remove temp directory {temp_dir}: {e}")

def main():
    repos_file = "repos.txt"
    
    if not os.path.exists(repos_file):
        print(f"Error: File '{repos_file}' not found")
        sys.exit(1)
    
    # Read repositories from file
    with open(repos_file, 'r') as f:
        repos = [line.strip() for line in f if line.strip()]
    
    if not repos:
        print("No repositories found in file")
        sys.exit(1)
    
    print(f"Processing {len(repos)} repositories...")
    
    results = []

    # Process repositories in parallel (reduced workers to be gentler on API)
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_repo = {executor.submit(process_repo, repo, token): repo for repo in repos}
        
        for future in as_completed(future_to_repo):
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                print(f"Error processing repository: {e}")

    # Write results to CSV
    if results:
        keys = set()
        for obj in results:
            keys.update(obj.keys())
        
        headers = sorted(keys)
        
        output_file = "results.csv"
        with open(output_file, 'w', newline='', encoding='utf-8') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=headers)
            writer.writeheader()
            for obj in results:
                writer.writerow(obj)
        
        print(f"\nCompleted! Results saved to {output_file}")
        print(f"Processed {len(results)} repositories")
        
        # Print summary statistics
        successful = [r for r in results if 'error' not in r]
        failed = [r for r in results if 'error' in r]
        
        print(f"Successful: {len(successful)}")
        print(f"Failed: {len(failed)}")
        
        if failed:
            print("\nFailed repositories:")
            for repo in failed:
                print(f"  - {repo['repository']}: {repo.get('error', 'Unknown error')}")
    else:
        print("No results to write")

if __name__ == "__main__":
    main()