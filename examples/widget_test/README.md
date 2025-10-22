# OpenAI Widget Demo

This directory contains a demonstration of FastMCP's OpenAI widget support using the Pizzaz mapping library.

## What's Here

- **`pizzaz_server.py`**: Demo server with three widget examples showing different return patterns
- **`test_widgets.py`**: Test script that validates the auto-transformation works correctly

## Setup

This uses a local virtual environment with an editable install of FastMCP:

```bash
# Already done, but for reference:
cd examples/widget_test
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ../..
```

## Running the Demo

### Test the Widgets Locally

```bash
source .venv/bin/activate
python test_widgets.py
```

This will test all three widget patterns:
- **dict return**: Structured data only (no narrative text)
- **str return**: Narrative text only (no structured data)
- **tuple[str, dict] return**: Both narrative text and structured data

### Run the Server

```bash
source .venv/bin/activate
python pizzaz_server.py
```

The server will start on `http://0.0.0.0:8080`.

### Inspect the Server

```bash
source .venv/bin/activate
fastmcp inspect pizzaz_server.py
```

Use `--format fastmcp` to see the full JSON including OpenAI metadata.

## Testing with ChatGPT

To test the widgets with ChatGPT:

1. Expose your server with ngrok:
   ```bash
   ngrok http 8080
   ```

2. In ChatGPT, go to Settings → Developer Mode and add your server

3. Try prompts like:
   - "Show me a pizza map for pepperoni"
   - "Track pizza order 12345"
   - "What's the pizza status?"

## Widget Examples

### 1. Pizza Map (dict return)

Returns structured data only, which the widget renders:

```python
@app.ui.openai.widget(
    name="pizza-map",
    template_uri="ui://widget/pizza-map.html",
    html=PIZZAZ_HTML,
    invoking="Hand-tossing a map",
    invoked="Served a fresh map",
)
def show_pizza_map(topping: str) -> dict:
    return {"pizza_topping": topping.strip()}
```

### 2. Pizza Tracker (tuple return)

Returns both narrative text and structured data:

```python
@app.ui.openai.widget(
    name="pizza-tracker",
    template_uri="ui://widget/pizza-tracker.html",
    html=PIZZAZ_HTML,
    invoking="Tracking your pizza",
    invoked="Pizza located!",
)
def track_pizza(order_id: str) -> tuple[str, dict]:
    narrative = f"Tracking pizza order {order_id}..."
    data = {"order_id": order_id, "status": "out_for_delivery"}
    return narrative, data
```

### 3. Pizza Status (str return)

Returns text only, no structured data:

```python
@app.ui.openai.widget(
    name="pizza-status",
    template_uri="ui://widget/pizza-status.html",
    html=PIZZAZ_HTML,
)
def pizza_status() -> str:
    return "Pizza ovens are hot and ready! 🍕"
```

## How It Works

The `@app.ui.openai.widget` decorator automatically:

1. **Registers the HTML** as an MCP resource with MIME type `text/html+skybridge`
2. **Adds OpenAI metadata** to the tool including:
   - `openai/outputTemplate`: Points to the widget HTML
   - `openai/toolInvocation/invoking` and `invoked`: Status messages
   - `openai.com/widget`: Embedded widget resource
   - CSP configuration for security
3. **Auto-transforms return values** to OpenAI format:
   - `dict` → `{"content": [], "structuredContent": {...}}`
   - `str` → `{"content": [{"type": "text", "text": "..."}], "structuredContent": {}}`
   - `tuple[str, dict]` → Both content and structuredContent

You don't need to manually call `build_widget_tool_response()` or `register_decorated_widgets()` - it all happens automatically!
