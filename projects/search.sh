#!/bin/bash
# Wrapper script to run the academic search CLI

# Run the CLI module
python -m api_academic_search.search_cli "$@"
