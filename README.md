# ISO 8583 to ILP Middleware

A production-grade middleware system that bridges traditional banking ISO 8583 financial messages with modern Interledger Protocol (ILP) networks via Rafiki implementation.

## Overview

This middleware acts as a protocol translator, converting ISO 8583 transaction messages to ILP packets, sending them to Rafiki for processing, and converting responses back to ISO 8583 format.

## Architecture

```
ISO 8583 Message → Parser → Validator → ILP Mapper → Packet Builder → Rafiki API → Response Mapper → ISO 8583 Response
```

## Tech Stack

- **Language:** Python 3.11+
- **Async Framework:** asyncio
- **HTTP Client:** requests with retry logic
- **Configuration:** Pydantic settings
- **Logging:** Structured JSON logging
- **Testing:** unittest with mocking

## Project Structure

```
middleware-code/
├── app/
│   ├── core/
│   │   ├── server.py            # TCP server for ISO 8583 messages
│   │   └── orchestrator.py      # Main workflow controller
│   ├── modules/
│   │   ├── iso8583/
│   │   │   ├── parser.py        # ISO 8583 message parsing
│   │   │   └── validator.py     # Message validation rules
│   │   ├── ilp/
│   │   │   ├── mapper.py        # ISO ↔ ILP data transformation
│   │   │   └── packet.py        # ILP packet construction
│   │   └── rafiki/
│   │       ├── client.py        # Rafiki API communication
│   │       └── config.py        # Rafiki-specific settings
│   └── utils/
│       ├── logger.py            # Structured logging system
│       └── config.py            # Global configuration
├── tests/
│   ├── test_iso8583.py          # Unit tests for ISO parsing
│   ├── test_ilp.py              # Unit tests for ILP mapping
│   └── test_integration.py      # Integration tests
├── docs/
│   └── architecture.md          # Detailed architecture docs
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Prerequisites

- Python 3.11+
- pip
- Virtual environment (recommended)

## Installation

1. Clone the repository
2. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate     # Windows
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Create a `.env` file with the following variables:

```env
MIDDLEWARE_HOST=0.0.0.0
MIDDLEWARE_PORT=8583
RAFIKI_BASE_URL=https://your-rafiki-instance.com
RAFIKI_API_KEY=your-api-key
LOG_LEVEL=INFO
```

## Running the Application

Start the middleware server:

```bash
python -m app.core.server
```

The server will listen for ISO 8583 messages on the configured host and port.

## Testing

Run the test suite:

```bash
python -m unittest discover tests/
```

## API Flow

1. **Receive ISO 8583**: TCP server accepts raw ISO 8583 messages
2. **Parse Message**: Extract MTI, bitmap, and data elements
3. **Validate**: Check required fields and business rules
4. **Map to ILP**: Transform ISO data to ILP packet structure
5. **Send to Rafiki**: HTTP POST to Rafiki's ILP endpoint
6. **Process Response**: Handle ILP Fulfill/Reject packets
7. **Map Back**: Convert ILP response to ISO 8583 format
8. **Return Response**: Send ISO 8583 response to originator

## Key Features

- **Modular Design**: Clean separation of concerns
- **Error Handling**: Comprehensive exception handling and logging
- **Retry Logic**: Automatic retries for network failures
- **Security**: Input validation and secure API communication
- **Monitoring**: Structured logging for observability
- **Testing**: Unit and integration test coverage

## Production Considerations

- **Scalability**: Async processing for high throughput
- **Monitoring**: Integration with logging aggregators
- **Security**: TLS encryption, API key management
- **Deployment**: Container-ready with Docker

## Contributing

1. Follow the existing code structure
2. Add tests for new features
3. Update documentation
4. Use type hints and docstrings

## License

[Add your license here]

```text
payment-middleware/
├── app/
│   └── main.py          # Entry point and API routes
├── Dockerfile           # Docker image configuration
├── docker-compose.yml   # Multi-container orchestration
├── requirements.txt     # Python dependencies
└── README.md            # Project documentation
```
