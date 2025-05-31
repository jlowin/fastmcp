# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PIP_NO_CACHE_DIR 1

# Set the working directory in the container
WORKDIR /app

# Install uv (recommended by FastMCP and good for venv/dependency management)
RUN pip install uv

# Copy project configuration and lock file (if it exists)
# This step leverages Docker layer caching. If only code changes, dependencies won't be reinstalled.
COPY pyproject.toml uv.lock* ./
# uv.lock* is used in case uv.lock doesn't exist on the first build;
# if pyproject.toml changes, this layer and subsequent layers will be rebuilt.

# Install project dependencies using uv
# This will also create/update uv.lock if it's not present or outdated
RUN uv pip install . --system

# Copy the rest of the application code into the working directory
COPY . .

# Expose the port the app runs on
EXPOSE 8080

# Define environment variable placeholders for API keys.
# These should be set when running the container.
ENV DATAFORSEO_API_KEY=""
ENV REPLICATE_API_TOKEN=""
ENV FIRECRAWL_API_KEY=""

# Command to run the application
CMD ["python", "server.py"]
