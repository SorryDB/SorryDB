#!/bin/bash
# browse_proofs.sh - Browse verified proofs with fzf preview

FILE="${1:-result.json}"

jq -r '.[] | select(.proof_verified == true) | "\(.sorry.id)\t\(.sorry.debug_info.goal | gsub("\n"; " ") | .[0:80])"' "$FILE" | \
fzf --delimiter='\t' \
    --with-nth=2 \
    --preview="jq -r '.[] | select(.sorry.id == \"{1}\") | \"Repo: \(.sorry.repo.remote)\nURL:  \(.sorry.debug_info.url)\n\nGoal:\n\(.sorry.debug_info.goal)\n\nProof:\n\(.proof)\"' \"$FILE\"" \
    --preview-window=right:60%:wrap
