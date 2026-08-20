from __future__ import annotations

import importlib.util
import json
import subprocess
from importlib import import_module
from pathlib import Path

from research_synthesis.evidence_index import compile_evidence_index
from research_synthesis.identifiers import sha256_file
from research_synthesis.models import BundleReference, ResolvedBundle
from tests.factories import MODULES, real_resolved_bundles


def test_evidence_and_binding_modules_exist() -> None:
    assert importlib.util.find_spec("research_synthesis.evidence_envelopes") is not None
    assert importlib.util.find_spec("research_synthesis.bindings") is not None


def test_real_bundles_normalize_to_evidence_envelopes() -> None:
    module = import_module("research_synthesis.evidence_envelopes")
    assert hasattr(module, "build_evidence_envelope")
    bundles = real_resolved_bundles()
    envelopes = {
        role: module.build_evidence_envelope(role, bundle)
        for role, bundle in bundles.items()
    }

    assert envelopes["research_design"].identities["plan_id"] == (
        "research-plan-0123456789abcdef"
    )
    assert envelopes["macro_data"].identities["macro_result_id"] == (
        "macro-result-0123456789abcdef"
    )
    assert envelopes["estimator"].identities["request_id"] == (
        "tsd-request-0123456789abcdef"
    )
    assert envelopes["robustness_audit"].identities["audit_result_id"] == (
        "ra-result-dbaf513e89f215e68f6ecb5609900a5d"
    )
    assert all(envelope.artifacts for envelope in envelopes.values())


def test_associational_design_can_omit_identification_audit(
    tmp_path: Path,
) -> None:
    module = import_module("research_synthesis.evidence_envelopes")
    design_root = MODULES / "research-design"

    def load(name: str) -> dict[str, object]:
        path = design_root / "fixtures" / "contracts" / name
        document = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(document, dict)
        return document

    intake = load("intake.valid.json")
    request = load("request.valid.json")
    plan = load("research-plan.valid.json")
    requirements = load("data-requirements.valid.json")
    request["intended_claim"] = "associational"
    request.pop("response_horizons", None)
    request["variables"] = [
        {
            "variable_id": "gdp_per_capita_growth",
            "role": "outcome",
            "concept": "实际人均GDP增长",
            "definition_constraints": ["实际值", "人均口径"],
        }
    ]
    request["intervention_or_shock"] = None
    requirements["macro_data_requests"] = []
    requirements["status"] = "review_required"
    paths = {}
    for name, document in (
        ("intake", intake),
        ("request", request),
        ("plan", plan),
        ("requirements", requirements),
    ):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        paths[name] = path
    target = tmp_path / "design"
    run = subprocess.run(  # noqa: S603
        [
            str(design_root / ".venv" / "bin" / "python"),
            "scripts/materialize_execution_ready_bundle.py",
            "--intake-json",
            str(paths["intake"]),
            "--request-json",
            str(paths["request"]),
            "--research-plan-json",
            str(paths["plan"]),
            "--data-requirements-json",
            str(paths["requirements"]),
            "--output",
            str(target),
        ],
        cwd=design_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    manifest = target / "research-design-run-manifest.json"
    digest = sha256_file(manifest)
    reference = BundleReference(
        bundle_ref_id=f"rs-bundle-ref-{digest[:32]}",
        artifact_role="research_design",
        skill_name="research-design",
        skill_version="0.1.0",
        bundle_path=Path("design"),
        manifest_path=Path(manifest.name),
        expected_manifest_sha256=f"sha256:{digest}",
        expected_ids={"plan_id": str(plan["plan_id"])},
        required=True,
    )
    bundle = ResolvedBundle(
        reference,
        target,
        manifest,
        digest,
    )

    envelope = module.build_evidence_envelope("research_design", bundle)
    envelopes = {
        role: (
            envelope
            if role == "research_design"
            else module.build_evidence_envelope(role, item)
        )
        for role, item in real_resolved_bundles().items()
    }
    index = compile_evidence_index(envelopes)
    identification = next(
        item
        for item in index["evidence"]
        if item["semantic_role"] == "identification"
    )

    assert envelope.identities["audit_id"] == ""
    assert identification["artifact_path"].endswith("research_plan.json")
