import os

# --- Configuration and API Key Management ---
# Load API keys from environment variables.
# These should be set in your deployment environment.

DATAFORSEO_API_KEY = os.getenv("DATAFORSEO_API_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")

# Example of other potential configurations:
# DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
# REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
