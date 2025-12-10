#!/bin/bash

# Startup script for MAMAD Validation App
# This script kills any running instances and starts both frontend and backend

set -e  # Exit on error

echo "🚀 Starting MAMAD Validation App..."
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to check if a process is running
check_process() {
    pgrep -f "$1" > /dev/null 2>&1
}

# Function to kill process
kill_process() {
    local process_name=$1
    local display_name=$2
    
    if check_process "$process_name"; then
        echo -e "${YELLOW}⏹️  Stopping existing $display_name...${NC}"
        pkill -f "$process_name" || true
        sleep 2
        
        # Force kill if still running
        if check_process "$process_name"; then
            echo -e "${RED}⚠️  Force killing $display_name...${NC}"
            pkill -9 -f "$process_name" || true
            sleep 1
        fi
        echo -e "${GREEN}✅ $display_name stopped${NC}"
    else
        echo -e "${GREEN}✓ No existing $display_name process found${NC}"
    fi
}

echo "📍 Current directory: $(pwd)"
echo ""

# Kill existing processes
echo "🧹 Cleaning up existing processes..."
kill_process "uvicorn" "Backend (Python)"
kill_process "vite.*frontend" "Frontend (Vite)"
echo ""

# Check Node.js version
echo "🔍 Checking Node.js version..."
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Use Node.js 22
nvm use 22 > /dev/null 2>&1 || {
    echo -e "${RED}❌ Node.js 22 not found. Installing...${NC}"
    nvm install 22
    nvm use 22
}

NODE_VERSION=$(node --version)
echo -e "${GREEN}✓ Using Node.js $NODE_VERSION${NC}"
echo ""

# Check Python version
echo "🔍 Checking Python..."
PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}✓ Using $PYTHON_VERSION${NC}"
echo ""

# Check Azure CLI authentication
echo "🔐 Checking Azure authentication..."
if az account show > /dev/null 2>&1; then
    ACCOUNT=$(az account show --query name -o tsv)
    TENANT=$(az account show --query tenantId -o tsv)
    echo -e "${GREEN}✓ Authenticated as: $ACCOUNT${NC}"
    echo -e "${GREEN}  Tenant: $TENANT${NC}"
else
    echo -e "${RED}⚠️  Not authenticated with Azure. Please run: az login${NC}"
    exit 1
fi

# Check Azure Developer CLI (azd) authentication
echo "🔐 Checking Azure Developer CLI (azd) authentication..."
if azd auth login --check-status > /dev/null 2>&1; then
    echo -e "${GREEN}✓ azd is authenticated${NC}"
else
    echo -e "${YELLOW}⚠️  azd not authenticated. Logging in with storage scope...${NC}"
    azd auth login --scope https://storage.azure.com/.default
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ azd authentication successful${NC}"
    else
        echo -e "${RED}❌ azd authentication failed${NC}"
        exit 1
    fi
fi
echo ""

# Start Backend
echo "🐍 Starting Backend (FastAPI)..."
cd /Users/robenhai/aga
python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000 > /tmp/mamad-backend.log 2>&1 &
BACKEND_PID=$!
echo -e "${GREEN}✓ Backend started (PID: $BACKEND_PID)${NC}"
echo "  📄 Logs: tail -f /tmp/mamad-backend.log"
echo "  🌐 URL: http://localhost:8000"
echo ""

# Wait for backend to start
echo "⏳ Waiting for backend to be ready..."
for i in {1..30}; do
    HEALTH_CHECK=$(curl -s http://localhost:8000/health 2>&1)
    if echo "$HEALTH_CHECK" | grep -q "status"; then
        echo -e "${GREEN}✓ Backend is ready!${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ Backend failed to start within 30 seconds${NC}"
        echo -e "${RED}Check logs: tail -f /tmp/mamad-backend.log${NC}"
        exit 1
    fi
    sleep 1
done
echo ""

# Start Frontend
echo "⚛️  Starting Frontend (React + Vite)..."
cd /Users/robenhai/aga/frontend
npm run dev > /tmp/mamad-frontend.log 2>&1 &
FRONTEND_PID=$!
echo -e "${GREEN}✓ Frontend started (PID: $FRONTEND_PID)${NC}"
echo "  📄 Logs: tail -f /tmp/mamad-frontend.log"
echo "  🌐 URL: http://localhost:5173"
echo ""

# Wait for frontend to start
echo "⏳ Waiting for frontend to be ready..."
for i in {1..30}; do
    FRONTEND_CHECK=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5173 2>&1)
    if [ "$FRONTEND_CHECK" = "200" ]; then
        echo -e "${GREEN}✓ Frontend is ready!${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ Frontend failed to start within 30 seconds${NC}"
        echo -e "${RED}Check logs: tail -f /tmp/mamad-frontend.log${NC}"
        exit 1
    fi
    sleep 1
done
echo ""

# Success message
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}🎉 MAMAD Validation App is running!${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  🌐 Frontend:  http://localhost:5173"
echo "  🔧 Backend:   http://localhost:8000"
echo "  📚 API Docs:  http://localhost:8000/docs"
echo ""
echo "  📄 Backend logs:  tail -f /tmp/mamad-backend.log"
echo "  📄 Frontend logs: tail -f /tmp/mamad-frontend.log"
echo ""
echo "  ⏹️  To stop: ./stop.sh or pkill -f 'uvicorn|vite.*frontend'"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✨ App is ready! Open http://localhost:5173 in your browser"
echo ""

# Keep script running to show status
echo "Press Ctrl+C to view logs (app will continue running in background)"
echo ""

# Tail logs
trap 'echo ""; echo "App is still running in background. Use ./stop.sh to stop."; exit 0' INT
tail -f /tmp/mamad-backend.log /tmp/mamad-frontend.log
