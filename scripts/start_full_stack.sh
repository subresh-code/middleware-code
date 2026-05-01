#!/bin/bash
set -e

echo "Stopping middleware stack to free ports..."
cd /home/nif/payment-middleware
docker compose down || true

echo "Creating shared network if not exists..."
docker network create rafiki-shared 2>/dev/null || echo "Network already exists"

echo "Starting Rafiki core services..."
cd /home/nif/payment-middleware/rafiki/localenv/cloud-nine-wallet
docker compose \
  -f docker-compose.yml \
  -f docker-compose.override.yml \
  up cloud-nine-backend cloud-nine-auth shared-database shared-redis cloud-nine-admin \
  --build -d

echo "Waiting for Rafiki backend to be healthy..."
sleep 15

echo "Starting middleware..."
cd /home/nif/payment-middleware
docker compose up --build -d

echo "Running verification..."
echo "Middleware health:"
curl -s http://localhost:8000/health

echo ""
echo "Middleware can reach Rafiki Admin API:"
docker exec payment_api curl -s http://cloud-nine-wallet-backend:3001/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"{ __typename }"}' | head -c 100

echo ""
echo "Done. Full stack running."
