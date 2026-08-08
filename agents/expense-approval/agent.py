import os
from typing import Dict, Any

from gateway_client import GatewayClient
from reasoning import ExpenseReasoningEngine


class ExpenseApprovalAgent:
    """
    Expense Approval Agent (ADK-compliant framework agent).

    Performs end-to-end expense report assessment via AgentMesh Gateway:
      a. Fetches the expense via Gateway (sandbox_expenses collection).
      b. Uses Gemini reasoning to independently assess APPROVED / FLAGGED / ESCALATED.
      c. Writes its finding to Memory via Gateway.
      d. For FLAGGED or ESCALATED results, creates/updates a workflows document
         at 'waiting_approval', following the same schema as fraud-finance.

    CRITICAL: The agent NEVER reads pre-set `policyViolation` or `anomalyReason`
    fields. All assessment is derived from raw field values by the reasoning engine.
    """

    def __init__(
        self,
        gateway_client: GatewayClient = None,
        reasoning_engine: ExpenseReasoningEngine = None,
    ):
        self.client = gateway_client or GatewayClient()
        self.engine = reasoning_engine or ExpenseReasoningEngine()

    def process_expense(self, expense_id: str) -> Dict[str, Any]:
        print(f"\n[*] [ExpenseApprovalAgent] Starting review for Expense ID '{expense_id}'...")

        # Step a — Fetch expense via Gateway
        expense = self.client.get_expense(expense_id)
        if not expense:
            raise ValueError(f"Expense '{expense_id}' not found via Gateway.")

        print(
            f"[*] [ExpenseApprovalAgent] Fetched expense: "
            f"${expense.get('amount'):,.2f} ({expense.get('category')}) "
            f"from employee {expense.get('employeeId')}"
        )

        # Step b — Gemini reasoning (independent policy assessment from raw fields)
        risk_score, summary, findings, assessment_status = self.engine.analyze_expense(expense)
        print(
            f"[*] [ExpenseApprovalAgent] Reasoning complete: "
            f"riskScore={risk_score:.2f}, status={assessment_status}"
        )

        # Step c — Write findings to Memory via Gateway
        case_id = f"case-{expense_id}"
        workflow_id = f"wf-{expense_id}"

        history_log = [
            f"Expense review initiated for {expense_id}.",
            f"Amount: ${expense.get('amount'):,.2f}, Category: {expense.get('category')}.",
            f"Receipt attached: {expense.get('receiptAttached')}.",
            f"expenseDate: {expense.get('expenseDate')}, submittedDate: {expense.get('submittedDate')}.",
            f"Reasoning completed: Risk score {risk_score:.2f} ({assessment_status}).",
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
        print(f"[+] [ExpenseApprovalAgent] Memory written via Gateway for Case ID '{case_id}'.")

        # Step d — Set workflow status
        if assessment_status in ("FLAGGED", "ESCALATED"):
            wf_status = "waiting_approval"
            current_step = "human_approval_gate"
            print(
                f"[!] [ExpenseApprovalAgent] {assessment_status} detected "
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
            f"[+] [ExpenseApprovalAgent] Workflow '{workflow_id}' "
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
