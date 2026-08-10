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

class ExpenseApprovalAgent:
    """
    Expense Approval Agent powered by Google ADK (Agent Development Kit v2.6+).
    Performs end-to-end expense report review driven by ADK Runner, LlmAgent, and FunctionTools.
    All operations strictly via GatewayClient -> Gateway -> target resource.
    """

    def __init__(self, gateway_client: GatewayClient = None):
        self.client = gateway_client or GatewayClient()
        self.session_service = InMemorySessionService()
        self._execution_context: Dict[str, Any] = {}

        # Define ADK Function Tools wrapping Gateway client operations
        def fetch_expense(expense_id: str) -> dict:
            """Fetch expense report details by ID via AgentMesh Gateway (sandbox_expenses collection)."""
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'fetch_expense' called BY Runner for expense_id='{expense_id}'")
            expense = self.client.get_expense(expense_id)
            if not expense:
                raise ValueError(f"Expense '{expense_id}' not found via Gateway.")
            return expense

        def write_memory(case_id: str, workflow_id: str, entity_type: str, summary: str, findings: List[str], risk_score: float, history: List[str]) -> str:
            """Write expense assessment findings to Firestore Memory collection via AgentMesh Gateway."""
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
            """Update expense review workflow state in Firestore Workflows collection via AgentMesh Gateway."""
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
            FunctionTool(fetch_expense),
            FunctionTool(write_memory),
            FunctionTool(update_workflow)
        ]

        self.adk_agent = LlmAgent(
            name="ExpenseApprovalAgent",
            model="gemini-3.5-flash",
            instruction="""You are an expert Enterprise Expense Approval Agent built on Google ADK.
Your task is to conduct an automated review of an employee expense report using your tools.

Workflow steps you MUST execute in order using your tools:
1. Call tool `fetch_expense` with the given expense_id to get raw expense fields (amount, category, receiptAttached, expenseDate, submittedDate, employeeId, department).
2. Evaluate expense policy compliance from raw fields (NEVER rely on pre-set violation flags):
   - Check if receipt is missing for expenses over $25 or restricted categories.
   - Check if amount exceeds reasonable departmental or category limits (e.g. meals over $100, team dinners without receipt, electronics/hardware > $500).
   - If policy violation or missing receipt found: risk_score MUST be >= 0.60, assessmentStatus MUST be 'FLAGGED' or 'ESCALATED', workflowStatus MUST be 'waiting_approval'.
   - Otherwise (normal compliant expense): risk_score MUST be < 0.40, assessmentStatus MUST be 'APPROVED', workflowStatus MUST be 'completed'.
3. Formulate case_id = "case-" + expense_id and workflow_id = "wf-" + expense_id.
4. Call tool `write_memory` with (case_id, workflow_id, entity_type="expense", summary, findings, risk_score, history).
5. Call tool `update_workflow`:
   - If FLAGGED or ESCALATED: status = "waiting_approval", current_step = "human_approval_gate".
   - If APPROVED: status = "completed", current_step = "review_complete".
   - context = {"expenseId": expense_id, "employeeId": employeeId, "department": department, "amount": amount, "category": category, "riskScore": risk_score, "assessmentStatus": assessment_status, "summary": summary, "findings": findings}.

After calling all tools, output your final result as raw JSON in the exact structure:
{
  "expenseId": "<expense_id>",
  "caseId": "case-<expense_id>",
  "workflowId": "wf-<expense_id>",
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
            app_name="agentmesh-expense-approval",
            session_service=self.session_service
        )

    async def process_expense(self, expense_id: str) -> Dict[str, Any]:
        """Perform end-to-end expense report assessment via ADK Runner."""
        print(f"\n[*] [ExpenseApprovalAgent - ADK Runner] Starting ADK Runner review for Expense ID '{expense_id}'...")
        self._execution_context.clear()

        user_id = "agentmesh-system"
        session_id = f"session-exp-{expense_id}-{uuid.uuid4().hex[:8]}"

        # 1. Create ADK session via Runner's Session Service
        await self.runner.session_service.create_session(
            app_name=self.runner.app_name,
            user_id=user_id,
            session_id=session_id
        )

        user_prompt = f"Please review expense report ID '{expense_id}'. Fetch the expense details using tools, assess policy compliance, write findings to memory, and update workflow state."
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
        print(f"[+] [ExpenseApprovalAgent - ADK Runner] ADK Runner execution finished. Raw output length: {len(full_output)}")

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

        case_id = (parsed and parsed.get("caseId")) or mem_info.get("case_id") or f"case-{expense_id}"
        workflow_id = (parsed and parsed.get("workflowId")) or wf_info.get("workflow_id") or f"wf-{expense_id}"

        raw_risk = parsed.get("riskScore") if (parsed and "riskScore" in parsed) else mem_info.get("risk_score")
        if raw_risk is None:
            raw_risk = wf_context.get("riskScore", 0.0)
        risk_score = float(raw_risk)

        assessment_status = (parsed and parsed.get("assessmentStatus")) or ("FLAGGED" if risk_score >= 0.60 else "APPROVED")
        workflow_status = (parsed and parsed.get("workflowStatus")) or wf_info.get("status") or ("waiting_approval" if assessment_status in ("FLAGGED", "ESCALATED") else "completed")
        summary = (parsed and parsed.get("summary")) or mem_info.get("summary") or "Expense review complete."
        findings = (parsed and parsed.get("findings")) or mem_info.get("findings") or []

        print(f"[+] [ExpenseApprovalAgent - ADK Runner] Final Extraction: riskScore={risk_score:.2f}, assessmentStatus={assessment_status}, workflowStatus={workflow_status}")

        return {
            "expenseId": expense_id,
            "caseId": case_id,
            "workflowId": workflow_id,
            "riskScore": risk_score,
            "assessmentStatus": assessment_status,
            "workflowStatus": workflow_status,
            "summary": summary,
            "findings": findings
        }
