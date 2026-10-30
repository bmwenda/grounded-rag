---
name: issue-writing
description: Write or review GitHub issues for the Grounded RAG repository so they contain the context and acceptance criteria needed for implementation.
---

# Issue writing

Use this skill when creating a repository issue or checking whether an existing
issue is ready for the project workflow. Keep the issue focused on one outcome.

Give the issue a concise, outcome-focused title. Write its description in prose,
explaining the problem or need and the relevant context. For a new feature,
explain why it is needed and how it is expected to work. For a bug, describe the
observed behavior and the expected behavior.

Include an `## Acceptance criteria` section in every issue. State observable,
testable outcomes that let an implementer and reviewer decide whether the work
is complete. Do not substitute implementation steps for outcomes.

An `## Artifacts` section is optional. Include it when screenshots, error
traces, logs, or other evidence help explain the issue, especially for bugs.
Keep sensitive values out of issue text and attachments.

When reviewing an existing issue, do not begin implementation until it has a
prose description and an `## Acceptance criteria` section. If either is missing,
add it only when the issue and linked context make the intent clear; otherwise
ask for the missing intent before updating the issue.
