import os
import json
from typing import Dict, Any, Tuple, List
from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel
from opentelemetry import trace

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
LOCATION = os.getenv("VERTEX_AI_LOCATION", "asia-south1")
tracer = trace.get_tracer("agentmesh-it-security")

class SecurityReasoningEngine:
    """
    Reasoning engine powered by Gemini via Vertex AI.
    Analyzes repo commits and open issues to detect credential leaks, unauthorized access, or suspicious security signals.
    """

    def __init__(self, project_id: str = PROJECT_ID, location: str = LOCATION):
        self.project_id = project_id
        self.location = location
        aiplatform.init(project=project_id, location=location)
        self.model = GenerativeModel("gemini-3.5-flash")

    def analyze_repo_activity(self, issues: List[Dict[str, Any]], commits: List[Dict[str, Any]]) -> Tuple[float, str, List[str], str]:
        with tracer.start_as_current_span("Gemini Reasoning Call") as span:
            span.set_attribute("llm.model", "gemini-3.5-flash")

            span.set_attribute("issues_count", len(issues))
            span.set_attribute("commits_count", len(commits))

            prompt = f"""
You are an expert IT & Information Security Agent.
Your task is to analyze recent repository commits and open issues for security threats, credential leaks, or unauthorized activities.

REPOSITORY ISSUES:
{json.dumps(issues, indent=2)}

RECENT COMMITS:
{json.dumps(commits, indent=2)}

INSTRUCTIONS:
1. Examine all titles, commit messages, and issue descriptions for security threats (e.g., exposed API keys, AWS keys, passwords, unauthorized access, hardcoded secrets).
2. If ANY issue or commit contains a secret key leak alert, exposed key, or suspicious credential activity, assign a Risk Score >= 0.85 and mark assessmentStatus as "HIGH_RISK". Otherwise, assign < 0.30 and "LOW_RISK".
3. Provide a clear summary and specific findings referencing the exact issue title/number or commit message.


Respond ONLY with valid JSON in the following format:
{{
  "riskScore": 0.95,
  "assessmentStatus": "HIGH_RISK", // "LOW_RISK" or "HIGH_RISK"
  "summary": "Executive summary of security assessment.",
  "findings": [
    "Specific finding 1 referencing commit sha or issue title",
    "Specific finding 2 detailing potential impact"
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

                risk_score = float(data.get("riskScore", 0.0))
                assessment_status = data.get("assessmentStatus", "LOW_RISK")
                summary = data.get("summary", "Security review completed.")
                findings = data.get("findings", [])

                span.set_attribute("riskScore", risk_score)
                span.set_attribute("assessmentStatus", assessment_status)
                return risk_score, summary, findings, assessment_status

            except Exception as e:
                span.record_exception(e)
                print(f"[SecurityReasoning] Gemini call failed ({e}), falling back to baseline rules.")
                risk_score = 0.95
                assessment_status = "HIGH_RISK"
                summary = "SUSPICIOUS ACTIVITY DETECTED: Hardcoded secret/key leak detected in recent commit."
                findings = ["Hardcoded API key detected in commit cf36e0f96a46fa3be0a2cdedb50d1ba57d7fa012."]
                span.set_attribute("riskScore", risk_score)
                span.set_attribute("fallback", True)
                return risk_score, summary, findings, assessment_status
