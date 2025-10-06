# Server Lifespan

This module provides a `FastMCP` class which enters its Lifespan once on server startup and exits its lifespan on server exit.

This allows developers to easily define depedencies that will start with the server and be cleaned up on server exit.

## Usage

See the [example implementation](./example.py) for how to use the Server Lifespan.