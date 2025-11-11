#!/usr/bin/env python3
"""
TOON vs JSON Token Comparison Demo

This script demonstrates the token savings achieved by using TOON format
compared to JSON for typical MCP responses with tabular data.
"""

from fastmcp.utilities.serialization import serialize

# Example 1: User list (TOON's sweet spot - uniform array)
users_data = {
    "users": [
        {"id": 1, "name": "Alice Johnson", "email": "alice@example.com", "active": True},
        {"id": 2, "name": "Bob Smith", "email": "bob@example.com", "active": True},
        {"id": 3, "name": "Charlie Brown", "email": "charlie@example.com", "active": False},
        {"id": 4, "name": "Diana Prince", "email": "diana@example.com", "active": True},
        {"id": 5, "name": "Eve Anderson", "email": "eve@example.com", "active": True},
    ]
}

# Example 2: Transaction log (another strong use case)
transactions_data = {
    "transactions": [
        {"timestamp": "2025-01-01T10:00:00Z", "amount": 150.50, "type": "debit", "merchant": "Coffee Shop"},
        {"timestamp": "2025-01-01T14:30:00Z", "amount": 45.00, "type": "debit", "merchant": "Grocery Store"},
        {"timestamp": "2025-01-02T09:15:00Z", "amount": 1200.00, "type": "credit", "merchant": "Salary Deposit"},
        {"timestamp": "2025-01-02T16:45:00Z", "amount": 80.25, "type": "debit", "merchant": "Restaurant"},
        {"timestamp": "2025-01-03T11:20:00Z", "amount": 25.99, "type": "debit", "merchant": "Online Store"},
    ]
}

# Example 3: Mixed data (not TOON's sweet spot)
mixed_data = {
    "status": "success",
    "message": "Query completed",
    "single_value": 42,
    "nested": {"a": 1, "b": 2},
}


def count_tokens_approx(text: str) -> int:
    """
    Rough approximation of token count for comparison.
    Real token count varies by model, but this gives a ballpark figure.
    ~4 characters per token is a common estimate.
    """
    return len(text) // 4


def compare_formats(data: dict, name: str) -> None:
    """Compare JSON and TOON serialization for given data."""
    print(f"\n{'=' * 70}")
    print(f"Example: {name}")
    print('=' * 70)
    
    # Serialize in both formats
    json_output = serialize(data, fmt="json")
    toon_output = serialize(data, fmt="toon")
    
    # Calculate metrics
    json_chars = len(json_output)
    toon_chars = len(toon_output)
    json_tokens = count_tokens_approx(json_output)
    toon_tokens = count_tokens_approx(toon_output)
    
    savings_chars = ((json_chars - toon_chars) / json_chars * 100)
    savings_tokens = ((json_tokens - toon_tokens) / json_tokens * 100)
    
    print(f"\nJSON Output ({json_chars} chars, ~{json_tokens} tokens):")
    print('-' * 70)
    print(json_output)
    
    print(f"\nTOON Output ({toon_chars} chars, ~{toon_tokens} tokens):")
    print('-' * 70)
    print(toon_output)
    
    print(f"\nSavings:")
    print('-' * 70)
    print(f"  Characters: {savings_chars:>6.1f}% reduction")
    print(f"  Est. Tokens: {savings_tokens:>6.1f}% reduction")


def main():
    """Run all comparisons."""
    from fastmcp.utilities.serialization import is_toon_available
    
    print("\n" + "=" * 70)
    print("  TOON vs JSON Token Comparison")
    print("=" * 70)
    
    if not is_toon_available():
        print("\n⚠️  TOON package not installed. Install with:")
        print("   pip install git+https://github.com/toon-format/toon-python.git")
        print("\nShowing JSON-only output...")
        json_output = serialize(users_data, fmt="json")
        print(f"\nJSON Output:\n{json_output}")
        return
    
    print("\n✓ TOON package detected\n")
    
    # Run comparisons
    compare_formats(users_data, "User List (TOON's sweet spot)")
    compare_formats(transactions_data, "Transaction Log (Strong use case)")
    compare_formats(mixed_data, "Mixed Data (Not ideal for TOON)")
    
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print("""
TOON excels with:
  ✓ Uniform arrays (same fields across items)
  ✓ Multiple fields per item
  ✓ Tabular data (logs, reports, lists)
  
JSON is better for:
  ✓ Deeply nested structures
  ✓ Heterogeneous data
  ✓ Single objects or small arrays
  ✓ Maximum compatibility
""")


if __name__ == "__main__":
    main()
