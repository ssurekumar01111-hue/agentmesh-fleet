# Firestore Schema — AgentMesh

## `agent_registry` (collection)
One document per registered agent manifest.

```
agent_registry/{agentId}
  name: string
  department: string        # Finance, HR, IT, Legal, Compliance, Sales, Support
  owner: string
  version: string            # e.g. "1.0"
  status: "active" | "pending"
  description: string
  capabilities: string[]     # e.g. ["invoice-review", "vendor-lookup"]
  allowedTools: string[]     # e.g. ["firestore:invoices", "firestore:vendors"]
  allowedCollections: string[]  # enforced at Gateway — least privilege
  serviceAccountEmail: string   # the Cloud Run identity bound to this agent
  riskLevel: "low" | "medium" | "high"
  createdAt: timestamp
  updatedAt: timestamp
```

## `workflows` (collection)
One document per workflow execution — this is what Runtime reads/writes to survive
restarts and support pause/resume.

```
workflows/{workflowId}
  type: string                # e.g. "invoice-review"
  status: "queued" | "running" | "waiting_approval" | "resumed" | "completed" | "failed"
  initiatingAgentId: string
  involvedAgentIds: string[]
  currentStep: string
  context: map                 # accumulated state passed between steps
  createdAt: timestamp
  updatedAt: timestamp
  completedAt: timestamp | null
```

## `memory` (collection)
Case/entity memory — NOT chat history. Keyed by case, not by conversation turn.

```
memory/{caseId}
  workflowId: string
  entityType: string           # e.g. "invoice", "incident"
  entityId: string
  summary: string
  findings: array
  riskScore: number | null
  approvals: array
  history: array               # append-only log of state changes
  createdAt: timestamp
  updatedAt: timestamp
```

## `policies` (collection)
Cross-agent access rules, enforced at the Gateway.

```
policies/{policyId}
  name: string
  description: string
  effect: "allow" | "deny"
  subjectDepartment: string    # which agent department this applies to
  resource: string              # e.g. "firestore:hr_records"
  createdAt: timestamp
```

## `audit_log` (collection)
Every Gateway request/response, redacted. Doubles as the Observability backbone.

```
audit_log/{logId}
  agentId: string
  workflowId: string | null
  action: string
  requestSummary: string        # redacted
  responseSummary: string       # redacted
  policyDecision: "allowed" | "denied" | null
  policyReason: string | null
  armorFlags: string[]          # e.g. ["prompt_injection", "pii_leak"]
  latencyMs: number
  timestamp: timestamp
```

## `sandbox_*` collections (Northbridge Retail Co. data)
```
sandbox_vendors/{vendorId}
sandbox_invoices/{invoiceId}
sandbox_employees/{employeeId}
sandbox_incidents/{incidentId}
sandbox_expenses/{expenseId}
sandbox_leave_requests/{requestId}
```
Seeded via `sandbox-seed/`, genuinely read/written by agents during workflows.

## `sandbox_leave_requests` (collection)
Employee PTO and leave requests submitted for HR team approval. Read/written only by
the `leave-assistant` agent (and Gateway). Deliberately **not** accessible to
`fraud-finance`, `expense-approval`, `it-security`, or `compliance` agents.

```
sandbox_leave_requests/{requestId}
  requestId:        string          # e.g. "lvr-2026-001" (matches doc ID)
  employeeId:       string          # ref to sandbox_employees/{employeeId}
  department:       string          # submitting employee's dept, e.g. "Finance"
  leaveType:        string          # "annual" | "sick" | "unpaid" | "bereavement" | "parental"
  startDate:        string          # ISO 8601 date, e.g. "2026-08-15"
  endDate:          string          # ISO 8601 date, e.g. "2026-08-25"
  daysRequested:    number          # business/calendar leave days requested
  remainingBalance: number          # employee's available PTO balance at time of request
  submittedDate:    string          # ISO 8601 date request was submitted
  status:           string          # "pending_review" | "approved" | "flagged" | "escalated"
  createdAt:        timestamp
  updatedAt:        timestamp
```

