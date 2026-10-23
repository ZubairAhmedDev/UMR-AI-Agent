"use client";

import { FormEvent, useEffect, useState } from "react";
import { AgentReply, AssetStatus, Catalog, DiagnosisReply, Proposal, getAssetStatus, getCatalog, inspectAttempt, propose } from "@/lib/api";
import { AttemptWorkflow, RunMotionId, RunRequest } from "./attempt-workflow";

type Exchange = { id: number; goal: string; reply: AgentReply };

function supportedG1Motion(proposal: Proposal | null): RunMotionId | null {
  if (!proposal || proposal.robot_id !== "unitree-g1") return null;
  switch (proposal.motion_id) {
    case "humanoid-spin-kick": return "spin-kick";
    case "humanoid-run": return "run";
    case "humanoid-speed-vault": return "speed-vault";
    default: return null;
  }
}

export default function Home() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [assetStatus, setAssetStatus] = useState<AssetStatus | null>(null);
  const [assetChecking, setAssetChecking] = useState(false);
  const [assetError, setAssetError] = useState("");
  const [goal, setGoal] = useState("");
  const [history, setHistory] = useState<Exchange[]>([]);
  const [runRequest, setRunRequest] = useState<RunRequest | null>(null);
  const [pending, setPending] = useState(false);
  const [requestError, setRequestError] = useState("");
  const [attemptName, setAttemptName] = useState("g1-run-full-001");
  const [attemptGoal, setAttemptGoal] = useState("Explain the measured warnings and missing checks.");
  const [attemptProvider, setAttemptProvider] = useState<"rules" | "ollama">("rules");
  const [diagnosis, setDiagnosis] = useState<DiagnosisReply | null>(null);
  const [diagnosisError, setDiagnosisError] = useState("");
  const [diagnosisPending, setDiagnosisPending] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getCatalog(controller.signal)
      .then(setCatalog)
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setCatalogError(error instanceof Error ? error.message : "Could not load catalog.");
        }
      });
    return () => controller.abort();
  }, []);

  async function refreshAssets() {
    setAssetChecking(true);
    setAssetError("");
    try {
      setAssetStatus(await getAssetStatus());
    } catch (error) {
      setAssetStatus(null);
      setAssetError(error instanceof Error ? error.message : "Could not check Ubuntu assets.");
    } finally {
      setAssetChecking(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const request = goal.trim();
    if (!request || pending) return;
    setPending(true);
    setRequestError("");
    try {
      const reply = await propose(request, "rules");
      setHistory((current) => [...current, { id: Date.now(), goal: request, reply }]);

      if (reply.proposal) {
        const motionId = supportedG1Motion(reply.proposal);
        if (motionId) {
          setRunRequest({
            motionId,
            requestId: crypto.randomUUID(),
          });
        }
      }

      setGoal("");
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Request failed.");
    } finally {
      setPending(false);
    }
  }

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (diagnosisPending) return;
    setDiagnosisPending(true);
    setDiagnosisError("");
    setDiagnosis(null);
    try {
      setDiagnosis(await inspectAttempt(attemptName.trim(), attemptGoal.trim(), attemptProvider));
    } catch (error) {
      setDiagnosisError(error instanceof Error ? error.message : "Attempt inspection failed.");
    } finally { setDiagnosisPending(false); }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">U</span><div><strong>UMR Agent</strong><small>Motion workspace</small></div></div>
        <div className="sidebar-section">
          <span className="eyebrow">Workspace</span>
          <div className="nav-item selected"><span className="nav-icon">✦</span> Agent Studio</div>
        </div>
        <div className="sidebar-section">
          <span className="eyebrow">Available robots</span>
          {catalog?.robots.map((robot) => (
            <div className="catalog-item" key={robot.robot_id}>
              <span className="catalog-icon">R</span><span>{robot.name}</span>
              <span className={robot.registered ? "status-dot ready" : "status-dot"} title={robot.registered ? "Registered in planning catalog" : "Not marked registered in planning catalog; Ubuntu run preparation checks files separately"} />
            </div>
          ))}
          {!catalog && <p className="sidebar-note">{catalogError || "Loading catalog…"}</p>}
        </div>
        <div className="sidebar-section">
          <span className="eyebrow">Reference motions</span>
          {catalog?.motions.map((motion) => (
            <div className="catalog-item" key={motion.motion_id}>
              <span className="catalog-icon motion">M</span><span>{motion.name}</span>
              <span className={motion.registered ? "status-dot ready" : "status-dot"} title={motion.registered ? "Registered in planning catalog" : "Not marked registered in planning catalog; Ubuntu run preparation checks files separately"} />
            </div>
          ))}
        </div>
        <div className="sidebar-section asset-check">
          <span className="eyebrow">Ubuntu assets</span>
          <p>{assetError || assetStatus?.message || "Check the G1 and spin kick files in Ubuntu."}</p>
          {assetStatus?.state === "verified" && <p>{assetStatus.file_count} files · UMR {assetStatus.umr_git_commit?.slice(0, 8)}</p>}
          <button type="button" onClick={refreshAssets} disabled={assetChecking}>
            {assetChecking ? "Checking…" : "Verify files"}
          </button>
        </div>
        <div className="sidebar-footer">Local G1 workspace</div>
      </aside>

      <main className="main">
        <header className="topbar"><span>Project / UMR demo</span><span className="topbar-tag">Local G1 workspace</span></header>
        <div className="content">
          <div className="hero">
            <div className="hero-icon">✦</div>
            <p className="eyebrow accent">UMR AGENT STUDIO</p>
            <h1>Create a robot motion.</h1>
            <p>Tell the agent what motion you want Unitree G1 to perform.</p>
          </div>

          {history.length === 0 && (
            <div className="examples">
              <span className="eyebrow">TRY A REQUEST</span>
              <div className="example-list">
                <button type="button" onClick={() => setGoal("Create a spin kick for Unitree G1")}>Create a spin kick for Unitree G1 <span>↗</span></button>
                <button type="button" onClick={() => setGoal("Create a running motion for Unitree G1")}>Create a running motion for Unitree G1 <span>↗</span></button>
              </div>
            </div>
          )}

          <section className="conversation" aria-live="polite">
            {history.map(({ id, goal: previousGoal, reply }) => (
              <div className="exchange" key={id}>
                <div className="user-message">{previousGoal}</div>
                <article className="response-card">
                  <div className="response-heading"><span className="avatar">✦</span><strong>UMR Agent</strong><span className="response-status">{reply.status === "proposal" ? "Ready" : reply.status}</span></div>
                  {!reply.proposal && <p>{reply.message}</p>}
                  {reply.questions.length > 0 && <ul className="detail-list">{reply.questions.map((question) => <li key={question}>{question}</li>)}</ul>}
                  {reply.proposal && (
                    <div className="proposal-card">
                      <strong>
                        ✓ {reply.proposal.motion_name
                          .replace("Humanoid Character ", "")
                          .replace("MimicKit Humanoid ", "")} selected for {reply.proposal.robot_name}
                      </strong>
                    </div>
                  )}

                  {reply.proposal && !supportedG1Motion(reply.proposal) &&
                    <p>This motion is not connected to the local G1 runner yet. Choose run, spin kick, or speed vault.</p>}

                </article>
              </div>
            ))}
          </section>

          <form className="composer" onSubmit={submit}>
            <label className="sr-only" htmlFor="goal">Describe a motion request</label>
            <textarea id="goal" value={goal} maxLength={2000} onChange={(event) => setGoal(event.target.value)} placeholder="Example: Create a spin kick for Unitree G1…" rows={3} />
            <div className="composer-actions">
              <button type="submit" disabled={pending || !goal.trim()}>
                {pending ? "Understanding request…" : "Create Motion"} <span>→</span>
              </button>
            </div>
            {requestError && <p role="alert" className="error">{requestError}</p>}
          </form>
          <p className="footnote">The agent selects the motion and handles the technical setup automatically.</p>
          <AttemptWorkflow requestedRun={runRequest} />
        </div>
      </main>
    </div>
  );
}
