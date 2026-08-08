#!/usr/bin/env python3
"""
Query Cloud Trace for real trace IDs from agentmesh-hr-leave service.
"""
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

import google.auth
import google.auth.transport.requests

PROJECT_ID = "agentmesh-fleet-2026"

def get_token():
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token

def api_get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def list_traces(token, minutes_back=30):
    start = (datetime.now(timezone.utc) - timedelta(minutes=minutes_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (f"https://cloudtrace.googleapis.com/v1/projects/{PROJECT_ID}/traces"
           f"?pageSize=25&startTime={start}&orderBy=start+desc")
    return api_get(url, token)

def get_trace(token, trace_id):
    url = f"https://cloudtrace.googleapis.com/v1/projects/{PROJECT_ID}/traces/{trace_id}"
    return api_get(url, token)

if __name__ == "__main__":
    token = get_token()

    print("=" * 70)
    print("QUERYING CLOUD TRACE FOR HR LEAVE ASSISTANT SPANS")
    print("=" * 70)

    result = list_traces(token, minutes_back=30)
    traces = result.get("traces", [])
    print(f"Found {len(traces)} trace(s) in list response\n")

    hr_traces = []

    for t in traces:
        tid = t["traceId"]
        detail = get_trace(token, tid)
        spans = detail.get("spans", [])

        span_names = [s.get("name", "") for s in spans]
        has_custom = any(
            name in ("Review Leave Request Workflow", "Gemini Leave Reasoning Call")
            for name in span_names
        )
        has_hr_url = any(
            "agentmesh-hr-leave" in str(s.get("labels", {}))
            for s in spans
        )

        if has_custom or has_hr_url:
            hr_traces.append((tid, spans))

    print(f"Found {len(hr_traces)} HR Leave trace(s):\n")

    for tid, spans in hr_traces:
        print(f"=" * 70)
        print(f"HR LEAVE TRACE ID: {tid}")
        print(f"Cloud Trace URL  : https://console.cloud.google.com/traces/list?project={PROJECT_ID}&tid={tid}")
        print(f"=" * 70)
        for s in spans:
            name = s.get("name", "")
            labels = s.get("labels", {})
            print(f"  SPAN: {name}")
            print(f"    spanId:    {s.get('spanId')}")
            print(f"    start:     {s.get('startTime')}")
            print(f"    end:       {s.get('endTime')}")
            interesting = {k: v for k, v in labels.items()
                           if any(x in k.lower() for x in
                                  ['url', 'status', 'request', 'risk', 'assessment',
                                   'model', 'type', 'days', 'method'])}
            for k, v in interesting.items():
                print(f"    {k}: {v}")
            print()
