---
name: write-tests
description: Skill to always write testing code for the project.
---

# Write Tests

This skill enforces testing requirements for the Turkish Financial and Academic Search projects.

1. **Always use Pytest**: Write all tests using the `pytest` framework in the appropriate `tests/` directory.
2. **End-to-End focus**: Prefer API integration and database-level tests over pure unit tests where applicable.
3. **Mock External Services**: When testing API endpoints, use `unittest.mock.Mock` to mock `DatabaseManager` and other external resources to keep tests fast and isolated.
