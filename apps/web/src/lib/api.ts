export type Robot = {
  robot_id: string;
  name: string;
  aliases: string[];
  registered: boolean;
};

export type Motion = {
  motion_id: string;
  name: string;
  aliases: string[];
  source_type: string;
  registered: boolean;
};

export type Catalog = {
  schema_version: string;
  robots: Robot[];
  motions: Motion[];
};

export type AssetStatus = {
  state: "unconfigured" | "verified" | "failed";
  message: string;
  robot_id: string;
  motion_id: string;
  file_count: number | null;
  umr_git_commit: string | null;
};

export type DiagnosisReply = {
  attempt: string;
  state: string;
  summary: string;
  steps: string[];
  diagnosis: null | {
    frames: number;
    fps: number;
    findings: Array<{ check: string; severity: string; joint?: string; frames?: number[] }>;
    checks_not_run: string[];
    result_sha256: string;
  };
};

export type PreparedAttempt = {
  attempt: string;
  motion_id: "spin-kick" | "run" | "speed-vault";
  max_frames: number;
  profile: "baseline" | "ground-contact";
  plan_hash: string;
  motion_path: string;
  output: string;
  argv: string[];
  manifest_sha256: string;
  robot_xml_sha256: string;
  motion_sha256: string;
  correspondence_slots_sha256: string;
  config_sha256: string;
  pipeline_sha256: string;
  worker_sha256: string;
};

export type AttemptStatus = {
  attempt: string;
  state: "prepared" | "queued" | "running" | "completed" | "failed" | "failed_launch" | "failed_verification";
  plan_hash: string;
  motion_id: string;
  result: null | { frames: number; fps: number; sha256: string };
};

export async function prepareAttempt(attempt: string, motionId: string,
  maxFrames: 0 | 3): Promise<PreparedAttempt> {
  return parseResponse<PreparedAttempt>(await fetch("/api/attempts", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ attempt, motion_id: motionId, max_frames: maxFrames }),
  }));
}

export async function launchAttempt(attempt: string, approvedPlanHash: string): Promise<void> {
  await parseResponse(await fetch(`/api/attempts/${encodeURIComponent(attempt)}/launch`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved_plan_hash: approvedPlanHash }),
  }));
}

export async function getAttemptStatus(attempt: string): Promise<AttemptStatus> {
  return parseResponse<AttemptStatus>(await fetch(`/api/attempts/${encodeURIComponent(attempt)}/status`,
    { cache: "no-store" }));
}

export async function getPreparedAttempt(attempt: string): Promise<PreparedAttempt> {
  return parseResponse<PreparedAttempt>(await fetch(`/api/attempts/${encodeURIComponent(attempt)}/plan`,
    { cache: "no-store" }));
}

export async function inspectAttempt(attempt: string, goal: string,
  provider: "rules" | "ollama"): Promise<DiagnosisReply> {
  return parseResponse<DiagnosisReply>(await fetch("/api/agent/attempts/inspect", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ attempt, goal, provider }),
  }));
}

export type ImprovementPreparation = {
  state: "approval_required" | "not_needed" | "not_applicable";
  baseline_attempt: string;
  candidate_attempt: string | null;
  candidate_plan_hash: string | null;
  reason: string;
};

export type DiagnosisScore = {
  errors: number;
  skating_frames: number;
  velocity_warning_groups: number;
};

export type ImprovementEvaluation = {
  state: "evaluated";
  baseline_attempt: string;
  candidate_attempt: string;
  winner: "baseline" | "candidate";
  winner_attempt: string;
  reason: string;
  baseline: DiagnosisScore;
  candidate: DiagnosisScore;
};

export async function improveAttempt(
  attempt: string,
): Promise<ImprovementPreparation> {
  return parseResponse<ImprovementPreparation>(
    await fetch(
      `/api/agent/attempts/${encodeURIComponent(attempt)}/improve`,
      { method: "POST" },
    ),
  );
}

export async function evaluateAttempt(
  attempt: string,
): Promise<ImprovementEvaluation> {
  return parseResponse<ImprovementEvaluation>(
    await fetch(
      `/api/agent/attempts/${encodeURIComponent(attempt)}/evaluate`,
      { method: "POST" },
    ),
  );
}

export async function getAssetStatus(signal?: AbortSignal): Promise<AssetStatus> {
  return parseResponse<AssetStatus>(await fetch("/api/assets/status", { signal, cache: "no-store" }));
}

export type Proposal = {
  project_id: string;
  requested_by: string;
  robot_id: string;
  robot_name: string;
  motion_id: string;
  motion_name: string;
  source_type: string;
  correspondence_workers: number;
  requires_human_approval: boolean;
  executable: boolean;
};

export type AgentReply = {
  status: "proposal" | "clarification" | "information" | "rejected";
  intent: string;
  message: string;
  proposal: Proposal | null;
  questions: string[];
  warnings: string[];
};

export type InputReview = {
  robot_id: string;
  motion_id: string;
  robot_config: string;
  robot_xml: string;
  motion: string;
  correspondence_slots: string;
  robot_config_sha256: string;
  robot_xml_sha256: string;
  motion_sha256: string;
  correspondence_slots_sha256: string;
  manifest_sha256: string;
  umr_git_commit: string;
  file_count: number;
  correspondence_workers: number;
  executable: false;
  review_hash: string;
};

export async function reviewInputs(proposal: Proposal): Promise<InputReview> {
  return parseResponse<InputReview>(await fetch("/api/agent/reviews", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      robot_id: proposal.robot_id, motion_id: proposal.motion_id,
      correspondence_workers: proposal.correspondence_workers,
    }),
  }));
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    if (response.status === 409) {
      const body = (await response.json()) as { detail?: string };
      throw new Error(body.detail || "Ubuntu input review is unavailable.");
    }
    if (response.status === 503) {
      const body = (await response.json()) as { detail?: string };
      throw new Error(body.detail || "The private service or selected local model is unavailable.");
    }
    if (response.status === 422) {
      const body = (await response.json()) as { detail?: string };
      throw new Error(typeof body.detail === "string" ? body.detail : "The request or attempt is invalid.");
    }
    throw new Error(`Request failed (${response.status}). Check the API and your input.`);
  }
  return (await response.json()) as T;
}

export async function getCatalog(signal?: AbortSignal): Promise<Catalog> {
  return parseResponse<Catalog>(await fetch("/api/catalog", { signal }));
}

export async function propose(goal: string, provider: "rules" | "ollama"): Promise<AgentReply> {
  return parseResponse<AgentReply>(
    await fetch("/api/agent/proposals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal, provider, project_id: "project-umr-demo", actor: "local-user" }),
    }),
  );
}
