FROM ghcr.io/astral-sh/uv:bookworm-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy

# Copy the application
COPY . .

# Install dependencies
RUN uv sync --frozen --no-install-project

# Sync the project
RUN uv sync --frozen

# Copy entrypoint script
COPY docker/backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Expose the port
EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]

# Default command
CMD ["uv", "run", "python", "manage.py", "runserver", "0.0.0.0:8000"]
