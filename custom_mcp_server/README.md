# Custom MCP Server

A custom MCP server integrating DataForSEO, Replicate, and Firecrawl functionalities.

## Project Setup

This project uses `pyproject.toml` to define dependencies and project metadata. It is recommended to use a virtual environment.

1.  **Create and activate a virtual environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
    ```

2.  **Install dependencies:**
    It's recommended to use `uv` for faster dependency management, which is also used in the Dockerfile.
    ```bash
    pip install uv
    uv pip install -e .
    ```
    This command installs the project in editable mode and its dependencies from `pyproject.toml`.

## API Keys

This server requires API keys for the integrated services. These must be set as environment variables:

*   `DATAFORSEO_API_KEY`: Your API key for DataForSEO.
*   `REPLICATE_API_TOKEN`: Your API token for Replicate.
*   `FIRECRAWL_API_KEY`: Your API key for Firecrawl.

Refer to the documentation of each service to obtain these keys.

## Running the Server Locally

To run the FastMCP server locally (e.g., for testing):

```bash
python server.py
```
The server will start using Streamable HTTP transport on `http://0.0.0.0:8080`.

## Tools

The following tools are available (currently as placeholders, requiring full API integration):

*   **DataForSEO:**
    *   `get_google_serp_data(keyword: str, location_name: str, language_code: str)`
    *   `seo_audit(url: str)`
    *   `get_all_backlinks(domain: str)`
    *   `speed_test_website(url: str)`
    *   `get_google_paid_ad_competitors(keyword: str, location_name: str, language_code: str)`
    *   `get_google_maps_reviews(place_id: str, language_code: str, location_coordinate: str)`
*   **Replicate:**
    *   `create_image(prompt: str)`
*   **Firecrawl:**
    *   `scrape_website(url: str)`

## Dependency Management and `requirements.txt`

This project uses `pyproject.toml` as the primary source for dependency declarations.

A `requirements.txt` file is also included.
*   **To install dependencies using `requirements.txt` (e.g., in some environments or if not using `uv` with `pyproject.toml` directly):**
    ```bash
    pip install -r requirements.txt
    ```

*   **To update/regenerate `requirements.txt` with exact versions from your current environment (after installing/updating via `pyproject.toml`):**
    If using `uv`:
    ```bash
    uv pip freeze > requirements.txt
    ```
    Or, if you want to generate a lock file first (recommended for reproducible builds with `uv`):
    ```bash
    uv pip lock -o uv.lock
    # Then, if needed, generate requirements.txt from the lock file (though uv typically uses uv.lock directly)
    # uv pip freeze --from-lockfile uv.lock > requirements.txt
    ```
    If using standard `pip`:
    ```bash
    pip freeze > requirements.txt
    ```
    It's good practice to regenerate this file when dependencies in `pyproject.toml` are changed or updated to ensure it reflects the working set of package versions.

## Deployment

Refer to `DEPLOYMENT.md` for instructions on deploying this application to DigitalOcean using Docker.

## .gitignore

A `.gitignore` file is included to exclude common Python artifacts, virtual environments, and other non-essential files from version control.
