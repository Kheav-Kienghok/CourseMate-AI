# Canvas Client API (Function-Level Overview)

This document describes the helper functions in `app/canvas/canvas_client.py` that talk to the Canvas API. Each function takes a Canvas API token and returns parsed Python data structures.

All functions use `get_canvas_base_url()` from `utils.config`, which reads the `HTTP_URL` environment variable.

---

## Common Behaviour

- All functions require a non-empty `canvas_token`. If `canvas_token` is `None` or empty, they raise `ValueError("Canvas API token is missing")`.
- If `HTTP_URL` is not configured, they raise `ValueError("HTTP_URL environment variable is not set")`.
- Network or HTTP errors are surfaced by `requests` via `response.raise_for_status()` (typically raising `requests.HTTPError`).

---

## `get_dashboard_cards(canvas_token)`

```python
get_dashboard_cards(canvas_token: str | None) -> list[dict[str, Any]]
```

- **Purpose**: Fetch the user’s Canvas dashboard cards (courses) and return them in a simplified list format.
- **Inputs**:
  - `canvas_token: str | None` – Canvas API token for the current user.
- **HTTP request**:
  - Method: `GET`
  - URL: `{HTTP_URL}/v1/dashboard/dashboard_cards`
  - Headers: `Authorization: Bearer <canvas_token>`
- **Processing**:
  - Calls the Canvas endpoint and parses the JSON response.
  - For each course, extracts:
    - `id`, `shortName`, `originalName`, `courseCode`, `term`, `enrollmentState`, `links`.
  - Splits `shortName` to derive:
    - `shortName` (human-readable name segment).
    - `section` (last token of the prefix part).
- **Output**:
  - Returns a `list` of `dict` objects, each like:

    ```python
    {
        "id": int,
        "shortName": str,
        "originalName": str | None,
        "courseCode": str | None,
        "section": str | None,
        "term": Any,
        "enrollmentState": str | None,
        "links": [dict],
    }
    ```

  - If the raw response is not a list, raises `TypeError`.

---

## `get_student_assignment(assignment_lid, submission_id, canvas_token)`

```python
get_student_assignment(
    assignment_lid: str,
    submission_id: str,
    canvas_token: str | None,
) -> dict[str, Any]
```

- **Purpose**: Fetch detailed assignment and submission info for a specific assignment via Canvas GraphQL.
- **Inputs**:
  - `assignment_lid: str` – Canvas LID (global identifier) for the assignment.
  - `submission_id: str` – Submission ID for this assignment.
  - `canvas_token: str | None` – Canvas API token.
- **HTTP request**:
  - Method: `POST`
  - URL: `{HTTP_URL}/graphql`
  - Headers:
    - `Authorization: Bearer <canvas_token>`
    - `Content-Type: application/json`
  - JSON body:
    - `operationName`: `"GetStudentAssignment"`
    - `variables`: `{"assignmentLid": assignment_lid, "submissionID": submission_id}`
    - `query`: `GET_STUDENT_ASSIGNMENT_QUERY` imported from `canvas.queries`.
- **Processing**:
  - Parses the JSON response.
  - Validates that the top-level object is a `dict`; otherwise raises `TypeError`.
  - Extracts `data.assignment` and `data.submission` into simplified dicts with fields like `_id`, `name`, `pointsPossible`, `dueAt`, and `score`.
  - If the expected structure is missing, falls back to returning the raw response.
- **Output**:
  - On normal success, returns:

    ```python
    {
        "data": {
            "assignment": {
                "_id": str | None,
                "name": str | None,
                "pointsPossible": float | int | None,
                "dueAt": str | None,
            },
            "submission": {
                "_id": str | None,
                "score": float | int | None,
            },
        }
    }
    ```

  - On unexpected structure, returns the raw JSON `dict` from Canvas.

---

## `get_course_assignments(course_id, canvas_token)`

```python
get_course_assignments(
    course_id: int,
    canvas_token: str | None,
) -> list[dict[str, Any]]
```

- **Purpose**: Fetch all assignments for a specific course and return them as a flat, sorted list.
- **Inputs**:
  - `course_id: int` – Canvas course ID.
  - `canvas_token: str | None` – Canvas API token.
- **HTTP request**:
  - Method: `GET`
  - URL: `{HTTP_URL}/v1/courses/{course_id}/assignment_groups`
  - Query params:
    - `include[] = ["assignments"]`
    - `per_page = 50`
  - Headers: `Authorization: Bearer <canvas_token>`
- **Processing**:
  - Parses the JSON response and expects a list of assignment groups.
  - Iterates groups and flattens all `assignments` entries into a single list.
  - For each assignment, extracts fields such as:
    - `id`, `name`, `points_possible`, `created_at`, `due_at`,
      `assignment_group_id`, `allowed_attempts`,
      `lock_at` (from `lock_info.lock_at`),
      `lti_context_id`, `has_submitted_submissions`.
  - Sorts the final list by `due_at` ascending, putting assignments without `due_at` at the end.
- **Output**:
  - Returns a `list` of assignment `dict`s with the fields above.
  - If the raw response is not a list, raises `TypeError`.

---

## `get_assignment_submission(course_id, assignment_id, canvas_token)`

```python
get_assignment_submission(
    course_id: int,
    assignment_id: int,
    canvas_token: str | None,
) -> dict[str, Any]
```

- **Purpose**: Fetch the current user’s submission for a given assignment.
- **Inputs**:
  - `course_id: int` – Canvas course ID.
  - `assignment_id: int` – Canvas assignment ID.
  - `canvas_token: str | None` – Canvas API token.
- **HTTP request**:
  - Method: `GET`
  - URL: `{HTTP_URL}/v1/courses/{course_id}/assignments/{assignment_id}/submissions/self`
  - Headers: `Authorization: Bearer <canvas_token>`
- **Processing**:
  - Parses the JSON response and expects a `dict`.
  - Validates that the response is a `dict`; otherwise raises `TypeError`.
- **Output**:
  - Returns the submission JSON as a Python `dict` (fields like `score`, `graded_at`, `attempt`, etc., depending on Canvas).

---

This document is meant as a quick reference so junior developers can see exactly what each Canvas helper expects as input and what it returns, without digging through the implementation details.
