import { API_BASE_URL, apiHeaders } from "./client";
import type { ApiAction, ApiAlert, ApiApproval, ApiMonitorTask } from "./types";

export async function getAlerts(): Promise<{alerts: ApiAlert[]}> {
  const response = await fetch(`${API_BASE_URL}/api/alerts`, {headers: await apiHeaders()});
  if (!response.ok) {
    throw new Error("Failed to load alerts");
  }
  return response.json();
}

export async function getActions(): Promise<{actions: ApiAction[]; approvals: ApiApproval[]}> {
  const response = await fetch(`${API_BASE_URL}/api/actions`, {headers: await apiHeaders()});
  if (!response.ok) {
    throw new Error("Failed to load actions");
  }
  return response.json();
}

export async function approveAction(actionId: string, actor = "demo_officer"): Promise<{action: ApiAction; approval: ApiApproval}> {
  const response = await fetch(`${API_BASE_URL}/api/actions/${actionId}/approve`, {
    method: "POST",
    headers: await apiHeaders({"Content-Type": "application/json"}),
    body: JSON.stringify({actor})
  });
  if (!response.ok) {
    throw new Error("Failed to approve action");
  }
  return response.json();
}

export async function rejectAction(actionId: string, actor = "demo_officer"): Promise<{action: ApiAction; approval: ApiApproval}> {
  const response = await fetch(`${API_BASE_URL}/api/actions/${actionId}/reject`, {
    method: "POST",
    headers: await apiHeaders({"Content-Type": "application/json"}),
    body: JSON.stringify({actor})
  });
  if (!response.ok) {
    throw new Error("Failed to decline action");
  }
  return response.json();
}

export async function getMonitorTasks(): Promise<{monitor_tasks: ApiMonitorTask[]}> {
  const response = await fetch(`${API_BASE_URL}/api/monitor-tasks`, {headers: await apiHeaders()});
  if (!response.ok) {
    throw new Error("Failed to load monitor tasks");
  }
  return response.json();
}
