import os
import json
from datetime import date
from typing import Dict, Any, Tuple, List

from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel
from opentelemetry import trace

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
LOCATION = os.getenv("VERTEX_AI_LOCATION", "asia-south1")
tracer = trace.get_tracer("agentmesh-expense-approval")

# ---------------------------------------------------------------------------
# Northbridge Retail Co. expense policy reference.
# The agent reasons against these limits; they are NOT stored as a separate
# Firestore collection — this is intentional so the agent must use Gemini
# reasoning rather than a simple DB lookup.
# ---------------------------------------------------------------------------
POLICY_LIMITS = {
    "travel":        {"typical_min": 200,  "typical_max": 1500, "hard_cap": 3000},
    "meals":         {"typical_min": 15,   "typical_max": 75,   "hard_cap": 150},
    "equipment":     {"typical_min": 100,  "typical_max": 800,  "hard_cap": 2000},
    "accommodation": {"typical_min": 80,   "typical_max": 250,  "hard_cap": 500},
    "software":      {"typical_min": 20,   "typical_max": 300,  "hard_cap": 1000},
}

RECEIPT_SUBMISSION_WINDOW_DAYS = 30   # Northbridge policy: receipts due within 30 days


class ExpenseReasoningEngine:
    """
    Reasoning engine powered by Gemini via Vertex AI.

    Independently computes whether an expense report should be approved, flagged,
    or escalated by comparing raw field values against Northbridge Retail Co. policy.

    CRITICAL: This engine DOES NOT read or depend on pre-set `policyViolation`,
    `anomalyReason`, or any other pre-flagged fields in Firestore. All assessment
    is derived from raw numeric and date fields (amount, category, submittedDate,
    expenseDate, receiptAttached) compared against the POLICY_LIMITS table above.
    """

    def __init__(self, project_id: str = PROJECT_ID, location: str = LOCATION):
        self.project_id = project_id
        self.location = location
        aiplatform.init(project=project_id, location=location)
        self.model = GenerativeModel("gemini-3.5-flash")

    # ------------------------------------------------------------------
    # Pre-computation helpers (deterministic, not LLM) — these are passed
    # into the Gemini prompt so the model can reference concrete numbers
    # rather than re-parsing dates.
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_submission_lag(expense_date: str, submitted_date: str) -> int:
        """Returns the number of days between expense date and submission date."""
        try:
            ed = date.fromisoformat(expense_date)
            sd = date.fromisoformat(submitted_date)
            return (sd - ed).days
        except Exception:
            return -1  # unknown

    @staticmethod
    def _policy_context(category: str) -> Dict[str, Any]:
        """Returns the policy limits for a given expense category (case-insensitive)."""
        return POLICY_LIMITS.get(category.lower(), {
            "typical_min": 0, "typical_max": 9999, "hard_cap": 9999
        })

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def analyze_expense(
        self, expense: Dict[str, Any]
    ) -> Tuple[float, str, List[str], str]:
        """
        Analyzes a raw expense document against Northbridge policy.

        Returns:
            (risk_score: float [0.0–1.0],
             summary: str,
             findings: List[str],
             assessment_status: str)  # "APPROVED" | "FLAGGED" | "ESCALATED"
        """
        with tracer.start_as_current_span("Gemini Expense Reasoning Call") as span:
            exp_id = expense.get("id") or expense.get("docId", "unknown")
            amount = float(expense.get("amount", 0.0))
            category = expense.get("category", "unknown")
            description = expense.get("description", "")
            submitted_date = expense.get("submittedDate", "")
            expense_date = expense.get("expenseDate", "")
            receipt_attached = expense.get("receiptAttached", True)
            employee_id = expense.get("employeeId", "unknown")
            department = expense.get("department", "unknown")

            # Pre-compute raw signals — passed verbatim to the model
            lag_days = self._compute_submission_lag(expense_date, submitted_date)
            policy = self._policy_context(category)

            span.set_attribute("llm.model", "gemini-3.5-flash")
            span.set_attribute("expenseId", exp_id)
            span.set_attribute("amount", amount)
            span.set_attribute("category", category)
            span.set_attribute("submissionLagDays", lag_days)
            span.set_attribute("receiptAttached", receipt_attached)

            # Build a clean view of the expense — explicitly EXCLUDING any
            # pre-set `policyViolation` or `anomalyReason` fields so the model
            # cannot branch on them.
            clean_expense = {
                "expenseId": exp_id,
                "employeeId": employee_id,
                "department": department,
                "amount": amount,
                "category": category,
                "description": description,
                "expenseDate": expense_date,
                "submittedDate": submitted_date,
                "receiptAttached": receipt_attached,
            }

            prompt = f"""
You are an expert Enterprise Expense Audit Agent for Northbridge Retail Co.
Your task is to independently assess whether an employee expense report should be
APPROVED, FLAGGED for policy review, or ESCALATED for VP-level approval.

EXPENSE UNDER REVIEW:
{json.dumps(clean_expense, indent=2)}

PRE-COMPUTED METRICS (computed from raw date fields, for your reference):
- Submission lag: {lag_days} days between expense date ({expense_date}) and submission date ({submitted_date})
  (Northbridge policy requires submission within {RECEIPT_SUBMISSION_WINDOW_DAYS} days of the expense)

NORTHBRIDGE RETAIL CO. EXPENSE POLICY LIMITS FOR CATEGORY "{category}":
- Typical per-claim range: ${policy.get("typical_min"):,} – ${policy.get("typical_max"):,}
- Hard cap (VP approval required if exceeded): ${policy.get("hard_cap"):,}

ADDITIONAL POLICY RULES:
- receiptAttached must be true for all claims. A false value is an automatic policy flag.
- Claims submitted more than {RECEIPT_SUBMISSION_WINDOW_DAYS} days after the expense date violate the submission window policy.
- Claims exceeding the hard cap require VP-level escalation.

INSTRUCTIONS:
1. Compare the expense amount (${amount:,.2f}) against the category hard cap (${policy.get("hard_cap"):,}).
2. Check whether submission lag ({lag_days} days) exceeds the {RECEIPT_SUBMISSION_WINDOW_DAYS}-day window.
3. Check whether receiptAttached is false.
4. Assign a Risk Score between 0.0 (clearly compliant) and 1.0 (severe policy violation / escalation required).
5. Assign assessmentStatus: "APPROVED" (no violations found), "FLAGGED" (1–2 policy issues), or "ESCALATED" (hard cap exceeded or 3+ policy issues).
6. List each finding as a specific, evidence-based statement referencing the actual numbers from the expense.

CRITICAL: Base your assessment ONLY on the raw field values above.
Do NOT assume any pre-set classification exists. Compute everything from scratch.

Respond ONLY with valid JSON in this format:
{{
  "riskScore": 0.95,
  "assessmentStatus": "ESCALATED",
  "summary": "Short 1-2 sentence executive summary citing specific numbers.",
  "findings": [
    "Finding 1 citing actual amount vs policy limit",
    "Finding 2 citing submission lag vs policy window",
    "Finding 3 regarding receipt status"
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
                summary = data.get("summary", "Expense review completed.")
                findings = data.get("findings", [])

                span.set_attribute("riskScore", risk_score)
                span.set_attribute("assessmentStatus", assessment_status)
                return risk_score, summary, findings, assessment_status

            except Exception as e:
                span.record_exception(e)
                print(
                    f"[ExpenseReasoningEngine] Gemini call failed ({e}), "
                    "falling back to deterministic policy rule evaluation."
                )
                # Deterministic fallback — same logic as the Gemini prompt
                violations = []
                hard_cap = policy.get("hard_cap", 9999)

                if amount > hard_cap:
                    violations.append(
                        f"Amount ${amount:,.2f} exceeds {category} hard cap ${hard_cap:,.2f} "
                        f"(overage: ${amount - hard_cap:,.2f})."
                    )
                if not receipt_attached:
                    violations.append(
                        "receiptAttached is false — no receipt provided, automatic policy flag."
                    )
                if lag_days > RECEIPT_SUBMISSION_WINDOW_DAYS:
                    violations.append(
                        f"Submission lag {lag_days} days exceeds the {RECEIPT_SUBMISSION_WINDOW_DAYS}-day policy "
                        f"window by {lag_days - RECEIPT_SUBMISSION_WINDOW_DAYS} days."
                    )

                if len(violations) >= 3 or amount > hard_cap:
                    risk_score = 0.95
                    assessment_status = "ESCALATED"
                    summary = (
                        f"POLICY VIOLATION: Expense ${amount:,.2f} ({category}) has "
                        f"{len(violations)} independent policy breaches requiring VP escalation."
                    )
                elif violations:
                    risk_score = 0.65
                    assessment_status = "FLAGGED"
                    summary = (
                        f"Expense ${amount:,.2f} ({category}) flagged: "
                        f"{violations[0]}"
                    )
                else:
                    risk_score = 0.08
                    assessment_status = "APPROVED"
                    summary = (
                        f"Expense ${amount:,.2f} ({category}) is within policy limits "
                        "and has a valid receipt."
                    )

                span.set_attribute("riskScore", risk_score)
                span.set_attribute("assessmentStatus", assessment_status)
                span.set_attribute("fallback", True)
                return risk_score, summary, violations or [summary], assessment_status
