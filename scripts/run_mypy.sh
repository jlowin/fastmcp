set -o errexit

uv run --frozen --all-extras --all-groups --python 3.10 mypy ./src
uv run --frozen --all-extras --all-groups --python 3.10 mypy ./examples
# uv run --frozen mypy ./tests
