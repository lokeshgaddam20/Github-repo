#!/usr/bin/env python3
import os
import sys
import tempfile
import shutil
import subprocess
from pathlib import Path

def is_coding_file(file_path):
    """Check if file is a coding file based on extension."""
    coding_extensions = {
        '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.c', '.h', '.cpp', '.cxx', 
        '.cc', '.hpp', '.cs', '.go', '.rs', '.php', '.rb', '.pl', '.sh', '.bash',
        '.r', '.m', '.sql', '.lua', '.hs', '.coffee', '.scala', '.kt', '.swift', 
        '.html', '.css', '.xml', '.json', '.yaml', '.yml', '.md', '.dart',
        '.dart', '.elm', '.clj', '.ex', '.erl', '.f90', '.pas', '.vb', '.asm'
    }
    return file_path.suffix.lower() in coding_extensions

def count_lines(file_path):
    """Count non-blank lines in a file."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            non_blank_lines = sum(1 for line in f if line.strip())
            return non_blank_lines
    except:
        return 0

def clone_repo(repo_url, temp_dir):
    """Clone GitHub repository."""
    try:
        subprocess.run(['git', 'clone', repo_url, temp_dir], 
                      check=True, capture_output=True)
        return True
    except:
        return False

def main():
    if len(sys.argv) != 2:
        print("Usage: python loc_counter.py <user/repo>")
        sys.exit(1)
    
    repo_input = sys.argv[1]
    if '/' not in repo_input:
        print("Error: Use user/repo format")
        sys.exit(1)
    
    repo_url = f"https://github.com/{repo_input}.git"
    temp_dir = tempfile.mkdtemp()
    
    try:
        print(f"Cloning {repo_input}...")
        if not clone_repo(repo_url, temp_dir):
            print("Failed to clone repository")
            sys.exit(1)
        
        total_lines = 0
        file_count = 0
        
        for file_path in Path(temp_dir).rglob('*'):
            if file_path.is_file() and is_coding_file(file_path):
                lines = count_lines(file_path)
                if lines > 0:
                    total_lines += lines
                    file_count += 1
                    print(f"{file_path.name}: {lines}")
        
        print(f"\nTotal: {total_lines} non-blank lines in {file_count} files")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    main()
