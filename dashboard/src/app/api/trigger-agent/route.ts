import { NextResponse } from 'next/server';

const AGENT_ENDPOINTS: Record<string, { serviceUrl: string; endpointPath: string; defaultParamKey: string }> = {
  "fraud-finance": {
    serviceUrl: "https://agentmesh-fraud-finance-138003672216.asia-south1.run.app",
    endpointPath: "/investigate",
    defaultParamKey: "invoiceId",
  },
  "it-security": {
    serviceUrl: "https://agentmesh-it-security-138003672216.asia-south1.run.app",
    endpointPath: "/audit",
    defaultParamKey: "repo",
  },
  "compliance": {
    serviceUrl: "https://agentmesh-compliance-138003672216.asia-south1.run.app",
    endpointPath: "/review",
    defaultParamKey: "workflowId",
  },
  "expense-approval": {
    serviceUrl: "https://agentmesh-expense-approval-138003672216.asia-south1.run.app",
    endpointPath: "/review",
    defaultParamKey: "expenseId",
  },
  "hr-leave": {
    serviceUrl: "https://agentmesh-hr-leave-138003672216.asia-south1.run.app",
    endpointPath: "/review",
    defaultParamKey: "requestId",
  },
  "legal-contract": {
    serviceUrl: "https://agentmesh-legal-contract-138003672216.asia-south1.run.app",
    endpointPath: "/review",
    defaultParamKey: "contractId",
  },
};

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

    const res = await fetch(fullUrl, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      cache: "no-store",
    });

    const responseData = await res.json();
    return NextResponse.json(responseData, { status: res.status });
  } catch (error: any) {
    return NextResponse.json(
      { status: "error", detail: error.message || "Failed to trigger investigation" },
      { status: 500 }
    );
  }
}
