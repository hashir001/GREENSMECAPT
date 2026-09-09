"""Resolve applicability and build questions from versioned activity rules."""

import json
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path

from greensmecapt.assessment.profiles.models import (
    Applicability,
    ApplicabilityOverride,
    AssessmentContext,
    AssessmentPolicy,
    AssessmentProfile,
    CriterionDecision,
    FollowUp,
    Requirement,
    Rule,
)


def _unique_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_policy(path: str | Path) -> AssessmentPolicy:
    """Load JSON configuration without accepting duplicate or misspelled fields."""
    data = json.loads(
        Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_json_keys
    )
    return AssessmentPolicy.model_validate(data)


def _fingerprint(data: object) -> str:
    content = json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return sha256(content.encode("utf-8")).hexdigest()


def _evaluate(
    rule: Rule, facts: Mapping[str, bool | None]
) -> tuple[Applicability, tuple[str, ...], tuple[str, ...], str]:
    """Three-valued logic: false can resolve a rule despite unrelated unknowns."""
    failed: list[str] = []
    missing: set[str] = set()
    matched: list[str] = []

    for keys, expected in ((rule.all_true, True), (rule.all_false, False)):
        for key in keys:
            value = facts.get(key)
            if value is None:
                missing.add(key)
            elif value is not expected:
                failed.append(f"{key}={value}")
            else:
                matched.append(f"{key}={value}")

    if rule.any_true:
        true_keys = [key for key in rule.any_true if facts.get(key) is True]
        unknown_keys = [key for key in rule.any_true if facts.get(key) is None]
        if true_keys:
            matched.extend(f"{key}=True" for key in true_keys)
        elif unknown_keys:
            missing.update(unknown_keys)
        else:
            failed.append("all of " + ", ".join(rule.any_true) + " are false")

    if failed:
        return (
            Applicability.NOT_APPLICABLE, (), tuple(matched),
            "Activity conditions not met: " + "; ".join(failed),
        )
    if missing:
        return (
            Applicability.UNCERTAIN, tuple(sorted(missing)), tuple(matched),
            "Confirm the activity facts before deciding applicability.",
        )
    return (
        Applicability.APPLICABLE, (), tuple(matched),
        "Activity conditions met." if matched else "Included in the common profile.",
    )


def build_profile(
    context: AssessmentContext,
    policy: AssessmentPolicy,
    *,
    overrides: Sequence[ApplicabilityOverride] = (),
) -> AssessmentProfile:
    """Evaluate activities; retain every criterion with reasons and follow-ups.

    A future API must authorize overrides before calling this internal function.
    The output contains no score and grants no permission to run MCDM.
    """
    # Snapshot mutable dictionaries inside otherwise frozen Pydantic models.
    context = AssessmentContext.model_validate(context.model_dump())
    policy = AssessmentPolicy.model_validate(policy.model_dump())
    unknown_facts = context.facts.keys() - policy.fact_questions.keys()
    if unknown_facts:
        raise ValueError(f"Unrecognised activity facts: {sorted(unknown_facts)}")

    criterion_ids = {item.criterion_id for item in policy.criteria}
    overrides_by_id = {item.criterion_id: item for item in overrides}
    if len(overrides_by_id) != len(overrides):
        raise ValueError("Only one effective override per criterion is allowed.")
    if overrides_by_id.keys() - criterion_ids:
        raise ValueError("Override references an unknown criterion.")

    active_modules: list[str] = []
    uncertain_modules: list[str] = []
    for module in policy.modules:
        status, _, _, _ = _evaluate(module.when, context.facts)
        if status is Applicability.APPLICABLE:
            active_modules.append(module.module_id)
        elif status is Applicability.UNCERTAIN:
            uncertain_modules.append(module.module_id)

    decisions: list[CriterionDecision] = []
    activity_requests: dict[str, list[str]] = {}
    evidence_requests: list[FollowUp] = []
    priority = {level: index for index, level in enumerate(Requirement)}
    ordered = sorted(policy.criteria, key=lambda item: priority[item.requirement])
    for criterion in ordered:
        rule_status, missing, matched, reason = _evaluate(criterion.when, context.facts)
        status = rule_status
        override = overrides_by_id.get(criterion.criterion_id)
        if override is not None:
            status = override.status
            reason = f"Reviewed override by {override.decided_by}: {override.reason}"
            missing = () if status is not Applicability.UNCERTAIN else missing

        decisions.append(CriterionDecision(
            criterion_id=criterion.criterion_id, title=criterion.title,
            output=criterion.output, requirement=criterion.requirement,
            rule_status=rule_status, status=status, reason=reason,
            missing_facts=missing, matched_facts=matched, override=override,
        ))

        if status is Applicability.UNCERTAIN:
            for fact in missing:
                activity_requests.setdefault(fact, []).append(criterion.criterion_id)
            if not missing:
                evidence_requests.append(FollowUp(
                    request_id=f"clarify:{criterion.criterion_id}",
                    kind="activity_question",
                    question=(
                        f"Explain whether {criterion.title.lower()} "
                        "applies to your activity."
                    ),
                    criterion_ids=(criterion.criterion_id,),
                    response_routes=("explanation", "supporting_record", "unknown"),
                ))
        elif (
            status is Applicability.APPLICABLE
            and criterion.requirement is not Requirement.INFORMATIONAL
        ):
            evidence_requests.append(FollowUp(
                request_id=f"evidence:{criterion.criterion_id}",
                kind="evidence_question", question=criterion.question,
                criterion_ids=(criterion.criterion_id,),
                response_routes=criterion.evidence_routes,
            ))

    follow_ups = tuple(
        FollowUp(
            request_id=f"activity:{fact}", kind="activity_question",
            question=policy.fact_questions[fact], criterion_ids=tuple(ids),
            response_routes=("yes", "no", "unknown"),
        ) for fact, ids in activity_requests.items()
    ) + tuple(evidence_requests)

    return AssessmentProfile(
        sme_id=context.sme_id,
        policy_id=policy.policy_id, policy_version=policy.version,
        policy_sha256=_fingerprint(policy.model_dump(mode="json")),
        context_sha256=_fingerprint(context.model_dump(mode="json")),
        policy_snapshot=policy, context_snapshot=context,
        active_modules=tuple(active_modules),
        uncertain_modules=tuple(uncertain_modules),
        decisions=tuple(decisions), follow_ups=follow_ups,
    )
