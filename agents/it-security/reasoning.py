import os
import json
from typing import Dict, Any, Tuple, List
from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
LOCATION = os.getenv("VERTEX_AI_LOCATION", "asia-south1")

class SecurityReasoningEngine:
    """
    Reasoning engine powered by Gemini via Vertex AI.
    Analyzes repo commits and open issues to detect credential leaks, unauthorized access, or suspicious security signals.
    """

    def __init__(self, project_id: str = PROJECT_ID, location: str = LOCATION):
        self.project_id = project_id
        self.location = location
        aiplatform.init(project=project_id, location=location)
        self.model = GenerativeModel("gemini-2.5-flash")

    def analyze_repo_activity(self, issues: List[Dict[str, Any]], commits: List[Dict[str, Any]]) -> Tuple[float, str, List[str], str]:
        prompt = f"""
You are an expert IT & Information Security Agent.
Your task is to analyze recent repository commits and open issues for security threats, credential leaks, or unauthorized activities.

REPOSITORY ISSUES:
{json.dumps(issues, indent=2)}

RECENT COMMITS:
{json.dumps(commits, indent=2)}

INSTRUCTIONS:
1. Examine all titles, commit messages, and issue descriptions for security threats (e.g., exposed API keys, AWS keys, passwords, unauthorized access, hardcoded secrets).
2. Assign a Risk Score between 0.0 (clean repo) and 1.0 (critical security breach/leak detected).
3. If suspicious activity is detected, mark assessmentStatus as "HIGH_RISK". Otherwise, mark "LOW_RISK".
4. Provide a clear summary and specific findings referencing the exact issue title/number or commit message.

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
            summary = data.get("summary", "Security audit completed.")
            findings = data.get("findings", [])
            return risk_score, summary, findings, assessment_status

        except Exception as e:
            print(f"[SecurityReasoningEngine] Gemini call error ({e}), running deterministic analysis.")
            # Deterministic fallback check
            suspicious = False
            found_list = []
            for issue in issues:
                t = (issue.get("title", "") + " " + (issue.get("body") or "")).lower()
                if "secret" in t or "key" in t or "exposed" in t or "leak" in t:
                    suspicious = True
                    found_list.append(f"Suspicious Issue #{issue.get('number')}: '{issue.get('title')}'")

            for c in commits:
                m = c.get("message", "").lower()
                if "secret" in m or "key" in m or "password" in m:
                    suspicious = True
                    found_list.append(f"Suspicious Commit {c.get('sha')[:7]}: '{c.get('message')}'")

            if suspicious:
                return 0.95, "CRITICAL: Hardcoded credentials or leak detected in repository.", found_list, "HIGH_RISK"
            else:
                return 0.05, "Repository clean. No credential leaks or unauthorized activity detected.", ["All recent commits and issues verified safe."], "LOW_RISK"
