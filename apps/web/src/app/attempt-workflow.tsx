"use client";

import { useEffect, useRef, useState } from "react";

import {
  getWorkflow,
  launchWorkflow,
  prepareWorkflow,
  type MotionWorkflow,
} from "@/lib/api";

const SAVED_WORKFLOW = "umr-agent-current-workflow";
const VALID_WORKFLOW = /^[A-Za-z0-9_-]{1,77}$/;

export type RunMotionId =
  | "run"
  | "spin-kick"
  | "speed-vault";

export type RunRequest = {
  motionId: RunMotionId;
  requestId: string;
};

type SavedWorkflow = {
  workflowId: string;
  motionId: RunMotionId;
};

function isMotionId(value: unknown): value is RunMotionId {
  return (
    value === "run" ||
    value === "spin-kick" ||
    value === "speed-vault"
  );
}

function motionLabel(motionId: RunMotionId): string {
  if (motionId === "spin-kick") return "Spin Kick";
  if (motionId === "speed-vault") return "Speed Vault";
  return "Run";
}

function rememberWorkflow(
  workflowId: string,
  motionId: RunMotionId,
) {
  try {
    localStorage.setItem(
      SAVED_WORKFLOW,
      JSON.stringify({
        workflowId,
        motionId,
      }),
    );
  } catch {
    // Storage may be disabled.
  }
}

function forgetWorkflow() {
  try {
    localStorage.removeItem(SAVED_WORKFLOW);
  } catch {
    // Storage may be disabled.
  }
}

function readSavedWorkflow(): SavedWorkflow | null {
  try {
    const raw = localStorage.getItem(SAVED_WORKFLOW);

    if (!raw) return null;

    const value: unknown = JSON.parse(raw);

    if (
      typeof value !== "object" ||
      value === null ||
      Array.isArray(value)
    ) {
      return null;
    }

    const item = value as Record<string, unknown>;

    if (
      typeof item.workflowId !== "string" ||
      !VALID_WORKFLOW.test(item.workflowId) ||
      !isMotionId(item.motionId)
    ) {
      return null;
    }

    return {
      workflowId: item.workflowId,
      motionId: item.motionId,
    };
  } catch {
    return null;
  }
}

