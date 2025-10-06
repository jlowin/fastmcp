#!/bin/bash

# Keycloak Start Script
# Starts a local Keycloak instance with Docker Compose

set -e

echo "🚀 Starting Keycloak..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

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
echo "🎉 Keycloak is ready!"
echo ""
echo "Keycloak Admin Console: http://localhost:8080/admin"
echo "  Username: admin"
echo "  Password: admin123"
echo ""
echo "Test User Credentials:"
echo "  Username: testuser"
echo "  Password: password123"
echo ""
echo "Useful commands:"
echo "  • Check Keycloak logs: docker logs -f keycloak-fastmcp"
echo "  • Stop Keycloak: docker-compose down"
echo "  • Restart Keycloak: docker-compose restart"