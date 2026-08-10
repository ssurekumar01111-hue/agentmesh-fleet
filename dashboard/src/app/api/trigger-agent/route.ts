import { NextResponse } from 'next/server';

const AGENT_ENDPOINTS: Record<string, { serviceUrl: string; endpointPath: string; defaultParamKey: string; workflowIdPrefix: string }> = {
  "fraud-finance": {
    serviceUrl: "https://agentmesh-fraud-finance-138003672216.asia-south1.run.app",
    endpointPath: "/investigate",
    defaultParamKey: "invoiceId",
    workflowIdPrefix: "wf-",
  },
  "it-security": {
    serviceUrl: "https://agentmesh-it-security-138003672216.asia-south1.run.app",
    endpointPath: "/audit",
    defaultParamKey: "repo",
    workflowIdPrefix: "sec-wf-",
  },
  "compliance": {
    serviceUrl: "https://agentmesh-compliance-138003672216.asia-south1.run.app",
    endpointPath: "/review",
    defaultParamKey: "workflowId",
    workflowIdPrefix: "compliance-wf-",
  },
  "expense-approval": {
    serviceUrl: "https://agentmesh-expense-approval-138003672216.asia-south1.run.app",
    endpointPath: "/review",
    defaultParamKey: "expenseId",
    workflowIdPrefix: "exp-wf-",
  },
  "hr-leave": {
    serviceUrl: "https://agentmesh-hr-leave-138003672216.asia-south1.run.app",
    endpointPath: "/review",
    defaultParamKey: "requestId",
    workflowIdPrefix: "hr-wf-",
  },
  "legal-contract": {
    serviceUrl: "https://agentmesh-legal-contract-138003672216.asia-south1.run.app",
    endpointPath: "/review",
    defaultParamKey: "contractId",
    workflowIdPrefix: "ctr-wf-",
  },
};

async function getOidcToken(audience: string): Promise<string | null> {
  try {
    const res = await fetch(`http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=${encodeURIComponent(audience)}`, {
      headers: { 'Metadata-Flavor': 'Google' }
    });
    if (res.ok) {
      return (await res.text()).trim();
    }
  } catch (e) {
    console.log("[DashboardAuth] Not on GCP metadata server, skipping OIDC token fetch.");
  }
  return null;
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { agentId, targetRecord } = body;

    const agentConfig = AGENT_ENDPOINTS[agentId];
    if (!agentConfig) {
      return NextResponse.json(
        { status: "error", detail: `Unknown agent ID: ${agentId}` },
        { status: 400 }
      );
    }

    const fullUrl = `${agentConfig.serviceUrl}${agentConfig.endpointPath}`;
    const payload = { [agentConfig.defaultParamKey]: targetRecord || "inv-2026-009" };

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "x-emulated-sa": "agentmesh-dashboard@agentmesh-fleet-2026.iam.gserviceaccount.com",
    };

    const token = await getOidcToken(agentConfig.serviceUrl);
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch(fullUrl, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      cache: "no-store",
    });

    const responseData = await res.json();

    // Agents now return 202 + { status: "queued", workflowId, messageId, queuedAt }
    // Treat 202 as success — return the queued state to the UI for polling
    if (res.status === 202 || res.status === 200) {
      // Derive workflowId from the response or construct it from the targetRecord
      const workflowId = responseData.workflowId ||
        `${agentConfig.workflowIdPrefix}${(targetRecord || "inv-2026-009").replace(/\//g, '-')}`;

      return NextResponse.json({
        status: "queued",
        agentId,
        workflowId,
        messageId: responseData.messageId,
        queuedAt: responseData.queuedAt || new Date().toISOString(),
        targetRecord: targetRecord || "inv-2026-009",
        _rawAgentResponse: responseData,
      }, { status: 202 });
    }

    // Non-2xx responses are errors
    return NextResponse.json({
      status: "error",
      detail: responseData.detail || `Agent returned HTTP ${res.status}`,
      _rawAgentResponse: responseData,
    }, { status: res.status >= 500 ? 502 : res.status });

  } catch (error: any) {
    return NextResponse.json(
      { status: "error", detail: error.message || "Failed to trigger investigation" },
      { status: 500 }
    );
  }
}
