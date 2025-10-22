"""Pizzaz Widget Demo Server

This demonstrates FastMCP's OpenAI widget support using the Pizzaz mapping library.
The widget renders an interactive map when you ask about pizza toppings.

Example usage:
    Show me a pizza map for pepperoni
    Create a pizza map with mushrooms
"""

from fastmcp import FastMCP

app = FastMCP("pizzaz-demo")

# Pizzaz widget HTML with the library loaded from OpenAI's CDN
PIZZAZ_HTML = """
<div id="pizzaz-root"></div>
<link rel="stylesheet" href="https://persistent.oaistatic.com/ecosystem-built-assets/pizzaz-0038.css">
<script type="module" src="https://persistent.oaistatic.com/ecosystem-built-assets/pizzaz-0038.js"></script>
"""


@app.ui.openai.widget(
    name="pizza-map",
    template_uri="ui://widget/pizza-map.html",
    html=PIZZAZ_HTML,
    title="Pizza Map",
    description="Show an interactive pizza map for a given topping",
    invoking="Hand-tossing a map",
    invoked="Served a fresh map",
    widget_csp_resources=["https://persistent.oaistatic.com"],
)
def show_pizza_map(topping: str) -> dict:
    """Show an interactive pizza map for the given topping.

    Args:
        topping: The pizza topping to map (e.g., "pepperoni", "mushrooms")

    Returns:
        Structured data for the widget to render
    """
    return {
        "pizza_topping": topping.strip(),
        "map_type": "delicious",
    }


@app.ui.openai.widget(
    name="pizza-tracker",
    template_uri="ui://widget/pizza-tracker.html",
    html=PIZZAZ_HTML,
    title="Pizza Tracker",
    description="Track a pizza order with real-time updates",
    invoking="Tracking your pizza",
    invoked="Pizza located!",
    widget_csp_resources=["https://persistent.oaistatic.com"],
)
def track_pizza(order_id: str) -> tuple[str, dict]:
    """Track a pizza order by order ID.

    This demonstrates returning both narrative text and structured data.

    Args:
        order_id: The pizza order ID to track

    Returns:
        Tuple of (narrative text, structured data for widget)
    """
    narrative = f"Tracking pizza order {order_id}. Your pizza is on the way!"
    data = {
        "order_id": order_id,
        "status": "out_for_delivery",
        "estimated_time": "15 minutes",
        "driver_location": {"lat": 47.6062, "lng": -122.3321},
    }
    return narrative, data


@app.ui.openai.widget(
    name="pizza-status",
    template_uri="ui://widget/pizza-status.html",
    html=PIZZAZ_HTML,
    title="Pizza Status",
    description="Get the current status of your pizza",
    widget_csp_resources=["https://persistent.oaistatic.com"],
)
def pizza_status() -> str:
    """Get a simple status message about pizza availability.

    This demonstrates returning text only (no structured data).

    Returns:
        Status message text
    """
    return "Pizza ovens are hot and ready! 🍕 We can make any topping you'd like."


if __name__ == "__main__":
    # Run with HTTP transport for testing with ChatGPT
    app.run(transport="http", host="0.0.0.0", port=8080)
