# Payment Middleware

Middleware designed to translate ISO 20022 messages to ILP/Rafiki protocols.

## Tech Stack

- **Framework:** FastAPI
- **Language:** Python 3.11
- **Database:** PostgreSQL
- **Containerization:** Docker & Docker Compose

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- (Optional) [Python 3.11+](https://www.python.org/downloads/) for local development

## Getting Started

### Using Docker (Recommended)

1. Clone the repository.
2. Build and start the containers:
   ```bash
   docker-compose up --build
   ```
3. The API will be available at `http://localhost:8000`.
4. Interactive API documentation (Swagger UI) can be found at `http://localhost:8000/docs`.

### Local Development

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   uvicorn app.main:app --reload
   ```

## API Endpoints

- `GET /health`: Check if the service is running.

## Project Structure

```text
payment-middleware/
├── app/
│   └── main.py          # Entry point and API routes
├── Dockerfile           # Docker image configuration
├── docker-compose.yml   # Multi-container orchestration
├── requirements.txt     # Python dependencies
└── README.md            # Project documentation
```
