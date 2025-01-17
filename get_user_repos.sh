#!/bin/bash

# Check if GITHUB_TOKEN is set
if [ -z "$GITHUB_TOKEN" ]; then
    echo "Error: GITHUB_TOKEN environment variable is not set"
    exit 1
fi

# Function to fetch repositories for a user
fetch_user_repos() {
    local username=$1
    local page=1
    local per_page=100

    # Create directory for output if it doesn't exist
    mkdir -p user_repos

    echo "Fetching repositories for $username..."
    
    while true; do
        # Make API request with authentication
        response=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
            "https://api.github.com/users/$username/repos?page=$page&per_page=$per_page&type=owner")

        # Check if response is empty or we've reached the end
        if [ "$(echo $response | jq '. | length')" -eq 0 ]; then
            break
        fi

        # Extract repository names and append to user's file
        echo "$response" | jq -r '.[].full_name' >> "user_repos/${username}_repos.txt"

        # Rate limit check
        remaining=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
            "https://api.github.com/rate_limit" | jq .rate.remaining)
        
        if [ "$remaining" -lt 10 ]; then
            echo "Rate limit nearly exceeded. Waiting for reset..."
            sleep 60
        fi

        ((page++))
        sleep 1  # Be nice to GitHub API
    done
}

# Main script
while IFS= read -r username; do
    # Skip empty lines and trim whitespace
    username=$(echo "$username" | tr -d '[:space:]')
    if [ -n "$username" ]; then
        fetch_user_repos "$username"
    fi
done

# Combine all repository lists into one file
cat user_repos/*_repos.txt | sort -u > all_repositories.txt
echo "Complete! Repository list saved in all_repositories.txt" 