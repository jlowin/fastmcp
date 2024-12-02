# Getting your development environment set up properly
```bash
uv venv
.venv\Scripts\activate
uv pip install -e ".[dev]"
```

# Fixing `AttributeError: module 'collections' has no attribute 'Callable'`
- open `.venv\Lib\site-packages\pyreadline\py3k_compat.py`
- change `return isinstance(x, collections.Callable)` to 
``` 
from collections.abc import Callable
return isinstance(x, Callable)
```

