import os
import json
import uuid
from typing import Dict, Any, List
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from gateway_client import GatewayClient

# Ensure Vertex AI environment variables are set for google-adk execution
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026"))
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", os.getenv("VERTEX_AI_LOCATION", "asia-south1"))

class FraudFinanceAgent:
    """
    Fraud & Finance Agent powered by Google ADK (Agent Development Kit v2.6+).
    Performs end-to-end invoice review driven by ADK Runner, LlmAgent, and FunctionTools.
    """

    def __init__(self, gateway_client: GatewayClient = None):
        self.client = gateway_client or GatewayClient()
        self.session_service = InMemorySessionService()
        self._execution_context: Dict[str, Any] = {}

        # Define ADK Function Tools wrapping Gateway client operations
        def fetch_invoice(invoice_id: str) -> dict:
            """Fetch invoice details by ID via AgentMesh Gateway."""
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'fetch_invoice' called BY Runner for invoice_id='{invoice_id}'")
            inv = self.client.get_invoice(invoice_id)
            if not inv:
                raise ValueError(f"Invoice '{invoice_id}' not found via Gateway.")
            return inv

        def fetch_vendor_history(vendor_id: str) -> dict:
            """Fetch vendor historical payment baseline details by vendor ID via AgentMesh Gateway."""
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'fetch_vendor_history' called BY Runner for vendor_id='{vendor_id}'")
            if not vendor_id:
                return {}
            v = self.client.get_vendor(vendor_id)
            return v or {}

        def write_memory(case_id: str, workflow_id: str, entity_type: str, summary: str, findings: List[str], risk_score: float, history: List[str]) -> str:
            """Write investigation summary and risk findings to Firestore Memory collection via AgentMesh Gateway."""
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'write_memory' called BY Runner for case_id='{case_id}', risk_score={risk_score}")
            self._execution_context["written_memory"] = {
                "case_id": case_id,
                "workflow_id": workflow_id,
                "entity_type": entity_type,
                "summary": summary,
                "findings": findings,
                "risk_score": risk_score,
                "history": history
            }
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
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'update_workflow' called BY Runner for workflow_id='{workflow_id}', status='{status}'")
            self._execution_context["updated_workflow"] = {
                "workflow_id": workflow_id,
                "status": status,
                "current_step": current_step,
                "context": context
            }
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
Your task is to conduct an automated audit investigation of an invoice using your tools.

Workflow steps you MUST execute in order using your tools:
1. Call tool `fetch_invoice` with the given invoice_id to get invoice details (amount, description, vendorId, currency).
2. Call tool `fetch_vendor_history` with the vendorId from the invoice to retrieve the vendor's historical payment pattern and risk notes.
3. Compare the invoice amount against the vendor historical payment pattern:
   - Calculate anomaly risk score between 0.0 (safe / normal amount within baseline) and 1.0 (highly anomalous / fraud risk).
   - If invoice amount significantly exceeds vendor's historical payment pattern or indicates unusual overhaul/wire requests, risk score MUST be >= 0.70 and assessmentStatus MUST be 'HIGH_RISK'.
   - Otherwise risk score MUST be < 0.70 and assessmentStatus MUST be 'LOW_RISK'.
4. Formulate case_id = "case-" + invoice_id and workflow_id = "wf-" + invoice_id.
5. Call tool `write_memory` with (case_id, workflow_id, entity_type="invoice", summary, findings, risk_score, history).
6. Call tool `update_workflow`:
   - If HIGH_RISK (risk_score >= 0.70): status = "waiting_approval", current_step = "human_approval_gate".
   - If LOW_RISK (risk_score < 0.70): status = "completed", current_step = "review_complete".
   - context = {"invoiceId": invoice_id, "vendorId": vendorId, "amount": amount, "riskScore": risk_score, "summary": summary, "findings": findings}.

