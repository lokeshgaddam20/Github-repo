import os
import sys
import subprocess
import shutil
from pathlib import Path
import getpass

def check_ssh_access(owner, repo):
    """
    Check if SSH access to GitHub is configured
    
    Returns:
        bool: True if SSH access is available
    """
    try:
        # Test SSH connection to GitHub
        result = subprocess.run(
            ["ssh", "-T", "git@github.com"],
            capture_output=True,
            text=True,
            timeout=10
        )
        # SSH to GitHub returns exit code 1 but with success message
        return "successfully authenticated" in result.stderr
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        return False

def setup_ssh_instructions():
    """
    Print SSH setup instructions
    """
    print("\n" + "="*60)
    print("SSH KEY SETUP REQUIRED")
    print("="*60)
    print("To clone private repositories, you need SSH access to GitHub.")
    print("\nFollow these steps:")
    print("\n1. Generate SSH key (if you don't have one):")
    print("   ssh-keygen -t rsa -b 4096 -C \"your_email@example.com\"")
    print("\n2. Add SSH key to SSH agent:")
    print("   eval \"$(ssh-agent -s)\"")
    print("   ssh-add ~/.ssh/id_rsa")
    print("\n3. Copy your public key:")
    print("   cat ~/.ssh/id_rsa.pub")
    print("\n4. Add the key to GitHub:")
    print("   - Go to GitHub.com → Settings → SSH and GPG keys")
    print("   - Click 'New SSH key'")
    print("   - Paste your public key")
    print("\n5. Test SSH connection:")
    print("   ssh -T git@github.com")
    print("\nAlternatively, use HTTPS with token authentication.")
    print("="*60)

def clone_repo_ssh(owner, repo, temp_dir="temp_repo"):
    """
    Clone a GitHub repository using SSH
    
    Args:
        owner (str): Repository owner/organization
        repo (str): Repository name
        temp_dir (str): Temporary directory name for cloning
    
    Returns:
        str: Path to cloned repository or None if failed
    """
    ssh_url = f"git@github.com:{owner}/{repo}.git"
    
    # Remove existing temp directory if it exists
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    
    try:
        print(f"Cloning {owner}/{repo} via SSH...")
        result = subprocess.run(
            ["git", "clone", ssh_url, temp_dir],
            capture_output=True,
            text=True,
            check=True
        )
        print("Repository cloned successfully!")
        return temp_dir
        
    except subprocess.CalledProcessError as e:
        print(f"SSH clone failed: {e.stderr}")
        return None
    except FileNotFoundError:
        print("Error: Git is not installed or not in PATH")
        return None

def clone_repo_https(owner, repo, token, temp_dir="temp_repo"):
    """
    Clone a GitHub repository using HTTPS with token authentication
    
    Args:
        owner (str): Repository owner/organization
        repo (str): Repository name
        token (str): GitHub personal access token
        temp_dir (str): Temporary directory name for cloning
    
    Returns:
        str: Path to cloned repository or None if failed
    """
    https_url = f"https://{token}@github.com/{owner}/{repo}.git"
    
    # Remove existing temp directory if it exists
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    
    try:
        print(f"Cloning {owner}/{repo} via HTTPS...")
        result = subprocess.run(
            ["git", "clone", https_url, temp_dir],
            capture_output=True,
            text=True,
            check=True
        )
        print("Repository cloned successfully!")
        return temp_dir
        
    except subprocess.CalledProcessError as e:
        print(f"HTTPS clone failed: {e.stderr}")
        return None
    except FileNotFoundError:
        print("Error: Git is not installed or not in PATH")
        return None

