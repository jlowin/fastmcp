# Getting your development environment set up properly
To get your environment up and running properly, you'll need a slightly different set of commands that are windows specific:
```bash
uv venv
.venv\Scripts\activate
uv pip install -e ".[dev]"
```

This will install the package in editable mode, and install the development dependencies.


# Fixing `AttributeError: module 'collections' has no attribute 'Callable'`
- open `.venv\Lib\site-packages\pyreadline\py3k_compat.py`
- change `return isinstance(x, collections.Callable)` to 
``` 
from collections.abc import Callable
return isinstance(x, Callable)
```

# Helpful notes
For developing FastMCP
## Install local development version of FastMCP into a local FastMCP project server
- ensure
- change directories to your FastMCP Server location so you can install it in your .venv
- run `.venv\Scripts\activate` to activate your virtual environment
- Then run a series of commands to uninstall the old version and install the new
```bash
# First uninstall
uv pip uninstall fastmcp

# Clean any build artifacts in your fastmcp directory
cd C:\path\to\fastmcp
del /s /q *.egg-info

# Then reinstall in your weather project
cd C:\path\to\new\fastmcp_server
uv pip install --no-cache-dir -e C:\Users\justj\PycharmProjects\fastmcp

# Check that it installed properly and has the correct git hash
pip show fastmcp
```

## Running the FastMCP server with Inspector
MCP comes with a node.js application called Inspector that can be used to inspect the FastMCP server. To run the inspector, you'll need to install node.js and npm. Then you can run the following commands:
```bash
fastmcp dev server.py
```
This will launch a web app on http://localhost:5173/ that you can use to inspect the FastMCP server.

## If you start development before creating a fork - your get out of jail free card
- Add your fork as a new remote to your local repository `git remote add fork git@github.com:YOUR-USERNAME/REPOSITORY-NAME.git`
  - This will add your repo, short named 'fork', as a remote to your local repository
- Verify that it was added correctly by running `git remote -v`
- Commit your changes
- Push your changes to your fork `git push fork <branch>`
- Create your pull request on GitHub 


