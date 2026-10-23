from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from umr_agent.agent.workflow_service import (
    MotionWorkflow,
    workflow_approval_hash,
)
from umr_agent.api.app import Settings, create_app


TOKEN = "test-only-secret-token-with-at-least-32-chars"


def make_client(root="/srv/UMR") -> TestClient:
    client = TestClient(
        create_app(
            Settings(
                api_token=TOKEN,
                execution_mode="native",
                wsl_root=str(root),
                wsl_script="/srv/agent/scripts/register_umr_assets.py",
            )
        )
    )
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    return client


def make_workflow(
    state="prepared",
    *,
    winner=None,
    winner_attempt=None,
):
    return MotionWorkflow(
        workflow_id="spin-flow-1",
        baseline_attempt="spin-flow-1",
        candidate_attempt="spin-flow-1-gc",
        baseline_plan_hash="a" * 64,
        candidate_plan_hash="b" * 64,
        state=state,
        winner=winner,
        winner_attempt=winner_attempt,
    )


def test_prepare_workflow_returns_exact_approval_hash():
    client = make_client()
    workflow = make_workflow()

    with patch(
        "umr_agent.api.app.prepare_motion_workflow",
        return_value=workflow,
        create=True,
    ) as service:
        response = client.post(
            "/api/workflows",
            json={
                "workflow_id": "spin-flow-1",
                "motion_id": "spin-kick",
            },
        )

    assert response.status_code == 200

    body = response.json()

    assert body["workflow_id"] == "spin-flow-1"
    assert body["state"] == "prepared"
    assert body["approval_hash"] == workflow_approval_hash(workflow)

    assert service.call_args.args[:3] == (
        Path("/srv/UMR"),
        "spin-flow-1",
        "spin-kick",
    )


def test_launch_workflow_queues_exact_workflow():
    client = make_client()

    with patch(
        "umr_agent.api.app.queue_workflow",
        return_value=make_workflow(state="queued"),
        create=True,
    ) as service:
        response = client.post(
            "/api/workflows/spin-flow-1/launch",
            json={
                "approved_workflow_hash": "c" * 64,
            },
        )

    assert response.status_code == 200
    assert response.json()["state"] == "queued"
    assert response.json()["approval_hash"] is None

    service.assert_called_once_with(
        Path("/srv/UMR"),
        "spin-flow-1",
        "c" * 64,
    )


def test_get_workflow_returns_completed_winner():
    client = make_client()

    completed = make_workflow(
        state="completed",
        winner="candidate",
        winner_attempt="spin-flow-1-gc",
    )

    with patch(
        "umr_agent.api.app.read_workflow",
        return_value=completed,
        create=True,
    ):
        response = client.get(
            "/api/workflows/spin-flow-1"
        )

    assert response.status_code == 200

    body = response.json()

    assert body["state"] == "completed"
    assert body["winner"] == "candidate"
    assert body["winner_attempt"] == "spin-flow-1-gc"
    assert body["approval_hash"] is None


def test_preview_video_serves_winning_attempt(tmp_path):
    attempt_dir = (
        tmp_path
        / "output"
        / "agent_attempts"
        / "spin-flow-1-gc"
    )
    attempt_dir.mkdir(parents=True)

    expected = b"fake-mp4-content"
    (attempt_dir / "preview.mp4").write_bytes(expected)

    completed = make_workflow(
        state="completed",
        winner="candidate",
        winner_attempt="spin-flow-1-gc",
    )

    client = make_client(tmp_path)

    with patch(
        "umr_agent.api.app.read_workflow",
        return_value=completed,
    ):
        response = client.get(
            "/api/workflows/spin-flow-1/preview/video"
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "video/mp4"
    )
    assert response.content == expected


def test_preview_image_serves_winning_attempt(tmp_path):
    attempt_dir = (
        tmp_path
        / "output"
        / "agent_attempts"
        / "spin-flow-1-gc"
    )
    attempt_dir.mkdir(parents=True)

    expected = b"fake-png-content"
    (attempt_dir / "preview.png").write_bytes(expected)

    completed = make_workflow(
        state="completed",
        winner="candidate",
        winner_attempt="spin-flow-1-gc",
    )

    client = make_client(tmp_path)

    with patch(
        "umr_agent.api.app.read_workflow",
        return_value=completed,
    ):
        response = client.get(
            "/api/workflows/spin-flow-1/preview/image"
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "image/png"
    )
    assert response.content == expected


def test_preview_rejects_unfinished_workflow(tmp_path):
    client = make_client(tmp_path)

    with patch(
        "umr_agent.api.app.read_workflow",
        return_value=make_workflow(
            state="rendering_preview",
            winner="candidate",
            winner_attempt="spin-flow-1-gc",
        ),
    ):
        response = client.get(
            "/api/workflows/spin-flow-1/preview/video"
        )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Workflow preview is not ready."
    )


def test_preview_returns_404_when_artifact_missing(tmp_path):
    completed = make_workflow(
        state="completed",
        winner="candidate",
        winner_attempt="spin-flow-1-gc",
    )

    client = make_client(tmp_path)

    with patch(
        "umr_agent.api.app.read_workflow",
        return_value=completed,
    ):
        response = client.get(
            "/api/workflows/spin-flow-1/preview/video"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Workflow preview was not found."
    )


def test_download_motion_serves_winning_npz(tmp_path):
    attempt_dir = (
        tmp_path
        / "output"
        / "agent_attempts"
        / "spin-flow-1-gc"
    )
    attempt_dir.mkdir(parents=True)

    motion = attempt_dir / "spin_kick_g1.npz"
    expected = b"fake-npz-content"
    motion.write_bytes(expected)

    (attempt_dir / "plan.json").write_text(
        __import__("json").dumps(
            {
                "output": str(motion),
            }
        ),
        encoding="utf-8",
    )

    completed = make_workflow(
        state="completed",
        winner="candidate",
        winner_attempt="spin-flow-1-gc",
    )

    client = make_client(tmp_path)

    with patch(
        "umr_agent.api.app.read_workflow",
        return_value=completed,
    ):
        response = client.get(
            "/api/workflows/spin-flow-1/download/motion"
        )

    assert response.status_code == 200
    assert response.content == expected
    assert response.headers[
        "content-type"
    ].startswith(
        "application/octet-stream"
    )

    assert "attachment" in response.headers[
        "content-disposition"
    ]

    assert "spin_kick_g1.npz" in response.headers[
        "content-disposition"
    ]


def test_download_preview_returns_attachment(tmp_path):
    attempt_dir = (
        tmp_path
        / "output"
        / "agent_attempts"
        / "spin-flow-1-gc"
    )
    attempt_dir.mkdir(parents=True)

    expected = b"fake-preview-content"

    (
        attempt_dir
        / "preview.mp4"
    ).write_bytes(expected)

    completed = make_workflow(
        state="completed",
        winner="candidate",
        winner_attempt="spin-flow-1-gc",
    )

    client = make_client(tmp_path)

    with patch(
        "umr_agent.api.app.read_workflow",
        return_value=completed,
    ):
        response = client.get(
            "/api/workflows/spin-flow-1/download/preview"
        )

    assert response.status_code == 200
    assert response.content == expected

    assert "attachment" in response.headers[
        "content-disposition"
    ]

    assert "preview.mp4" in response.headers[
        "content-disposition"
    ]