def count_lines_in_file(file_path):
    """
    Count non-blank lines in a file
    
    Args:
        file_path (str): Path to the file
    
    Returns:
        int: Number of non-blank lines
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            lines = file.readlines()
            non_blank_lines = sum(1 for line in lines if line.strip())
            return non_blank_lines
    except Exception:
        return 0

def should_count_file(file_path, exclude_patterns=None):
    """
    Determine if a file should be counted for LOC
    
    Args:
        file_path (Path): Path object of the file
        exclude_patterns (list): List of patterns to exclude
    
    Returns:
        bool: True if file should be counted
    """
    if exclude_patterns is None:
        exclude_patterns = [
            '.git',
            '__pycache__',
            '.pytest_cache',
            'node_modules',
            '.venv',
            'venv',
            '.env',
            'dist',
            'build',
            '.DS_Store',
            '.gitignore',
            '.gitattributes',
            'LICENSE',
            'README.md',
            'package-lock.json',
            'yarn.lock',
            'Pipfile.lock'
        ]
    
    # Convert to string for pattern matching
    file_str = str(file_path)
    
    # Check if any exclude pattern is in the file path
    for pattern in exclude_patterns:
        if pattern in file_str:
            return False
    
    # Only count text files (common programming file extensions)
    code_extensions = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp', '.h', '.hpp',
        '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.scala', '.sh',
        '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd', '.html', '.htm', '.css',
        '.scss', '.sass', '.less', '.xml', '.json', '.yaml', '.yml', '.toml',
        '.ini', '.cfg', '.conf', '.sql', '.r', '.R', '.m', '.pl', '.lua',
        '.vim', '.tex', '.md', '.rst', '.txt', '.dockerfile', '.makefile'
    }
    
    # Check if file has a code extension or is a Makefile/Dockerfile
    if (file_path.suffix.lower() in code_extensions or 
        file_path.name.lower() in ['makefile', 'dockerfile', 'rakefile']):
        return True
    
    return False

def calculate_loc(repo_path):
    """
    Calculate lines of code in a repository
    
    Args:
        repo_path (str): Path to the repository directory
    
    Returns:
        dict: Dictionary containing LOC statistics
    """
    total_lines = 0
    file_count = 0
    file_stats = {}
    
    repo_path = Path(repo_path)
    
    # Walk through all files in the repository
    for file_path in repo_path.rglob('*'):
        if file_path.is_file() and should_count_file(file_path):
            lines = count_lines_in_file(file_path)
            if lines > 0:
                relative_path = file_path.relative_to(repo_path)
                file_stats[str(relative_path)] = lines
                total_lines += lines
                file_count += 1
    
    return {
        'total_lines': total_lines,
        'file_count': file_count,
        'file_stats': file_stats
    }

def cleanup_temp_dir(temp_dir):
    """
    Clean up temporary directory
    
    Args:
        temp_dir (str): Path to temporary directory
    """
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
        print(f"Cleaned up temporary directory: {temp_dir}")

def get_github_token():
    """
    Get GitHub token from user input
    
    Returns:
        str: GitHub personal access token
    """
    print("\nGitHub Personal Access Token required for HTTPS authentication.")
    print("You can create one at: https://github.com/settings/tokens")
    print("Required scopes: 'repo' (for private repositories)")
    token = getpass.getpass("Enter your GitHub token: ")
    return token.strip()

def main():
    # Check command line arguments
    if len(sys.argv) != 2:
        print("Usage: python main.py <owner/repo>")
        print("Example: python main.py myorg/my-private-repo")
        sys.exit(1)
    
    # Parse owner/repo from command line
    try:
        owner, repo = sys.argv[1].split('/')
        if not owner or not repo:
            raise ValueError("Invalid format")
    except ValueError:
        print("Error: Please provide repository in format 'owner/repo'")
        print("Example: python main.py myorg/my-private-repo")
        sys.exit(1)
    
    temp_dir = "temp_repo_clone"
    repo_path = None
    
    try:
        # Check if SSH access is available
        if check_ssh_access(owner, repo):
            print("SSH access detected. Attempting SSH clone...")
            repo_path = clone_repo_ssh(owner, repo, temp_dir)
        else:
            print("SSH access not detected.")
            choice = input("Choose authentication method:\n1. Set up SSH (recommended)\n2. Use HTTPS with token\nEnter choice (1 or 2): ")
            
            if choice == "1":
                setup_ssh_instructions()
                print("\nAfter setting up SSH, run the script again.")
                sys.exit(0)
            elif choice == "2":
                token = get_github_token()
                if not token:
                    print("Error: GitHub token is required for HTTPS authentication")
                    sys.exit(1)
                repo_path = clone_repo_https(owner, repo, token, temp_dir)
            else:
                print("Invalid choice. Exiting.")
                sys.exit(1)
        
        if not repo_path:
            print("\nFailed to clone repository. Common issues:")
            print("1. Repository doesn't exist or you don't have access")
            print("2. SSH key not set up properly (for SSH)")
            print("3. Invalid GitHub token or insufficient permissions (for HTTPS)")
            print("4. Repository name is incorrect")
            sys.exit(1)
        
        print(f"\nCalculating lines of code for {owner}/{repo}...")
        
        # Calculate LOC
        stats = calculate_loc(repo_path)
        
        # Display results
        print("\n" + "="*60)
        print(f"Repository: {owner}/{repo}")
        print(f"Total Files Analyzed: {stats['file_count']}")
        print(f"Total Lines of Code: {stats['total_lines']:,}")
        print("="*60)
        
        # Show top 10 files by LOC
        if stats['file_stats']:
            print("\nTop 10 files by lines of code:")
            sorted_files = sorted(stats['file_stats'].items(), key=lambda x: x[1], reverse=True)
            for i, (file_path, lines) in enumerate(sorted_files[:10], 1):
                print(f"{i:2d}. {file_path}: {lines:,} lines")
        
        print("="*60)
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # Always cleanup
        cleanup_temp_dir(temp_dir)

if __name__ == "__main__":
    main()