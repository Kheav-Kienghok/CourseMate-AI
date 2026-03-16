from __future__ import annotations
from typing import Any
import requests
from utils.config import get_canvas_base_url, get_canvas_token


def get_dashboard_cards(canvas_token: str | None = get_canvas_token()) -> list[dict[str, Any]]:
    """Fetch dashboard cards for a specific Canvas user.

    Uses HTTP_URL from env and the provided Canvas API token.
    """

    courses: list[dict[str, Any]] = []

    base_url = get_canvas_base_url()
    if not base_url:
        raise ValueError("HTTP_URL environment variable is not set")

    api_url = f"{base_url}/dashboard/dashboard_cards"
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
            "links": [
                course.get("links", {})
            ],
        }
        courses.append(course_info)

    if not isinstance(data, list):
        raise TypeError("Expected list of dashboard cards from Canvas API")

    return courses
