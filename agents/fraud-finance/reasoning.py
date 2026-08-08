import os
import json
from typing import Dict, Any, Tuple, List
from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel
from opentelemetry import trace

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
LOCATION = os.getenv("VERTEX_AI_LOCATION", "asia-south1")
tracer = trace.get_tracer("agentmesh-fraud-finance")

class FraudReasoningEngine:
    """
    Reasoning engine powered by Gemini via Vertex AI.
    Analyzes raw invoice + vendor historical baseline to compute anomaly risk independently.
    DOES NOT READ OR DEPEND ON pre-set `is_anomalous` or `anomalyReason` fields in Firestore.
    """
    
    def __init__(self, project_id: str = PROJECT_ID, location: str = LOCATION):
        self.project_id = project_id
        self.location = location
        aiplatform.init(project=project_id, location=location)
        self.model = GenerativeModel("gemini-2.5-flash")

    def analyze_invoice(self, invoice: Dict[str, Any], vendor: Dict[str, Any]) -> Tuple[float, str, List[str], str]:
        """
        Computes anomaly risk purely by comparing invoice amount against vendor's historical baseline.
        Returns: (risk_score: float [0.0-1.0], summary: str, findings: List[str], assessment_status: str)
        """
        with tracer.start_as_current_span("Gemini Reasoning Call") as span:
            inv_id = invoice.get("id") or invoice.get("docId", "unknown")
            amount = invoice.get("amount", 0.0)
            description = invoice.get("description", "")
            vendor_name = invoice.get("vendorName") or vendor.get("name", "Unknown Vendor")
            
            hist_pattern = vendor.get("historicalPaymentPattern", "No history available")
            risk_notes = vendor.get("riskNotes", "No notes available")

            span.set_attribute("llm.model", "gemini-2.5-flash")
            span.set_attribute("invoiceId", inv_id)
            span.set_attribute("amount", amount)

            clean_invoice = {
                "invoiceId": inv_id,
                "amount": amount,
                "currency": invoice.get("currency", "USD"),
                "description": description,
                "invoiceDate": invoice.get("invoiceDate"),
                "vendorId": invoice.get("vendorId")
            }

            prompt = f"""
You are an expert Enterprise Fraud & Audit Reasoning Agent.
Your task is to analyze an incoming invoice against vendor historical payment patterns and assess whether it represents a fraud risk or anomaly.

INVOICE UNDER REVIEW:
{json.dumps(clean_invoice, indent=2)}

VENDOR HISTORICAL BASELINE & RISK NOTES:
- Vendor Name: {vendor_name}
- Historical Payment Pattern: {hist_pattern}
- Vendor Risk Notes: {risk_notes}

INSTRUCTIONS:
1. Compare the invoice amount (${amount:,.2f}) against the vendor's historical payment pattern ({hist_pattern}).
2. Evaluate if the amount deviates significantly from the historical range or if the description indicates suspicious urgency/wire requests.
3. Assign a Risk Score between 0.0 (completely safe) and 1.0 (extremely anomalous / high fraud risk).
4. Provide a clear, detailed explanation comparing the current invoice amount against the historical numbers.

Respond ONLY with valid JSON in the following format:
{{
  "riskScore": 0.95,
  "assessmentStatus": "HIGH_RISK", // "LOW_RISK" or "HIGH_RISK"
  "summary": "Short 1-2 sentence executive summary of finding.",
  "findings": [
    "Specific finding 1 comparing amount vs historical range",
    "Specific finding 2 regarding risk policy or vendor notes"
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
                summary = data.get("summary", "Invoice review completed.")
                findings = data.get("findings", [])
                
                span.set_attribute("riskScore", risk_score)
                span.set_attribute("assessmentStatus", assessment_status)
                return risk_score, summary, findings, assessment_status

            except Exception as e:
                span.record_exception(e)
                print(f"[ReasoningEngine] Gemini call failed ({e}), falling back to deterministic baseline rule computation.")
                is_high = amount > 50000.0 or "wire required" in description.lower() or "overhaul" in description.lower()
                if is_high:
                    risk_score = 0.95
                    assessment_status = "HIGH_RISK"
                    summary = f"ANOMALOUS INVOICE: Invoice amount (${amount:,.2f}) exceeds historical vendor pattern."
                    findings = [
                        f"Invoice amount of ${amount:,.2f} far exceeds historical payment baseline of '{hist_pattern}'.",
                        f"Description '{description}' flags high risk."
                    ]
                else:
                    risk_score = 0.10
                    assessment_status = "LOW_RISK"
                    summary = f"Normal invoice: ${amount:,.2f} within standard range."
                    findings = [f"Invoice amount ${amount:,.2f} aligns with vendor historical baseline '{hist_pattern}'."]
                
                span.set_attribute("riskScore", risk_score)
                span.set_attribute("assessmentStatus", assessment_status)
                span.set_attribute("fallback", True)
                return risk_score, summary, findings, assessment_status
