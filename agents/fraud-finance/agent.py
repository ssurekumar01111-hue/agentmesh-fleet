import os
import uuid
from typing import Dict, Any
from gateway_client import GatewayClient
from reasoning import FraudReasoningEngine

class FraudFinanceAgent:
    """
    Fraud & Finance Agent (ADK compliant framework agent).
    Performs end-to-end invoice review via AgentMesh Gateway.
    """

    def __init__(self, gateway_client: GatewayClient = None, reasoning_engine: FraudReasoningEngine = None):
        self.client = gateway_client or GatewayClient()
        self.engine = reasoning_engine or FraudReasoningEngine()

    def process_invoice(self, invoice_id: str) -> Dict[str, Any]:
        print(f"\n[*] [FraudFinanceAgent] Starting investigation for Invoice ID '{invoice_id}'...")

        # 2a. Fetch invoice & vendor history via Gateway
        invoice = self.client.get_invoice(invoice_id)
        if not invoice:
            raise ValueError(f"Invoice '{invoice_id}' not found via Gateway.")

        vendor_id = invoice.get("vendorId")
        vendor = self.client.get_vendor(vendor_id) if vendor_id else {}

        # 2b. Independently compute anomaly risk using Gemini reasoning
        risk_score, summary, findings, assessment_status = self.engine.analyze_invoice(invoice, vendor)

        # 2c. Write findings to Memory collection via Gateway
        case_id = f"case-{invoice_id}"
        workflow_id = f"wf-{invoice_id}"

        history_log = [
            f"Investigation initiated for invoice {invoice_id}.",
            f"Fetched vendor baseline for '{vendor.get('name', vendor_id)}'.",
            f"Reasoning completed: Risk score {risk_score:.2f} ({assessment_status})."
        ]

        self.client.write_memory(
            case_id=case_id,
            workflow_id=workflow_id,
            entity_type="invoice",
            summary=summary,
            findings=findings,
            risk_score=risk_score,
            history=history_log
        )
        print(f"[+] [FraudFinanceAgent] Memory written via Gateway for Case ID '{case_id}'.")

        # 2d. If HIGH risk, escalate workflow to 'waiting_approval'
        wf_status = "completed"
        if risk_score >= 0.70 or assessment_status == "HIGH_RISK":
            wf_status = "waiting_approval"
            print(f"[!] [FraudFinanceAgent] HIGH RISK detected ({risk_score:.2f}). Escalating workflow to 'waiting_approval'.")

        context = {
            "invoiceId": invoice_id,
            "vendorId": vendor_id,
            "amount": invoice.get("amount"),
            "riskScore": risk_score,
            "summary": summary,
            "findings": findings
        }

        self.client.update_workflow(
            workflow_id=workflow_id,
            status=wf_status,
            current_step="human_approval_gate" if wf_status == "waiting_approval" else "review_complete",
            context=context
        )
        print(f"[+] [FraudFinanceAgent] Workflow '{workflow_id}' set to status '{wf_status}' via Gateway.")

        return {
            "invoiceId": invoice_id,
            "caseId": case_id,
            "workflowId": workflow_id,
            "riskScore": risk_score,
            "assessmentStatus": assessment_status,
            "workflowStatus": wf_status,
            "summary": summary,
            "findings": findings
        }
