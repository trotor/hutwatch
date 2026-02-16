Create a GitHub issue for the HutWatch project.

If arguments are provided, use them as the issue title. Otherwise ask the user what the issue is about.

Create the issue using `gh issue create` with this template:

```
## Description
[Clear description of the feature/bug/task]

## Problem
[Why this is needed / what's broken]

## Implementation
[Suggested approach or steps]

## Acceptance Criteria
- [ ] [Testable criterion 1]
- [ ] [Testable criterion 2]
```

Fill in all sections based on the conversation context and user input.

After creating the issue, display the issue URL and number.

If the current work relates to an existing issue, remind the user to reference it in commits with `Fixes #N` or `Closes #N`.
