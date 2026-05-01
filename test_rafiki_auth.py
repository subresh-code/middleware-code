#!/usr/bin/env python3
"""Test Rafiki API with proper authentication"""
import hmac
import hashlib
import time
import json
import urllib.request
import urllib.parse

# Configuration
ADMIN_SECRET = "iyIgCprjb9uL8wFckR+pLEkJWMB7FJhgkvqhTQR/964="
OPERATOR_TENANT_ID = "438fa74a-fa7d-4317-9ced-dde32ece1787"
API_URL = "http://localhost:3001/graphql"

def simple_canonicalize(obj):
    """Simple JSON canonicalization - sorts keys"""
    return json.dumps(obj, sort_keys=True, separators=(',', ':'))

def generate_signature(secret, body, version=1):
    """Generate Rafiki API signature"""
    timestamp = int(time.time() * 1000)
    
    # The body needs to be formatted as GraphQL request
    formatted_request = {
        "query": body.get("query"),
        "variables": body.get("variables"),
        "operationName": body.get("operationName")
    }
    # Remove None values
    formatted_request = {k: v for k, v in formatted_request.items() if v is not None}
    
    payload = f"{timestamp}.{simple_canonicalize(formatted_request)}"
    
    digest = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return f"t={timestamp}, v{version}={digest}"

# Test query
query_body = {"query": "{ __typename }"}
signature = generate_signature(ADMIN_SECRET, query_body)

print(f"Generated signature: {signature}")
print(f"Tenant ID: {OPERATOR_TENANT_ID}\n")

# Make request
headers = {
    "Content-Type": "application/json",
    "signature": signature,
    "tenant-id": OPERATOR_TENANT_ID
}

req = urllib.request.Request(
    API_URL,
    data=json.dumps(query_body).encode(),
    headers=headers,
    method="POST"
)

try:
    response = urllib.request.urlopen(req)
    print(f"Response: {response.read().decode()}")
except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}: {e.read().decode()}")
except Exception as e:
    print(f"Error: {e}")
