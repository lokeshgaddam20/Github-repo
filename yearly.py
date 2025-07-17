import requests
import json
from datetime import datetime, timedelta

def get_github_commits(owner, repo, token):
    """
    Fetch total commits and yearly commit counts for a GitHub repository
    """
    url = "https://api.github.com/graphql"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # GraphQL query to get total commits, default branch, and creation date
    query = """
    query($owner: String!, $repo: String!) {
      repository(owner: $owner, name: $repo) {
        createdAt
        defaultBranchRef {
          name
          target {
            ... on Commit {
              history {
                totalCount
              }
            }
          }
        }
      }
    }
    """
    
    variables = {
        "owner": owner,
        "repo": repo
    }
    
    response = requests.post(url, 
                           json={"query": query, "variables": variables}, 
                           headers=headers)
    
    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        return None
    
    data = response.json()
    
    if "errors" in data:
        print(f"GraphQL Error: {data['errors']}")
        return None
    
    # Get total commits and repository creation date
    total_commits = data["data"]["repository"]["defaultBranchRef"]["target"]["history"]["totalCount"]
    default_branch = data["data"]["repository"]["defaultBranchRef"]["name"]
    created_at = data["data"]["repository"]["createdAt"]
    
    # Parse creation date to get creation year
    creation_year = datetime.fromisoformat(created_at.replace('Z', '+00:00')).year
    
    print(f"Repository: {owner}/{repo}")
    print(f"Created: {created_at[:10]} (Year: {creation_year})")
    print(f"Default branch: {default_branch}")
    print(f"Total commits: {total_commits}")
    print("\nYearly commit counts:")
    
    # Get yearly commits from creation year to current year
    yearly_commits = {}
    current_year = datetime.now().year
    
    for year in range(creation_year, current_year + 1):
        # Create date range for the year
        start_date = f"{year}-01-01T00:00:00Z"
        end_date = f"{year + 1}-01-01T00:00:00Z"
        
        yearly_query = """
        query($owner: String!, $repo: String!, $since: GitTimestamp!, $until: GitTimestamp!) {
          repository(owner: $owner, name: $repo) {
            defaultBranchRef {
              target {
                ... on Commit {
                  history(since: $since, until: $until) {
                    totalCount
                  }
                }
              }
            }
          }
        }
        """
        
        yearly_variables = {
            "owner": owner,
            "repo": repo,
            "since": start_date,
            "until": end_date
        }
        
        yearly_response = requests.post(url, 
                                      json={"query": yearly_query, "variables": yearly_variables}, 
                                      headers=headers)
        
        if yearly_response.status_code == 200:
            yearly_data = yearly_response.json()
            if "errors" not in yearly_data:
                count = yearly_data["data"]["repository"]["defaultBranchRef"]["target"]["history"]["totalCount"]
                yearly_commits[year] = count
                print(f"{year}: {count} commits")
    
    return {
        "total_commits": total_commits,
        "yearly_commits": yearly_commits,
        "creation_year": creation_year,
        "created_at": created_at
    }

def main():
    # Get user input
    repo_input = input("Enter repository (format: owner/repo): ")
    
    if "/" not in repo_input:
        print("Invalid format. Please use: owner/repo")
        return
    
    owner, repo = repo_input.split("/", 1)
    
    # GitHub token (you need to set this)
    token = input("Enter your GitHub personal access token: ")
    
    if not token:
        print("GitHub token is required. Create one at: https://github.com/settings/tokens")
        return
    
    # Fetch commits data
    result = get_github_commits(owner, repo, token)
    
    if result:
        print(f"\nSummary:")
        print(f"Repository created: {result['created_at'][:10]} (Year: {result['creation_year']})")
        print(f"Total commits: {result['total_commits']}")
        print(f"Years active: {result['creation_year']} - {datetime.now().year}")
        print(f"Yearly breakdown: {result['yearly_commits']}")

if __name__ == "__main__":
    main()