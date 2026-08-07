# AgentMesh — Full Build Plan (v2, locked)
### Fortified Enterprise Fleet track — All Things Agentic Hackathon (deadline: Aug 31, 2026, 5:00pm PDT)

---

## 1. Positioning

**AgentMesh is the Enterprise AI Control Plane — a real, production-grade platform that lets an organization securely publish, discover, orchestrate, protect, and audit a fleet of AI agents across departments.**

The unifying narrative for every feature: **how do enterprises trust AI agents?**
- Registry → trusted discovery
- Identity → trusted access
- Gateway → trusted execution
- Memory → trusted continuity
- Armor → trusted safety
- Observability → trusted accountability

Demoed live against a self-built but fully real sandbox company, **Northbridge Retail Co.** Not a demo with fake data behind a nice UI — every call is real: real Firestore records, a real GitHub repo, real async execution that survives a restart, real per-agent IAM identity, a real prompt-injection scanner in the request path, real OpenTelemetry traces.

**Governing rule for scope decisions:** every feature must either satisfy a judging criterion or create a memorable demo moment — otherwise it doesn't get built.

---

## 2. Required components → what we're actually building

| Track requirement | AgentMesh component | Real implementation |
|---|---|---|
| Agent Registry | Registry Service | Firestore collection of agent manifests (name, owner, dept, version, capabilities, allowed tools, approval status) + a small admin API to publish/version/approve agents |
| Agent Runtime | Runtime Engine | Cloud Run service + Pub/Sub for async job dispatch; execution state persisted in Firestore so a job can pause (e.g. "waiting on approval") and resume days later without an in-memory process running |
| Memory Bank | Memory Service | Firestore (structured, per-agent, per-thread memory) — not chat history, but durable case/entity memory (e.g. "Incident #431: status, findings, next step") |
| Agent Identity | Identity Layer | Per-agent Cloud Run service identity + scoped IAM role (machine layer) + Firebase Auth for human approvals (user layer) — zero-trust: an agent's credentials only unlock the specific tools/collections its manifest declares |
| Agent Gateway | Gateway | A single Cloud Run entrypoint every agent call routes through — auth check, policy check, rate limit, then forward |
| Model Armor | Security Layer | Real prompt-injection / PII-leak scanning on every inbound tool result and outbound response before it's trusted — using pattern + LLM-based classification, sitting inline in the Gateway |
| Agent Observability | Telemetry | OpenTelemetry SDK → Cloud Trace + Cloud Logging; every agent step emits a span (tool called, latency, tokens, decision) |

Mandatory hackathon tech satisfied: Gemini 3.5 (via Vertex AI or Gemini API) for all agent reasoning; Google ADK as the agent framework; Cloud Run + Firestore + Pub/Sub as GCP infra.

---

## 2b. Registry scale — honest, not padded

The Registry holds **8–12 real department manifests**, of which **3 are fully active/runnable**. Nothing fake — the rest are legitimately "registered, pending activation," a normal enterprise state. Example:

| Department | Agent | Status |
|---|---|---|
| Finance | Fraud Investigation | **Active** |
| Finance | Expense Approval | Pending |
| HR | Leave Assistant | Pending |
| HR | Recruitment | Pending |
| IT | Security Monitor | **Active** |
| Legal | Contract Review | Pending |
| Compliance | Policy Engine | **Active** |
| Sales | CRM Assistant | Pending |
| Support | Customer Resolution | Pending |

This avoids the trap of inflating scale with empty shells — a judge who pokes at a "pending" agent finds an honest manifest, not a broken promise.

---

## 3. The sandbox company

A small synthetic company, **"Northbridge Retail Co."**, with real backing systems (not screenshots, not canned JSON):

- **Real Firestore database** — vendors, invoices, employees, tickets, incidents (seeded but genuinely queried/written by agents)
- **Real GitHub repo** — the IT/Security agent opens and closes real issues, reads real commits
- **Real Slack webhook or email (e.g. via SendGrid/Gmail API)** — agents actually notify a human, not a mocked toast message
- Optional: a tiny real Cloud SQL or Firestore-based "SAP-like" invoice table to stand in for an ERP

This gives judges something they can genuinely test: submit a request, watch it flow through Registry → Gateway → Identity → Runtime → Memory → Armor → Observability, with real writes they can inspect in Firestore/GitHub afterward.

---

## 4. The 3 domain agents (deep, not wide)

Building 3 agents *well* beats 8 agents shallow — matches "Architectural Discipline" (30% of judging).

1. **Fraud/Finance Agent** — reviews a submitted invoice against vendor history in Firestore, flags anomalies, escalates to a human approval step, resumes the workflow days later once approved, writes the final decision to Memory Bank.
2. **IT/Security Agent** — monitors a real GitHub repo for suspicious activity (e.g. a flagged commit or issue), opens a real GitHub issue, and coordinates with the Compliance Agent before closing it.
3. **Compliance Agent** — enforces cross-agent policy (e.g. "Finance agent cannot see HR data"), and is the one Identity/Gateway actively blocks in a live demo moment ("watch it get denied") to prove zero-trust isn't just a slide.

**Cross-agent workflow for the demo:** invoice upload → Fraud Agent investigates → escalates → Compliance Agent checks policy → human approval via a real in-app **web approval page** (Approve/Reject button, one click, no external dependency like email/Slack) → workflow resumes from persisted Firestore state → Observability shows the full trace.

**Runtime states** (shown in the dashboard, not just internal): `Queued → Running → Waiting Approval → Resumed → Completed` or `Failed`. Modeling this explicitly (rather than just "done/not done") is cheap and materially strengthens the Runtime story.

---

## 5. Tech stack (locked)

