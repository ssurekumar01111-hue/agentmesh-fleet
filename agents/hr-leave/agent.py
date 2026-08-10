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

class HRLeaveAgent:
    """
    HR Leave Assistant Agent powered by Google ADK (Agent Development Kit v2.6+).
    Performs end-to-end leave request assessment driven by ADK Runner, LlmAgent, and FunctionTools.
    All operations strictly via GatewayClient -> Gateway -> target resource.
    """

    def __init__(self, gateway_client: GatewayClient = None):
        self.client = gateway_client or GatewayClient()
        self.session_service = InMemorySessionService()
        self._execution_context: Dict[str, Any] = {}

        # Define ADK Function Tools wrapping Gateway client operations
        def fetch_leave_request(request_id: str) -> dict:
            """Fetch a leave request by ID from sandbox_leave_requests via AgentMesh Gateway."""
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'fetch_leave_request' called BY Runner for request_id='{request_id}'")
            req = self.client.get_leave_request(request_id)
            if not req:
                raise ValueError(f"Leave request '{request_id}' not found via Gateway.")
            return req

        def fetch_employee(employee_id: str) -> dict:
            """Fetch employee profile by ID from sandbox_employees via AgentMesh Gateway."""
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'fetch_employee' called BY Runner for employee_id='{employee_id}'")
            if not employee_id:
                return {}
            emp = self.client.get_employee(employee_id)
            return emp or {}

        def write_memory(case_id: str, workflow_id: str, entity_type: str, summary: str, findings: List[str], risk_score: float, history: List[str]) -> str:
            """Write leave assessment findings to Firestore Memory collection via AgentMesh Gateway."""
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
            """Update leave review workflow state in Firestore Workflows collection via AgentMesh Gateway."""
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
            FunctionTool(fetch_leave_request),
            FunctionTool(fetch_employee),
            FunctionTool(write_memory),
            FunctionTool(update_workflow)
        ]

        self.adk_agent = LlmAgent(
            name="HRLeaveAgent",
            model="gemini-3.5-flash",
            instruction="""You are an expert Enterprise HR Leave Assistant Agent built on Google ADK.
Your task is to conduct an automated review of an employee leave request using your tools.

Workflow steps you MUST execute in order using your tools:
1. Call tool `fetch_leave_request` with the given request_id to get raw leave request fields (daysRequested, remainingBalance, leaveType, startDate, endDate, employeeId, department).
2. Call tool `fetch_employee` with the employeeId to get employee details and tenure.
3. Evaluate leave policy compliance from raw fields (NEVER rely on pre-set violation flags):
   - Compare daysRequested against remainingBalance.
   - Check if daysRequested exceeds remainingBalance or results in negative accrued balance, or if dates are invalid/overlapping.
   - If daysRequested > remainingBalance or policy violation found: risk_score MUST be >= 0.60, assessmentStatus MUST be 'FLAGGED' or 'ESCALATED', workflowStatus MUST be 'waiting_approval'.
   - Otherwise (normal compliant request within accrued balance): risk_score MUST be < 0.40, assessmentStatus MUST be 'APPROVED', workflowStatus MUST be 'completed'.
4. Formulate case_id = "case-" + request_id and workflow_id = "wf-" + request_id.
5. Call tool `write_memory` with (case_id, workflow_id, entity_type="leave_request", summary, findings, risk_score, history).
6. Call tool `update_workflow`:
   - If FLAGGED or ESCALATED: status = "waiting_approval", current_step = "human_approval_gate".
   - If APPROVED: status = "completed", current_step = "review_complete".
   - context = {"requestId": request_id, "employeeId": employeeId, "department": department, "daysRequested": daysRequested, "remainingBalance": remainingBalance, "riskScore": risk_score, "assessmentStatus": assessment_status, "summary": summary, "findings": findings}.

After calling all tools, output your final result as raw JSON in the exact structure:
{
  "requestId": "<request_id>",
  "caseId": "case-<request_id>",
  "workflowId": "wf-<request_id>",
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
            app_name="agentmesh-hr-leave",
            session_service=self.session_service
        )

    async def process_leave_request(self, request_id: str) -> Dict[str, Any]:
        """Perform end-to-end leave request assessment via ADK Runner."""
        print(f"\n[*] [HRLeaveAgent - ADK Runner] Starting ADK Runner review for Leave Request ID '{request_id}'...")
        self._execution_context.clear()

        user_id = "agentmesh-system"
        session_id = f"session-lvr-{request_id}-{uuid.uuid4().hex[:8]}"

        # 1. Create ADK session via Runner's Session Service
        await self.runner.session_service.create_session(
            app_name=self.runner.app_name,
            user_id=user_id,
            session_id=session_id
        )

        user_prompt = f"Please review leave request ID '{request_id}'. Fetch the request and employee details using tools, assess policy compliance, write findings to memory, and update workflow state."
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
        print(f"[+] [HRLeaveAgent - ADK Runner] ADK Runner execution finished. Raw output length: {len(full_output)}")

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

        case_id = (parsed and parsed.get("caseId")) or mem_info.get("case_id") or f"case-{request_id}"
        workflow_id = (parsed and parsed.get("workflowId")) or wf_info.get("workflow_id") or f"wf-{request_id}"

        raw_risk = parsed.get("riskScore") if (parsed and "riskScore" in parsed) else mem_info.get("risk_score")
        if raw_risk is None:
            raw_risk = wf_context.get("riskScore", 0.0)
        risk_score = float(raw_risk)

        assessment_status = (parsed and parsed.get("assessmentStatus")) or ("FLAGGED" if risk_score >= 0.60 else "APPROVED")
        workflow_status = (parsed and parsed.get("workflowStatus")) or wf_info.get("status") or ("waiting_approval" if assessment_status in ("FLAGGED", "ESCALATED") else "completed")
        summary = (parsed and parsed.get("summary")) or mem_info.get("summary") or "Leave request review complete."
        findings = (parsed and parsed.get("findings")) or mem_info.get("findings") or []

        print(f"[+] [HRLeaveAgent - ADK Runner] Final Extraction: riskScore={risk_score:.2f}, assessmentStatus={assessment_status}, workflowStatus={workflow_status}")

        return {
            "requestId": request_id,
            "caseId": case_id,
            "workflowId": workflow_id,
            "riskScore": risk_score,
            "assessmentStatus": assessment_status,
            "workflowStatus": workflow_status,
            "summary": summary,
            "findings": findings
        }
