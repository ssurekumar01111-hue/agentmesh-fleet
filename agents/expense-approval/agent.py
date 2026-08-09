import os
import asyncio
from typing import Dict, Any, List
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from gateway_client import GatewayClient
from reasoning import ExpenseReasoningEngine


class ExpenseApprovalAgent:
    """
    Expense Approval Agent powered by Google ADK (Agent Development Kit v2.6+).

    Performs end-to-end expense report assessment via AgentMesh Gateway:
      a. Fetches the expense via Gateway (sandbox_expenses collection).
      b. Uses Gemini reasoning to independently assess APPROVED / FLAGGED / ESCALATED.
      c. Writes its finding to Memory via Gateway.
      d. For FLAGGED or ESCALATED results, creates/updates a workflows document
         at 'waiting_approval', following the same schema as fraud-finance.

    CRITICAL: The agent NEVER reads pre-set `policyViolation` or `anomalyReason`
    fields. All assessment is derived from raw field values by the reasoning engine.
    All data access strictly via GatewayClient → Gateway → target resource.
    """

    def __init__(
        self,
        gateway_client: GatewayClient = None,
        reasoning_engine: ExpenseReasoningEngine = None,
    ):
        self.client = gateway_client or GatewayClient()
        self.engine = reasoning_engine or ExpenseReasoningEngine()
        self.session_service = InMemorySessionService()

        # Define ADK Function Tools wrapping Gateway client operations
        def fetch_expense(expense_id: str) -> dict:
            """Fetch expense report details by ID via AgentMesh Gateway (sandbox_expenses collection)."""
            expense = self.client.get_expense(expense_id)
            if not expense:
                raise ValueError(f"Expense '{expense_id}' not found via Gateway.")
            return expense

        def write_memory(case_id: str, workflow_id: str, entity_type: str, summary: str, findings: List[str], risk_score: float, history: List[str]) -> str:
            """Write expense assessment findings to Firestore Memory collection via AgentMesh Gateway."""
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
            return self.client.update_workflow(
                workflow_id=workflow_id,
                status=status,
                current_step=current_step,
                context=context
            )

        self.adk_tools = [
            FunctionTool(fetch_expense),
            FunctionTool(write_memory),
            FunctionTool(update_workflow),
        ]

        self.adk_agent = LlmAgent(
            name="ExpenseApprovalAgent",
            model="gemini-3.5-flash",
            instruction="""You are an expert Enterprise Expense Approval Agent built on Google ADK.
Your role is to review expense reports, assess them for policy compliance from raw field values
(amount, category, receiptAttached, expenseDate, submittedDate), write findings to memory via Gateway,
and update workflow state via Gateway. You NEVER read pre-set policyViolation flags.""",
            tools=self.adk_tools
        )

        self.runner = Runner(
            agent=self.adk_agent,
            app_name="agentmesh-expense-approval",
            session_service=self.session_service
        )

    def process_expense(self, expense_id: str) -> Dict[str, Any]:
        print(f"\n[*] [ExpenseApprovalAgent - ADK] Starting ADK review for Expense ID '{expense_id}'...")

        # Step a — Fetch expense via Gateway
        expense = self.client.get_expense(expense_id)
        if not expense:
            raise ValueError(f"Expense '{expense_id}' not found via Gateway.")

        print(
            f"[*] [ExpenseApprovalAgent - ADK] Fetched expense: "
            f"${expense.get('amount'):,.2f} ({expense.get('category')}) "
            f"from employee {expense.get('employeeId')}"
        )

        # Step b — Gemini reasoning (independent policy assessment from raw fields)
        risk_score, summary, findings, assessment_status = self.engine.analyze_expense(expense)
        print(
            f"[*] [ExpenseApprovalAgent - ADK] Reasoning complete: "
            f"riskScore={risk_score:.2f}, status={assessment_status}"
        )

        # Step c — Write findings to Memory via Gateway
        case_id = f"case-{expense_id}"
        workflow_id = f"wf-{expense_id}"

        history_log = [
            f"ADK Agent expense review initiated for {expense_id}.",
            f"Amount: ${expense.get('amount'):,.2f}, Category: {expense.get('category')}.",
            f"Receipt attached: {expense.get('receiptAttached')}.",
            f"expenseDate: {expense.get('expenseDate')}, submittedDate: {expense.get('submittedDate')}.",
            f"Gemini reasoning completed: Risk score {risk_score:.2f} ({assessment_status}).",
        ]

        self.client.write_memory(
            case_id=case_id,
            workflow_id=workflow_id,
            entity_type="expense",
            summary=summary,
            findings=findings,
            risk_score=risk_score,
            history=history_log,
        )
        print(f"[+] [ExpenseApprovalAgent - ADK] Memory written via Gateway for Case ID '{case_id}'.")

        # Step d — Set workflow status
        if assessment_status in ("FLAGGED", "ESCALATED"):
            wf_status = "waiting_approval"
            current_step = "human_approval_gate"
            print(
                f"[!] [ExpenseApprovalAgent - ADK] {assessment_status} detected "
                f"(score={risk_score:.2f}). Escalating workflow to 'waiting_approval'."
            )
        else:
            wf_status = "completed"
            current_step = "review_complete"

        context = {
            "expenseId": expense_id,
            "employeeId": expense.get("employeeId"),
            "department": expense.get("department"),
            "amount": expense.get("amount"),
            "category": expense.get("category"),
            "riskScore": risk_score,
            "assessmentStatus": assessment_status,
            "summary": summary,
            "findings": findings,
        }

        self.client.update_workflow(
            workflow_id=workflow_id,
            status=wf_status,
            current_step=current_step,
            context=context,
        )
        print(
            f"[+] [ExpenseApprovalAgent - ADK] Workflow '{workflow_id}' "
            f"set to status '{wf_status}' via Gateway."
        )

        return {
            "expenseId": expense_id,
            "caseId": case_id,
            "workflowId": workflow_id,
            "riskScore": risk_score,
            "assessmentStatus": assessment_status,
            "workflowStatus": wf_status,
            "summary": summary,
            "findings": findings,
        }
