import os
import subprocess
import shutil
import requests
import re
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import tempfile
import glob

load_dotenv()

# --- CONFIGURATION ---
# Your GitHub organization name
ORG_NAME = "dnb-main"
# The output file for the report
OUTPUT_CSV = "terraform_modules_report.csv"
# Number of parallel threads to speed up processing
MAX_WORKERS = 5  # Reduced for git operations
# The base path in repositories to start scanning from
BASE_SCAN_PATH = "terraform/infrastructure"

# --- SCRIPT START ---

# Securely get tokens from environment variables
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
TFC_TOKEN = os.getenv("TFC_TOKEN")

if not GITHUB_TOKEN:
    raise ValueError("GITHUB_TOKEN environment variable not set.")

# Headers for GitHub API requests
API_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

def get_latest_module_version(session, module_source):
    """
    Fetches the latest version of a Terraform module from either 
    Terraform Cloud (private) or public registry.
    """
    module_source = module_source.strip()
    
    if module_source.startswith("app.terraform.io"):
        # Handle Terraform Cloud private modules
        if not TFC_TOKEN:
            print(f"  [!] TFC_TOKEN not set, cannot fetch version for private module: {module_source}")
            return "TFC_TOKEN_MISSING"
            
        try:
            parts = module_source.replace("app.terraform.io/", "").split("/")
            if len(parts) < 3:
                return "Invalid_Source_Format"

            org, name, provider = parts[:3]
            url = f"https://app.terraform.io/api/registry/v1/modules/{org}/{name}/{provider}/versions"
            headers = {
                "Authorization": f"Bearer {TFC_TOKEN}",
                "Content-Type": "application/vnd.api+json",
            }
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            modules = data.get("modules", [])
            if modules and len(modules) > 0:
                versions = modules[0].get("versions", [])
                if versions:
                    return versions[-1]["version"]
            return "No_Versions_Found"
            
        except Exception as e:
            print(f"  [!] Error fetching private module {module_source}: {e}")
            return "API_Error"
    else:
        # Handle public Terraform registry modules
        try:
            url = f"https://registry.terraform.io/v1/modules/{module_source}"
            response = session.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            latest_version = data.get("version")
            if latest_version:
                return latest_version
            return "No_Version_Found"
            
        except Exception as e:
            print(f"  [!] Error fetching public module {module_source}: {e}")
            return "API_Error"


def clone_repository(repo_url, temp_dir):
    """Clone a repository to a temporary directory."""
    try:
        # Create authenticated URL
        auth_url = repo_url.replace("https://", f"https://{GITHUB_TOKEN}@")
        
        subprocess.run([
            "git", "clone", "--depth", "1", auth_url, temp_dir
        ], check=True, capture_output=True, text=True)
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [!] Failed to clone repository: {e}")
        return False


