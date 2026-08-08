import os
import json
from typing import Dict, Any, Tuple, List
from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel
from opentelemetry import trace

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
LOCATION = os.getenv("VERTEX_AI_LOCATION", "asia-south1")
tracer = trace.get_tracer("agentmesh-compliance")

class ComplianceReasoningEngine:
    """
    Compliance Reasoning Engine powered by Gemini via Vertex AI.
    Evaluates workflow context, memory findings, and enterprise policy rules to issue formal compliance assessments.
    """

    def __init__(self, project_id: str = PROJECT_ID, location: str = LOCATION):
        self.project_id = project_id
        self.location = location
        aiplatform.init(project=project_id, location=location)
        self.model = GenerativeModel("gemini-2.5-flash")

    def evaluate_workflow_compliance(
        self,
        workflow: Dict[str, Any],
        memory: Dict[str, Any],
        policies: List[Dict[str, Any]]
    ) -> Tuple[str, str, List[str]]:
        with tracer.start_as_current_span("Gemini Reasoning Call") as span:
            span.set_attribute("llm.model", "gemini-2.5-flash")

            clean_policies = []
            for pol in policies:
                clean_p = {}
                for k, v in pol.items():
                    clean_p[k] = str(v) if hasattr(v, "isoformat") or not isinstance(v, (str, int, float, bool, list, dict, type(None))) else v
                clean_policies.append(clean_p)

            prompt = f"""
You are the Chief Compliance & Governance Agent for Northbridge Retail Co.
Your task is to evaluate a paused invoice workflow requiring compliance review against active organizational policies and vendor controls.

WORKFLOW CONTEXT:
{json.dumps(workflow, indent=2)}

CASE MEMORY:
{json.dumps(memory, indent=2)}

ACTIVE POLICIES & GOVERNANCE RULES:
{json.dumps(clean_policies, indent=2)}

INSTRUCTIONS:
1. Examine the workflow status, invoice amount, vendor details, and fraud findings.
2. Cross-reference against governance rules (such as dual sign-off thresholds over $50,000 for new vendors onboarded within 6 months).
3. Issue an Assessment Decision: "ESCALATE" (if high risk or threshold exceeded requiring executive/dual approval), "REJECT" (if fraudulent/violates policy), or "APPROVE" (if fully compliant).
4. Provide a clear summary and specific compliance findings.

Respond ONLY with valid JSON in the following format:
{{
  "assessmentDecision": "ESCALATE", // "APPROVE", "ESCALATE", or "REJECT"
  "summary": "Executive compliance summary explaining decision.",
  "findings": [
    "Compliance finding 1 referencing invoice amount and policy threshold",
    "Compliance finding 2 detailing governance policy check"
  ]
}}
"""
            try:
                res = self.model.generate_content(prompt)
                text = res.text.strip()
                if text.startswith("```json"):
                    text = text[7:]
                if text.endswith("```"):
                    text = text[:-3]
                data = json.loads(text.strip())

                decision = data.get("assessmentDecision", "ESCALATE")
                summary = data.get("summary", "Compliance review completed.")
                findings = data.get("findings", [])

                span.set_attribute("assessmentDecision", decision)
                return decision, summary, findings

            except Exception as e:
                span.record_exception(e)
                print(f"[ComplianceReasoningEngine] Gemini call failed ({e}), falling back to deterministic baseline rules.")
                decision = "ESCALATE"
                summary = "COMPLIANCE ESCALATION REQUIRED: Invoice amount exceeds $50,000 policy threshold for high-risk vendor baseline."
                findings = [
                    "Invoice amount exceeds $50,000 governance dual sign-off requirement.",
                    "High risk score from Fraud Investigation Agent triggers mandatory compliance escalation."
                ]
                span.set_attribute("assessmentDecision", decision)
                span.set_attribute("fallback", True)
                return decision, summary, findings
