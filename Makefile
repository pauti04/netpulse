.PHONY: install lint test ci demo charts clean

install:
	uv sync

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run mypy src/netpulse

test:
	uv run pytest -q

ci: lint test

demo:
	uv run netpulse demo

# Regenerate docs/img/*.svg from the bundled fixture and the recorded
# FPR numbers. Requires the [viz] extra installed.
charts:
	uv run python scripts/plot_youtube_hijack.py
	uv run python scripts/plot_fpr_bars.py

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
