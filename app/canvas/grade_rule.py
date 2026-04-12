from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class GradeRule:
    grade: str
    min_percent: float
    max_percent: float
    gpa: float
    description: str


class GradeCalculator:
    def __init__(self):
        self.rules: List[GradeRule] = [
            GradeRule("A", 93.0, 100.0, 4.00, "Outstanding attainment of course goals"),
            GradeRule("A-", 90.0, 92.99, 3.67, "Superior attainment of course goals"),
            GradeRule("B+", 87.0, 89.99, 3.33, "Very good attainment of course goals"),
            GradeRule("B", 83.0, 86.99, 3.00, "Good attainment of course goals"),
            GradeRule(
                "B-", 80.0, 82.99, 2.67, "Well above average attainment of course goals"
            ),
            GradeRule(
                "C+", 77.0, 79.99, 2.33, "Above average attainment of course goals"
            ),
            GradeRule("C", 73.0, 76.99, 2.00, "Average attainment of course goals"),
            GradeRule(
                "C-", 70.0, 72.99, 1.67, "Below average attainment of course goals"
            ),
            GradeRule("D+", 67.0, 69.99, 1.33, "Weak attainment of course goals"),
            GradeRule("D", 63.0, 66.99, 1.00, "Poor attainment of course goals"),
            GradeRule("D-", 60.0, 62.99, 0.67, "Very poor attainment of course goals"),
            GradeRule(
                "F", 0.0, 59.99, 0.00, "Unsatisfactory attainment of course goals"
            ),
        ]

    def get_rule(self, percent: float) -> Optional[GradeRule]:
        if percent < 0 or percent > 100:
            raise ValueError("Percentage must be between 0 and 100")

        for rule in self.rules:
            if rule.min_percent <= percent <= rule.max_percent:
                return rule

        return None

    def get_letter_grade(self, percent: float) -> str:
        rule = self.get_rule(percent)
        return rule.grade if rule else "N/A"

    def get_gpa(self, percent: float) -> float:
        rule = self.get_rule(percent)
        return rule.gpa if rule else 0.0

    def get_rule_by_gpa(self, gpa: float) -> Optional[GradeRule]:
        """Return the GradeRule whose GPA is closest to the given value.

        This is useful when we have an aggregated GPA across multiple
        courses and want to map it back to the nearest letter grade.
        """

        if not self.rules:
            return None

        return min(self.rules, key=lambda r: abs(r.gpa - gpa))

    def format_grade(self, percent: float) -> str:
        rule = self.get_rule(percent)
        if not rule:
            return "Invalid"
        return f"{percent:.2f}% -> {rule.grade} (GPA {rule.gpa:.2f})"

    def simple_output(self, percent: float) -> str:
        rule = self.get_rule(percent)
        if not rule:
            return "Invalid"
        return f"{percent:.0f} {rule.grade}"
