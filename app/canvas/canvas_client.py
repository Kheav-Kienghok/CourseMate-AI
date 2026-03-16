from __future__ import annotations

from typing import Any

import requests

from utils.config import get_canvas_base_url
from canvas.queries import GET_STUDENT_ASSIGNMENT_QUERY


def get_dashboard_cards(canvas_token: str | None) -> list[dict[str, Any]]:
    """Fetch dashboard cards for a specific Canvas user.

    Uses HTTP_URL from env and the provided Canvas API token.
    """

    base_url = get_canvas_base_url()
    if not base_url:
        raise ValueError("HTTP_URL environment variable is not set")

    if not canvas_token:
        raise ValueError("Canvas API token is missing")

    courses: list[dict[str, Any]] = []

    api_url = f"{base_url}/v1/dashboard/dashboard_cards"
    headers = {"Authorization": f"Bearer {canvas_token}"}

    response = requests.get(api_url, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()

    for course in data:

        courseName = course.get("shortName").split(" - ")

        course_info = {
            "id": course.get("id"),
            "shortName": courseName[1],
            "originalName": course.get("originalName"),
            "courseCode": course.get("courseCode"),
            "section": courseName[0].split(" ")[-1],
            "term": course.get("term"),
            "enrollmentState": course.get("enrollmentState"),
            "links": [course.get("links", {})],
        }
        courses.append(course_info)

    if not isinstance(data, list):
        raise TypeError("Expected list of dashboard cards from Canvas API")

    return courses


def get_student_assignment(
    assignment_lid: str,
    submission_id: str,
    canvas_token: str | None,
) -> dict[str, Any]:
    base_url = get_canvas_base_url()
    if not base_url:
        raise ValueError("HTTP_URL environment variable is not set")

    if not canvas_token:
        raise ValueError("Canvas API token is missing")

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
    if not base_url:
        raise ValueError("HTTP_URL environment variable is not set")

    if not canvas_token:
        raise ValueError("Canvas API token is missing")

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
                    "has_submitted_submissions": a.get(
                        "has_submitted_submissions"
                    ),
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
