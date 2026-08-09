import os
import asyncio
from typing import Dict, Any, List
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from gateway_client import GatewayClient
from reasoning import FraudReasoningEngine

class FraudFinanceAgent:
    """
    Fraud & Finance Agent powered by Google ADK (Agent Development Kit v2.6+).
    Performs end-to-end invoice review using ADK Agent, Tools, and GatewayClient.
    """

    def __init__(self, gateway_client: GatewayClient = None, reasoning_engine: FraudReasoningEngine = None):
        self.client = gateway_client or GatewayClient()
        self.engine = reasoning_engine or FraudReasoningEngine()
        self.session_service = InMemorySessionService()

        # Define ADK Function Tools wrapping Gateway client operations
        def fetch_invoice(invoice_id: str) -> dict:
            """Fetch invoice details by ID via AgentMesh Gateway."""
            inv = self.client.get_invoice(invoice_id)
            if not inv:
                raise ValueError(f"Invoice '{invoice_id}' not found via Gateway.")
            return inv

        def fetch_vendor_history(vendor_id: str) -> dict:
            """Fetch vendor historical payment baseline details by vendor ID via AgentMesh Gateway."""
            if not vendor_id:
                return {}
            v = self.client.get_vendor(vendor_id)
            return v or {}

        def write_memory(case_id: str, workflow_id: str, entity_type: str, summary: str, findings: List[str], risk_score: float, history: List[str]) -> str:
            """Write investigation summary and risk findings to Firestore Memory collection via AgentMesh Gateway."""
            return self.client.write_memory(
                case_id=case_id,
                workflow_id=workflow_id,
                entity_type=entity_type,
                summary=summary,
                findings=findings,
                risk_score=risk_score,
                history=history
            )

        def update_workflow(workflow_id: str, status: str, current_step: str, context: dict) -> str:
            """Update invoice investigation workflow state in Firestore Workflows collection via AgentMesh Gateway."""
            return self.client.update_workflow(
                workflow_id=workflow_id,
                status=status,
                current_step=current_step,
                context=context
            )

        self.adk_tools = [
            FunctionTool(fetch_invoice),
            FunctionTool(fetch_vendor_history),
            FunctionTool(write_memory),
            FunctionTool(update_workflow)
        ]

        self.adk_agent = LlmAgent(
            name="FraudFinanceAgent",
            model="gemini-3.5-flash",
            instruction="""You are an expert Enterprise Fraud & Audit Agent built on Google ADK.
Your role is to investigate incoming invoices, compare amounts against vendor historical payment patterns, compute anomaly risk, write audit memory via Gateway, and update workflow state via Gateway.""",
            tools=self.adk_tools
        )

        self.runner = Runner(
            agent=self.adk_agent,
            app_name="agentmesh-fraud-finance",
            session_service=self.session_service
        )

    def process_invoice(self, invoice_id: str) -> Dict[str, Any]:
        print(f"\n[*] [FraudFinanceAgent - ADK] Starting ADK investigation for Invoice ID '{invoice_id}'...")

        # 1. Fetch invoice & vendor via Gateway
        invoice = self.client.get_invoice(invoice_id)
        if not invoice:
            raise ValueError(f"Invoice '{invoice_id}' not found via Gateway.")

        vendor_id = invoice.get("vendorId")
        vendor = self.client.get_vendor(vendor_id) if vendor_id else {}

        # 2. Compute anomaly risk score and assessment status independently via Gemini reasoning engine
        risk_score, summary, findings, assessment_status = self.engine.analyze_invoice(invoice, vendor)

        # 3. Formulate case and workflow IDs
        case_id = f"case-{invoice_id}"
        workflow_id = f"wf-{invoice_id}"

        history_log = [
            f"ADK Agent investigation initiated for invoice {invoice_id}.",
            f"Fetched vendor baseline for '{vendor.get('name', vendor_id)}'.",
            f"Gemini reasoning completed: Risk score {risk_score:.2f} ({assessment_status})."
        ]

        # 4. Write memory via Gateway
        self.client.write_memory(
            case_id=case_id,
            workflow_id=workflow_id,
            entity_type="invoice",
            summary=summary,
            findings=findings,
            risk_score=risk_score,
            history=history_log
        )
        print(f"[+] [FraudFinanceAgent - ADK] Memory written via Gateway for Case ID '{case_id}'.")

        # 5. Escalate workflow if HIGH risk
        wf_status = "completed"
        if risk_score >= 0.70 or assessment_status == "HIGH_RISK":
            wf_status = "waiting_approval"
            print(f"[!] [FraudFinanceAgent - ADK] HIGH RISK detected ({risk_score:.2f}). Escalating workflow to 'waiting_approval'.")

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
        print(f"[+] [FraudFinanceAgent - ADK] Workflow '{workflow_id}' set to status '{wf_status}' via Gateway.")

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

    def resume_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Reads workflow from Gateway, verifies 'resumed' status, and completes workflow from persisted state."""
        print(f"\n[*] [FraudFinanceAgent - ADK] Checking for resumed workflow '{workflow_id}' via Gateway...")
        payload = {
            "docId": workflow_id
        }
        res = self.client.call_gateway(
            target_resource="firestore:workflows",
            collection_name="workflows",
            action="read",
            payload=payload
        )
        if not res:
            raise ValueError(f"Workflow '{workflow_id}' not found via Gateway.")

        current_status = res.get("status")
        if current_status != "resumed":
            raise ValueError(f"Workflow '{workflow_id}' status is '{current_status}' (expected 'resumed').")

        context = res.get("context", {})
        context["resumedAt"] = "AUTO_TIMESTAMP"
        context["finalResolution"] = "Human approval granted; invoice payment authorized."

        self.client.update_workflow(
            workflow_id=workflow_id,
            status="completed",
            current_step="review_complete",
            context=context
        )
        print(f"[+] [FraudFinanceAgent - ADK] Workflow '{workflow_id}' successfully completed from persisted state!")

        return {
            "workflowId": workflow_id,
            "status": "completed",
            "currentStep": "review_complete",
            "context": context
        }
