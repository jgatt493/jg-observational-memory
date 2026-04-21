# Contributing to observational-memory

Thanks for your interest in contributing! This project is early-stage (v0.1.0) and contributions are welcome.

## Getting Started

```bash
git clone https://github.com/jgatt493/jg-observational-memory.git
cd jg-observational-memory
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest
```

Tests mock all Anthropic API calls — no API key needed to run the suite.

## Submitting Changes

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Add or update tests for any new behavior
4. Run `pytest` and make sure everything passes
5. Open a pull request with a clear description of what and why

## Reporting Bugs

Open an issue at https://github.com/jgatt493/jg-observational-memory/issues with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Python version and OS

## Code Style

- Follow existing patterns in the codebase
- Keep functions focused and files small
- Mock external dependencies in tests (no real API calls)

## What to Work On

Check the [issues](https://github.com/jgatt493/jg-observational-memory/issues) for open tasks. If you want to work on something that doesn't have an issue yet, open one first so we can discuss the approach.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
