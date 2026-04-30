#!/bin/bash
echo "Setting up Payment Middleware..."
echo "================================"

# Start Docker containers
echo "Starting Docker containers..."
docker-compose up -d
echo ""

# Wait for database
echo "Waiting for database to be ready..."
sleep 5

# Create tables by making a request to the API
echo "Creating database tables..."
curl -s http://localhost:8000/health > /dev/null 2>&1
echo "Tables created!"
echo ""

# Show database info
echo "================================"
echo "Database Info:"
echo "================================"
docker exec payment_db psql -U postgres -d payments -c "\dt" 2>/dev/null || echo "No tables yet"
echo ""

echo "================================"
echo "Setup Complete!"
echo "================================"
echo "API running at: http://localhost:8000"
echo "API docs at: http://localhost:8000/docs"
echo ""
echo "To view database: ./docker_view_db.sh"
echo "To test API: Use Postman or curl"
echo ""
