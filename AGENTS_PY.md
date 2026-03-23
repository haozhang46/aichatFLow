You are the coding agent for this Python repository.

Follow repository conventions strictly. Do not invent a new style unless explicitly requested.

# Primary objective
Generate and refactor Python code that is maintainable, typed, testable, and aligned with the repository architecture.

# Architecture rules
- domain: pure business rules and models
- application: orchestration and use cases
- infra: external systems, database, files, network, cache
- interface: HTTP/CLI/RPC adapters and entrypoints
- schemas: structured payload definitions
- utils: pure helper functions
- tests: automated tests

Rules:
- domain should not depend on infra
- application should not contain low-level IO details
- interface should stay thin
- infra handles side effects
- avoid placing business logic in utils

# Naming rules
- Python files: snake_case.py
- Classes: PascalCase
- Functions and variables: snake_case
- Constants: UPPER_SNAKE_CASE
- Names must be semantically explicit

Avoid vague names like:
- temp.py
- utils2.py
- do_it
- handle_data
- obj
- data2
- my_service

# Typing and schema rules
- Add type hints by default
- Avoid Any unless truly necessary
- Prefer explicit input/output types
- Validate external inputs with pydantic or dataclass-based schemas
- Do not pass raw dict payloads through many layers without structure

# Function rules
- functions should generally stay under 50 lines
- one function should do one job
- split complex conditionals into named helpers
- keep input/output explicit

# Class rules
- create classes only when state or dependency injection is needed
- avoid giant classes
- class names must describe their role clearly

# Error handling rules
- never use bare except
- never silently pass
- catch expected exceptions only
- add useful context in logs and errors

# Logging rules
- use logging, not print
- log actionable messages with context
- never log secrets or sensitive data

# Testing rules
- add tests for new business logic
- cover happy path, edge cases, and error path
- use pytest
- test file names should start with test_

# Implementation preferences
- prefer simple, clear, stable implementations
- prefer standard library unless extra dependencies are justified
- preserve existing repository style
- reuse existing modules before creating new ones

# Required reasoning before coding
Before writing code, determine:
1. which layer the change belongs to
2. the correct file path
3. whether an existing module should be reused
4. whether names follow repository conventions
5. whether typing and validation are sufficient
6. whether exception handling is explicit and safe

# Response behavior
When creating or refactoring code:
- first state the module category
- then state the suggested path
- then implement the code
- include tests if relevant
- preserve behavior during refactors unless behavior changes are explicitly requested

If the request conflicts with repository conventions, prefer conventions and explain the tradeoff.