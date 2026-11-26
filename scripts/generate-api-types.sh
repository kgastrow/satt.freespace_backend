#!/usr/bin/env bash
#
# OpenAPI TypeScript Type Generator
#
# This script downloads the OpenAPI schema from the running backend server
# and generates TypeScript types for the frontend.
#
# Usage:
#   ./scripts/generate-api-types.sh          # from project root
#   npm run generate:types                   # from app/frontend
#
# Requirements:
#   - Backend server must be running at http://localhost:8000
#   - API_DOCS_USERNAME and API_DOCS_PASSWORD environment variables must be set
#     (or use default values from backend settings)
#
# The generated types will be placed in:
#   app/frontend/src/types/api-generated.ts
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Determine script and project directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
FRONTEND_DIR="${PROJECT_ROOT}/app/frontend"

# Configuration
# Source frontend .env for BACKEND_DOCS_URL if available
if [ -f "${FRONTEND_DIR}/.env" ]; then
    # Only import non-VITE_ variables to avoid polluting environment
    eval "$(grep -E '^(BACKEND_DOCS_URL|API_DOCS_USERNAME|API_DOCS_PASSWORD)=' "${FRONTEND_DIR}/.env")"
fi

# If .ports.env exists in project root, source it for BACKEND_PORT
if [ -f "${PROJECT_ROOT}/.ports.env" ]; then
    source "${PROJECT_ROOT}/.ports.env"
    DEFAULT_BACKEND_URL="http://localhost:${BACKEND_PORT:-8000}"
elif [ -n "${BACKEND_DOCS_URL}" ]; then
    DEFAULT_BACKEND_URL="${BACKEND_DOCS_URL}"
else
    DEFAULT_BACKEND_URL="http://localhost:8000"
fi

BACKEND_URL="${BACKEND_URL:-$DEFAULT_BACKEND_URL}"
OPENAPI_PATH="${BACKEND_URL}/openapi.json"
OUTPUT_FILE="${FRONTEND_DIR}/src/types/api-generated.ts"
TEMP_SCHEMA="${PROJECT_ROOT}/openapi.json"

# Get credentials from environment, config.json, or use defaults
BACKEND_CONFIG="${PROJECT_ROOT}/app/backend/config.json"
if [ -z "$API_DOCS_USERNAME" ] && [ -f "$BACKEND_CONFIG" ]; then
    API_DOCS_USERNAME=$(python3 -c "import json; print(json.load(open('$BACKEND_CONFIG'))['api_docs']['username'])" 2>/dev/null)
fi
if [ -z "$API_DOCS_PASSWORD" ] && [ -f "$BACKEND_CONFIG" ]; then
    API_DOCS_PASSWORD=$(python3 -c "import json; print(json.load(open('$BACKEND_CONFIG'))['api_docs']['password'])" 2>/dev/null)
fi
API_DOCS_USERNAME="${API_DOCS_USERNAME:-ayzer}"
API_DOCS_PASSWORD="${API_DOCS_PASSWORD:-ayzer}"

echo -e "${GREEN}OpenAPI TypeScript Type Generator${NC}"
echo "===================================="
echo ""

# Check if backend is running
echo -e "${YELLOW}Checking backend health...${NC}"
if ! curl -s --fail "${BACKEND_URL}/health" > /dev/null; then
    # Backend is not running - check if we already have generated types
    if [ -f "${OUTPUT_FILE}" ]; then
        echo -e "${YELLOW}Backend server is not running, but types file already exists${NC}"
        echo -e "${GREEN}Skipping type generation - using existing types${NC}"
        echo ""
        echo "Existing file: ${OUTPUT_FILE}"
        echo ""
        echo "Note: To regenerate types, start the backend and run this script again."
        exit 0
    fi

    echo -e "${RED}Error: Backend server is not running at ${BACKEND_URL}${NC}"
    echo ""
    echo "Please start the backend server first:"
    echo "  cd app/backend && make dev"
    echo ""
    echo "Or use the project start script:"
    echo "  ./scripts/start.sh"
    exit 1
fi
echo -e "${GREEN}Backend is healthy${NC}"
echo ""

# Download OpenAPI schema with basic auth
echo -e "${YELLOW}Downloading OpenAPI schema...${NC}"
if ! curl -s --fail \
    -u "${API_DOCS_USERNAME}:${API_DOCS_PASSWORD}" \
    "${OPENAPI_PATH}" \
    -o "${TEMP_SCHEMA}"; then
    echo -e "${RED}Error: Failed to download OpenAPI schema${NC}"
    echo ""
    echo "Please check:"
    echo "  1. Backend server is running at ${BACKEND_URL}"
    echo "  2. API_DOCS_USERNAME and API_DOCS_PASSWORD are correct"
    echo "     Current username: ${API_DOCS_USERNAME}"
    echo ""
    echo "You can set credentials with:"
    echo "  export API_DOCS_USERNAME=your_username"
    echo "  export API_DOCS_PASSWORD=your_password"
    exit 1
fi
echo -e "${GREEN}Schema downloaded successfully${NC}"
echo ""

# Generate TypeScript types
echo -e "${YELLOW}Generating TypeScript types...${NC}"
cd "${FRONTEND_DIR}"
if ! npx openapi-typescript "${TEMP_SCHEMA}" -o src/types/api-generated.ts; then
    echo -e "${RED}Error: Failed to generate TypeScript types${NC}"
    rm -f "${TEMP_SCHEMA}"
    exit 1
fi
echo -e "${GREEN}Types generated successfully${NC}"
echo ""

# Clean up temp schema file
rm -f "${TEMP_SCHEMA}"

# Print summary
echo -e "${GREEN}✓ OpenAPI types generated successfully!${NC}"
echo ""
echo "Generated file: ${OUTPUT_FILE}"
echo ""
echo "You can now import types from this file:"
echo "  import type { paths, components } from '@/types/api-generated'"
echo ""
echo "Note: This file is auto-generated and git-ignored."
echo "      Run this script whenever the backend API changes."
