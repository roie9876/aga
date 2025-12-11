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
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the script's directory (project root)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "📍 Project root: $PROJECT_ROOT"
echo ""

# ============================================================================
# STEP 1: KILL ALL EXISTING PROCESSES (INCLUDING BACKGROUND)
# ============================================================================
echo "🧹 Step 1: Cleaning up ALL existing processes..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Kill by port (most reliable method)
kill_port() {
    local port=$1
    local name=$2
    local pids=$(lsof -ti:$port 2>/dev/null || true)
    
    if [ -n "$pids" ]; then
        echo -e "${YELLOW}⏹️  Killing processes on port $port ($name)...${NC}"
        echo "   PIDs: $pids"
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 1
        echo -e "${GREEN}✅ Port $port cleared${NC}"
    else
        echo -e "${GREEN}✓ Port $port is free ($name)${NC}"
    fi
}

# Kill by process name
kill_process() {
    local pattern=$1
    local name=$2
    local pids=$(pgrep -f "$pattern" 2>/dev/null || true)
    
    if [ -n "$pids" ]; then
        echo -e "${YELLOW}⏹️  Killing $name processes...${NC}"
        echo "   Pattern: $pattern"
        echo "   PIDs: $pids"
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 1
        echo -e "${GREEN}✅ $name processes killed${NC}"
    else
        echo -e "${GREEN}✓ No $name processes found${NC}"
    fi
}

# Kill by port first (most reliable)
kill_port 8000 "Backend"
kill_port 5173 "Frontend"

# Kill by process pattern (catches background processes)
kill_process "uvicorn.*src.api.main" "Backend (uvicorn)"
kill_process "node.*vite" "Frontend (Vite/Node)"

# Final cleanup - kill any orphaned Python/Node processes from this project
kill_process "python.*aga" "Python (project)"
kill_process "node.*aga" "Node (project)"

# Wait to ensure ports are fully released
sleep 2

echo ""
echo -e "${GREEN}✅ All cleanup complete${NC}"
echo ""

# ============================================================================
# STEP 2: ENVIRONMENT CHECKS
# ============================================================================
echo "🔍 Step 2: Environment checks..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check Node.js version
echo -e "${BLUE}Checking Node.js...${NC}"
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Use Node.js 22
nvm use 22 > /dev/null 2>&1 || {
    echo -e "${YELLOW}⚠️  Node.js 22 not found. Installing...${NC}"
    nvm install 22
    nvm use 22
}

NODE_VERSION=$(node --version)
echo -e "${GREEN}✓ Using Node.js $NODE_VERSION${NC}"

# Check Python version
echo -e "${BLUE}Checking Python...${NC}"
if [ -f "$PROJECT_ROOT/.venv/bin/python" ]; then
    PYTHON_VERSION=$("$PROJECT_ROOT/.venv/bin/python" --version)
    echo -e "${GREEN}✓ Using $PYTHON_VERSION (virtual environment)${NC}"
else
    PYTHON_VERSION=$(python3 --version)
    echo -e "${YELLOW}⚠️  Using system Python: $PYTHON_VERSION${NC}"
    echo -e "${YELLOW}   Consider activating virtual environment: source .venv/bin/activate${NC}"
fi

# Check Azure CLI authentication
echo -e "${BLUE}Checking Azure authentication...${NC}"
if az account show > /dev/null 2>&1; then
    ACCOUNT=$(az account show --query name -o tsv)
    echo -e "${GREEN}✓ Authenticated as: $ACCOUNT${NC}"
else
    echo -e "${RED}❌ Not authenticated with Azure. Run: az login${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ Environment checks complete${NC}"
echo ""

# ============================================================================
# STEP 3: START BACKEND
# ============================================================================
echo "🐍 Step 3: Starting Backend (FastAPI)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd "$PROJECT_ROOT"

# Activate virtual environment if exists
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
    echo -e "${GREEN}✓ Virtual environment activated${NC}"
fi

# Start backend in background
python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000 > /tmp/mamad-backend.log 2>&1 &
BACKEND_PID=$!

echo -e "${GREEN}✓ Backend process started (PID: $BACKEND_PID)${NC}"
echo "  📄 Logs: tail -f /tmp/mamad-backend.log"
echo "  🌐 URL: http://localhost:8000"

# Wait for backend to be ready (health check)
echo -e "${BLUE}⏳ Waiting for backend health check...${NC}"
BACKEND_READY=false

for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        BACKEND_READY=true
        echo -e "${GREEN}✅ Backend is ready and healthy!${NC}"
        break
    fi
    
    # Check if process died
    if ! ps -p $BACKEND_PID > /dev/null 2>&1; then
        echo -e "${RED}❌ Backend process died! Check logs:${NC}"
        echo ""
        tail -20 /tmp/mamad-backend.log
        exit 1
    fi
    
    printf "."
    sleep 1
done