def parse_terraform_files(repo_path, base_scan_path):
    """Parse Terraform files to extract module information."""
    modules = []
    
    # Look for .tf files in the base scan path and subdirectories
    scan_full_path = os.path.join(repo_path, base_scan_path)
    
    if not os.path.exists(scan_full_path):
        print(f"  [i] Path {base_scan_path} not found in repository")
        return modules
    
    # Find all .tf files recursively
    tf_files = glob.glob(os.path.join(scan_full_path, "**/*.tf"), recursive=True)
    
    for tf_file in tf_files:
        try:
            # Determine environment from path
            rel_path = os.path.relpath(tf_file, scan_full_path)
            env_parts = rel_path.split(os.sep)
            if len(env_parts) > 1:
                environment = env_parts[0]
            else:
                environment = "infrastructure"
            
            with open(tf_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Extract modules using regex
            module_blocks = extract_modules_from_tf_content(content, tf_file, environment)
            modules.extend(module_blocks)
            
        except Exception as e:
            print(f"  [!] Error reading {tf_file}: {e}")
    
    return modules


def extract_modules_from_tf_content(content, file_path, environment):
    """Extract module information from Terraform file content."""
    modules = []
    
    # Regex to match module blocks
    # Matches: module "name" { ... }
    module_pattern = re.compile(
        r'module\s+"([^"]+)"\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}',
        re.MULTILINE | re.DOTALL
    )
    
    matches = module_pattern.findall(content)
    
    for module_name, module_content in matches:
        # Extract source
        source_match = re.search(r'source\s*=\s*"([^"]+)"', module_content)
        # Extract version
        version_match = re.search(r'version\s*=\s*"([^"]+)"', module_content)
        
        if source_match:
            source = source_match.group(1)
            version = version_match.group(1) if version_match else "No_Version_Specified"
            
            print(f"    [*] Found module: {module_name} | Source: {source} | Version: {version}")
            
            modules.append({
                "module_name": module_name,
                "module_source": source,
                "current_version": version,
                "environment": environment,
                "file_path": file_path
            })
    
    return modules


def process_repo_with_git(repo):
    """
    Process a repository by cloning it and scanning actual Terraform files.
    """
    repo_name = repo.get("full_name")
    repo_url = repo.get("clone_url")
    
    print(f"-> Processing repo: {repo_name}")
    
    # Create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        # Clone repository
        if not clone_repository(repo_url, temp_dir):
            return []
        
        # Parse Terraform files
        modules = parse_terraform_files(temp_dir, BASE_SCAN_PATH)
        
        # Add repository name to each module
        for module in modules:
            module["repository"] = repo_name
        
        # Get latest versions for each module
        with requests.Session() as session:
            for module in modules:
                print(f"    [*] Fetching latest version for {module['module_source']}...")
                latest_version = get_latest_module_version(session, module['module_source'])
                module["latest_version"] = latest_version
                
                # Determine if module is outdated
                if (latest_version not in ["API_Error", "Unexpected_Error", "No_Version_Found", 
                                         "No_Versions_Found", "TFC_TOKEN_MISSING", "Invalid_Source_Format"] 
                    and module["current_version"] != "No_Version_Specified"):
                    module["is_outdated"] = module["current_version"] != latest_version
                else:
                    module["is_outdated"] = "Unknown"
        
        return modules


def main():
    """Main function to orchestrate the module extraction and analysis."""
    print(f"Starting Terraform file analysis for organization: {ORG_NAME}...")
    
    # For testing, using a single repository
    # Uncomment the block below to fetch all repositories from the organization
    """
    with requests.Session() as session:
        session.headers.update(API_HEADERS)
        
        all_repos = []
        page = 1
        while True:
            url = f"https://api.github.com/orgs/{ORG_NAME}/repos?type=all&per_page=100&page={page}"
            try:
                response = session.get(url)
                response.raise_for_status()
                data = response.json()
                if not data:
                    break
                all_repos.extend(data)
                page += 1
            except requests.exceptions.RequestException as e:
                print(f"Error fetching repositories: {e}")
                return
    """
    
    # Test with single repository
    all_repos = [{
        "full_name": "dnb-main/dap-project-repo",
        "clone_url": "https://github.com/dnb-main/dap-project-repo.git"
    }]

    print(f"Found {len(all_repos)} repositories. Starting analysis...")
    
    all_results = []

    # Process repositories (reduced parallelism due to git operations)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_repo = {executor.submit(process_repo_with_git, repo): repo for repo in all_repos}
        for future in as_completed(future_to_repo):
            try:
                results = future.result()
                if results:
                    all_results.extend(results)
            except Exception as exc:
                repo_name = future_to_repo[future].get('full_name', 'unknown repo')
                print(f"  [!] Repository {repo_name} generated an exception: {exc}")
    
    if not all_results:
        print("No Terraform modules found in any repositories.")
        return
    
    # Create DataFrame and save to CSV
    df = pd.DataFrame(all_results)
    
    # Reorder columns for better readability
    cols = ['repository', 'environment', 'module_name', 'module_source', 
            'current_version', 'latest_version', 'is_outdated', 'file_path']
    df = df[cols]
    
    # Save to CSV
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"Module report saved to {OUTPUT_CSV}")
    
    # Print summary statistics
    total_modules = len(df)
    outdated_modules = len(df[df['is_outdated'] == True])
    error_modules = len(df[df['latest_version'].str.contains('Error|Missing|Invalid|No_', na=False)])
    
    print(f"\n=== SUMMARY ===")
    print(f"Total modules found: {total_modules}")
    print(f"Outdated modules: {outdated_modules}")
    print(f"Modules with version fetch errors: {error_modules}")
    print(f"Up-to-date modules: {total_modules - outdated_modules - error_modules}")


if __name__ == "__main__":
    main()