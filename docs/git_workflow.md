# Git Workflow – Sprint 1

## Main Branch
The `main` branch must always contain stable code.

## Branch Naming
Each task should be developed in a separate branch:

SCRUM-XX-short-task-name

Examples:

SCRUM-25-read-courses-file

SCRUM-30-detect-exam-conflicts

## Pull Requests
Every branch must be merged using a Pull Request.

## Merge Rules
Only the Version Lead can merge into `main`.
A Pull Request should be reviewed before merge.

## Basic Workflow

1. Pull latest main:

`git checkout main`

`git pull origin main`

2. Create a new feature branch:

`git checkout -b SCRUM-XX-short-task-name`

Example:

`git checkout -b SCRUM-25-read-courses-file`

3. Implement the task.

4. Check changed files:

`git status`

5. Add changed files:

`git add .`

6. Commit changes:

`git commit -m "SCRUM-XX: short description of the change"`

Example:

`git commit -m "SCRUM-25: implement courses file parser"`

7. Push the branch:

`git push origin SCRUM-XX-short-task-name`

Example:

`git push origin SCRUM-25-read-courses-file`

8. Open a Pull Request on GitHub from your feature branch into `main`.

9. Wait for review.

10. Merge after approval.

Only the Version Lead merges approved Pull Requests into `main`.