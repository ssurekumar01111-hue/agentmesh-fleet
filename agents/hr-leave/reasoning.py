import os
import json
from datetime import date
from typing import Dict, Any, Tuple, List

from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel
from opentelemetry import trace

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
LOCATION = os.getenv("VERTEX_AI_LOCATION", "asia-south1")
tracer = trace.get_tracer("agentmesh-hr-leave")

# ---------------------------------------------------------------------------
# Northbridge Retail Co. HR Leave Policy reference.
# The agent reasons against these rules; they are NOT stored as a pre-set
# Firestore flag — this is intentional so the agent must use Gemini
# reasoning to compare raw request values against company policy.
# ---------------------------------------------------------------------------
NOTICE_POLICY = {
    "short_leave_max_days": 5,      # <=5 days leave requires >= 7 days notice
    "short_leave_notice_days": 7,
    "long_leave_threshold": 10,     # >10 days leave requires >= 30 days notice
    "long_leave_notice_days": 30,
}


class LeaveReasoningEngine:
    """
    Reasoning engine powered by Gemini via Vertex AI.

    Independently computes whether an employee leave request should be APPROVED, FLAGGED,
    or ESCALATED by comparing raw field values against Northbridge Retail Co. HR policy.

    CRITICAL: This engine DOES NOT read or depend on pre-set `policyViolation`,
    `anomalyReason`, or any pre-flagged fields in Firestore. All assessment is
    derived from raw numeric and date fields (daysRequested, remainingBalance,
    startDate, endDate, submittedDate, leaveType).
    """

    def __init__(self, project_id: str = PROJECT_ID, location: str = LOCATION):
        self.project_id = project_id
        self.location = location
        aiplatform.init(project=project_id, location=location)
        self.model = GenerativeModel("gemini-3.5-flash")

    @staticmethod
    def _compute_notice_days(submitted_date: str, start_date: str) -> int:
        """Returns the number of advance notice days between submission date and leave start date."""
        try:
            sd = date.fromisoformat(submitted_date)
            st = date.fromisoformat(start_date)
            return (st - sd).days
        except Exception:
            return -1

    def analyze_leave_request(
        self, leave_req: Dict[str, Any], employee: Dict[str, Any] = None
    ) -> Tuple[float, str, List[str], str]:
        """
        Analyzes a raw leave request document against Northbridge HR policy.

        Returns:
            (risk_score: float [0.0–1.0],
             summary: str,
             findings: List[str],
             assessment_status: str)  # "APPROVED" | "FLAGGED" | "ESCALATED"
        """
        with tracer.start_as_current_span("Gemini Leave Reasoning Call") as span:
            req_id = leave_req.get("id") or leave_req.get("docId", "unknown")
            emp_id = leave_req.get("employeeId", "unknown")
            dept = leave_req.get("department", "unknown")
            leave_type = leave_req.get("leaveType", "annual")
            days_req = float(leave_req.get("daysRequested", 0))
            rem_bal = float(leave_req.get("remainingBalance", 0))
            start_date = leave_req.get("startDate", "")
            end_date = leave_req.get("endDate", "")
            submitted_date = leave_req.get("submittedDate", "")

            notice_days = self._compute_notice_days(submitted_date, start_date)

            emp_name = employee.get("name", emp_id) if employee else emp_id
            emp_role = employee.get("role", "Employee") if employee else "Employee"

            span.set_attribute("llm.model", "gemini-3.5-flash")
            span.set_attribute("requestId", req_id)
            span.set_attribute("daysRequested", days_req)
            span.set_attribute("remainingBalance", rem_bal)
            span.set_attribute("noticeDays", notice_days)
            span.set_attribute("leaveType", leave_type)

            # Build a clean view explicitly EXCLUDING any pre-set anomaly flags
            clean_request = {
                "requestId": req_id,
                "employeeId": emp_id,
                "employeeName": emp_name,
                "employeeRole": emp_role,
                "department": dept,
                "leaveType": leave_type,
                "startDate": start_date,
                "endDate": end_date,
                "daysRequested": days_req,
                "remainingBalance": rem_bal,
                "submittedDate": submitted_date,
            }

            prompt = f"""
You are an expert Enterprise HR Leave Audit Agent for Northbridge Retail Co.
Your task is to independently assess whether an employee leave request should be
APPROVED, FLAGGED for HR policy review, or ESCALATED for manager sign-off.

LEAVE REQUEST UNDER REVIEW:
{json.dumps(clean_request, indent=2)}

PRE-COMPUTED METRICS:
- Notice period provided: {notice_days} days advance notice (submitted {submitted_date} for leave starting {start_date})
- Balance deficit/surplus: {rem_bal - days_req} days (requested {days_req} days vs {rem_bal} days available)

NORTHBRIDGE RETAIL CO. HR LEAVE POLICY RULES:
1. Balance Policy: PTO days requested must not exceed the employee's available remaining balance. If daysRequested > remainingBalance, this is a major policy breach.
2. Advance Notice Policy:
   - Requests > 10 days require at least 30 days advance notice.
   - Requests 1-5 days require at least 7 days advance notice.
3. Assessment Categories:
   - "APPROVED": Fully compliant (daysRequested <= remainingBalance, notice period satisfied).
   - "FLAGGED": Minor notice deficit or single non-critical issue.
   - "ESCALATED": Balance exceeded (daysRequested > remainingBalance) OR major notice violation.

INSTRUCTIONS:
1. Compare daysRequested ({days_req}) against remainingBalance ({rem_bal}).
2. Check if notice period ({notice_days} days) satisfies the required notice for a {days_req}-day leave.
3. Assign Risk Score: 0.0 for fully compliant, up to 1.0 for severe balance deficit / policy breaches.
4. Assign assessmentStatus: "APPROVED", "FLAGGED", or "ESCALATED".
5. Provide specific, evidence-based findings citing exact numbers.

Respond ONLY with valid JSON in this format:
{{
  "riskScore": 0.95,
  "assessmentStatus": "ESCALATED",
  "summary": "Executive summary citing exact numbers.",
  "findings": [
    "Finding 1 citing requested days vs remaining balance",
    "Finding 2 citing notice period vs required policy window"
  ]
}}
"""
            try:
                res = self.model.generate_content(prompt)
                text = res.text.strip()
                if text.startswith("```json"):
                    text = text[7:]
                if text.startswith("```"):
                    text = text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                data = json.loads(text.strip())

                risk_score = float(data.get("riskScore", 0.0))
                assessment_status = data.get("assessmentStatus", "APPROVED")
                summary = data.get("summary", "Leave request review completed.")
                findings = data.get("findings", [])

                span.set_attribute("riskScore", risk_score)
                span.set_attribute("assessmentStatus", assessment_status)
                return risk_score, summary, findings, assessment_status

            except Exception as e:
                span.record_exception(e)
                print(
                    f"[LeaveReasoningEngine] Gemini call failed ({e}), "
                    "falling back to deterministic rule computation."
                )
                violations = []
                if days_req > rem_bal:
                    deficit = days_req - rem_bal
                    violations.append(
                        f"Days requested ({days_req}) exceeds remaining PTO balance ({rem_bal}) "
                        f"by {deficit} days."
                    )
                if days_req > 10 and notice_days < 30:
                    violations.append(
                        f"Notice period of {notice_days} days is insufficient for a {days_req}-day leave "
                        f"(30 days required)."
                    )

                if violations:
                    risk_score = 0.95 if days_req > rem_bal else 0.65
                    assessment_status = "ESCALATED" if days_req > rem_bal else "FLAGGED"
                    summary = f"POLICY VIOLATION: Leave request for {days_req} days has policy issues."
                else:
                    risk_score = 0.05
                    assessment_status = "APPROVED"
                    summary = f"Leave request for {days_req} days is within balance and notice policy."

                span.set_attribute("riskScore", risk_score)
                span.set_attribute("assessmentStatus", assessment_status)
                span.set_attribute("fallback", True)
                return risk_score, summary, violations or [summary], assessment_status