export function AttemptWorkflow({
  requestedRun,
}: {
  requestedRun: RunRequest | null;
}) {
  const [workflow, setWorkflow] =
    useState<MotionWorkflow | null>(null);

  const [motion, setMotion] =
    useState<RunMotionId>("spin-kick");

  const [pending, setPending] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [error, setError] = useState("");

  const lastRequestId = useRef<string | null>(null);

  /*
   * Restore the last workflow after reopening the browser.
   * The FAU worker may have continued while the laptop was offline.
   */
  useEffect(() => {
    let active = true;

    const saved = readSavedWorkflow();

    if (!saved) {
      setRestoring(false);
      return;
    }

    setMotion(saved.motionId);

    getWorkflow(saved.workflowId)
      .then((restored) => {
        if (!active) return;
        setWorkflow(restored);
      })
      .catch((cause: unknown) => {
        if (!active) return;

        forgetWorkflow();

        setError(
          cause instanceof Error
            ? cause.message
            : "The previous motion could not be restored.",
        );
      })
      .finally(() => {
        if (active) setRestoring(false);
      });

    return () => {
      active = false;
    };
  }, []);

  /*
   * A natural-language request prepares BOTH exact plans:
   * baseline + deterministic improved candidate.
   *
   * Nothing executes yet.
   */
  useEffect(() => {
    if (
      !requestedRun ||
      restoring ||
      lastRequestId.current === requestedRun.requestId
    ) {
      return;
    }

    lastRequestId.current = requestedRun.requestId;

    if (
      workflow &&
      !["completed", "failed"].includes(workflow.state)
    ) {
      setError(
        "Finish the current motion before starting another one.",
      );
      return;
    }

    const workflowId =
      `g1-${requestedRun.motionId}-` +
      `${Date.now().toString(36)}-` +
      `${crypto.randomUUID().slice(0, 8)}`;

    setMotion(requestedRun.motionId);
    setWorkflow(null);
    setError("");
    setPending(true);

    prepareWorkflow(
      workflowId,
      requestedRun.motionId,
    )
      .then((prepared) => {
        setWorkflow(prepared);

        rememberWorkflow(
          prepared.workflow_id,
          requestedRun.motionId,
        );
      })
      .catch((cause: unknown) => {
        setError(
          cause instanceof Error
            ? cause.message
            : "The motion could not be prepared.",
        );
      })
      .finally(() => {
        setPending(false);
      });
  }, [
    requestedRun,
    restoring,
    workflow?.state,
  ]);

  /*
   * Generate Motion is the ONE user approval.
   * After this succeeds, the FAU worker owns execution.
   */
  async function generateMotion() {
    if (
      !workflow ||
      workflow.state !== "prepared" ||
      !workflow.approval_hash ||
      pending
    ) {
      return;
    }

    setPending(true);
    setError("");

    try {
      const launched = await launchWorkflow(
        workflow.workflow_id,
        workflow.approval_hash,
      );

      setWorkflow(launched);

      rememberWorkflow(
        launched.workflow_id,
        motion,
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "The motion could not be started.",
      );
    } finally {
      setPending(false);
    }
  }

  /*
   * The browser only OBSERVES the workflow.
   * It no longer runs improvement or evaluation itself.
   */
  useEffect(() => {
    if (
      !workflow ||
      ![
        "queued",
        "running_baseline",
        "running_candidate",
        "evaluating",
        "rendering_preview",
      ].includes(workflow.state)
    ) {
      return;
    }

    let active = true;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const next = await getWorkflow(
          workflow!.workflow_id,
        );

        if (!active) return;

        setWorkflow(next);
        setError("");

        rememberWorkflow(
          next.workflow_id,
          motion,
        );

        if (
          next.state === "completed" ||
          next.state === "failed"
        ) {
          return;
        }

        timer = setTimeout(poll, 3000);
      } catch {
        if (!active) return;

        setError(
          "Connection lost. FAU is still processing the motion; reconnecting automatically…",
        );

        timer = setTimeout(poll, 5000);
      }
    }

    poll();

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [
    workflow?.workflow_id,
    workflow?.state,
    motion,
  ]);

  function reset() {
    forgetWorkflow();
    setWorkflow(null);
    setError("");
    setPending(false);
  }

  if (restoring) {
    if (!requestedRun) return null;

    return (
      <section
        className="workflow-panel"
        aria-labelledby="workflow-title"
      >
        <p className="eyebrow accent">
          ROBOT MOTION
        </p>

        <h2 id="workflow-title">
          Create Robot Motion
        </h2>

        <div
          className="prepared-plan"
          aria-live="polite"
        >
          <strong>Restoring motion…</strong>
        </div>
      </section>
    );
  }

  if (!requestedRun && !workflow) {
    return null;
  }

  const state = workflow?.state;

  return (
    <section
      className="workflow-panel"
      aria-labelledby="workflow-title"
    >
      <p className="eyebrow accent">
        ROBOT MOTION
      </p>

      <h2 id="workflow-title">
        Create Robot Motion
      </h2>

      <p>
        Generate and automatically improve a motion
        for Unitree G1.
      </p>

      {pending && !workflow && (
        <div
          className="prepared-plan"
          aria-live="polite"
        >
          <strong>Preparing motion…</strong>

          <p>
            The robot and motion are being verified
            automatically.
          </p>
        </div>
      )}

      {workflow && state === "prepared" && (
        <div
          className="prepared-plan"
          aria-live="polite"
        >
          <div className="prepared-heading">
            <strong>
              Ready to generate · {motionLabel(motion)} → Unitree G1
            </strong>

            <button
              type="button"
              onClick={reset}
              disabled={pending}
            >
              Choose another motion
            </button>
          </div>

          <p>
            The motion and improved version are ready.
            The best version will be selected automatically.
          </p>

          <dl>
            <div>
              <dt>Motion</dt>
              <dd>{motionLabel(motion)}</dd>
            </div>

            <div>
              <dt>Robot</dt>
              <dd>Unitree G1</dd>
            </div>
          </dl>

          <button
            type="button"
            disabled={
              pending ||
              !workflow.approval_hash
            }
            onClick={generateMotion}
          >
            {pending
              ? "Starting motion…"
              : "Generate Motion"}
          </button>
        </div>
      )}

      {workflow &&
        (state === "queued" ||
          state === "running_baseline") && (
          <div
            className="workflow-status"
            aria-live="polite"
          >
            <strong>
              Generating motion…
            </strong>

            <p>
              FAU is generating the motion.
              You can leave this page and return later.
            </p>
          </div>
        )}

      {workflow &&
        state === "running_candidate" && (
          <div
            className="workflow-status"
            aria-live="polite"
          >
            <strong>
              Improving motion…
            </strong>

            <p>
              An improved version is being generated
              automatically.
            </p>
          </div>
        )}

      {workflow &&
        state === "evaluating" && (
          <div
            className="workflow-status"
            aria-live="polite"
          >
            <strong>
              Selecting best version…
            </strong>

            <p>
              The original and improved motions are being
              compared automatically.
            </p>
          </div>
        )}

      {workflow &&
        state === "rendering_preview" && (
          <div
            className="workflow-status"
            aria-live="polite"
          >
            <strong>
              Preparing preview…
            </strong>

            <p>
              The selected motion is being prepared for
              viewing.
            </p>
          </div>
        )}

      {workflow &&
        state === "completed" && (
          <div
            className="workflow-result"
            aria-live="polite"
          >
            <strong>
              {workflow.winner === "candidate"
                ? "Motion improved successfully"
                : "Motion ready"}
            </strong>

            <p>
              {workflow.winner === "candidate"
                ? "The improved version performed better and was selected automatically."
                : "The improved version was tested, but the original performed better overall, so the original was kept."}
            </p>

            <video
              className="motion-preview"
              controls
              playsInline
              preload="metadata"
              poster={`/api/workflows/${encodeURIComponent(
                workflow.workflow_id,
              )}/preview/image`}
            >
              <source
                src={`/api/workflows/${encodeURIComponent(
                  workflow.workflow_id,
                )}/preview/video`}
                type="video/mp4"
              />
              Your browser does not support video playback.
            </video>

            <p className="motion-preview-caption">
              {motionLabel(motion)} · Unitree G1
            </p>

            <div className="download-actions">
              <a
                className="download-link"
                href={`/api/workflows/${encodeURIComponent(
                  workflow.workflow_id,
                )}/download/motion`}
                download
              >
                Download Motion (.npz)
              </a>

              <a
                className="download-link secondary-download"
                href={`/api/workflows/${encodeURIComponent(
                  workflow.workflow_id,
                )}/download/preview`}
                download
              >
                Download Preview (.mp4)
              </a>
            </div>

            <button
              type="button"
              onClick={reset}
            >
              Create another motion
            </button>
          </div>
        )}

      {workflow &&
        state === "failed" && (
          <div
            className="workflow-result"
            aria-live="polite"
          >
            <strong>
              Motion generation stopped
            </strong>

            <p>
              {workflow.error ||
                "The motion could not be completed."}
            </p>

            <button
              type="button"
              onClick={reset}
            >
              Try another motion
            </button>
          </div>
        )}


      {error && (
        <p
          role="alert"
          className="error"
        >
          {error}
        </p>
      )}
    </section>
  );
}
