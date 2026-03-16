from __future__ import annotations

# GraphQL queries used by the Canvas client.

GET_STUDENT_ASSIGNMENT_QUERY = """query GetStudentAssignment($assignmentLid: ID!, $submissionID: ID!) {
  assignment(id: $assignmentLid) {
    _id
    name
    pointsPossible
    submissionTypes
    dueAt
    rubric {
      criteria {
        _id
        description
        points
      }
    }
  }
  submission(id: $submissionID) {
    _id
    score
    grade
    enteredGrade
    deductedPoints
    feedbackForCurrentAttempt
    submissionStatus
    gradingStatus
    turnitinData {
      score
      reportUrl
    }
  }
}
"""
