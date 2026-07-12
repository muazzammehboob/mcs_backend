FROM python:3.12-slim

WORKDIR /app

# Prevent Python from writing pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install hatchling (build backend)
RUN pip install --no-cache-dir hatchling

# Copy dependency definition
COPY pyproject.toml ./

# Copy application source code and configurations
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations

# Install the application and its dependencies
RUN pip install --no-cache-dir .

# Create a directory for the SQLite database so it can be volume mounted
RUN mkdir -p /app/data

EXPOSE 8000

# Run the FastAPI application using uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
