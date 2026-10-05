from umr_agent.agent.improvement_service import compare_diagnoses
from umr_agent.api.wsl_attempts import AttemptDiagnosis


def make_report(findings):
    return AttemptDiagnosis(
        attempt="test-attempt",
        plan_hash="a" * 64,
        result_sha256="b" * 64,
        frames=78,
        fps=60.0,
        findings=findings,
        viewer_xml="assets/g1/test.xml",
        viewer_xml_sha256="c" * 64,
        viewer_model_provenance="test",
        checks_not_run=["visual_motion_review"],
        thresholds={},
    )


def test_candidate_wins_when_skating_is_reduced():
    baseline = make_report([
        {
            "check": "foot_skating",
            "severity": "warning",
            "foot": "left",
            "count": 7,
            "frames": [59, 60, 61, 62, 65, 66, 67],
        }
    ])

    candidate = make_report([
        {
            "check": "foot_skating",
            "severity": "warning",
            "foot": "left",
            "count": 6,
            "frames": [58, 59, 60, 61, 66, 67],
        }
    ])

    result = compare_diagnoses(baseline, candidate)

    assert result.winner == "candidate"
    assert result.baseline.skating_frames == 7
    assert result.candidate.skating_frames == 6


def test_candidate_loses_if_it_adds_an_error():
    baseline = make_report([
        {
            "check": "foot_skating",
            "severity": "warning",
            "foot": "left",
            "count": 7,
            "frames": [59, 60, 61, 62, 65, 66, 67],
        }
    ])

    candidate = make_report([
        {
            "check": "joint_limits",
            "severity": "error",
            "joint": "left_knee_joint",
            "count": 1,
            "frames": [30],
        },
        {
            "check": "foot_skating",
            "severity": "warning",
            "foot": "left",
            "count": 5,
            "frames": [58, 59, 60, 61, 62],
        },
    ])

    result = compare_diagnoses(baseline, candidate)

    assert result.winner == "baseline"
    assert result.candidate.errors == 1


def test_baseline_wins_when_candidate_does_not_improve():
    baseline = make_report([
        {
            "check": "foot_skating",
            "severity": "warning",
            "foot": "left",
            "count": 6,
            "frames": [58, 59, 60, 61, 66, 67],
        }
    ])

    candidate = make_report([
        {
            "check": "foot_skating",
            "severity": "warning",
            "foot": "left",
            "count": 6,
            "frames": [58, 59, 60, 61, 66, 67],
        }
    ])

    result = compare_diagnoses(baseline, candidate)

    assert result.winner == "baseline"
