import { NextResponse } from 'next/server';

// Map of agent ID → Cloud Run service URL (same as trigger-agent)
const AGENT_SERVICE_URLS: Record<string, string> = {
  "fraud-finance":    "https://agentmesh-fraud-finance-138003672216.asia-south1.run.app",
  "it-security":     "https://agentmesh-it-security-138003672216.asia-south1.run.app",
  "compliance":      "https://agentmesh-compliance-138003672216.asia-south1.run.app",
  "expense-approval":"https://agentmesh-expense-approval-138003672216.asia-south1.run.app",
  "hr-leave":        "https://agentmesh-hr-leave-138003672216.asia-south1.run.app",
  "legal-contract":  "https://agentmesh-legal-contract-138003672216.asia-south1.run.app",
};

/**
 * Derive the agentId from a workflow document.
 * Priority:
 *   1. workflow.agentId field
 *   2. workflow.initiatingAgentId field
 *   3. workflow.type field (e.g. "invoice-review" → "fraud-finance")
 *   4. workflowId prefix heuristics (wf- / sec-wf- / compliance-wf- / hr-wf- / exp-wf- / ctr-wf-)
 *
 * Falls back to "fraud-finance" (the primary demo agent) if nothing matches.
 */
function resolveAgentId(params: {
  agentId?: string;
  workflowId: string;
  workflowType?: string;
  initiatingAgentId?: string;
}): string {
  const { agentId, workflowId, workflowType, initiatingAgentId } = params;

  // Explicit agent overrides win first
  if (agentId && AGENT_SERVICE_URLS[agentId]) return agentId;
  if (initiatingAgentId && AGENT_SERVICE_URLS[initiatingAgentId]) return initiatingAgentId;

  // Map type strings to agents
  if (workflowType) {
    const t = workflowType.toLowerCase();
    if (t.includes("invoice") || t.includes("fraud") || t.includes("finance")) return "fraud-finance";
    if (t.includes("security") || t.includes("audit") || t.includes("repo")) return "it-security";
    if (t.includes("compliance")) return "compliance";
    if (t.includes("expense")) return "expense-approval";
    if (t.includes("leave") || t.includes("hr")) return "hr-leave";
    if (t.includes("contract") || t.includes("legal") || t.includes("nda")) return "legal-contract";
  }

  // Prefix-based heuristics on workflowId
  if (workflowId.startsWith("sec-wf-")) return "it-security";
  if (workflowId.startsWith("compliance-wf-")) return "compliance";
  if (workflowId.startsWith("hr-wf-")) return "hr-leave";
  if (workflowId.startsWith("exp-wf-")) return "expense-approval";
  if (workflowId.startsWith("ctr-wf-")) return "legal-contract";
  // wf- prefix is used by fraud-finance (and also by expense/hr/legal-contract for /review flows)
  // but for now the primary demo workflow type is fraud-finance
  if (workflowId.startsWith("wf-")) return "fraud-finance";

  return "fraud-finance";
}

async function getOidcToken(audience: string): Promise<string | null> {
  try {
    const res = await fetch(
      `http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=${encodeURIComponent(audience)}`,
      { headers: { "Metadata-Flavor": "Google" } }
    );
    if (res.ok) {
      return (await res.text()).trim();
    }
  } catch {
    console.log("[ResumeWorkflow] Not on GCP metadata server, skipping OIDC token fetch.");
  }
  return null;
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const {
      workflowId,
      agentId: explicitAgentId,
      workflowType,
      initiatingAgentId,
    } = body;

    if (!workflowId) {
      return NextResponse.json(
        { status: "error", detail: "workflowId is required" },
        { status: 400 }
      );
    }

    const resolvedAgentId = resolveAgentId({
      agentId: explicitAgentId,
      workflowId,
      workflowType,
      initiatingAgentId,
    });

    const serviceUrl = AGENT_SERVICE_URLS[resolvedAgentId];
    if (!serviceUrl) {
      return NextResponse.json(
        { status: "error", detail: `No service URL found for agent '${resolvedAgentId}'` },
        { status: 400 }
      );
    }

    const resumeUrl = `${serviceUrl}/resume`;
    console.log(`[ResumeWorkflow] Calling ${resumeUrl} for workflowId='${workflowId}' via agent='${resolvedAgentId}'`);

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "x-emulated-sa": "agentmesh-dashboard@agentmesh-fleet-2026.iam.gserviceaccount.com",
    };

    const token = await getOidcToken(serviceUrl);
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const agentRes = await fetch(resumeUrl, {
      method: "POST",
      headers,
      body: JSON.stringify({ workflowId }),
      cache: "no-store",
    });

    const responseText = await agentRes.text();
    let responseData: any;
    try {
      responseData = JSON.parse(responseText);
    } catch {
      responseData = { raw: responseText };
    }

    if (agentRes.ok) {
      return NextResponse.json({
        status: "resumed",
        agentId: resolvedAgentId,
        workflowId,
        agentResponse: responseData,
      });
    }

    return NextResponse.json(
      {
        status: "error",
        agentId: resolvedAgentId,
        workflowId,
        detail: responseData?.detail || `Agent /resume returned HTTP ${agentRes.status}`,
        agentResponse: responseData,
      },
      { status: agentRes.status >= 500 ? 502 : agentRes.status }
    );
  } catch (error: any) {
    return NextResponse.json(
      { status: "error", detail: error.message || "Failed to call agent /resume" },
      { status: 500 }
    );
  }
}