### Planted policy-violating leave request — `lvr-2026-006`
Leave request `lvr-2026-006` is the deliberately planted policy-violation seed record:
- **Employee**: `emp-002` (Marcus Chen, Senior AP Lead, Finance)
- **Leave Type**: `annual`
- **Days Requested**: 15 days (`startDate`: 2026-09-01, `endDate`: 2026-09-21)
- **Remaining Balance**: 4 days
- **Notice Period**: Submitted 2026-08-07 for leave starting 2026-09-01 (25 days notice vs 30 days required for >10 day leave)

This gives the `leave-assistant` agent **two independent, computable signals** to
reason against:
1. `daysRequested` (15) > `remainingBalance` (4) → 11-day deficit (exceeds balance by 275%).
2. Notice period (25 days) < 30 days required for leave requests over 10 days.

The agent must compute these from raw field values; it must not read any pre-set
`policyViolation` or `anomalyReason` flag.

## `sandbox_expenses` (collection)
Employee expense reports submitted for Finance team approval. Read/written only by
the `expense-approval` agent (and Gateway). Deliberately **not** accessible to
`fraud-finance`, `hr` or any other department agent.

```
sandbox_expenses/{expenseId}
  expenseId:      string          # e.g. "exp-2026-001" (matches doc ID)
  employeeId:     string          # ref to sandbox_employees/{employeeId}
  department:     string          # submitting employee's dept, e.g. "Sales"
  amount:         number          # expense amount in USD
  category:       string          # "travel" | "meals" | "equipment" | "accommodation" | "software"
  description:    string          # free-text employee-provided description
  submittedDate:  string          # ISO 8601 date the report was filed, e.g. "2026-08-01"
  expenseDate:    string          # ISO 8601 date the actual expense was incurred
  receiptAttached: boolean        # whether a receipt was attached at submission
  status:         string          # "pending_review" | "approved" | "flagged" | "escalated"
  createdAt:      timestamp
  updatedAt:      timestamp
```

### Category policy baselines (agent-discoverable via Gemini reasoning)
These are the internal Northbridge Retail Co. policy limits the expense-approval agent
reasons against. They are **not** stored as a separate collection — the agent is
prompted with this reference and must independently decide whether a submitted expense
falls within or outside the expected range.

| Category      | Typical per-claim range | Hard cap (requires VP approval) |
|---------------|------------------------|----------------------------------|
| travel        | $200 – $1,500          | $3,000                           |
| meals         | $15 – $75 per person   | $150 per claim                   |
| equipment     | $100 – $800            | $2,000                           |
| accommodation | $80 – $250 per night   | $500 per night                   |
| software      | $20 – $300 per license | $1,000 per claim                 |

### Planted policy-violating expense — `exp-2026-006`
Expense `exp-2026-006` is the deliberately planted policy-violation seed record:
- **Category**: `meals` — per-claim hard cap is $150.
- **Amount**: $1,240.00 — 8× the hard cap.
- **Description**: "Team dinner and client entertainment — invited 3 clients + 4 internal"
- **submittedDate**: `2026-08-07` / **expenseDate**: `2026-05-15` — submitted **84 days**
  after the meal occurred, far beyond the 30-day Northbridge receipt-submission policy.
- **receiptAttached**: `false` — no receipt provided.

This gives the expense-approval agent **three independent, computable signals** to
reason against:
1. Amount ($1,240) vs meals hard cap ($150) → 8× overage.
2. Submission lag (84 days) vs 30-day policy window → 54-day violation.
3. Missing receipt → automatic policy flag.

The agent must compute all three from raw field values; it must not read any pre-set
`policyViolation` or `anomalyReason` flag.

---

## Design notes

- **Least privilege is enforced in code, not just documented.** The Gateway reads
  `agent_registry.{agentId}.allowedCollections` and rejects any Firestore call outside
  that list — this is in addition to (not instead of) the per-agent IAM service account
  restricting what the underlying Cloud Run identity can reach at the infra layer.
- **`workflows` is the single source of truth for Runtime state.** No in-memory job
  queue — a Cloud Run instance can restart mid-workflow and resume purely by reading
  this collection, which is what proves Runtime isn't a brittle script.
- **`audit_log` writes happen at the Gateway, not in each agent.** This guarantees
  nothing bypasses logging, since every agent call is required to route through Gateway.