- **Reasoning**: Gemini 3.5 via Vertex AI (keeps you inside GCP IAM/billing, cleaner for "Model Armor"-style interception)
- **Agent framework**: Google ADK (matches your existing CloudGuardian experience)
- **Runtime/infra**: Cloud Run (stateless agent services), Pub/Sub (async dispatch/resume), Firestore (registry, memory, sandbox company data)
- **Identity**: Per-agent Cloud Run service identity + scoped IAM role (machine layer, least-privilege), Firebase Auth for human approval actions (user layer)
- **Observability**: OpenTelemetry SDK → Cloud Trace + Cloud Logging
- **Frontend/dashboard**: Web dashboard (React/Next, deployed on Cloud Run or Firebase Hosting) — NOT Flutter for this one, since judges expect a browsable web control-plane UI. **Five tabs only**, each answering one judging question directly: **Overview** (fleet manages agents), **Registry** (agents are governed/discoverable), **Live Workflows** (Runtime supports long-running execution), **Policies** (zero-trust enforced, includes Policy Playground), **Observability** (every action traceable, includes threat tally). No screen without a purpose.
- **Repo/integration target**: real GitHub repo via GitHub API (PAT or GitHub App)

---

## 6. Data & security design (do this properly, not as an afterthought)

- **Identity — kept real, not simplified away.** Each agent gets its own **Cloud Run service identity with a scoped IAM role** (not one shared Firebase Auth identity policed only by app-layer checks). This is barely more work at deploy time and is the actual zero-trust boundary: even if the Gateway has a bug, Firestore/GitHub scopes independently refuse an out-of-scope call. Firebase Auth sits on top for the *human-facing* approval layer, IAM handles the *machine-facing* layer.
- Gateway pipeline: **Authentication → Identity Check → Policy Check → Model Armor → Tool Access → Agent.** Simple, linear, matches the track requirement directly.
- Gateway logs every request/response pair (redacted) for audit — this doubles as your Observability backbone.
- **Model Armor — expanded categories**, each backed by rules + a cheap Gemini Flash classification call: Prompt Injection, Tool Poisoning, Secret Leakage, PII Leakage, Malicious URLs, Jailbreak Attempts. Dashboard shows a running "threats blocked" tally by category — high demo value for low extra cost. Build one deliberate "attack" scenario for the demo video (a poisoned invoice PDF with a hidden instruction) so judges see Armor actually catch something live.
- **Policy Playground** — a page where you deliberately trigger a denial live (e.g. Finance Agent attempts to read HR records → Denied, with the policy reason shown). Cheap: it's a UI wrapper around the existing Gateway policy check, no new backend logic, and it's one of the most convincing "this isn't just a slide" demo moments.
- Secrets (GitHub PAT, API keys) go in Secret Manager, never in code — this alone is worth real judging points ("secures credentials").
- No real personal data anywhere — sandbox company data is synthetic, so you avoid privacy/compliance issues in a public repo.

---

## 7. Build timeline (target: ~3.5 weeks to Aug 31)

**Week 1 — Foundation**
- Set up GCP project, billing, $150 credit, enable Vertex AI / Firestore / Cloud Run / Pub/Sub / Secret Manager
- Stand up Firestore schema: agent registry, sandbox company data, memory collections
- Build the Gateway skeleton (auth check → policy check → forward) as a Cloud Run service
- Seed the sandbox company data + real GitHub repo

**Week 2 — Core agents**
- Build Fraud/Finance Agent (ADK + Gemini 3.5) with real Firestore reads/writes
- Build async Runtime: Pub/Sub job dispatch, pause/resume via Firestore state (prove it survives a redeploy)
- Wire Identity: per-agent service accounts, enforce scopes at Gateway

**Week 3 — Remaining agents + governance layer**
- Build IT/Security Agent (real GitHub integration) and Compliance Agent (policy engine)
- Build Model Armor inline scanning + one deliberate attack demo scenario
- Wire Observability: OpenTelemetry spans across all agent calls → Cloud Trace dashboard

**Week 3.5 (final days) — Dashboard, polish, submission**
- Build the web dashboard (Registry browser, live trace viewer, "run a scenario" trigger)
- Write architecture diagram
- Record the ~4-min demo video (must show it live on Cloud Run/Vertex AI logs, per submission rules)
- Write README with spin-up instructions (must be reproducible even if judges don't run it)
- Submit: category, hosted URL, text description, repo, architecture diagram, video

---

## 8. Submission checklist (from the official rules)

- [ ] Category selected (Fortified Enterprise Fleet)
- [ ] Hosted project URL (dashboard on Cloud Run/Firebase Hosting)
- [ ] Text description: features, tech used, data sources, findings/learnings
- [ ] Public/private repo + README with step-by-step spin-up instructions
- [ ] Architecture diagram (Gemini ↔ backend ↔ database ↔ frontend)
- [ ] ~4-min demo video showing it running live on Google Cloud (Cloud Run dashboard/Vertex AI logs visible)
- [ ] Confirm: Gemini 3.5+, an ADK-family framework, and ≥1 GCP infra service are all visibly used

**Optional bonus points:** public blog/video write-up (state it was made for this hackathon) + a social post with #AllThingsAgenticHackathon; integrating Gemma/Veo/Lyria.

---

## 9. What would make this stand out (only after the core works)

- **Live "attack" moment** in the demo: feed a poisoned document, watch Model Armor block it in real time.
- **Live "denied" moment**: try to make the Compliance Agent breach a policy, watch Identity/Gateway refuse it.
- **Resume-after-days proof**: pause a workflow, redeploy the service, show it resumes from Firestore state — proves Runtime isn't just an in-memory script.
- Keep the "Time Machine" / "Digital Twin" / "Policy Simulator" ideas as stretch goals only if the core 3-agent fleet is fully real and stable first — a broken stretch feature costs more than it earns.
