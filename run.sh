#!/bin/bash

echo "Starting Payment Middleware..."
echo "================================"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/update dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Run the application
echo ""
echo "Starting FastAPI server..."
echo "API docs available at: http://localhost:8000/docs"
echo "================================"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
