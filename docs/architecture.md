# middleware-code/docs/architecture.md

# Middleware System Architecture

## Overview
This middleware system bridges traditional ISO 8583 banking messages with modern ILP (Interledger Protocol) networks via Rafiki. It acts as a protocol translator, enabling seamless interoperability between legacy banking systems and next-generation payment networks.

## System Components

### 1. Core Layer
- **server.py**: Entry point that receives ISO 8583 messages via TCP socket or HTTP endpoint
- **orchestrator.py**: Central controller managing the entire request-response pipeline

### 2. Module Layer
- **iso8583/**: Handles parsing, validation, and serialization of ISO 8583 messages
- **ilp/**: Manages ILP packet creation and response handling
- **rafiki/**: Interfaces with Rafiki's API for ILP transactions

### 3. Utility Layer
- **logger.py**: Structured logging for monitoring and debugging
- **config.py**: Centralized configuration management

## Data Flow Architecture

```
ISO 8583 Message (TCP/HTTP)
        ↓
    server.py
        ↓
  orchestrator.py
        ↓
iso8583/parser.py
        ↓
iso8583/validator.py
        ↓
  ilp/mapper.py
        ↓
 ilp/packet.py
        ↓
rafiki/client.py
        ↓
Rafiki API Response
        ↓
  orchestrator.py
        ↓
ISO 8583 Response
        ↓
Return to Source
```

## Key Design Principles

1. **Modularity**: Each module has a single responsibility
2. **Separation of Concerns**: Clear boundaries between protocol handling
3. **Error Resilience**: Comprehensive error handling and retry mechanisms
4. **Observability**: Detailed logging and monitoring
5. **Scalability**: Asynchronous processing for high throughput
6. **Security**: Input validation, secure API communication

## Module Responsibilities

### ISO8583 Module
- Parse MTI, bitmap, and data elements
- Validate message structure and required fields
- Handle different message types (0200, 0210, etc.)

### ILP Module
- Transform ISO 8583 fields to ILP packet structure
- Handle currency conversion and address mapping
- Manage ILP-specific data formats

### Rafiki Module
- Authenticate with Rafiki API
- Send ILP packets and handle responses
- Implement retry logic for network failures

### Core Module
- Coordinate all modules in sequence
- Handle exceptions and fallback scenarios
- Ensure atomic transaction processing

## Production Considerations

- **Concurrency**: Use asyncio for non-blocking I/O
- **Monitoring**: Integrate with logging and metrics systems
- **Security**: TLS encryption, API key management
- **Scalability**: Containerization with Docker, load balancing
- **Testing**: Comprehensive unit and integration tests