if [ "$BACKEND_READY" = false ]; then
    echo ""
    echo -e "${RED}❌ Backend failed to start within 30 seconds${NC}"
    echo -e "${RED}Last 20 lines of logs:${NC}"
    echo ""
    tail -20 /tmp/mamad-backend.log
    exit 1
fi

echo ""

# ============================================================================
# STEP 4: START FRONTEND
# ============================================================================
echo "⚛️  Step 4: Starting Frontend (React + Vite)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd "$PROJECT_ROOT/frontend"

# Start frontend in background
npm run dev > /tmp/mamad-frontend.log 2>&1 &
FRONTEND_PID=$!

echo -e "${GREEN}✓ Frontend process started (PID: $FRONTEND_PID)${NC}"
echo "  📄 Logs: tail -f /tmp/mamad-frontend.log"
echo "  🌐 URL: http://localhost:5173"

# Wait for frontend to be ready
echo -e "${BLUE}⏳ Waiting for frontend to be ready...${NC}"
FRONTEND_READY=false

for i in {1..30}; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5173 2>&1)
    
    if [ "$HTTP_CODE" = "200" ]; then
        FRONTEND_READY=true
        echo -e "${GREEN}✅ Frontend is ready and serving!${NC}"
        break
    fi
    
    # Check if process died
    if ! ps -p $FRONTEND_PID > /dev/null 2>&1; then
        echo -e "${RED}❌ Frontend process died! Check logs:${NC}"
        echo ""
        tail -20 /tmp/mamad-frontend.log
        exit 1
    fi
    
    printf "."
    sleep 1
done

if [ "$FRONTEND_READY" = false ]; then
    echo ""
    echo -e "${RED}❌ Frontend failed to start within 30 seconds${NC}"
    echo -e "${RED}Last 20 lines of logs:${NC}"
    echo ""
    tail -20 /tmp/mamad-frontend.log
    exit 1
fi

echo ""

# ============================================================================
# STEP 5: FINAL VERIFICATION
# ============================================================================
echo "🔍 Step 5: Final verification..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Verify processes are still running
BACKEND_ALIVE=$(ps -p $BACKEND_PID > /dev/null 2>&1 && echo "✓" || echo "✗")
FRONTEND_ALIVE=$(ps -p $FRONTEND_PID > /dev/null 2>&1 && echo "✓" || echo "✗")

# Verify ports are listening
BACKEND_PORT=$(lsof -ti:8000 > /dev/null 2>&1 && echo "✓" || echo "✗")
FRONTEND_PORT=$(lsof -ti:5173 > /dev/null 2>&1 && echo "✓" || echo "✗")

echo -e "${BLUE}Process Status:${NC}"
echo "  Backend PID $BACKEND_PID:    $BACKEND_ALIVE"
echo "  Frontend PID $FRONTEND_PID:  $FRONTEND_ALIVE"
echo ""
echo -e "${BLUE}Port Status:${NC}"
echo "  Port 8000 (Backend):   $BACKEND_PORT"
echo "  Port 5173 (Frontend):  $FRONTEND_PORT"
echo ""

# Final health checks
BACKEND_HEALTH=$(curl -s http://localhost:8000/health 2>&1 | grep -q "status" && echo "✓ Healthy" || echo "✗ Unhealthy")
FRONTEND_HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5173 2>&1)

echo -e "${BLUE}Health Checks:${NC}"
echo "  Backend:  $BACKEND_HEALTH"
echo "  Frontend: HTTP $FRONTEND_HTTP"
echo ""

# Success banner
if [ "$BACKEND_ALIVE" = "✓" ] && [ "$FRONTEND_ALIVE" = "✓" ] && [ "$BACKEND_PORT" = "✓" ] && [ "$FRONTEND_PORT" = "✓" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${GREEN}🎉 MAMAD Validation App is running!${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo -e "${GREEN}  🌐 Frontend:${NC}  http://localhost:5173"
    echo -e "${GREEN}  🔧 Backend:${NC}   http://localhost:8000"
    echo -e "${GREEN}  📚 API Docs:${NC}  http://localhost:8000/docs"
    echo ""
    echo -e "${BLUE}  📄 Logs:${NC}"
    echo "     Backend:  tail -f /tmp/mamad-backend.log"
    echo "     Frontend: tail -f /tmp/mamad-frontend.log"
    echo ""
    echo -e "${BLUE}  ⏹️  Stop:${NC}     ./stop.sh"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo -e "${GREEN}✨ App is ready! Open http://localhost:5173 in your browser${NC}"
    echo ""
else
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${RED}⚠️  WARNING: Some services may not be fully operational${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Check logs for details:"
    echo "  tail -f /tmp/mamad-backend.log"
    echo "  tail -f /tmp/mamad-frontend.log"
    echo ""
fi

# Option to tail logs
echo -e "${YELLOW}Press Ctrl+C to exit (app continues running in background)${NC}"
echo ""
trap 'echo ""; echo -e "${GREEN}✓ App is still running. Use ./stop.sh to stop.${NC}"; exit 0' INT

# Show combined logs
tail -f /tmp/mamad-backend.log /tmp/mamad-frontend.log
