# Pull Request

## Description
Please provide a clear and concise description of the changes made in this pull request.

## Related Issue
**Required**: This PR must be linked to an open issue.
- Closes #(issue number)
- Related to #(issue number)

## Type of Change
Please check the relevant option(s):

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Refactoring (no functional changes)
- [ ] Performance improvement
- [ ] Other (please describe):

## Testing
Please check all that apply:

- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] All new and existing tests pass (`uv run pytest`)
- [ ] I have performed manual testing of the changes
- [ ] I have tested the changes in different environments/configurations

## Code Quality
Please check all that apply:

- [ ] My code follows the project's coding standards
- [ ] I have run the linting checks (`uv run pre-commit run --all-files`)
- [ ] I have run type checking (`uv run ty check`) 
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas

## Documentation
Please check all that apply:

- [ ] I have updated relevant documentation
- [ ] I have added docstrings to new functions/classes
- [ ] I have updated the changelog (if applicable)
- [ ] I have added examples for new features (if applicable)

## Dependencies
Please check if applicable:

- [ ] I have updated `pyproject.toml` with any new dependencies
- [ ] I have run `uv sync` to ensure dependencies are properly installed
- [ ] All dependencies are compatible with Python ≥3.10

## Additional Notes
Any additional information, context, or screenshots that would be helpful for reviewers.

---

**Reminder**: Before submitting this PR, ensure you have run the required development workflow:
```bash
uv sync                              # Install dependencies
uv run pre-commit run --all-files    # Ruff + Prettier + ty
uv run pytest                        # Run full test suite
```