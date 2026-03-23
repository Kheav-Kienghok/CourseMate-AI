# Canvas Client API (Function-Level Overview)

This document describes the functions in `app/canvas/canvas_client.py` that interact with Canvas (REST + GraphQL).

All functions use:

- `utils.config.get_canvas_base_url()` which reads the `HTTP_URL` environment variable
- `Authorization: Bearer <canvas_token>`

---

## Common behavior

### Configuration requirements

- If `HTTP_URL` is unset/empty:
  - functions that use it raise `ValueError("HTTP_URL environment variable is not set")`

### Token requirements

- If `canvas_token` is `None` or empty:
  - functions raise `ValueError("Canvas API token is missing")`

### Network/HTTP failures

- All HTTP requests use `requests.*(..., timeout=...)` then `response.raise_for_status()`
- Errors propagate as `requests.HTTPError`, `requests.Timeout`, etc.

---

## REST: Courses / Dashboard

### `get_dashboard_cards(canvas_token: str | None) -> list[dict[str, Any]]`

**Purpose**
Fetches the user’s dashboard courses and normalizes them into a simplified list.

**HTTP**

- `GET {HTTP_URL}/v1/dashboard/dashboard_cards`

**Returns**
A list of dicts shaped like:

```python
{
  "id": int | None,
  "shortName": str,              # derived from Canvas "shortName" split on " - "
  "originalName": str | None,
  "courseCode": str | None,
  "section": str,                # derived from the prefix of "shortName"
  "term": Any,
  "enrollmentState": str | None,
  "links": [dict],               # wrapped in a single-element list
}
```

**Important implementation notes**

- The code currently assumes `course.get("shortName")` exists and contains `" - "`.
  If Canvas returns an unexpected format, it may raise (e.g., `AttributeError` or `IndexError`)
  before the final `isinstance(data, list)` validation occurs.

---

## REST: Calendar Events

### `get_calendar_events(canvas_token: str | None, start_date: str, end_date: str, context_codes: list[str]) -> list[dict[str, Any]]`

**Purpose**
Fetches assignment calendar events within a time window and for specific Canvas contexts (typically courses).

**HTTP**

- `GET {HTTP_URL}/v1/calendar_events`
- Query params:
  - `type=assignment`
  - `per_page=50`
  - `start_date=<ISO8601>`
  - `end_date=<ISO8601>`
  - optionally: `context_codes[]=course_123&context_codes[]=course_456...`

**Inputs**

- `start_date`, `end_date`: ISO8601 strings used by Canvas
  - examples: `2026-02-28T17:00:00.000Z`

**Return**
A simplified list:

```python
{
  "id": ...,
  "title": ...,
  "description": ...,  # prefers event.description, falls back to event.assignment.description
  "has_submitted": ...,
  "user_sumbited": ...,
  "context_code": ...,
  "context_name": ...,
  "start_at": ...,
  "end_at": ...,
}
```

---

## REST: File download support

### `download_canvas_file(canvas_token: str | None, file_api_endpoint: str) -> tuple[str, str, str | None]`

**Purpose**
Downloads a Canvas file given its file API endpoint URL (commonly extracted from HTML `data-api-endpoint="..."`).

**Input**

- `file_api_endpoint`: typically looks like:
  - `https://<school>.instructure.com/api/v1/courses/<course_id>/files/<file_id>`

**Flow**

1. GET file metadata from `file_api_endpoint`
2. Determine filename from:
   - `filename` or `display_name` or fallback `canvas-file-<id>`
3. Determine download URL:
   - `meta["url"]` or `meta["download_url"]`
   - else fallback: append `/download`
4. GET the actual file bytes from download URL
5. Write bytes to a NamedTemporaryFile (not deleted automatically)

**Returns**

- `tmp_path: str` - local temp file path
- `filename: str`
- `content_type: str | None` from the download response headers

**Caller responsibility**
The caller should remove the temp file after sending/processing it.

---

## GraphQL: Assignment details

### `get_student_assignment(assignment_lid: str, submission_id: str, canvas_token: str | None) -> dict[str, Any]`

**Purpose**
Fetches assignment + submission details from Canvas GraphQL using a predefined query.

**HTTP**

- `POST {HTTP_URL}/graphql`
- JSON payload:
  - `operationName="GetStudentAssignment"`
  - `variables={"assignmentLid": assignment_lid, "submissionID": submission_id}`
  - `query=GET_STUDENT_ASSIGNMENT_QUERY` from `app/canvas/queries.py`

**Returns**
On expected structure:

```python
{
  "data": {
    "assignment": {
      "_id": ...,
      "name": ...,
      "pointsPossible": ...,
      "dueAt": ...,
    },
    "submission": {
      "_id": ...,
      "score": ...,
    }
  }
}
```

If Canvas returns an unexpected GraphQL shape, the function returns the raw payload `raw` (still a dict).

---

## REST: Assignments

### `get_course_assignments(course_id: int, canvas_token: str | None) -> list[dict[str, Any]]`

**Purpose**
Returns a flattened list of assignments for a course by fetching assignment groups.

**HTTP**

- `GET {HTTP_URL}/v1/courses/{course_id}/assignment_groups`
- Query:
  - `include[]=assignments`
  - `per_page=50`

**Returns**
A list of simplified assignment dicts:

```python
{
  "id": ...,
  "name": ...,
  "points_possible": ...,
  "created_at": ...,
  "due_at": ...,
  "assignment_group_id": ...,
  "allowed_attempts": ...,
  "lock_at": ...,                  # from lock_info.lock_at
  "lti_context_id": ...,
  "has_submitted_submissions": ...,
}
```

**Sorting**
Sort key:

- assignments with `due_at is None` are last
- otherwise ordered by `due_at` string ascending

---

## REST: Submission

### `get_assignment_submission(course_id: int, assignment_id: int, canvas_token: str | None) -> dict[str, Any]`

**Purpose**
Fetches the current user’s submission for an assignment.

**HTTP**

- `GET {HTTP_URL}/v1/courses/{course_id}/assignments/{assignment_id}/submissions/self`

**Returns**
The Canvas submission JSON as a dict (Canvas-defined fields; varies by submission type).

---

## Related: GraphQL queries (`app/canvas/queries.py`)

### `GET_STUDENT_ASSIGNMENT_QUERY`

GraphQL query string used by `get_student_assignment()`. It requests:

- assignment: `_id`, `name`, `pointsPossible`, `submissionTypes`, `dueAt`, rubric criteria
- submission: `_id`, `score`, grade info, status, Turnitin data, etc.
