#!/bin/bash
# Script to view database contents using Docker

echo "=========================================="
echo "Payment Middleware - Database Viewer"
echo "=========================================="
echo ""

# Check if Docker is running
if ! docker ps | grep -q payment_db; then
    echo "Error: payment_db container is not running."
    echo "Start it with: docker-compose up -d"
    exit 1
fi

echo "Tables in database:"
docker exec payment_db psql -U postgres -d payments -c "\dt"
echo ""

echo "=========================================="
echo "All Transactions:"
echo "=========================================="
docker exec payment_db psql -U postgres -d payments -c "SELECT id, mti, stan, rrn, source_account, amount, currency, status, response_code, created_at FROM transactions ORDER BY id DESC;"
echo ""

echo "=========================================="
echo "Transaction Count by Status:"
echo "=========================================="
docker exec payment_db psql -U postgres -d payments -c "SELECT status, COUNT(*) as count FROM transactions GROUP BY status;"
echo ""

echo "=========================================="
echo "Recent Transactions (Last 5):"
echo "=========================================="
docker exec payment_db psql -U postgres -d payments -c "SELECT id, amount, currency, status, created_at FROM transactions ORDER BY created_at DESC LIMIT 5;"
