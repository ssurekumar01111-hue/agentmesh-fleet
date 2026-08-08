import os
import json
from typing import Dict, Any, Tuple, List

from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel
from opentelemetry import trace

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
LOCATION = os.getenv("VERTEX_AI_LOCATION", "asia-south1")
tracer = trace.get_tracer("agentmesh-legal-contract")

# ---------------------------------------------------------------------------
# Northbridge Retail Co. Legal & Contracting Policy Rules.
# The agent reasons against these rules; they are NOT stored as pre-set
# flags in Firestore — the agent reads raw contract text/fields and evaluates them.
# ---------------------------------------------------------------------------
APPROVED_JURISDICTIONS = ["Delaware", "New York", "California"]
MIN_AUTO_RENEW_NOTICE_DAYS = 30


class ContractReasoningEngine:
    """
    Reasoning engine powered by Gemini via Vertex AI.

    Independently analyzes contract text, clause summaries, and key metadata against
    Northbridge Retail Co. legal guidelines to decide APPROVED, FLAGGED, or ESCALATED.

    CRITICAL: This engine DOES NOT read or depend on pre-set `policyViolation`,
    `anomalyReason`, or any pre-flagged fields in Firestore. All assessment is
    derived from raw prose text and contract fields (governingLaw, liabilityCapAmount,
    autoRenewNoticeDays, clauseSummary, fullText).
    """

    def __init__(self, project_id: str = PROJECT_ID, location: str = LOCATION):
        self.project_id = project_id
        self.location = location
        aiplatform.init(project=project_id, location=location)
        self.model = GenerativeModel("gemini-3.5-flash")

    def analyze_contract(
        self, contract: Dict[str, Any]
    ) -> Tuple[float, str, List[str], str]:
        """
        Analyzes a raw contract/NDA document against Northbridge legal policy.

        Returns:
            (risk_score: float [0.0–1.0],
             summary: str,
             findings: List[str],
             assessment_status: str)  # "APPROVED" | "FLAGGED" | "ESCALATED"
        """
        with tracer.start_as_current_span("Gemini Contract Reasoning Call") as span:
            contract_id = contract.get("id") or contract.get("docId", "unknown")
            counterparty = contract.get("vendorOrCounterparty", "unknown")
            contract_type = contract.get("contractType", "Vendor Agreement")
            governing_law = contract.get("governingLaw", "unknown")
            liability_cap = float(contract.get("liabilityCapAmount", 0))
            auto_renew = bool(contract.get("autoRenew", False))
            notice_days = int(contract.get("autoRenewNoticeDays", 0))
            clause_summary = contract.get("clauseSummary", "")
            full_text = contract.get("fullText", "")

            span.set_attribute("llm.model", "gemini-3.5-flash")
            span.set_attribute("contractId", contract_id)
            span.set_attribute("counterparty", counterparty)
            span.set_attribute("contractType", contract_type)
            span.set_attribute("governingLaw", governing_law)
            span.set_attribute("liabilityCapAmount", liability_cap)
            span.set_attribute("autoRenewNoticeDays", notice_days)

            # Clean contract dict EXCLUDING any pre-set anomaly flags
            clean_contract = {
                "contractId": contract_id,
                "vendorOrCounterparty": counterparty,
                "contractType": contract_type,
                "governingLaw": governing_law,
                "liabilityCapAmount": liability_cap,
                "autoRenew": auto_renew,
                "autoRenewNoticeDays": notice_days,
                "effectiveDate": contract.get("effectiveDate"),
                "expirationDate": contract.get("expirationDate"),
                "clauseSummary": clause_summary,
                "fullText": full_text,
            }

            prompt = f"""
You are an expert Enterprise Legal Counsel and NDA Audit Agent for Northbridge Retail Co.
Your task is to independently review a contract or agreement and determine whether it should be
APPROVED, FLAGGED for legal review, or ESCALATED for executive legal sign-off.

CONTRACT UNDER REVIEW:
{json.dumps(clean_contract, indent=2)}

NORTHBRIDGE RETAIL CO. LEGAL POLICY RULES:
1. Governing Jurisdiction: Governing law MUST be Delaware, New York, or California. Foreign or unusual jurisdictions (e.g. Cayman Islands, offshore entities) are strictly non-compliant and require ESCALATION.
2. Limitation of Liability: Unlimited liability exposure (liabilityCapAmount = 0 or missing liability cap) is strictly prohibited and requires ESCALATION.
3. Auto-Renewal Notice Window: Contracts with auto-renewal must provide at least 30 days advance notice to opt out. Notice periods < 30 days (e.g. 3 days) are non-compliant.
4. Indemnification: Unilateral or one-sided indemnification requiring Northbridge to indemnify counterparty gross negligence is unacceptable.

INSTRUCTIONS:
1. Review the governing law ({governing_law}), liability cap (${liability_cap:,.2f}), auto-renew notice ({notice_days} days), and clause summary/full text.
2. Determine risk score between 0.0 (fully compliant) and 1.0 (severe legal risk / unacceptable terms).
3. Assign assessmentStatus: "APPROVED" (all rules satisfied), "FLAGGED" (minor ambiguity), or "ESCALATED" (unlimited liability, non-standard jurisdiction, or unacceptable notice/indemnity).
4. Provide specific findings referencing exact quotes or text clauses from the contract text.

Respond ONLY with valid JSON in this format:
{{
  "riskScore": 0.95,
  "assessmentStatus": "ESCALATED",
  "summary": "Executive summary citing specific clauses and legal issues.",
  "findings": [
    "Finding 1 citing governing law clause and jurisdiction",
    "Finding 2 citing liability cap clause",
    "Finding 3 citing auto-renewal notice or indemnification clause"
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
                summary = data.get("summary", "Contract legal review completed.")
                findings = data.get("findings", [])

                span.set_attribute("riskScore", risk_score)
                span.set_attribute("assessmentStatus", assessment_status)
                return risk_score, summary, findings, assessment_status

            except Exception as e:
                span.record_exception(e)
                print(
                    f"[ContractReasoningEngine] Gemini call failed ({e}), "
                    "falling back to deterministic rule computation."
                )
                violations = []
                if governing_law not in APPROVED_JURISDICTIONS:
                    violations.append(
                        f"Governing law '{governing_law}' is non-compliant. Policy requires Delaware, New York, or California."
                    )
                if liability_cap == 0:
                    violations.append(
                        "Liability cap is $0.0 (unlimited liability exposure), violating Northbridge liability policy."
                    )
                if auto_renew and notice_days < MIN_AUTO_RENEW_NOTICE_DAYS:
                    violations.append(
                        f"Auto-renewal notice period of {notice_days} days is less than the 30-day policy requirement."
                    )

                if violations:
                    risk_score = 0.95 if liability_cap == 0 or governing_law not in APPROVED_JURISDICTIONS else 0.65
                    assessment_status = "ESCALATED"
                    summary = f"LEGAL POLICY VIOLATION: Contract with {counterparty} contains {len(violations)} non-compliant clauses."
                else:
                    risk_score = 0.05
                    assessment_status = "APPROVED"
                    summary = f"Contract with {counterparty} is compliant with standard legal guidelines."

                span.set_attribute("riskScore", risk_score)
                span.set_attribute("assessmentStatus", assessment_status)
                span.set_attribute("fallback", True)
                return risk_score, summary, violations or [summary], assessment_status
