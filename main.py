import requests
import json
import sys

def get_repo_stats(owner, repo, token=None):
    """
    Fetch GitHub repository statistics
    
    Args:
        owner (str): Repository owner username
        repo (str): Repository name
        token (str, optional): GitHub personal access token
    
    Returns:
        dict: Repository statistics
    """
    base_url = "https://api.github.com"
    
    # Set up headers
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "GitHub-Stats-Fetcher"
    }
    
    # Add token if provided
    if token:
        headers["Authorization"] = f"token {token}"
    
    try:
        # Get repository info
        repo_url = f"{base_url}/repos/{owner}/{repo}"
        repo_response = requests.get(repo_url, headers=headers)
        repo_response.raise_for_status()
        repo_data = repo_response.json()
        
        # Get pull requests count
        pr_url = f"{base_url}/repos/{owner}/{repo}/pulls"
        pr_params = {"state": "all", "per_page": 1}
        pr_response = requests.get(pr_url, headers=headers, params=pr_params)
        pr_response.raise_for_status()
        
        # Get total PR count from Link header or make another request
        pr_count_url = f"{base_url}/repos/{owner}/{repo}/pulls?state=all"
        pr_count_response = requests.get(pr_count_url, headers=headers)
        pr_count_response.raise_for_status()
        total_prs = len(pr_count_response.json())
        
        # Get contributors
        contributors_url = f"{base_url}/repos/{owner}/{repo}/contributors"
        contributors_response = requests.get(contributors_url, headers=headers)
        contributors_response.raise_for_status()
        contributors_data = contributors_response.json()
        
        # Compile stats
        stats = {
            "repository": f"{owner}/{repo}",
            "total_pull_requests": total_prs,
            "total_contributors": len(contributors_data),
            "top_contributors": [
                {
                    "username": contributor["login"],
                    "contributions": contributor["contributions"]
                }
                for contributor in contributors_data[:5]  # Top 5 contributors
            ]
        }
        
        return stats
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return None
    except KeyError as e:
        print(f"Error parsing response: {e}")
        return None

def main():
    # Check command line arguments
    if len(sys.argv) != 2:
        print("Usage: python main.py <owner/repo>")
        print("Example: python main.py octocat/Hello-World")
        sys.exit(1)
    
    # Parse owner/repo from command line
    try:
        owner, repo = sys.argv[1].split('/')
        if not owner or not repo:
            raise ValueError("Invalid format")
    except ValueError:
        print("Error: Please provide repository in format 'owner/repo'")
        print("Example: python main.py octocat/Hello-World")
        sys.exit(1)
    
    # Configuration
    GITHUB_TOKEN = "your_github_token_here"  # Replace with your token or set to None
    
    print(f"Fetching stats for {owner}/{repo}...")
    
    # Fetch stats
    stats = get_repo_stats(owner, repo, GITHUB_TOKEN)
    
    if stats:
        print("\n" + "="*50)
        print(f"Repository: {stats['repository']}")
        print(f"Total Pull Requests: {stats['total_pull_requests']}")
        print(f"Total Contributors: {stats['total_contributors']}")
        print("\nTop Contributors:")
        for contributor in stats['top_contributors']:
            print(f"  - {contributor['username']}: {contributor['contributions']} contributions")
        print("="*50)
    else:
        print("Failed to fetch repository stats")

if __name__ == "__main__":
    main()