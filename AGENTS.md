# thinkchainai/fastmcp — Agent Context

Org fork of [PrefectHQ/fastmcp](https://github.com/PrefectHQ/fastmcp) for MCPBundles Connect Auth upstream work.

Submodule path in MCPBundles monorepo: `public_github_repos/fastmcp`.

**Execution checklist:** parent repo `product/mcp-connect-auth/coding-plan.md` § P7 (provider PR), § P7b (auth-attached middleware follow-up).

## Remotes

| Remote | URL | Use |
|--------|-----|-----|
| `origin` | `https://github.com/thinkchainai/fastmcp.git` | Push feature branches; open PRs to PrefectHQ |
| `upstream` | `https://github.com/PrefectHQ/fastmcp.git` | Sync before new work |

```bash
git fetch upstream
git checkout main
git merge upstream/main   # or rebase feature branch onto upstream/main
```

## Workflow

1. Branch in this submodule (e.g. `mcpbundles-connect-provider`).
2. Add `McpbundlesConnectProvider` under the upstream auth providers path (follow layout at ship time).
3. Push to **`origin`**; open PR **`PrefectHQ/fastmcp`** from `thinkchainai/fastmcp:<branch>`.
4. Parent monorepo bumps submodule SHA on `main` while PR is open.

## Rules

- Provider uses only **public** FastMCP APIs (vendor apps `pip install fastmcp`, not fork internals).
- PyPI package `mcpbundles-mcp-connect` may re-export until upstream merge — keep provider file in sync.
