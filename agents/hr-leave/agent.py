import os
from typing import Dict, Any

from gateway_client import GatewayClient
from reasoning import LeaveReasoningEngine


class HRLeaveAgent:
    """
    HR Leave Assistant Agent (ADK-compliant framework agent).

    Performs end-to-end leave request assessment via AgentMesh Gateway:
      a. Fetches the leave request via Gateway (sandbox_leave_requests collection).
      b. Optionally fetches employee details via Gateway (sandbox_employees collection).
      c. Uses Gemini reasoning to independently assess APPROVED / FLAGGED / ESCALATED.
      d. Writes findings to Memory via Gateway.
      e. For FLAGGED or ESCALATED results, creates/updates a workflows document
         at 'waiting_approval', following the standard AgentMesh workflow schema.

    CRITICAL: The agent NEVER reads pre-set policy violation flags.
    All assessment is derived from raw field values by the reasoning engine.
    """

    def __init__(
        self,
        gateway_client: GatewayClient = None,
        reasoning_engine: LeaveReasoningEngine = None,
    ):
        self.client = gateway_client or GatewayClient()
        self.engine = reasoning_engine or LeaveReasoningEngine()

    def process_leave_request(self, request_id: str) -> Dict[str, Any]:
        print(f"\n[*] [HRLeaveAgent] Starting review for Leave Request ID '{request_id}'...")

        # Step a — Fetch leave request via Gateway
        leave_req = self.client.get_leave_request(request_id)
        if not leave_req:
            raise ValueError(f"Leave request '{request_id}' not found via Gateway.")

        print(
            f"[*] [HRLeaveAgent] Fetched request: {leave_req.get('daysRequested')} days "
            f"({leave_req.get('leaveType')}) for employee {leave_req.get('employeeId')}"
        )

        # Step b — Fetch employee info via Gateway
        emp_id = leave_req.get("employeeId")
        employee = self.client.get_employee(emp_id) if emp_id else {}

        # Step c — Gemini reasoning (independent policy assessment from raw fields)
        risk_score, summary, findings, assessment_status = self.engine.analyze_leave_request(
            leave_req, employee
        )
        print(
            f"[*] [HRLeaveAgent] Reasoning complete: "
            f"riskScore={risk_score:.2f}, status={assessment_status}"
        )

        # Step d — Write findings to Memory via Gateway
        case_id = f"case-{request_id}"
        workflow_id = f"wf-{request_id}"

        history_log = [
            f"Leave request review initiated for {request_id}.",
            f"Days requested: {leave_req.get('daysRequested')}, Remaining balance: {leave_req.get('remainingBalance')}.",
            f"Start date: {leave_req.get('startDate')}, End date: {leave_req.get('endDate')}.",
            f"Reasoning completed: Risk score {risk_score:.2f} ({assessment_status}).",
        ]

        self.client.write_memory(
            case_id=case_id,
            workflow_id=workflow_id,
            entity_type="leave_request",
            summary=summary,
            findings=findings,
            risk_score=risk_score,
            history=history_log,
        )
        print(f"[+] [HRLeaveAgent] Memory written via Gateway for Case ID '{case_id}'.")

        # Step e — Set workflow status
        if assessment_status in ("FLAGGED", "ESCALATED"):
            wf_status = "waiting_approval"
            current_step = "human_approval_gate"
            print(
                f"[!] [HRLeaveAgent] {assessment_status} detected "
                f"(score={risk_score:.2f}). Escalating workflow to 'waiting_approval'."
            )
        else:
            wf_status = "completed"
            current_step = "review_complete"

        context = {
            "requestId": request_id,
            "employeeId": leave_req.get("employeeId"),
            "department": leave_req.get("department"),
            "daysRequested": leave_req.get("daysRequested"),
            "remainingBalance": leave_req.get("remainingBalance"),
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
            f"[+] [HRLeaveAgent] Workflow '{workflow_id}' "
            f"set to status '{wf_status}' via Gateway."
        )

        return {
            "requestId": request_id,
            "caseId": case_id,
            "workflowId": workflow_id,
            "riskScore": risk_score,
            "assessmentStatus": assessment_status,
            "workflowStatus": wf_status,
            "summary": summary,
            "findings": findings,
        }
