#!/bin/bash

# Stop script for MAMAD Validation App

set -e

echo "🛑 Stopping MAMAD Validation App..."
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Function to kill process
kill_process() {
    local process_name=$1
    local display_name=$2
    
    if pgrep -f "$process_name" > /dev/null 2>&1; then
        echo -e "${YELLOW}⏹️  Stopping $display_name...${NC}"
        pkill -f "$process_name" || true
        sleep 2
        
        # Force kill if still running
        if pgrep -f "$process_name" > /dev/null 2>&1; then
            echo -e "${RED}⚠️  Force killing $display_name...${NC}"
            pkill -9 -f "$process_name" || true
            sleep 1
        fi
        echo -e "${GREEN}✅ $display_name stopped${NC}"
    else
        echo -e "${GREEN}✓ $display_name is not running${NC}"
    fi
}

kill_process "uvicorn" "Backend"
kill_process "vite.*frontend" "Frontend"

echo ""
echo -e "${GREEN}✅ All services stopped${NC}"
echo ""
