"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import {
  AttemptStatus,
  DiagnosisReply,
  ImprovementEvaluation,
  ImprovementPreparation,
  PreparedAttempt,
  evaluateAttempt,
  getAttemptStatus,
  getPreparedAttempt,
  improveAttempt,
  inspectAttempt,
  launchAttempt,
  prepareAttempt,
} from "@/lib/api";

const SAVED_ATTEMPT = "umr-agent-current-attempt";
const VALID_ATTEMPT = /^[A-Za-z0-9_-]{1,80}$/;
export type RunMotionId = "run" | "spin-kick" | "speed-vault";
export type RunRequest = { motionId: RunMotionId; requestId: string };

function rememberAttempt(attempt: string) {
  try { sessionStorage.setItem(SAVED_ATTEMPT, attempt); } catch { /* Storage may be disabled. */ }
}

function forgetAttempt() {
  try { sessionStorage.removeItem(SAVED_ATTEMPT); } catch { /* Storage may be disabled. */ }
}

export function AttemptWorkflow({ requestedRun }: { requestedRun: RunRequest | null }) {
  const [attempt, setAttempt] = useState("");
  const [motion, setMotion] = useState("run");
  const [frames, setFrames] = useState<0 | 3>(3);
  const [plan, setPlan] = useState<PreparedAttempt | null>(null);
  const [approved, setApproved] = useState(false);
  const [pending, setPending] = useState(false);
  const [tracking, setTracking] = useState("");
  const [status, setStatus] = useState<AttemptStatus | null>(null);
  const [analysis, setAnalysis] = useState<DiagnosisReply | null>(null);
  const [improvement, setImprovement] = useState<ImprovementPreparation | null>(null);
  const [evaluation, setEvaluation] = useState<ImprovementEvaluation | null>(null);
  const [trackingMode, setTrackingMode] = useState<"baseline" | "candidate" | null>(null);
  const [error, setError] = useState("");
  const [restoring, setRestoring] = useState(true);
  const lastRequestId = useRef<string | null>(null);

  useEffect(() => {
    if (!requestedRun || restoring || lastRequestId.current === requestedRun.requestId) return;
    lastRequestId.current = requestedRun.requestId;
    if (plan || pending || tracking) {
      setError("Finish or clear the current attempt, then select the proposed motion again.");
      return;
    }
    setAttempt(`g1-${requestedRun.motionId}-${Date.now().toString(36)}-${crypto.randomUUID().slice(0, 8)}`);
    setMotion(requestedRun.motionId);
    setFrames(3);
    setStatus(null); setAnalysis(null); setError("");
  }, [requestedRun, restoring, plan, pending, tracking]);

  async function recover(id: string, isActive: () => boolean = () => true) {
    const savedPlan = await getPreparedAttempt(id);
    const current = await getAttemptStatus(id);

    if (
      savedPlan.attempt !== id ||
      current.attempt !== id ||
      savedPlan.plan_hash !== current.plan_hash
    ) {
      throw new Error(
        "The saved attempt and its verified plan do not match.",
      );
    }

    if (!isActive()) return;

    const isCandidate =
      savedPlan.profile === "ground-contact" ||
      id.endsWith("-gc");

    if (!isCandidate) {
      setAttempt(id);
      setMotion(savedPlan.motion_id);
      setFrames(savedPlan.max_frames as 0 | 3);
      setPlan(savedPlan);
      setApproved(false);
      setStatus(
        current.state === "prepared"
          ? null
          : current,
      );
      setAnalysis(null);
      setImprovement(null);
      setEvaluation(null);
      setTrackingMode(
        ["queued", "running", "completed"].includes(current.state)
          ? "baseline"
          : null,
      );

      if (
        ["queued", "running", "completed"].includes(current.state)
      ) {
        setTracking(id);
      } else {
        setTracking("");
      }

      rememberAttempt(id);
      return;
    }

    if (!id.endsWith("-gc")) {
      throw new Error(
        "The saved improvement attempt has an invalid name.",
      );
    }

    const baselineAttempt = id.slice(0, -3);
    const baselinePlan = await getPreparedAttempt(baselineAttempt);
    const baselineStatus = await getAttemptStatus(baselineAttempt);

    if (
      baselinePlan.profile !== "baseline" ||
      baselinePlan.motion_id !== savedPlan.motion_id ||
      baselinePlan.max_frames !== savedPlan.max_frames
    ) {
      throw new Error(
        "The saved improvement does not match its baseline motion.",
      );
    }

    if (baselineStatus.state !== "completed") {
      throw new Error(
        "The baseline motion is not complete.",
      );
    }

    if (!isActive()) return;

    setAttempt(baselineAttempt);
    setMotion(baselinePlan.motion_id);
    setFrames(baselinePlan.max_frames as 0 | 3);
    setPlan(baselinePlan);
    setApproved(false);
    setAnalysis(null);
    setEvaluation(null);

    if (current.state === "prepared") {
      setStatus(baselineStatus);
      setImprovement({
        state: "approval_required",
        baseline_attempt: baselineAttempt,
        candidate_attempt: id,
        candidate_plan_hash: savedPlan.plan_hash,
        reason:
          "An improved version is prepared and ready to run.",
      });
      setTracking("");
      setTrackingMode(null);
      rememberAttempt(baselineAttempt);
      return;
    }

    setImprovement(null);
    setStatus(current);

    if (
      ["queued", "running", "completed"].includes(current.state)
    ) {
      setTrackingMode("candidate");
      setTracking(id);
      rememberAttempt(id);
      return;
    }

    setTracking("");
    setTrackingMode(null);
    rememberAttempt(id);
  }

  useEffect(() => {
    let active = true;
    let id: string | null = null;
    try { id = sessionStorage.getItem(SAVED_ATTEMPT); } catch { /* Storage may be disabled. */ }
    if (id && VALID_ATTEMPT.test(id)) {
      recover(id, () => active)
        .catch((cause: unknown) => {
          if (active) setError(cause instanceof Error ? cause.message : "Could not resume the attempt.");
        })
        .finally(() => { if (active) setRestoring(false); });
    } else {
      if (id) forgetAttempt();
      setRestoring(false);
    }
    return () => { active = false; };
  }, []);

  async function resume() {
    const id = attempt.trim();
    if (pending || restoring || !VALID_ATTEMPT.test(id)) return;
    setPending(true); setError(""); setApproved(false); setStatus(null); setAnalysis(null);
    setImprovement(null); setEvaluation(null); setTrackingMode(null);
    try { await recover(id); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not resume the attempt."); }
    finally { setPending(false); }
  }

  async function prepare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || tracking || restoring) return;
    setPending(true); setPlan(null); setApproved(false); setStatus(null); setAnalysis(null);
    setImprovement(null); setEvaluation(null); setTrackingMode(null); setError("");
    try {
      const prepared = await prepareAttempt(attempt.trim(), motion, frames);
      setPlan(prepared);
      rememberAttempt(prepared.attempt);
    }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Preparation failed."); }
    finally { setPending(false); }
  }

  async function launch() {
    if (!plan || !approved || pending || restoring || status) return;
    setPending(true); setError("");
    try {
      await launchAttempt(plan.attempt, plan.plan_hash);
      setStatus({ attempt: plan.attempt, state: "queued", plan_hash: plan.plan_hash,
                  motion_id: plan.motion_id, result: null });
      setTrackingMode("baseline");
      setTracking(plan.attempt);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Launch failed."); }
    finally { setPending(false); }
  }

  async function launchImprovement() {
    if (
      improvement?.state !== "approval_required" ||
      !improvement.candidate_attempt ||
      !improvement.candidate_plan_hash ||
      pending ||
      tracking
    ) return;

    setPending(true);
    setError("");
    setEvaluation(null);

    try {
      const candidatePlan = await getPreparedAttempt(
        improvement.candidate_attempt,
      );

      if (
        candidatePlan.plan_hash !== improvement.candidate_plan_hash ||
        candidatePlan.profile !== "ground-contact"
      ) {
        throw new Error(
          "The prepared improvement no longer matches the verified candidate plan.",
        );
      }

      await launchAttempt(
        candidatePlan.attempt,
        candidatePlan.plan_hash,
      );

      setStatus({
        attempt: candidatePlan.attempt,
        state: "queued",
        plan_hash: candidatePlan.plan_hash,
        motion_id: candidatePlan.motion_id,
        result: null,
      });

      setAnalysis(null);
      setTrackingMode("candidate");
      setTracking(candidatePlan.attempt);
      rememberAttempt(candidatePlan.attempt);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "The improved motion could not be started.",
      );
    } finally {
      setPending(false);
    }
  }


  useEffect(() => {
    if (!tracking) return;

    let active = true;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const next = await getAttemptStatus(tracking);
        if (!active) return;

        setStatus(next);

        if (next.state === "completed") {
          const candidateRun =
            trackingMode === "candidate" ||
            tracking.endsWith("-gc");

          if (candidateRun) {
            const baselineAttempt = tracking.endsWith("-gc")
              ? tracking.slice(0, -3)
              : plan?.attempt;

            if (!baselineAttempt) {
              throw new Error(
                "The baseline motion could not be identified for evaluation.",
              );
            }

            const result = await evaluateAttempt(baselineAttempt);

            if (active) {
              setEvaluation(result);
              setImprovement(null);
              setAnalysis(null);
              setTracking("");
              setTrackingMode(null);
              rememberAttempt(result.winner_attempt);
            }

            return;
          }

          const report = await inspectAttempt(
            tracking,
            "Explain measured warnings and missing checks.",
            "rules",
          );

          if (!active) return;

          setAnalysis(report);

          if (
            plan?.profile === "baseline" &&
            plan.max_frames === 0
          ) {
            try {
              const preparedImprovement = await improveAttempt(
                tracking,
              );

              if (active) {
                setImprovement(preparedImprovement);
              }
            } catch (cause) {
              if (active) {
                setError(
                  cause instanceof Error
                    ? cause.message
                    : "Motion quality improvement could not be prepared.",
                );
              }
            }
          }

          if (active) {
            setTracking("");
            setTrackingMode(null);
          }

          return;
        }

        if (
          ["failed", "failed_launch", "failed_verification"].includes(
            next.state,
          )
        ) {
          setTracking("");
          setTrackingMode(null);
          return;
        }

        timer = setTimeout(poll, 3000);
      } catch (cause) {
        if (active) {
          setError(
            cause instanceof Error
              ? cause.message
              : "Status check failed.",
          );
          setTracking("");
          setTrackingMode(null);
        }
      }
    }

    poll();

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [tracking, trackingMode, plan]);

  return <section className="workflow-panel" aria-labelledby="workflow-title">
    <p className="eyebrow accent">ROBOT MOTION</p>
    <h2 id="workflow-title">Create Robot Motion</h2>
    <p>Choose a motion and generate a verified local motion for Unitree G1.</p>
    <form onSubmit={prepare}>
      <label htmlFor="new-attempt">Name this run</label>
      <input id="new-attempt" value={attempt} pattern="[A-Za-z0-9_-]{1,80}" maxLength={80}
        placeholder="g1-run-smoke-002" required disabled={pending || restoring || !!tracking || !!plan}
        onChange={(event) => setAttempt(event.target.value)} />
      <div className="workflow-fields">
        <div><label htmlFor="new-motion">Source motion</label>
          <select id="new-motion" value={motion} disabled={pending || restoring || !!tracking || !!plan}
            onChange={(event) => setMotion(event.target.value)}>
            <option value="run">Run</option><option value="spin-kick">Spin kick</option>
            <option value="speed-vault">Speed vault</option>
          </select></div>
        <div><label htmlFor="frame-limit">Frames</label>
          <select id="frame-limit" value={frames} disabled={pending || restoring || !!tracking || !!plan}
            onChange={(event) => setFrames(Number(event.target.value) as 0 | 3)}>
            <option value={3}>Three-frame smoke test</option><option value={0}>Full motion</option>
          </select></div>
      </div>
      {!plan && <div className="workflow-actions">
        <button type="submit" disabled={pending || restoring || !!tracking}>{pending ? "Checking Ubuntu…" : restoring ? "Restoring attempt…" : "Generate run files"}</button>
        <button type="button" className="secondary-action" disabled={pending || restoring || !!tracking || !VALID_ATTEMPT.test(attempt.trim())}
          onClick={resume}>Resume existing attempt</button>
      </div>}
    </form>
    {plan && <div className="prepared-plan">
      <div className="prepared-heading"><strong>{status ? "Motion details" : "Ready to generate"} · {plan.motion_id} → Unitree G1</strong>
        {!tracking && !status && <button type="button" onClick={() => {
          forgetAttempt(); setPlan(null); setApproved(false); setAttempt("");
        }}>Choose another motion or run name</button>}</div>
      <p>
        {status
          ? "The motion was generated from verified inputs."
          : "The motion is ready to generate. Quality checks will run automatically after completion."}
      </p>
      <dl>
        <div><dt>Motion</dt><dd>{plan.motion_id}</dd></div>
        <div><dt>Robot</dt><dd>Unitree G1</dd></div>
        <div><dt>Mode</dt><dd>{plan.max_frames === 0 ? "Full motion" : `${plan.max_frames}-frame test`}</dd></div>
      </dl>
      {!status && <>
        <label className="run-confirmation" htmlFor="run-approval">
          <input id="run-approval" type="checkbox" checked={approved} disabled={pending}
            onChange={(event) => setApproved(event.target.checked)} />
          <span>I want to generate this {plan.max_frames === 3 ? "3-frame test" : "full motion"} for {plan.motion_id}.</span>
        </label>
        <button type="button" disabled={pending || !approved}
          onClick={launch}>{pending ? "Generating motion…" : plan.max_frames === 3 ? "Generate 3-frame test" : "Generate motion"}</button>
      </>}
      <details><summary>Developer details</summary>
        <p>Technical provenance and verification details for this motion.</p>
        <dl>
          <div><dt>Attempt</dt><dd>{plan.attempt}</dd></div>
          <div><dt>Source</dt><dd>{plan.motion_path}</dd></div>
          <div><dt>Output</dt><dd>{plan.output}</dd></div>
        </dl>
        <dl>
          <div><dt>Manifest</dt><dd>{plan.manifest_sha256}</dd></div>
          <div><dt>Motion</dt><dd>{plan.motion_sha256}</dd></div>
          <div><dt>Robot XML</dt><dd>{plan.robot_xml_sha256}</dd></div>
          <div><dt>Correspondence slots</dt><dd>{plan.correspondence_slots_sha256}</dd></div>
          <div><dt>Configuration</dt><dd>{plan.config_sha256}</dd></div>
          <div><dt>Pipeline</dt><dd>{plan.pipeline_sha256}</dd></div>
          <div><dt>Worker</dt><dd>{plan.worker_sha256}</dd></div>
        </dl><p>Arguments: {JSON.stringify(plan.argv)}</p>
        <p>Plan ID (SHA-256): <code className="plan-hash">{plan.plan_hash}</code></p>
      </details>
    </div>}
    {status && <div className="workflow-status" aria-live="polite">
      <strong>
        {status.state === "completed"
          ? "Motion generated"
          : status.state === "queued" || status.state === "running"
            ? "Generating motion"
            : "Motion generation stopped"}
      </strong>
      <p>
        {status.state === "completed"
          ? evaluation
            ? "Quality evaluation complete."
            : improvement
              ? "Quality check complete."
              : analysis
                ? "Quality check complete."
                : "Checking motion quality…"
          : status.state === "queued" || status.state === "running"
            ? "The motion is being generated. This page updates automatically."
            : "The motion could not be completed. Review developer details before trying again."}
      </p>
      {!tracking && <button type="button" onClick={() => {
        forgetAttempt();
        setPlan(null);
        setApproved(false);
        setStatus(null);
        setAnalysis(null);
        setImprovement(null);
        setEvaluation(null);
        setTrackingMode(null);
        setError("");
        setAttempt("");
      }}>Create another motion</button>}
    </div>}
    {improvement?.state === "approval_required" &&
      !tracking &&
      !evaluation && (
        <div className="workflow-result" aria-live="polite">
          <strong>Improvement available</strong>
          <p>
            The motion completed successfully, and an improved version is available
            based on the measured quality checks.
          </p>
          <button
            type="button"
            disabled={pending}
            onClick={launchImprovement}
          >
            {pending ? "Starting improvement…" : "Run improved version"}
          </button>
        </div>
      )}

    {improvement?.state === "not_needed" &&
      !evaluation && (
        <div className="workflow-result" aria-live="polite">
          <strong>Motion ready</strong>
          <p>
            The motion passed the available quality checks and no automatic
            improvement is needed.
          </p>
        </div>
      )}

    {improvement?.state === "not_applicable" &&
      !evaluation && (
        <div className="workflow-result" aria-live="polite">
          <strong>Motion needs review</strong>
          <p>{improvement.reason}</p>
        </div>
      )}

    {evaluation && (
      <div className="workflow-result" aria-live="polite">
        <strong>
          {evaluation.winner === "candidate"
            ? "Motion improved successfully"
            : "Original motion kept"}
        </strong>
        <p>
          {evaluation.winner === "candidate"
            ? "The improved version performed better in the measured motion-quality checks and has been selected."
            : "The improved version did not perform better overall, so the original motion was kept."}
        </p>
      </div>
    )}

    {analysis?.diagnosis && !evaluation && <div className="workflow-result" aria-live="polite">
      <strong>Diagnosis · {analysis.diagnosis.frames} frames</strong>
      <p>{analysis.summary}</p>
      <p>Checks not run: {analysis.diagnosis.checks_not_run.join(", ")}.</p>
      <details><summary>Technical details</summary><p>Result SHA-256: {analysis.diagnosis.result_sha256}</p></details>
    </div>}
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}
