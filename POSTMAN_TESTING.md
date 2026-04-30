# Postman Testing Guide for Payment Middleware

## API Base URL
```
http://localhost:8000
```

## Interactive API Docs (Alternative to Postman)
```
http://localhost:8000/docs
```
FastAPI provides automatic Swagger UI documentation where you can test all endpoints directly in the browser.

---

## Endpoint 1: Process ISO 8583 Message

**Method:** `POST`  
**URL:** `http://localhost:8000/iso8583/process`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| source_account | string | Yes | Source account number (ISO Field 2) |
| amount | float | Yes | Transfer amount |
| currency | string | No | Currency code (default: "840" = USD) |
| source_coop_id | string | No | Source cooperative ID |
| dest_coop_wallet | string | No | Destination wallet URL |
| use_mock | boolean | No | Use mock Rafiki client (default: true) |

**Example Request (Postman):**
```
POST http://localhost:8000/iso8583/process?source_account=1234567890123456&amount=100.50&currency=840&source_coop_id=001234&use_mock=true
```

**Example Response:**
```json
{
  "mti": "0210",
  "fields": {
    "2": "1234567890123456",
    "3": "000000",
    "4": "000000010050",
    "11": "123456",
    "37": "123456789012",
    "39": "00",
    "49": "840"
  },
  "bitmap": "7238000108008000",
  "transaction_id": 1,
  "success": true,
  "message": "Transfer completed"
}
```

---

## Endpoint 2: Simplified Transfer

**Method:** `POST`  
**URL:** `http://localhost:8000/transfer`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| source_account | string | Yes | Source account number |
| amount | float | Yes | Transfer amount |
| dest_coop_wallet | string | Yes | Destination coop's Rafiki wallet URL |
| currency | string | No | Currency code (default: "840") |
| source_coop_id | string | No | Source cooperative ID |
| use_mock | boolean | No | Use mock Rafiki client |

**Example Request:**
```
POST http://localhost:8000/transfer?source_account=1234567890123456&amount=250.75&dest_coop_wallet=http://localhost:3001/bob&use_mock=true
```

---

## Endpoint 3: List Transactions

**Method:** `GET`  
**URL:** `http://localhost:8000/transactions`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| skip | integer | No | Number of records to skip (pagination) |
| limit | integer | No | Max records to return (default: 100) |
| status | string | No | Filter by status (PENDING, COMPLETED, FAILED) |

**Example Request:**
```
GET http://localhost:8000/transactions
GET http://localhost:8000/transactions?status=COMPLETED
GET http://localhost:8000/transactions?skip=0&limit=10
```

---

## Endpoint 4: Get Single Transaction

**Method:** `GET`  
**URL:** `http://localhost:8000/transactions/{transaction_id}`

**Example Request:**
```
GET http://localhost:8000/transactions/1
```

---

## Endpoint 5: Parse ISO 8583 Hex

**Method:** `POST`  
**URL:** `http://localhost:8000/iso8583/parse`

**Request Body (JSON):**
```json
{
  "hex_data": "3032303072380001080080003136313233343536373839303132333435363030303030303030303030303031303035303034333031353038343931323334353612312..."
}
```

**Example Request in Postman:**
- Method: `POST`
- URL: `http://localhost:8000/iso8583/parse`
- Headers: `Content-Type: application/json`
- Body (raw JSON):
```json
{
  "hex_data": "30323030723800010800800031363132333435363738393031323334353630"
}
```

---

## Endpoint 6: Health Check

**Method:** `GET`  
**URL:** `http://localhost:8000/health`

**Example Request:**
```
GET http://localhost:8000/health
```

**Example Response:**
```json
{
  "status": "ok"
}
```

---

## Postman Collection Setup

### Import OpenAPI Spec
FastAPI automatically generates OpenAPI specification:
```
http://localhost:8000/openapi.json
```

You can import this into Postman:
1. Open Postman
2. Click "Import" button
3. Select "Link" and enter: `http://localhost:8000/openapi.json`
4. Click "Import"

### Manual Collection Setup

Create a new Postman Collection called "Payment Middleware" with these requests:

1. **Health Check**
   - Method: GET
   - URL: `{{base_url}}/health`

2. **Process ISO 8583**
   - Method: POST
   - URL: `{{base_url}}/iso8583/process`
   - Params: source_account, amount, currency, etc.

3. **Simple Transfer**
   - Method: POST
   - URL: `{{base_url}}/transfer`
   - Params: source_account, amount, dest_coop_wallet, etc.

4. **List Transactions**
   - Method: GET
   - URL: `{{base_url}}/transactions`

5. **Get Transaction**
   - Method: GET
   - URL: `{{base_url}}/transactions/:id`

6. **Parse ISO 8583 Hex**
   - Method: POST
   - URL: `{{base_url}}/iso8583/parse`
   - Body: raw JSON

**Set Collection Variable:**
- Variable: `base_url`
- Value: `http://localhost:8000`

---

## Testing Workflow

### Test 1: Health Check
```
GET http://localhost:8000/health
```
Expected: `{"status": "ok"}`

### Test 2: Process ISO 8583 Transfer
```
POST http://localhost:8000/iso8583/process?source_account=1234567890123456&amount=100.00&currency=840&use_mock=true
```
Expected: Response with MTI 0210 and success=true

### Test 3: View Transaction
```
GET http://localhost:8000/transactions/1
```
Expected: Transaction details with status "COMPLETED"

### Test 4: List All Transactions
```
GET http://localhost:8000/transactions
```
Expected: Array of transaction objects

---

## Response Codes (ISO 8583 Field 39)

| Code | Meaning |
|------|---------|
| 00 | Approved/Completed |
| 51 | Insufficient funds |
| 91 | Issuer or switch inoperative |
| 94 | Duplicate transaction |

---

## Quick Test Script (in Postman Tests tab)

Add this to any request's "Tests" tab to automatically validate response:

```javascript
// Check status code
pm.test("Status code is 200", function () {
    pm.response.to.have.status(200);
});

// Check response structure
pm.test("Response has required fields", function () {
    var jsonData = pm.response.json();
    pm.expect(jsonData).to.have.property('success');
    pm.expect(jsonData).to.have.property('transaction_id');
});

// Log transaction ID
pm.test("Log transaction ID", function () {
    var jsonData = pm.response.json();
    console.log("Transaction ID:", jsonData.transaction_id);
    pm.environment.set("last_transaction_id", jsonData.transaction_id);
});
```
