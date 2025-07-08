import os
import sys
import subprocess
import shutil
import json
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

def clone_repo(owner, repo, token, temp_dir):
    """Clone repository using HTTPS with PAT"""
    https_url = f"https://{token}@github.com/{owner}/{repo}.git"
    
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    
    try:
        subprocess.run(["git", "clone", https_url, temp_dir], 
                      capture_output=True, text=True, check=True)
        return temp_dir
    except subprocess.CalledProcessError:
        return None

def count_lines_in_file(file_path):
    """Count non-blank lines in a file"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            return sum(1 for line in file if line.strip())
    except:
        return 0

def is_code_file(file_path):
    """Check if file is a code file"""
    skip_patterns = ['.git', '__pycache__', 'node_modules', '.venv', 'dist', 'build']
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
    """Calculate lines of code in repository"""
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

def get_repo_info(owner, repo, token):
    """Get repository info from GitHub API"""
    url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {"Authorization": f"token {token}"}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
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
        
        # Get repo info from API
        repo_info = get_repo_info(owner, repo, token)
        
        # Clone repository
        repo_path = clone_repo(owner, repo, token, temp_dir)
        if not repo_path:
            return {
                "repository": f"{owner}/{repo}",
                "error": "Failed to clone repository"
            }
        
        # Calculate LOC
        total_lines, file_count, file_stats = calculate_loc(repo_path)
        
        # Create result
        result = {
            "repository": f"{owner}/{repo}",
            "total_files": file_count,
            "total_lines": total_lines,
            "files": file_stats
        }
        
        # Add API info if available
        if repo_info:
            result["repo_info"] = {
                "stars": repo_info.get("stargazers_count", 0),
                "forks": repo_info.get("forks_count", 0),
                "language": repo_info.get("language"),
                "description": repo_info.get("description")
            }
        
        return result
        
    except Exception as e:
        return {
            "repository": f"{owner}/{repo}",
            "error": str(e)
        }
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

def main():
    if len(sys.argv) != 2:
        print("Usage: python script.py <repos_file.txt>")
        sys.exit(1)
    
    repos_file = sys.argv[1]
    
    if not os.path.exists(repos_file):
        print(f"Error: File '{repos_file}' not found")
        sys.exit(1)
    
    token = input("Enter GitHub PAT: ").strip()
    if not token:
        print("Token required")
        sys.exit(1)
    
    # Read repositories from file
    with open(repos_file, 'r') as f:
        repos = [line.strip() for line in f if line.strip()]
    
    if not repos:
        print("No repositories found in file")
        sys.exit(1)
    
    print(f"Processing {len(repos)} repositories...")
    
    results = []
    
    # Process repositories in parallel
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_repo = {executor.submit(process_repo, repo, token): repo for repo in repos}
        
        for future in as_completed(future_to_repo):
            result = future.result()
            if result:
                results.append(result)
    
    # Write results to JSON file
    output_file = "results.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nCompleted! Results saved to {output_file}")
    print(f"Processed {len(results)} repositories")

if __name__ == "__main__":
    main()