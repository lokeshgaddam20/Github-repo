import os
import requests
import re
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
# Your GitHub organization name
ORG_NAME = "your-github-org-name"
# The output file for the report
OUTPUT_CSV = "terraform_modules_report.csv"
# Number of parallel threads to speed up API calls
MAX_WORKERS = 10

# --- SCRIPT START ---

# Securely get the GitHub token from environment variables
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Regex to find a markdown table row with a Terraform module source and version
# Assumes a format like: | terraform-aws-modules/vpc/aws | v5.1.2 |
# It captures the module source (group 1) and the version (group 2)
MODULE_REGEX = re.compile(
    r"\|\s*([a-zA-Z0-9\-_/]+\/[a-zA-Z0-9\-_/]+\/[a-zA-Z0-9\-_/]+)\s*\|\s*(v?\d+\.\d+\.\d+.*?)\s*\|"
)

def get_latest_module_version(module_source):
    """Queries the Terraform Registry for the latest version of a module."""
    try:
        url = f"https://registry.terraform.io/v1/modules/{module_source}"
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.json().get("version")
    except requests.exceptions.RequestException as e:
        print(f"  [!] Error fetching module {module_source}: {e}")
        return "Error"

def process_repo(repo):
    """Processes a single repository to find and analyze Terraform modules."""
    repo_name = repo.get("full_name")
    print(f"-> Scanning repo: {repo_name}")
    
    # Get the default branch to construct the README URL
    default_branch = repo.get("default_branch")
    readme_url = f"https://raw.githubusercontent.com/{repo_name}/{default_branch}/README.md"
    
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    try:
        response = requests.get(readme_url, headers=headers, timeout=10)
        # GitHub returns 404 for missing files, which is fine
        if response.status_code != 200:
            return []
        
        readme_content = response.text
        found_modules = MODULE_REGEX.findall(readme_content)
        
        repo_results = []
        for module_source, in_use_version in found_modules:
            print(f"  [*] Found module: {module_source} version {in_use_version}")
            
            latest_version = get_latest_module_version(module_source)
            
            repo_results.append({
                "repository": repo_name,
                "module_source": module_source,
                "in_use_version": in_use_version.strip(),
                "latest_version": latest_version,
                "is_outdated": latest_version != "Error" and in_use_version.strip() != latest_version,
            })
        return repo_results
        
    except requests.exceptions.RequestException as e:
        print(f"  [!] Could not fetch README for {repo_name}: {e}")
        return []

def main():
    """Main function to orchestrate the module extraction and analysis."""
    if not GITHUB_TOKEN:
        print("Error: GITHUB_TOKEN environment variable not set.")
        return

    print(f"Fetching repositories for organization: {ORG_NAME}...")
    
    # Fetch all repositories for the organization (handles pagination)
    all_repos = []
    page = 1
    while True:
        url = f"https://api.github.com/orgs/{ORG_NAME}/repos?type=all&per_page=100&page={page}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if not data:
            break
        all_repos.extend(data)
        page += 1
    
    print(f"Found {len(all_repos)} repositories. Starting analysis with {MAX_WORKERS} workers...")

    all_results = []
    # Use a thread pool to process repositories in parallel for speed
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_repo = {executor.submit(process_repo, repo): repo for repo in all_repos}
        for future in as_completed(future_to_repo):
            try:
                results = future.result()
                if results:
                    all_results.extend(results)
            except Exception as exc:
                print(f"  [!] A repository generated an exception: {exc}")

    if not all_results:
        print("No Terraform modules found in any READMEs.")
        return

    # Create a DataFrame and save to CSV
    df = pd.DataFrame(all_results)
    df.to_csv(OUTPUT_CSV, index=False)
    
    print(f"\n✅ Report complete! Data saved to '{OUTPUT_CSV}'.")
    print(f"Total modules found: {len(df)}")
    print(f"Outdated modules: {df['is_outdated'].sum()}")


if __name__ == "__main__":
    main()

