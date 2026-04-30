# Rafiki Server Setup Guide

## Overview

Rafiki is an open-source Interledger connector implementing Open Payments specification. This guide shows how to set it up for your middleware.

## Quick Start (Docker)

### 1. Clone Rafiki

```bash
git clone https://github.com/interledger/rafiki.git
cd rafiki
```

### 2. Start with Docker

```bash
# Copy environment file
cp .env.example .env

# Edit .env if needed (default should work for local dev)
# DATABASE_URL=postgresql://postgres:postgres@postgres:5432/rafiki
# REDIS_URL=redis://redis:6379

# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f rafiki
```

### 3. Verify Installation

```bash
# Test if Rafiki is running
curl http://localhost:3001/.well-known/open-payments

# Expected response:
# {
#   "resource": "http://localhost:3001",
#   "auth_server": "http://localhost:3003"
# }
```

---

## Manual Setup (Development)

### Prerequisites
- Node.js v18+
- PostgreSQL
- Redis

### Steps

```bash
# 1. Clone repository
git clone https://github.com/interledger/rafiki.git
cd rafiki

# 2. Install dependencies
npm install

# 3. Set up environment
cp .env.example .env

# Edit .env:
# DATABASE_URL=postgresql://postgres:postgres@localhost:5432/rafiki
# REDIS_URL=redis://localhost:6379
# AUTH_SERVER_URL=http://localhost:3003

# 4. Run database migrations
npm run migrate

# 5. Start development server
npm run dev
```

---

## Rafiki Components

| Component | Port | Description |
|-----------|------|-------------|
| Rafiki API | 3001 | Main API server |
| Auth Server | 3003 | GNAP authentication |
| PostgreSQL | 5432 | Database |
| Redis | 6379 | Caching |

---

## Configure Middleware for Real Rafiki

### 1. Update `app/config.py`

Create configuration file:

```python
# app/config.py
RAFIKI_CONFIG = {
    "base_url": "http://localhost:3001",
    "auth_server": "http://localhost:3003",
    "wallet_addresses": {
        "coop1": "http://localhost:3001/coop1",
        "coop2": "http://localhost:3001/coop2",
        "001234": "http://localhost:3001/wallets/001234",
    }
}

def get_wallet_address(coop_id: str) -> str:
    """Get wallet address for a cooperative."""
    return RAFIKI_CONFIG["wallet_addresses"].get(coop_id)
```

### 2. Update `app/rafiki_client.py`

```python
from app.config import RAFIKI_CONFIG

class RafikiClient:
    def __init__(self, base_url: str = None, auth_token: str = None):
        self.base_url = base_url or RAFIKI_CONFIG["base_url"]
        self.auth_token = auth_token
        self.session = requests.Session()
        
        if auth_token:
            self.session.headers.update({
                'Authorization': f'GNAP {auth_token}',
                'Content-Type': 'application/json'
            })
```

### 3. Test Rafiki Connection

```bash
# Test from your middleware
cd /home/nif/Documents/middleware-code
source venv/bin/activate

python3 -c "
from app.rafiki_client import RafikiClient
client = RafikiClient(base_url='http://localhost:3001')
print('Rafiki client created')
"
```

---

## Wallet Address Setup

### Create Wallet Addresses for Cooperatives

```bash
# Using Rafiki CLI or API
# Example: Create wallet for coop1

curl -X POST http://localhost:3001/wallet-addresses \
  -H "Content-Type: application/json" \
  -d '{
    "walletAddress": "http://localhost:3001/coop1",
    "assetCode": "USD",
    "assetScale": 2
  }'
```

### Map Cooperatives to Wallets

Update `app/config.py`:

```python
RAFIKI_CONFIG = {
    "wallet_addresses": {
        "001234": "http://localhost:3001/wallets/001234",
        "005678": "http://localhost:3001/wallets/005678",
    }
}
```

---

## Testing Middleware with Real Rafiki

### 1. Start Rafiki

```bash
cd rafiki
docker-compose up -d
```

### 2. Start Middleware

```bash
cd /home/nif/Documents/middleware-code
./run.sh
```

### 3. Test Transfer (Real Rafiki)

```bash
curl -X POST "http://localhost:8000/iso8583/process?source_account=1234567890123456&amount=100.50&use_mock=false"
```

**Note:** Set `use_mock=false` to use real Rafiki.

---

## Common Issues

### Issue: "Connection refused"
**Solution:** Make sure Rafiki is running on port 3001

```bash
docker-compose ps
curl http://localhost:3001/health
```

### Issue: "Authentication failed"
**Solution:** Implement GNAP authentication or use test tokens

```python
# For testing, you might need to disable auth temporarily
# or use Rafiki's test mode
```

### Issue: "Wallet address not found"
**Solution:** Create wallet addresses first

```bash
# Create wallet addresses for your cooperatives
# Use Rafiki API or admin interface
```

---

## Resources

- **Rafiki GitHub:** https://github.com/interledger/rafiki
- **Open Payments Spec:** https://openpayments.guide/
- **Interledger Docs:** https://interledger.org/
- **Rafiki API Docs:** http://localhost:3001/docs (when running)

---

## Next Steps

1. ✅ Set up Rafiki server (Docker or manual)
2. ✅ Create wallet addresses for cooperatives
3. ✅ Update middleware config with wallet mappings
4. ✅ Test with `use_mock=false`
5. ✅ Implement GNAP authentication for production

Your middleware is ready for real Rafiki integration!
