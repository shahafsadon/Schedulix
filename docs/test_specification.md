# Test Specification Document

**Project:** Schedulix — Exam Schedule Builder
**Version:** 1.0
**Sprint:** 1
**Document Owner:** QA Lead (אחראי בדיקות)
**Status:** Draft
**Last Updated:** 2026-05-06

---

## 1. Introduction

This document defines the testing plan for **Schedulix v1.0**.
It lists all tests planned for Sprint 1, the format used to describe them, and the results recorded after execution.

This document is a deliverable required by course rule 7.5 (`מפרט בדיקות`).

---

## 2. Scope

### In Scope (v1.0)
- Parsing of the three input files (courses, exam periods, selected programs).
- Filtering courses by selected programs and by `Exam` evaluation type.
- Detection of date conflicts within the same program/year.
- Application of the elective-elective exception.
- Application of excluded dates (Shabbat, holidays).
- Generation of all valid exam schedules.
- Output file readability and structure.
- Performance: full run under 30 seconds.

### Out of Scope (v1.0)
- Time-of-day conflict detection.
- Repeated-course handling.
- GUI testing.
- Schedule optimization.

---

## 3. Test Strategy

| Level | Goal |
|---|---|
| Unit | Validate isolated behavior of each class/method. |
| Integration | Validate collaboration between components. |
| System | Validate end-to-end behavior from input to output. |

**Tool:** `pytest`

**Priorities:** High (must pass) / Medium (should pass) / Low (nice to have)

---

## 4. Test Case Format

Each test case follows this template:

```
Test ID:        [UT|IT|ST]-[Number]
Name:           Short descriptive name
Type:           Unit | Integration | System
Priority:       High | Medium | Low
Goal:           What this test verifies
Preconditions:  Required state before the test
Input:          Exact input provided
Steps:          Numbered steps
Expected:       Expected output / behavior
Status:         Not Run | Pass | Fail | Blocked
Notes:          Optional comments
```

**ID prefixes:** `UT-` Unit · `IT-` Integration · `ST-` System

---

## 5. Unit Tests

> To be populated in the dedicated Jira tasks (Test Input Parsing, Test Scheduling Rules).
> Each test case must follow the format defined in section 4.

---

## 6. Integration Tests

> To be populated in the dedicated Jira tasks.
> Integration tests verify collaboration between two or more components.

---

## 7. System Tests

> To be populated in the Run Full System Test Jira task.
> System tests run the full application end-to-end via `main.py`.

---

## 8. Test Results

This section is filled during and after test execution.

### 8.1. Summary Table

| Test ID | Type | Priority | Status | Date Run | Tester | Notes |
|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — |

### 8.2. Statistics

| Metric | Value |
|---|---|
| Total tests defined | — |
| Pass | — |
| Fail | — |
| Blocked | — |

### 8.3. Defects Discovered

| Defect ID | Test ID | Description | Severity | Status |
|---|---|---|---|---|
| — | — | — | — | — |

---

## 9. Change Log

| Date | Author | Change |
|---|---|---|
| 2026-05-06 | QA Lead | Initial structure (SCRUM-16). |