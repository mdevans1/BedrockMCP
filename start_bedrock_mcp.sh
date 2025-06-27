#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Navigate to the project directory (same as script directory)
cd "$SCRIPT_DIR"

# Load environment variables from .env file if it exists
if [ -f ".env" ]; then
    echo "Loading environment variables from .env file..."
    # Use the most reliable method from GitHub gist: set -a enables auto-export
    set -a
    source .env
    set +a
else
    echo "Warning: .env file not found, using environment variables from mcp.json"
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Error: Virtual environment .venv not found in $SCRIPT_DIR"
    exit 1
fi

# Activate the virtual environment
source .venv/bin/activate

# Check if activation was successful
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Error: Failed to activate virtual environment"
    exit 1
fi

# Run the MCP server with all passed arguments
python bedrock_mcp_server.py "$@" 