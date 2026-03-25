from __future__ import annotations

import tempfile
from typing import Any

import requests

from canvas.queries import GET_STUDENT_ASSIGNMENT_QUERY
from utils.config import get_canvas_base_url


def get_dashboard_cards(canvas_token: str | None) -> list[dict[str, Any]]:
    """Fetch dashboard cards for a specific Canvas user.

    Uses HTTP_URL from env and the provided Canvas API token.
    """

    base_url = get_canvas_base_url()

    courses: list[dict[str, Any]] = []

    api_url = f"{base_url}/v1/dashboard/dashboard_cards"
    headers = {"Authorization": f"Bearer {canvas_token}"}

    response = requests.get(api_url, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()

    for course in data:

        course_name = course.get("shortName").split(" - ")

        course_info = {
            "id": course.get("id"),
            "shortName": course_name[1],
            "originalName": course.get("originalName"),
            "courseCode": course.get("courseCode"),
            "section": course_name[0].split(" ")[-1],
            "term": course.get("term"),
            "enrollmentState": course.get("enrollmentState"),
            "links": [course.get("links", {})],
        }

        courses.append(course_info)

    if not isinstance(data, list):
        raise TypeError("Expected list of dashboard cards from Canvas API")

    return courses


def get_calendar_events(
    canvas_token: str | None,
    start_date: str,
    end_date: str,
    context_codes: list[str],
) -> list[dict[str, Any]]:
    """Fetch calendar events for the given window and contexts.

    This is a thin wrapper around the Canvas
    /v1/calendar_events endpoint. It expects ISO8601 strings for
    ``start_date`` and ``end_date`` (e.g. ``2026-02-28T17:00:00.000Z``)
    and a list of context codes like ``user_123`` or ``course_456``.
    """

    base_url = get_canvas_base_url()

    api_url = f"{base_url}/v1/calendar_events"
    headers = {"Authorization": f"Bearer {canvas_token}"}

    params: dict[str, Any] = {
        "type": "assignment",
        "per_page": 50,
        "start_date": start_date,
        "end_date": end_date,
    }

    # requests will encode list values for "context_codes[]" correctly.
    if context_codes:
        params["context_codes[]"] = context_codes

    response = requests.get(api_url, headers=headers, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    if not isinstance(data, list):
        raise TypeError("Expected list of calendar events from Canvas API")

    the_events: list[dict[str, Any]] = []
    for event in data:
        assignment = event.get("assignment") or {}

        # Canvas often stores the rich HTML description on the assignment
        # object, not on the top-level calendar event.
        description = event.get("description") or assignment.get("description")

        the_events.append(
            {
                "id": event.get("id"),
                "title": event.get("title"),
                "description": description,
                "has_submitted": assignment.get("has_submitted_submissions"),
                "user_sumbited": assignment.get("user_submitted"),
                "context_code": event.get("context_code"),
                "context_name": event.get("context_name"),
                "start_at": event.get("start_at"),
                "end_at": event.get("end_at"),
            }
        )

    return the_events


def get_planner_items(
    canvas_token: str | None,
    *,
    start_date: str,
    filter: str = "incomplete_items",
    order: str = "asc",
    per_page: int = 14,
) -> list[dict[str, Any]]:
    """Fetch planner items (e.g. incomplete assignments) for the user.

    Thin wrapper around ``/v1/planner/items``. ``start_date`` should be an
    ISO8601 string with UTC timezone (e.g. ``2026-03-25T00:00:00Z``).
    """

    base_url = get_canvas_base_url()

    api_url = f"{base_url}/v1/planner/items"
    headers = {"Authorization": f"Bearer {canvas_token}"}

    params: dict[str, Any] = {
        "start_date": start_date,
        "filter": filter,
        "order": order,
        "per_page": per_page,
    }

    response = requests.get(api_url, headers=headers, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    if not isinstance(data, list):
        raise TypeError("Expected list of planner items from Canvas API")

    return data


def download_canvas_file(
    canvas_token: str | None,
    file_api_endpoint: str,
) -> tuple[str, str, str | None]:
    """Download a Canvas file given its API endpoint.

    The *file_api_endpoint* is the value from Canvas's
    ``data-api-endpoint`` attribute, for example:
    ``https://aupp.instructure.com/api/v1/courses/4377/files/626681``.

    Returns a tuple of ``(content_bytes, filename, mime_type)``.
    """

    if not canvas_token:
        raise ValueError("Canvas API token is missing")

    # First, fetch metadata for the file to discover a proper filename
    # and the download URL.
    headers = {"Authorization": f"Bearer {canvas_token}"}

    meta_resp = requests.get(file_api_endpoint, headers=headers, timeout=10)
    meta_resp.raise_for_status()
    meta = meta_resp.json()

    if not isinstance(meta, dict):
        raise TypeError("Expected dict for Canvas file metadata")

    filename = (
        meta.get("filename")
        or meta.get("display_name")
        or f"canvas-file-{meta.get('id', 'download')}"
    )

    download_url = meta.get("url") or meta.get("download_url")
    if not download_url:
        # Fallback: most Canvas file endpoints also support /download.
        download_url = f"{file_api_endpoint.rstrip('/')}/download"

    file_resp = requests.get(download_url, headers=headers, timeout=30)
    file_resp.raise_for_status()

    content_type = file_resp.headers.get("Content-Type")

    # Persist the file to a temporary location so callers can stream it
    # to Telegram and then delete it.
    tmp = tempfile.NamedTemporaryFile(delete=False)
    try:
        tmp.write(file_resp.content)
        tmp_path = tmp.name
    finally:
        tmp.close()

    return tmp_path, str(filename), content_type


def get_student_assignment(
    assignment_lid: str,
    submission_id: str,
    canvas_token: str | None,
) -> dict[str, Any]:

    base_url = get_canvas_base_url()

    api_url = f"{base_url}/graphql"
    headers = {
        "Authorization": f"Bearer {canvas_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "operationName": "GetStudentAssignment",
        "variables": {
            "assignmentLid": assignment_lid,
            "submissionID": submission_id,
        },
        "query": GET_STUDENT_ASSIGNMENT_QUERY,
    }

    response = requests.post(api_url, headers=headers, json=payload, timeout=10)
    response.raise_for_status()
    raw = response.json()

    if not isinstance(raw, dict):
        raise TypeError("Expected dict response from Canvas GraphQL API")

    graph_data = raw.get("data")
    if not isinstance(graph_data, dict):
        # Fallback: return the raw payload if it doesn't match expectations
        return raw

    assignment_src = graph_data.get("assignment") or {}
    submission_src = graph_data.get("submission") or {}

    assignment: dict[str, Any] = {
        "_id": assignment_src.get("_id"),
        "name": assignment_src.get("name"),
        "pointsPossible": assignment_src.get("pointsPossible"),
        "dueAt": assignment_src.get("dueAt"),
    }

    submission: dict[str, Any] = {
        "_id": submission_src.get("_id"),
        "score": submission_src.get("score"),
    }

    return {"data": {"assignment": assignment, "submission": submission}}


def get_course_assignments(
    course_id: int,
    canvas_token: str | None,
) -> list[dict[str, Any]]:
    """Return all assignments for a given Canvas course.

    Uses the /v1/courses/{course_id}/assignment_groups endpoint with
    include[]=assignments and flattens all assignments into a list of
    simplified dicts.
    """

    base_url = get_canvas_base_url()

    api_url = f"{base_url}/v1/courses/{course_id}/assignment_groups"
    headers = {"Authorization": f"Bearer {canvas_token}"}
    params = {
        "include[]": ["assignments"],
        "per_page": 50,
    }

    response = requests.get(api_url, headers=headers, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    if not isinstance(data, list):
        raise TypeError("Expected list of assignment groups from Canvas API")

    filtered_assignments: list[dict[str, Any]] = []

    for group in data:
        for a in group.get("assignments", []) or []:
            filtered_assignments.append(
                {
                    "id": a.get("id"),
                    "name": a.get("name"),
                    "points_possible": a.get("points_possible"),
                    "created_at": a.get("created_at"),
                    "due_at": a.get("due_at"),
                    "assignment_group_id": a.get("assignment_group_id"),
                    "allowed_attempts": a.get("allowed_attempts"),
                    "lock_at": (a.get("lock_info") or {}).get("lock_at"),
                    "lti_context_id": a.get("lti_context_id"),
                    "has_submitted_submissions": a.get("has_submitted_submissions"),
                }
            )

    # Sort assignments by due date (earliest first). Assignments without a
    # due date are placed at the end.
    filtered_assignments.sort(
        key=lambda a: (
            a.get("due_at") is None,
            a.get("due_at") or "",
        )
    )

    return filtered_assignments


def get_assignment_submission(
    course_id: int,
    assignment_id: int,
    canvas_token: str | None,
) -> dict[str, Any]:
    """Return the current user's submission for a specific assignment.

    Uses the /v1/courses/{course_id}/assignments/{assignment_id}/submissions/self
    endpoint, which resolves "self" based on the token's user.
    """

    base_url = get_canvas_base_url()

    api_url = (
        f"{base_url}/v1/courses/{course_id}/assignments/"
        f"{assignment_id}/submissions/self"
    )
    headers = {"Authorization": f"Bearer {canvas_token}"}

    response = requests.get(api_url, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()

    if not isinstance(data, dict):
        raise TypeError("Expected dict for assignment submission from Canvas API")

    return data
