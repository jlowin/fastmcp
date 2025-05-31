# Deploying to DigitalOcean

This guide provides instructions for deploying the custom MCP server to DigitalOcean. We recommend using the DigitalOcean App Platform for ease of use, but deploying to a Droplet with Docker is also an option.

## Prerequisites

1.  **Docker Image:** You need to have a Docker image of the application. Build it using the `Dockerfile` in this directory:
    ```bash
    docker build -t your-image-name:latest .
    ```
    (Replace `your-image-name` with a name of your choice, e.g., `custom-mcp-server`)

2.  **Container Registry:** Push your Docker image to a container registry.
    *   **DigitalOcean Container Registry (DOCR):**
        1.  Create a registry in your DigitalOcean account.
        2.  Log in to your DOCR: `doctl registry login`
        3.  Tag your image: `docker tag your-image-name:latest registry.digitalocean.com/your-registry-name/your-image-name:latest`
        4.  Push the image: `docker push registry.digitalocean.com/your-registry-name/your-image-name:latest`
    *   **Docker Hub:**
        1.  Log in to Docker Hub: `docker login`
        2.  Tag your image: `docker tag your-image-name:latest your-dockerhub-username/your-image-name:latest`
        3.  Push the image: `docker push your-dockerhub-username/your-image-name:latest`

3.  **API Keys:** Have your API keys ready for DataForSEO, Replicate, and Firecrawl.

## Option 1: Using DigitalOcean App Platform (Recommended)

1.  **Create an App:**
    *   In your DigitalOcean dashboard, go to "Apps" and click "Create App".
    *   Choose your container registry (DOCR or Docker Hub) and select the image you pushed.

2.  **Configure the App:**
    *   **Service Type:** Choose "Web Service".
    *   **HTTP Port:** Set to `8080` (as configured in the Dockerfile and `server.py`).
    *   **Environment Variables:** This is crucial. Add the following environment variables with your actual API keys:
        *   `DATAFORSEO_API_KEY` = `your_dataforseo_api_key`
        *   `REPLICATE_API_TOKEN` = `your_replicate_api_token`
        *   `FIRECRAWL_API_KEY` = `your_firecrawl_api_key`
    *   **Instance Size & Scaling:** Choose appropriate instance sizes and scaling options based on your expected load.
    *   **Autodeploy:** Enable autodeploy if you want the app to update automatically when you push new images to your registry.

3.  **Deploy:**
    *   Review your settings and deploy the app. DigitalOcean will provide you with a URL for your service.

## Option 2: Using a DigitalOcean Droplet with Docker

1.  **Create a Droplet:**
    *   Choose an OS image with Docker pre-installed (e.g., from the Marketplace tab: "Docker on Ubuntu").
    *   Select a plan and region.
    *   Add SSH keys for access.

2.  **Connect to your Droplet:**
    *   SSH into your Droplet: `ssh root@your_droplet_ip`

3.  **Pull the Docker Image:**
    *   If using DOCR, you might need to log in: `docker login -u your_token -p your_token registry.digitalocean.com` (using a DOCR token).
    *   Or for Docker Hub: `docker login`
    *   Pull your image: `docker pull registry.digitalocean.com/your-registry-name/your-image-name:latest` (or from Docker Hub).

4.  **Run the Docker Container:**
    ```bash
    docker run -d -p 80:8080 \
      -e DATAFORSEO_API_KEY="your_dataforseo_api_key" \
      -e REPLICATE_API_TOKEN="your_replicate_api_token" \
      -e FIRECRAWL_API_KEY="your_firecrawl_api_key" \
      --name custom-mcp-app \
      registry.digitalocean.com/your-registry-name/your-image-name:latest
    ```
    *   `-d`: Run in detached mode.
    *   `-p 80:8080`: Map port 80 on the Droplet to port 8080 in the container. This allows access via the Droplet's IP without specifying the port.
    *   `-e`: Set environment variables for your API keys.
    *   `--name custom-mcp-app`: Assign a name to your container.

5.  **Firewall (Optional but Recommended):**
    *   Configure UFW (Uncomplicated Firewall) on your Droplet to only allow necessary traffic (e.g., on port 80 for HTTP, 443 for HTTPS if you set up SSL, and your SSH port).

## Accessing Your Server

Once deployed, your MCP server should be accessible via the URL provided by the App Platform or your Droplet's IP address (port 80 if mapped as above).

## Important Considerations

*   **HTTPS:** For production, always configure HTTPS. App Platform can often handle this automatically. For Droplets, you'd typically use a reverse proxy like Nginx or Caddy with Let's Encrypt.
*   **Logging & Monitoring:** Set up proper logging and monitoring for your application. App Platform provides some built-in tools. For Droplets, you might configure Docker logging drivers or use external services.
*   **Actual API Implementation:** Remember that the tool functions in `server.py` are currently placeholders. You will need to implement the actual API calls to DataForSEO, Replicate, and Firecrawl using their respective client libraries and your API keys for the server to be functional.
