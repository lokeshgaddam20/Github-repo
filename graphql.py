import requests
import json
from datetime import datetime, timedelta

class GitHubGraphQLClient:
    def __init__(self, token):
        self.token = token
        self.endpoint = "https://api.github.com/graphql"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def execute_query(self, query, variables=None):
        """Execute GraphQL query"""
        payload = {
            "query": query,
            "variables": variables or {}
        }
        
        response = requests.post(
            self.endpoint,
            json=payload,
            headers=self.headers
        )
        
        return response.json()
    
    def get_organization_repos_bulk(self, org_name, first=100):
        """Get all repos for an organization with comprehensive metrics"""
        query = """
        query($org: String!, $first: Int!, $after: String) {
          organization(login: $org) {
            name
            description
            createdAt
            repositories(first: $first, after: $after, orderBy: {field: PUSHED_AT, direction: DESC}) {
              pageInfo {
                hasNextPage
                endCursor
              }
              totalCount
              nodes {
                name
                description
                visibility
                createdAt
                updatedAt
                pushedAt
                isArchived
                isDisabled
                isFork
                isTemplate
                stargazerCount
                forkCount
                diskUsage
                primaryLanguage {
                  name
                  color
                }
                languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
                  totalCount
                  nodes {
                    name
                    color
                  }
                  edges {
                    size
                    node {
                      name
                    }
                  }
                }
                repositoryTopics(first: 10) {
                  nodes {
                    topic {
                      name
                    }
                  }
                }
                licenseInfo {
                  name
                  key
                  spdxId
                }
                defaultBranchRef {
                  name
                  target {
                    ... on Commit {
                      committedDate
                      author {
                        name
                        email
                      }
                    }
                  }
                }
                pullRequests(states: [OPEN, CLOSED, MERGED], first: 100) {
                  totalCount
                  nodes {
                    number
                    state
                    title
                    createdAt
                    mergedAt
                    closedAt
                    additions
                    deletions
                    changedFiles
                    commits {
                      totalCount
                    }
                    reviews(first: 10) {
                      totalCount
                      nodes {
                        state
                        createdAt
                        author {
                          login
                        }
                      }
                    }
                    author {
                      login
                    }
                    labels(first: 10) {
                      nodes {
                        name
                      }
                    }
                  }
                }
                issues(states: [OPEN, CLOSED], first: 100) {
                  totalCount
                  nodes {
                    number
                    state
                    title
                    createdAt
                    closedAt
                    author {
                      login
                    }
                    labels(first: 10) {
                      nodes {
                        name
                      }
                    }
                    assignees(first: 5) {
                      nodes {
                        login
                      }
                    }
                  }
                }
                collaborators(first: 100) {
                  totalCount
                  nodes {
                    login
                    name
                    email
                  }
                }
                vulnerabilityAlerts(first: 50) {
                  totalCount
                  nodes {
                    createdAt
                    dismissedAt
                    state
                    securityVulnerability {
                      severity
                      package {
                        name
                        ecosystem
                      }
                    }
                  }
                }
                branchProtectionRules(first: 10) {
                  nodes {
                    pattern
                    requiredStatusCheckContexts
                    requiresApprovingReviews
                    requiresCodeOwnerReviews
                    dismissesStaleReviews
                    requiresStrictStatusChecks
                    enforceAdmins
                  }
                }
                deployments(first: 50, orderBy: {field: CREATED_AT, direction: DESC}) {
                  totalCount
                  nodes {
                    createdAt
                    environment
                    state
                    statuses(first: 5) {
                      nodes {
                        state
                        createdAt
                        description
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        
        variables = {
            "org": org_name,
            "first": first
        }
        
        all_repos = []
        has_next_page = True
        after = None
        
        while has_next_page:
            if after:
                variables["after"] = after
            
            result = self.execute_query(query, variables)
            
            if "errors" in result:
                print(f"GraphQL errors: {result['errors']}")
                break
            
            repos = result["data"]["organization"]["repositories"]
            all_repos.extend(repos["nodes"])
            
            has_next_page = repos["pageInfo"]["hasNextPage"]
            after = repos["pageInfo"]["endCursor"]
        
        return all_repos
    
    def get_repository_detailed_metrics(self, owner, repo_name):
        """Get detailed metrics for a specific repository"""
        query = """
        query($owner: String!, $repo: String!) {
          repository(owner: $owner, name: $repo) {
            name
            description
            createdAt
            pushedAt
            diskUsage
            
            # Commit history and contributors
            defaultBranchRef {
              target {
                ... on Commit {
                  history(first: 100) {
                    totalCount
                    nodes {
                      committedDate
                      author {
                        name
                        email
                        user {
                          login
                        }
                      }
                      additions
                      deletions
                      changedFiles
                    }
                  }
                }
              }
            }
            
            # Recent activity
            pullRequests(first: 100, orderBy: {field: CREATED_AT, direction: DESC}) {
              totalCount
              nodes {
                number
                state
                title
                createdAt
                mergedAt
                closedAt
                additions
                deletions
                changedFiles
                commits {
                  totalCount
                }
                reviews {
                  totalCount
                  nodes {
                    state
                    createdAt
                    author {
                      login
                    }
                  }
                }
                comments {
                  totalCount
                }
                author {
                  login
                }
                timelineItems(first: 10, itemTypes: [READY_FOR_REVIEW_EVENT, REVIEW_REQUESTED_EVENT]) {
                  nodes {
                    ... on ReadyForReviewEvent {
                      createdAt
                    }
                    ... on ReviewRequestedEvent {
                      createdAt
                    }
                  }
                }
              }
            }
            
            # Release information
            releases(first: 20, orderBy: {field: CREATED_AT, direction: DESC}) {
              totalCount
              nodes {
                name
                tagName
                createdAt
                publishedAt
                isDraft
                isPrerelease
                author {
                  login
                }
              }
            }
            
            # Workflow runs (if accessible)
            # Note: This requires additional permissions
            # workflowRuns(first: 100) {
            #   totalCount
            #   nodes {
            #     conclusion
            #     status
            #     createdAt
            #     updatedAt
            #   }
            # }
          }
        }
        """
        
        variables = {
            "owner": owner,
            "repo": repo_name
        }
        
        return self.execute_query(query, variables)
    
    def get_user_contributions(self, username, from_date=None):
        """Get user contribution data"""
        if not from_date:
            from_date = (datetime.now() - timedelta(days=365)).isoformat()
        
        query = """
        query($username: String!, $from: DateTime!) {
          user(login: $username) {
            login
            name
            email
            createdAt
            contributionsCollection(from: $from) {
              totalCommitContributions
              totalIssueContributions
              totalPullRequestContributions
              totalPullRequestReviewContributions
              contributionCalendar {
                totalContributions
                weeks {
                  contributionDays {
                    contributionCount
                    date
                  }
                }
              }
              commitContributionsByRepository(maxRepositories: 100) {
                repository {
                  name
                  owner {
                    login
                  }
                }
                contributions(first: 100) {
                  totalCount
                  nodes {
                    commitCount
                    occurredAt
                  }
                }
              }
            }
          }
        }
        """
        
        variables = {
            "username": username,
            "from": from_date
        }
        
        return self.execute_query(query, variables)

# Usage example
def main():
    # Initialize client
    client = GitHubGraphQLClient("your-github-token")
    
    # Get all repos for an organization
    org_repos = client.get_organization_repos_bulk("your-org")
    
    print(f"Found {len(org_repos)} repositories")
    
    # Process each repository
    for repo in org_repos:
        print(f"Processing {repo['name']}...")
        
        # Get detailed metrics
        detailed_metrics = client.get_repository_detailed_metrics(
            "your-org", 
            repo['name']
        )
        
        # Extract and process metrics
        metrics = process_repo_metrics(repo, detailed_metrics)
        
        # Store in your results
        # store_metrics(metrics)

def process_repo_metrics(repo, detailed_data):
    """Process GraphQL response into structured metrics"""
    metrics = {
        "repo_name": repo["name"],
        "description": repo["description"],
        "created_at": repo["createdAt"],
        "updated_at": repo["updatedAt"],
        "pushed_at": repo["pushedAt"],
        "primary_language": repo["primaryLanguage"]["name"] if repo["primaryLanguage"] else None,
        "languages": [
            {
                "name": edge["node"]["name"],
                "bytes": edge["size"]
            }
            for edge in repo["languages"]["edges"]
        ],
        "pull_requests": {
            "total": repo["pullRequests"]["totalCount"],
            "open": len([pr for pr in repo["pullRequests"]["nodes"] if pr["state"] == "OPEN"]),
            "merged": len([pr for pr in repo["pullRequests"]["nodes"] if pr["state"] == "MERGED"]),
            "closed": len([pr for pr in repo["pullRequests"]["nodes"] if pr["state"] == "CLOSED"]),
            "average_size": sum(pr["additions"] + pr["deletions"] for pr in repo["pullRequests"]["nodes"]) / max(1, len(repo["pullRequests"]["nodes"])),
            "review_metrics": {
                "total_reviews": sum(pr["reviews"]["totalCount"] for pr in repo["pullRequests"]["nodes"]),
                "avg_reviews_per_pr": sum(pr["reviews"]["totalCount"] for pr in repo["pullRequests"]["nodes"]) / max(1, len(repo["pullRequests"]["nodes"]))
            }
        },
        "issues": {
            "total": repo["issues"]["totalCount"],
            "open": len([issue for issue in repo["issues"]["nodes"] if issue["state"] == "OPEN"]),
            "closed": len([issue for issue in repo["issues"]["nodes"] if issue["state"] == "CLOSED"])
        },
        "contributors": {
            "total": repo["collaborators"]["totalCount"],
            "active": len(set(pr["author"]["login"] for pr in repo["pullRequests"]["nodes"] if pr["author"]))
        },
        "security": {
            "vulnerability_alerts": repo["vulnerabilityAlerts"]["totalCount"],
            "open_alerts": len([alert for alert in repo["vulnerabilityAlerts"]["nodes"] if alert["state"] == "OPEN"])
        },
        "deployments": {
            "total": repo["deployments"]["totalCount"],
            "recent": len([dep for dep in repo["deployments"]["nodes"] if datetime.fromisoformat(dep["createdAt"].replace('Z', '+00:00')) > datetime.now().replace(tzinfo=None) - timedelta(days=30)])
        }
    }
    
    return metrics

if __name__ == "__main__":
    main()