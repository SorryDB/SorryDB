#!/bin/bash
set -e

# Filter only sorries from the checklist database that are from the checklist branch
jq '
  .sorries |= map(select(.repo.branch == "checklist"))
' checklist_database.json > checklist_sorry_list.json
