.DEFAULT_GOAL := help
ZSH_LOGIN     := zsh -lc

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

# ── Dev ──────────────────────────────────────────────────────────────────────

install:  ## Install package in editable mode
	@uv tool install --editable .

test:  ## Run pytest
	@uv run pytest -q

check:  ## py_compile + pytest
	@python3 -m py_compile $$(find src tests -name '*.py' 2>/dev/null)
	@uv run pytest -q

# ── Package ───────────────────────────────────────────────────────────────────

build:  ## Build package with uv
	@rm -rf dist && uv build

publish: build  ## Publish to PyPI as k-mail-mcp (requires UV_PUBLISH_TOKEN via bw-env)
	@$(ZSH_LOGIN) 'if ! env | grep -q "^UV_PUBLISH_TOKEN="; then \
		echo "UV_PUBLISH_TOKEN missing — run bw-env first"; exit 1; fi; \
	uv publish --check-url https://pypi.org/simple'

release: check build publish push  ## Full release: check → build → publish → push

# ── Git ───────────────────────────────────────────────────────────────────────

push:  ## Push current branch to all remotes (github + gitlab)
	@branch="$$(git branch --show-current)"; \
	for remote in $$(git remote); do \
		echo "==> pushing $$branch to $$remote"; \
		git push "$$remote" "$$branch"; \
	done

push-tags:  ## Push all tags to all remotes
	@for remote in $$(git remote); do git push "$$remote" --tags; done

status:  ## git status --short
	@git status --short

log:  ## Last 10 commits oneline
	@git log --oneline -10
