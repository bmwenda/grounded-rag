---
name: project-workflow
description: Execute the repository's issue-driven GitHub Project workflow from a supplied issue link through implementation and a closing pull request.
---

# Project workflow

Use this skill when the user selects a GitHub issue from the Grounded RAG project
board and provides its link, or asks for an ad hoc change without an existing
issue. The issue is the source of truth for scope and acceptance criteria; do
not start implementation without an issue number.

For an ad hoc request with no issue, create a GitHub issue before reviewing or
implementing the change. Use `skills/issue-writing/SKILL.md` to write its title,
description, acceptance criteria, and any useful artifacts. Use the newly
created issue as the workflow input, and add it to the project when it belongs
to the project backlog. Do not treat the chat request as a substitute for the
issue or begin implementation before the issue exists.

## 1. Review the issue

Read the issue, its acceptance criteria, comments, labels, milestone, and
linked context. Check its content against `skills/issue-writing/SKILL.md`.
Inspect relevant repository code and documentation, and note dependencies,
ambiguities, and required verification. Resolve missing issue content using
the issue-writing skill before implementation. If requirements conflict, ask
for clarification before making changes.

## 2. Update project status

Confirm that the issue belongs to the linked Grounded RAG project. Move its
project item to `In Progress` before implementation. Use the project item and
Status field rather than changing unrelated issue labels. If the status field
or project item cannot be found, report the blocker instead of silently
continuing.

## 3. Create the issue branch

Check the worktree for unrelated changes before branching. Preserve user work;
do not reset, discard, or stash it without explicit direction. Fetch the
configured base branch when safe, then create a branch named
`issue-<number>-<short-kebab-slug>` (for example,
`issue-24-large-document-test`). Keep the implementation focused on the
selected issue.

## 4. Implement and verify

Implement the requested behavior and add or update regression tests. Run the
repository's applicable formatter, type checker, and test commands. Review the
diff for scope, security, configuration, and documentation impact. Do not
claim checks that were not run.

## 5. Open the pull request

Commit using the GitLab-style commit skill, push the issue branch, and use the
pull-request skill to create the PR. The PR must include prose Description,
Acceptance criteria mapped to the issue, Testing when applicable, and a
closing reference such as `Closes #<number>`. Include only the selected issue
unless the user explicitly authorizes related scope. After opening the PR,
move the selected issue's project item Status to `In Review` and verify the
change on the project board. Do not mark the issue `Done` before merge. If the
project item or `In Review` status is unavailable, report the blocker instead
of silently leaving the handoff incomplete.
