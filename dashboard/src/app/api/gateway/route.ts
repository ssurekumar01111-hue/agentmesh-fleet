import { NextResponse } from 'next/server';

const GATEWAY_URL = process.env.GATEWAY_URL || "https://agentmesh-gateway-138003672216.asia-south1.run.app";
const DEFAULT_DASHBOARD_SA = "agentmesh-dashboard@agentmesh-fleet-2026.iam.gserviceaccount.com";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { targetResource, collectionName, action, payload, callerServiceAccount } = body;
    const effectiveSA = callerServiceAccount || DEFAULT_DASHBOARD_SA;

    const gatewayRes = await fetch(`${GATEWAY_URL}/v1/execute`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-emulated-sa": effectiveSA,
      },
      body: JSON.stringify({
        callerServiceAccount: effectiveSA,
        targetResource,
        collectionName,
        action,
        payload: payload || {},
      }),
      cache: "no-store",
    });

    const data = await gatewayRes.json();
    return NextResponse.json(data, { status: gatewayRes.status });
  } catch (error: any) {
    return NextResponse.json(
      { status: "error", detail: error.message || "Failed to contact Gateway" },
      { status: 500 }
    );
  }
}