After calling all tools, output your final result as raw JSON in the exact structure:
{
  "invoiceId": "<invoice_id>",
  "caseId": "case-<invoice_id>",
  "workflowId": "wf-<invoice_id>",
  "riskScore": <risk_score_float>,
  "assessmentStatus": "HIGH_RISK" or "LOW_RISK",
  "workflowStatus": "waiting_approval" or "completed",
  "summary": "<summary_string>",
  "findings": ["<finding_1>", "<finding_2>"]
}""",
            tools=self.adk_tools
        )

        self.runner = Runner(
            agent=self.adk_agent,
            app_name="agentmesh-fraud-finance",
            session_service=self.session_service
        )

    async def process_invoice(self, invoice_id: str) -> Dict[str, Any]:
        print(f"\n[*] [FraudFinanceAgent - ADK Runner] Starting ADK Runner investigation for Invoice ID '{invoice_id}'...")
        self._execution_context.clear()

        user_id = "agentmesh-system"
        session_id = f"session-{invoice_id}-{uuid.uuid4().hex[:8]}"

        # 1. Create ADK session via Runner's Session Service
        await self.runner.session_service.create_session(
            app_name=self.runner.app_name,
            user_id=user_id,
            session_id=session_id
        )

        user_prompt = f"Please investigate invoice ID '{invoice_id}'. Perform the audit, call all required tools, write memory, and update workflow state."
        new_msg = types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_prompt)]
        )

        # 2. Execute ADK Runner drive loop
        final_text_parts = []
        async for event in self.runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_msg
        ):
            if hasattr(event, "content") and event.content and hasattr(event.content, "parts"):
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        final_text_parts.append(part.text)

        full_output = "".join(final_text_parts).strip()
        print(f"[+] [FraudFinanceAgent - ADK Runner] ADK Runner execution finished. Raw output length: {len(full_output)}")

        # 3. Extract final risk score, assessment, findings, workflow status from Runner output / session execution state
        parsed = None
        cleaned_text = full_output
        if "```json" in cleaned_text:
            cleaned_text = cleaned_text.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned_text:
            cleaned_text = cleaned_text.split("```")[1].split("```")[0].strip()

        try:
            parsed = json.loads(cleaned_text)
        except Exception:
            start = full_output.find("{")
            end = full_output.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    parsed = json.loads(full_output[start:end+1])
                except Exception:
                    pass

        # Fall back or augment from tool execution context if LLM JSON missing any key
        mem_info = self._execution_context.get("written_memory", {})
        wf_info = self._execution_context.get("updated_workflow", {})
        wf_context = wf_info.get("context", {})

        case_id = (parsed and parsed.get("caseId")) or mem_info.get("case_id") or f"case-{invoice_id}"
        workflow_id = (parsed and parsed.get("workflowId")) or wf_info.get("workflow_id") or f"wf-{invoice_id}"
        
        raw_risk = parsed.get("riskScore") if (parsed and "riskScore" in parsed) else mem_info.get("risk_score")
        if raw_risk is None:
            raw_risk = wf_context.get("riskScore", 0.0)
        risk_score = float(raw_risk)

        assessment_status = (parsed and parsed.get("assessmentStatus")) or ("HIGH_RISK" if risk_score >= 0.70 else "LOW_RISK")
        workflow_status = (parsed and parsed.get("workflowStatus")) or wf_info.get("status") or ("waiting_approval" if risk_score >= 0.70 else "completed")
        summary = (parsed and parsed.get("summary")) or mem_info.get("summary") or wf_context.get("summary", "Invoice investigation complete.")
        findings = (parsed and parsed.get("findings")) or mem_info.get("findings") or wf_context.get("findings", [])

        print(f"[+] [FraudFinanceAgent - ADK Runner] Final Extraction: riskScore={risk_score:.2f}, assessmentStatus={assessment_status}, workflowStatus={workflow_status}")

        return {
            "invoiceId": invoice_id,
            "caseId": case_id,
            "workflowId": workflow_id,
            "riskScore": risk_score,
            "assessmentStatus": assessment_status,
            "workflowStatus": workflow_status,
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
        from datetime import datetime, timezone
        context["resumedAt"] = datetime.now(timezone.utc).isoformat()
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
