import os
import sys
import subprocess
import shutil
from pathlib import Path

def clone_repo(owner, repo, token, temp_dir="temp_repo"):
    """Clone repository using HTTPS with PAT"""
    https_url = f"https://{token}@github.com/{owner}/{repo}.git"
    
    # Remove existing temp directory
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    
    try:
        print(f"Cloning {owner}/{repo}...")
        subprocess.run(["git", "clone", https_url, temp_dir], 
                      capture_output=True, text=True, check=True)
        return temp_dir
    except subprocess.CalledProcessError:
        print("Failed to clone repository")
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
    # Skip these directories/files
    skip_patterns = ['.git', '__pycache__', 'node_modules', '.venv', 'dist', 'build']
    file_str = str(file_path)
    
    for pattern in skip_patterns:
        if pattern in file_str:
            return False
    
    # Code file extensions
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
    
    for file_path in Path(repo_path).rglob('*'):
        if file_path.is_file() and is_code_file(file_path):
            lines = count_lines_in_file(file_path)
            if lines > 0:
                total_lines += lines
                file_count += 1
    
    return total_lines, file_count

def main():
    if len(sys.argv) != 2:
        print("Usage: python main.py <owner/repo>")
        sys.exit(1)
    
    try:
        owner, repo = sys.argv[1].split('/')
    except ValueError:
        print("Error: Use format 'owner/repo'")
        sys.exit(1)
    
    # Get GitHub token
    token = input("Enter GitHub PAT: ").strip()
    if not token:
        print("Token required")
        sys.exit(1)
    
    temp_dir = "temp_repo"
    
    try:
        # Clone repository
        repo_path = clone_repo(owner, repo, token, temp_dir)
        if not repo_path:
            sys.exit(1)
        
        # Calculate LOC
        total_lines, file_count = calculate_loc(repo_path)
        
        # Display results
        print(f"\nRepository: {owner}/{repo}")
        print(f"Files analyzed: {file_count}")
        print(f"Total lines of code: {total_lines:,}")
        
    finally:
        # Cleanup
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    main()