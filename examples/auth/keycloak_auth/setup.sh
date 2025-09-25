#!/bin/bash

# Keycloak OAuth Example Setup Script
# This script helps set up the Keycloak example environment

set -e

echo "🚀 Setting up Keycloak OAuth Example..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo "❌ uv not found. Please install uv first: https://github.com/astral-sh/uv"
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file..."
    cp .env.example .env
    echo "✅ Created .env file with default configuration"
else
    echo "📝 Using existing .env file"
fi

# Create virtual environment with uv
echo "🐍 Setting up Python virtual environment with uv..."
if [ ! -d ".venv" ]; then
    echo "📁 Creating new virtual environment..."
    uv venv
else
    echo "📁 Virtual environment already exists, using existing one..."
fi

# Activate virtual environment and install dependencies
echo "📦 Installing Python dependencies with uv..."
source .venv/bin/activate  # Unix/Linux/macOS
# For Windows: source .venv/Scripts/activate
uv pip install -r requirements.txt

# Start Keycloak using docker-compose
echo "🐳 Starting Keycloak with docker-compose..."
docker-compose up -d

# Wait for Keycloak to become ready
echo "⏳ Waiting for Keycloak to become ready..."
echo ""

timeout=120
counter=0

while [ $counter -lt $timeout ]; do
    if curl -s http://localhost:8080/health/ready > /dev/null 2>&1; then
        echo "✅ Keycloak is ready!"
        break
    fi

    # Show recent logs while waiting
    echo "   Still waiting... ($counter/$timeout seconds)"
    echo "   Recent logs:"
    docker logs --tail 3 keycloak-fastmcp 2>/dev/null | sed 's/^/     /' || echo "     (logs not available yet)"
    echo ""

    sleep 5
    counter=$((counter + 5))
done

if [ $counter -ge $timeout ]; then
    echo "❌ Keycloak failed to get ready within $timeout seconds"
    echo "   Check logs with: docker logs -f keycloak-fastmcp"
    exit 1
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Activate the venv with:
echo "     source .venv/bin/activate  # Unix/Linux/macOS"
echo "     # or .venv\\Scripts\\activate  # Windows"
echo "  2. Start the server: python server.py"
echo "  3. In another terminal, activate the venv and test with:"
echo "     source .venv/bin/activate  # Unix/Linux/macOS"
echo "     # or .venv\\Scripts\\activate  # Windows"
echo "     python client.py"
echo ""
echo "Keycloak Admin Console: http://localhost:8080/admin"
echo "  Username: admin"
echo "  Password: admin123"
echo ""
echo "Test User Credentials:"
echo "  Username: testuser"
echo "  Password: password123"
echo ""
echo "To check the Keycloak logs: docker logs -f keycloak-fastmcp"
echo "To stop Keycloak: docker-compose down"