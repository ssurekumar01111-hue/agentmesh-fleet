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

class LegalContractAgent:
    """
    Legal Contract & NDA Reviewer Agent powered by Google ADK (Agent Development Kit v2.6+).
    Performs end-to-end legal contract assessment driven by ADK Runner, LlmAgent, and FunctionTools.
    All operations strictly via GatewayClient -> Gateway -> target resource.
    """

    def __init__(self, gateway_client: GatewayClient = None):
        self.client = gateway_client or GatewayClient()
        self.session_service = InMemorySessionService()
        self._execution_context: Dict[str, Any] = {}

        # Define ADK Function Tools wrapping Gateway client operations
        def fetch_contract(contract_id: str) -> dict:
            """Fetch a contract or NDA document by ID from sandbox_contracts via AgentMesh Gateway."""
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'fetch_contract' called BY Runner for contract_id='{contract_id}'")
            contract = self.client.get_contract(contract_id)
            if not contract:
                raise ValueError(f"Contract '{contract_id}' not found via Gateway.")
            return contract

        def write_memory(case_id: str, workflow_id: str, entity_type: str, summary: str, findings: List[str], risk_score: float, history: List[str]) -> str:
            """Write legal assessment findings to Firestore Memory collection via AgentMesh Gateway."""
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'write_memory' called BY Runner for case_id='{case_id}', risk_score={risk_score}")
            self._execution_context["written_memory"] = {
                "case_id": case_id,
                "workflow_id": workflow_id,
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
            """Update contract review workflow state in Firestore Workflows collection via AgentMesh Gateway."""
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
            FunctionTool(fetch_contract),
            FunctionTool(write_memory),
            FunctionTool(update_workflow)
        ]

        self.adk_agent = LlmAgent(
            name="LegalContractAgent",
            model="gemini-3.5-flash",
            instruction="""You are an expert Enterprise Legal Contract & NDA Reviewer Agent built on Google ADK.
Your task is to conduct an automated review of a contract or NDA document using your tools.

Workflow steps you MUST execute in order using your tools:
1. Call tool `fetch_contract` with the given contract_id to get raw contract fields (contractType, vendorOrCounterparty, governingLaw, liabilityCapAmount, terminationClause, disputeResolution, clauses).
2. Evaluate legal policy compliance from raw text/fields (NEVER rely on pre-set violation flags):
   - Check governingLaw: standard approved jurisdictions are Delaware, California, New York, or standard US states. Foreign or non-standard governing laws (e.g. Cayman Islands, foreign jurisdictions without approval) trigger legal risk.
   - Check liabilityCapAmount: uncapped liabilities ($0 cap or unlimited liability) for high-risk agreements trigger severe policy violation.
   - Check termination and dispute resolution clauses for unusual constraints.
   - If policy violation, uncapped liability, or foreign governing law found: risk_score MUST be >= 0.60, assessmentStatus MUST be 'FLAGGED' or 'ESCALATED', workflowStatus MUST be 'waiting_approval'.
   - Otherwise (normal compliant contract with standard governing law and liability caps): risk_score MUST be < 0.40, assessmentStatus MUST be 'APPROVED', workflowStatus MUST be 'completed'.
3. Formulate case_id = "case-" + contract_id and workflow_id = "wf-" + contract_id.
4. Call tool `write_memory` with (case_id, workflow_id, entity_type="contract", summary, findings, risk_score, history).
5. Call tool `update_workflow`:
   - If FLAGGED or ESCALATED: status = "waiting_approval", current_step = "human_approval_gate".
   - If APPROVED: status = "completed", current_step = "review_complete".
   - context = {"contractId": contract_id, "vendorOrCounterparty": vendorOrCounterparty, "contractType": contractType, "governingLaw": governingLaw, "liabilityCapAmount": liabilityCapAmount, "riskScore": risk_score, "assessmentStatus": assessment_status, "summary": summary, "findings": findings}.

After calling all tools, output your final result as raw JSON in the exact structure:
{
  "contractId": "<contract_id>",
  "caseId": "case-<contract_id>",
  "workflowId": "wf-<contract_id>",
  "riskScore": <risk_score_float>,
  "assessmentStatus": "APPROVED" or "FLAGGED" or "ESCALATED",
  "workflowStatus": "waiting_approval" or "completed",
  "summary": "<summary_string>",
  "findings": ["<finding_1>", "<finding_2>"]
}""",
            tools=self.adk_tools
        )

        self.runner = Runner(
            agent=self.adk_agent,
            app_name="agentmesh-legal-contract",
            session_service=self.session_service
        )

    async def process_contract(self, contract_id: str) -> Dict[str, Any]:
        """Perform end-to-end legal contract assessment via ADK Runner."""
        print(f"\n[*] [LegalContractAgent - ADK Runner] Starting ADK Runner review for Contract ID '{contract_id}'...")
        self._execution_context.clear()

        user_id = "agentmesh-system"
        session_id = f"session-ctr-{contract_id}-{uuid.uuid4().hex[:8]}"

        # 1. Create ADK session via Runner's Session Service
        await self.runner.session_service.create_session(
            app_name=self.runner.app_name,
            user_id=user_id,
            session_id=session_id
        )

        user_prompt = f"Please review contract ID '{contract_id}'. Fetch contract details using tools, assess legal policy compliance, write findings to memory, and update workflow state."
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
        print(f"[+] [LegalContractAgent - ADK Runner] ADK Runner execution finished. Raw output length: {len(full_output)}")

        # 3. Extract final assessment status, findings, workflow status from Runner output / execution state
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

        mem_info = self._execution_context.get("written_memory", {})
        wf_info = self._execution_context.get("updated_workflow", {})
        wf_context = wf_info.get("context", {})

        case_id = (parsed and parsed.get("caseId")) or mem_info.get("case_id") or f"case-{contract_id}"
        workflow_id = (parsed and parsed.get("workflowId")) or wf_info.get("workflow_id") or f"wf-{contract_id}"

        raw_risk = parsed.get("riskScore") if (parsed and "riskScore" in parsed) else mem_info.get("risk_score")
        if raw_risk is None:
            raw_risk = wf_context.get("riskScore", 0.0)
        risk_score = float(raw_risk)

        assessment_status = (parsed and parsed.get("assessmentStatus")) or ("FLAGGED" if risk_score >= 0.60 else "APPROVED")
        workflow_status = (parsed and parsed.get("workflowStatus")) or wf_info.get("status") or ("waiting_approval" if assessment_status in ("FLAGGED", "ESCALATED") else "completed")
        summary = (parsed and parsed.get("summary")) or mem_info.get("summary") or "Contract review complete."
        findings = (parsed and parsed.get("findings")) or mem_info.get("findings") or []

        print(f"[+] [LegalContractAgent - ADK Runner] Final Extraction: riskScore={risk_score:.2f}, assessmentStatus={assessment_status}, workflowStatus={workflow_status}")

        return {
            "contractId": contract_id,
            "caseId": case_id,
            "workflowId": workflow_id,
            "riskScore": risk_score,
            "assessmentStatus": assessment_status,
            "workflowStatus": workflow_status,
            "summary": summary,
            "findings": findings
        }
