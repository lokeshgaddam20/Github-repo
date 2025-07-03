#!/bin/bash

# GitHub API Repo Metrics Collector - Fixed LOC Version
# Usage: ./github_metrics.sh owner/repo-name

if [ $# -eq 0 ]; then
    echo "Usage: $0 owner/repo-name"
    echo "Example: $0 microsoft/vscode"
    exit 1
fi

REPO_FULL=$1
GITHUB_TOKEN=${GITHUB_TOKEN}

# Split owner/repo
OWNER=$(echo "$REPO_FULL" | cut -d'/' -f1)
REPO=$(echo "$REPO_FULL" | cut -d'/' -f2)

if [ -z "$OWNER" ] || [ -z "$REPO" ]; then
    echo "Error: Invalid repository format. Use: owner/repo-name"
    echo "Example: microsoft/vscode"
    exit 1
fi

if [ -z "$GITHUB_TOKEN" ]; then
    echo "Error: GITHUB_TOKEN environment variable not set"
    echo "Get token from: https://github.com/settings/tokens"
    exit 1
fi

# Check if cloc is available for accurate counting
CLOC_AVAILABLE=false
if command -v cloc >/dev/null 2>&1; then
    CLOC_AVAILABLE=true
    echo "✓ cloc found - will use for accurate line counting"
else
    echo "⚠ cloc not found - will use estimation methods"
    echo "  For accurate results, install cloc: apt-get install cloc (or brew install cloc)"
fi

echo "Collecting metrics for: $OWNER/$REPO"

# Headers for GitHub API
AUTH_HEADER="Authorization: Bearer $GITHUB_TOKEN"
ACCEPT_HEADER="Accept: application/vnd.github+json"
API_VERSION_HEADER="X-GitHub-Api-Version: 2022-11-28"

# Function to safely extract JSON values
extract_json_value() {
    local json="$1"
    local key="$2"
    local default="$3"
    
    # Try different extraction methods
    local value=""
    
    # Method 1: Use jq if available
    if command -v jq >/dev/null 2>&1; then
        value=$(echo "$json" | jq -r ".$key // empty" 2>/dev/null)
    fi
    
    # Method 2: Fallback to grep/sed
    if [ -z "$value" ] || [ "$value" = "null" ]; then
        value=$(echo "$json" | grep -o "\"$key\":[^,}]*" | head -1 | cut -d':' -f2- | sed 's/[", ]//g')
    fi
    
    # Return default if empty
    if [ -z "$value" ] || [ "$value" = "null" ]; then
        echo "$default"
    else
        echo "$value"
    fi
}

# Get basic repo info
echo "Getting repository info..."
REPO_DATA=$(curl -s -H "$AUTH_HEADER" -H "$ACCEPT_HEADER" -H "$API_VERSION_HEADER" \
    "https://api.github.com/repos/$OWNER/$REPO")

# Check if repo exists
if echo "$REPO_DATA" | grep -q '"message": "Not Found"'; then
    echo "Error: Repository not found or not accessible"
    exit 1
fi

# Extract basic repo info
DEFAULT_BRANCH=$(extract_json_value "$REPO_DATA" "default_branch" "main")
STARS=$(extract_json_value "$REPO_DATA" "stargazers_count" "0")
FORKS=$(extract_json_value "$REPO_DATA" "forks_count" "0")
LANGUAGE=$(extract_json_value "$REPO_DATA" "language" "Unknown")
SIZE_KB=$(extract_json_value "$REPO_DATA" "size" "0")
CLONE_URL=$(extract_json_value "$REPO_DATA" "clone_url" "")

echo "Repository found: $LANGUAGE project, ${SIZE_KB}KB"

# Get contributors count
echo "Getting contributors..."
CONTRIBUTORS_DATA=$(curl -s -H "$AUTH_HEADER" -H "$ACCEPT_HEADER" -H "$API_VERSION_HEADER" \
    "https://api.github.com/repos/$OWNER/$REPO/contributors?per_page=100")

CONTRIBUTORS_COUNT=$(echo "$CONTRIBUTORS_DATA" | grep -o '"login":' | wc -l | tr -d ' ')

# Handle pagination for contributors
if [ "$CONTRIBUTORS_COUNT" -eq 100 ]; then
    LINK_HEADER=$(curl -s -I -H "$AUTH_HEADER" -H "$ACCEPT_HEADER" -H "$API_VERSION_HEADER" \
        "https://api.github.com/repos/$OWNER/$REPO/contributors?per_page=100" | grep -i "^link:" | head -1)
    if echo "$LINK_HEADER" | grep -q 'rel="last"'; then
        LAST_PAGE=$(echo "$LINK_HEADER" | grep -o 'page=[0-9]*>; rel="last"' | grep -o '[0-9]*' | head -1)
        if [ -n "$LAST_PAGE" ]; then
            CONTRIBUTORS_COUNT=$((LAST_PAGE * 100))
        fi
    fi
fi

# Get pull requests count
echo "Getting pull requests count..."
PR_DATA=$(curl -s -H "$AUTH_HEADER" -H "$ACCEPT_HEADER" -H "$API_VERSION_HEADER" \
    "https://api.github.com/search/issues?q=repo:$OWNER/$REPO+type:pr")
PR_COUNT=$(extract_json_value "$PR_DATA" "total_count" "0")

# ACCURATE LINES OF CODE CALCULATION
echo "Calculating lines of code..."

TOTAL_LINES=0
TOTAL_LOC=0
LINE_COUNT_METHOD="unknown"

if [ "$CLOC_AVAILABLE" = true ]; then
    # Method 1: Use cloc for accurate counting (clone repo temporarily)
    echo "Using cloc for accurate line counting..."
    TEMP_DIR=$(mktemp -d)
    
    if git clone --depth 1 "https://github.com/$OWNER/$REPO.git" "$TEMP_DIR/$REPO" >/dev/null 2>&1; then
        CLOC_OUTPUT=$(cloc "$TEMP_DIR/$REPO" 2>/dev/null)
        
        if [ $? -eq 0 ] && [ -n "$CLOC_OUTPUT" ]; then
            # Extract lines of code from cloc output (last column of SUM line)
            TOTAL_LOC=$(echo "$CLOC_OUTPUT" | grep "^SUM:" | awk '{print $NF}')
            # Extract total lines (files + blank + comment + code)
            TOTAL_LINES=$(echo "$CLOC_OUTPUT" | grep "^SUM:" | awk '{print $2+$3+$4+$5}')
            LINE_COUNT_METHOD="cloc_accurate"
            echo "✓ cloc analysis complete: $TOTAL_LOC lines of code, $TOTAL_LINES total lines"
        else
            echo "✗ cloc failed, falling back to estimation"
            CLOC_AVAILABLE=false
        fi
        
        # Cleanup
        rm -rf "$TEMP_DIR"
    else
        echo "✗ Failed to clone repository, falling back to estimation"
        CLOC_AVAILABLE=false
    fi
fi

if [ "$CLOC_AVAILABLE" = false ] || [ "$TOTAL_LOC" -eq 0 ]; then
    # Method 2: Enhanced estimation using GitHub API
    echo "Using GitHub API for line estimation..."
    
    # Get language statistics
    LANGUAGES_DATA=$(curl -s -H "$AUTH_HEADER" -H "$ACCEPT_HEADER" -H "$API_VERSION_HEADER" \
        "https://api.github.com/repos/$OWNER/$REPO/languages")
    
    if [ "$LANGUAGES_DATA" != "{}" ] && [ -n "$LANGUAGES_DATA" ]; then
        echo "Analyzing language statistics..."
        
        # Language-specific bytes-to-LOC ratios (more accurate than generic)
        declare -A LOC_RATIOS
        LOC_RATIOS["JavaScript"]=25
        LOC_RATIOS["TypeScript"]=28
        LOC_RATIOS["Python"]=22
        LOC_RATIOS["Java"]=35
        LOC_RATIOS["C"]=30
        LOC_RATIOS["C++"]=32
        LOC_RATIOS["Go"]=28
        LOC_RATIOS["Rust"]=30
        LOC_RATIOS["PHP"]=26
        LOC_RATIOS["Ruby"]=24
        LOC_RATIOS["CSS"]=18
        LOC_RATIOS["HTML"]=20
        LOC_RATIOS["Shell"]=25
        
        # Default ratio for unknown languages
        DEFAULT_RATIO=25
        
        # Parse languages and calculate LOC
        if command -v jq >/dev/null 2>&1; then
            # Use jq for accurate parsing
            echo "$LANGUAGES_DATA" | jq -r 'to_entries[] | "\(.key) \(.value)"' | while read -r lang bytes; do
                ratio=${LOC_RATIOS[$lang]:-$DEFAULT_RATIO}
                loc=$((bytes / ratio))
                TOTAL_LOC=$((TOTAL_LOC + loc))
                echo "  $lang: $bytes bytes ≈ $loc LOC (ratio: $ratio)"
            done > /tmp/loc_calc.txt
            
            # Read the calculated total
            TOTAL_LOC=$(awk '{sum += $NF} END {print sum}' /tmp/loc_calc.txt 2>/dev/null || echo 0)
            rm -f /tmp/loc_calc.txt
        else
            # Fallback: extract byte counts and use average ratio
            BYTE_COUNTS=$(echo "$LANGUAGES_DATA" | grep -o ': *[0-9][0-9]*' | grep -o '[0-9]*')
            for bytes in $BYTE_COUNTS; do
                if [ -n "$bytes" ] && [ "$bytes" -gt 0 ]; then
                    loc=$((bytes / DEFAULT_RATIO))
                    TOTAL_LOC=$((TOTAL_LOC + loc))
                fi
            done
        fi
        
        # Estimate total lines (LOC is typically 70-80% of total lines)
        TOTAL_LINES=$((TOTAL_LOC * 130 / 100))
        LINE_COUNT_METHOD="language_analysis"
        
        echo "Language-based estimation: $TOTAL_LOC lines of code"
    fi
    
    # Method 3: Repository tree analysis (if language stats failed)
    if [ "$TOTAL_LOC" -eq 0 ]; then
        echo "Language stats unavailable, analyzing repository tree..."
        
        TREE_DATA=$(curl -s -H "$AUTH_HEADER" -H "$ACCEPT_HEADER" -H "$API_VERSION_HEADER" \
            "https://api.github.com/repos/$OWNER/$REPO/git/trees/$DEFAULT_BRANCH?recursive=1")
        
        TRUNCATED=$(extract_json_value "$TREE_DATA" "truncated" "false")
        
        if [ "$TRUNCATED" = "true" ]; then
            # Large repository - use size-based estimation
            TOTAL_LOC=$((SIZE_KB * 15))  # Conservative: ~15 LOC per KB
            TOTAL_LINES=$((SIZE_KB * 20))
            LINE_COUNT_METHOD="size_based_large_repo"
        else
            # Count and categorize files
            declare -A FILE_LOC_ESTIMATES
            FILE_LOC_ESTIMATES["js"]=45
            FILE_LOC_ESTIMATES["ts"]=50
            FILE_LOC_ESTIMATES["py"]=40
            FILE_LOC_ESTIMATES["java"]=60
            FILE_LOC_ESTIMATES["c"]=55
            FILE_LOC_ESTIMATES["cpp"]=60
            FILE_LOC_ESTIMATES["go"]=45
            FILE_LOC_ESTIMATES["rs"]=50
            FILE_LOC_ESTIMATES["php"]=45
            FILE_LOC_ESTIMATES["rb"]=35
            FILE_LOC_ESTIMATES["css"]=25
            FILE_LOC_ESTIMATES["html"]=30
            FILE_LOC_ESTIMATES["sh"]=25
            
            # Extract and analyze file extensions
            for ext in "${!FILE_LOC_ESTIMATES[@]}"; do
                count=$(echo "$TREE_DATA" | grep '"type": "blob"' | grep -o '"path": "[^"]*"' | \
                    grep -iE "\\.$ext\"$" | wc -l | tr -d ' ')
                if [ "$count" -gt 0 ]; then
                    est_loc=$((count * FILE_LOC_ESTIMATES[$ext]))
                    TOTAL_LOC=$((TOTAL_LOC + est_loc))
                    echo "  .$ext files: $count × ${FILE_LOC_ESTIMATES[$ext]} = $est_loc LOC"
                fi
            done
            
            TOTAL_LINES=$((TOTAL_LOC * 130 / 100))
            LINE_COUNT_METHOD="file_analysis"
        fi
    fi
fi

# Final fallback
if [ "$TOTAL_LOC" -eq 0 ]; then
    TOTAL_LOC=$((SIZE_KB * 10))
    TOTAL_LINES=$((SIZE_KB * 15))
    LINE_COUNT_METHOD="size_fallback"
fi

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Create filename with timestamp
FILENAME="github_metrics_$(date +%Y%m%d_%H%M%S).csv"

# Create CSV header if file doesn't exist
if [ ! -f "$FILENAME" ]; then
    echo "repo_name,lines_of_code,total_lines,line_count_method,pull_requests_count,contributors_count,primary_language,stars,forks,size_kb,collected_at" > "$FILENAME"
fi

# Append data to CSV
echo "$OWNER/$REPO,$TOTAL_LOC,$TOTAL_LINES,$LINE_COUNT_METHOD,$PR_COUNT,$CONTRIBUTORS_COUNT,$LANGUAGE,$STARS,$FORKS,$SIZE_KB,$TIMESTAMP" >> "$FILENAME"

echo ""
echo "=== RESULTS ==="
echo "Repository: $OWNER/$REPO"
echo "Lines of Code: $TOTAL_LOC ($LINE_COUNT_METHOD)"
echo "Total Lines: $TOTAL_LINES"
echo "Pull Requests: $PR_COUNT"
echo "Contributors: $CONTRIBUTORS_COUNT"
echo "Primary Language: $LANGUAGE"
echo "Stars: $STARS"
echo "Forks: $FORKS"
echo "Size: ${SIZE_KB}KB"
echo ""
echo "Data saved to: $FILENAME"
echo ""
if [ "$CLOC_AVAILABLE" = false ]; then
    echo "💡 Tip: Install 'cloc' for accurate line counting:"
    echo "   Ubuntu/Debian: sudo apt-get install cloc"
    echo "   macOS: brew install cloc"
    echo "   CentOS/RHEL: sudo yum install cloc"
fi