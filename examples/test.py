#!/usr/bin/env python3
"""Test script for FastMCP metadata server functionality using built-in modules."""

import time
import urllib.request
import urllib.parse
import json
from fastmcp import FastMCP

def test_metadata_server():
    """Test the metadata server functionality."""
    
    server = FastMCP("test-server", instructions="A test server for metadata")
    
    @server.tool
    def get_weather(city: str) -> str:
        """Get weather information for a city."""
        return f"Weather for {city}: Sunny, 75°F"
    
    @server.tool
    def calculate_sum(a: int, b: int) -> int:
        """Calculate the sum of two numbers."""
        return a + b
    
    @server.resource("weather://forecast")
    def get_forecast() -> str:
        """Get weather forecast."""
        return "7-day forecast: Sunny with occasional clouds"
    
    @server.resource("data://{dataset}")
    def get_data(dataset: str) -> str:
        """Get dataset information."""
        return f"Data for {dataset}"
    
    @server.prompt
    def analyze_data(data_type: str) -> list:
        """Analyze data prompt."""
        return [{"role": "user", "content": f"Please analyze this {data_type}"}]
    
    print("Starting metadata server...")
    
    server.start_metadata_server(
        port=8080,
        cors_enabled=True,
        custom_headers={
            "X-Test-Header": "FastMCP-Test",
            "X-Server-Version": "1.0.0"
        }
    )
    
    time.sleep(1)
    
    print("Testing metadata endpoint...")
    
    try:
        request = urllib.request.Request("http://localhost:8080/.well-known/mcp-metadata")
        
        with urllib.request.urlopen(request) as response:
            status_code = response.getcode()
            headers = dict(response.headers)
            content = response.read().decode('utf-8')
            
            print(f"Status Code: {status_code}")
            print(f"Headers: {headers}")
            
            if status_code == 200:
                print("✓ Metadata endpoint working!")
                
                # Parse and display metadata
                metadata = json.loads(content)
                print("\nMetadata Content:")
                print(json.dumps(metadata, indent=2))
                
                # Verify expected content
                assert "name" in metadata
                assert "capabilities" in metadata
                assert "schemas" in metadata
                
                capabilities = metadata["capabilities"]
                schemas = metadata["schemas"]
                
                print(f"\n✓ Server: {metadata['name']}")
                print(f"✓ Tools: {capabilities['tools']}")
                print(f"✓ Resources: {capabilities['resources']}")
                print(f"✓ Resource Templates: {capabilities['resource_templates']}")
                print(f"✓ Prompts: {capabilities['prompts']}")
                
                # Verify CORS headers
                if "Access-Control-Allow-Origin" in headers:
                    print("✓ CORS headers present")
                
                # Verify custom headers
                if "X-Test-Header" in headers:
                    print("✓ Custom headers present")
                
            else:
                print(f"✗ Metadata endpoint failed: {status_code}")
                print(f"Response: {content}")
                
    except urllib.error.URLError as e:
        print(f"✗ Could not connect to metadata server: {e}")
    except Exception as e:
        print(f"✗ Error testing metadata endpoint: {e}")
    
    # test OPTIONS request (CORS preflight)
    print("\nTesting CORS preflight...")
    try:
        request = urllib.request.Request("http://localhost:8080/.well-known/mcp-metadata")
        request.get_method = lambda: 'OPTIONS'
        
        with urllib.request.urlopen(request) as response:
            status_code = response.getcode()
            headers = dict(response.headers)
            
            print(f"OPTIONS Status Code: {status_code}")
            
            if status_code == 200:
                print("✓ CORS preflight working!")
                if "Access-Control-Allow-Origin" in headers:
                    print("✓ CORS headers in OPTIONS response")
            else:
                print(f"✗ CORS preflight failed: {status_code}")
                
    except Exception as e:
        print(f"✗ Error testing CORS preflight: {e}")
    
    # test 404 handling
    print("\nTesting 404 handling...")
    try:
        request = urllib.request.Request("http://localhost:8080/unknown-path")
        
        with urllib.request.urlopen(request) as response:
            status_code = response.getcode()
            print(f"✗ Expected 404, got {status_code}")
            
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("✓ 404 handling working!")
        else:
            print(f"✗ Expected 404, got {e.code}")
    except Exception as e:
        print(f"✗ Error testing 404: {e}")
    
    # Stop server
    print("\nStopping metadata server...")
    server.stop_metadata_server()
    print("✓ Test completed!")

def quick_test():
    """Quick validation test."""
    print("Quick validation test...")
    
    server = FastMCP("quick-test")
    
    @server.tool
    def test_tool(msg: str) -> str:
        return f"Echo: {msg}"
    
    server.start_metadata_server(port=8080)
    time.sleep(0.5)
    
    try:
        with urllib.request.urlopen("http://localhost:8080/.well-known/mcp-metadata") as response:
            data = json.loads(response.read().decode())
            print(f"✓ Quick test passed - Server: {data['name']}, Tools: {data['capabilities']['tools']}")
    except Exception as e:
        print(f"✗ Quick test failed: {e}")
    finally:
        server.stop_metadata_server()

if __name__ == "__main__":
    # Run full test
    test_metadata_server()
    
    print("\n" + "="*50)
    
    # Run quick test
    quick_test()