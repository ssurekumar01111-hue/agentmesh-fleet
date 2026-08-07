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
```
Seeded via `sandbox-seed/`, genuinely read/written by agents during workflows.

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
