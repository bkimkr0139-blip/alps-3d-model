"""Deterministic test-program twin compute for EPIC D (지시서 §4).

Pure arithmetic over TestFlow/TestFlowItem/WaferMap rows — no solver, no
invented numbers. Every claim the module makes traces to the flow's own
declared limits/durations/coverage or to the (SYNTHETIC, disclosed) wafer-map
fixture; anything undeclared surfaces as TBD, never zero.

도메인 금지 (수용기준 4): optimization proposals are REVIEW-ONLY. The module
names candidates and their arithmetic; nothing here mutates a flow — applying
anything is a human action through the supersedes endpoint.
"""

TOOL_VERSION = "asic-testprog-v1"

DEFECT_CLASSES = ("open", "short", "leakage", "parametric", "esd", "latchup")
# stages that exist to (re)center a part rather than detect defects — dropping
# a duplicate in these would break trim/cal, so the analyzer never proposes it
_ESSENTIAL_STAGES = {"trim_cal", "interface", "final_bin"}


def flow_totals(items: list, cost_rate_per_site_hour: float | None) -> dict:
    """Time/cost per die: wall time = Σ duration / site_count (sites run in
    parallel). No rate → cost stays TBD (0은 금지, EPIC B 규칙과 동일)."""
    total_duration_s = 0.0
    wall_time_s = 0.0
    for it in items:
        d = float(it.expected_duration_s or 0.0)
        sites = max(1, int(it.site_count or 1))
        total_duration_s += d
        wall_time_s += d / sites
    cost_per_die: float | None = None
    if cost_rate_per_site_hour is not None:
        cost_per_die = round(wall_time_s / 3600.0 * float(cost_rate_per_site_hour), 6)
    return {
        "item_count": len(items),
        "total_duration_s": round(total_duration_s, 3),
        "wall_time_s_per_die": round(wall_time_s, 3),
        "cost_rate_per_site_hour": cost_rate_per_site_hour,
        "cost_per_die": cost_per_die,  # None = TBD (rate 미확정)
    }


def coverage_matrix(items: list) -> dict:
    """Per defect class: best declared coverage_pct + the items providing it.
    Items with no coverage/requirement/failure-mode links are listed as
    `unlinked` (수용기준 1 checks exactly these)."""
    per_class: dict[str, dict] = {}
    unlinked = []
    for it in items:
        cov = it.defect_coverage or []
        if not (it.requirement_ids or []) and not (it.failure_mode_refs or []) and not cov:
            unlinked.append({"item_id": str(it.id), "seq": it.seq, "name": it.name})
        for c in cov:
            dc = c.get("defect_class")
            if dc not in DEFECT_CLASSES:
                continue
            pct = float(c.get("coverage_pct", 0.0))
            cur = per_class.get(dc)
            if cur is None or pct > cur["coverage_pct"]:
                per_class[dc] = {
                    "coverage_pct": pct, "item_id": str(it.id), "name": it.name,
                }
    covered = {dc: v["coverage_pct"] for dc, v in per_class.items()}
    aggregate = round(sum(covered.values()) / len(DEFECT_CLASSES), 4) if covered else 0.0
    return {
        "per_class": per_class,
        "uncovered_classes": [dc for dc in DEFECT_CLASSES if dc not in per_class],
        "aggregate_avg_pct": aggregate,
        "unlinked_items": unlinked,
    }


def cross_target_analysis(sort_items: list, final_items: list) -> dict:
    """Wafer sort ↔ final test 계보·중복·누락 (구현 범위 3).

    duplicates: same normalized name on both targets — a drop candidate ONLY
      when the item is a pure detection repeat (not trim_cal/interface/final_bin).
    gaps: defect classes the final test no longer re-covers while the sort-side
      coverage may drift (parametric/leakage classes classically rechecked).
    """
    def norm(n: str) -> str:
        return n.strip().lower()

    final_by_name = {norm(f.name): f for f in final_items}
    duplicates = []
    for s in sort_items:
        f = final_by_name.get(norm(s.name))
        if f is None:
            continue
        same_limits = (s.limits or None) == (f.limits or None)
        duplicates.append({
            "name": s.name,
            "sort_item_id": str(s.id), "final_item_id": str(f.id),
            "same_limits": same_limits,
            "drop_candidate": f.stage not in _ESSENTIAL_STAGES and same_limits,
            "reason": (
                "동일 limits로 wafer sort에서 이미 검출 — final test 반복은 검토 후 제거 가능"
                if (same_limits and f.stage not in _ESSENTIAL_STAGES)
                else "trim/cal·bin 등 목적이 다른 항목 또는 limits 상이 — 제거 대상 아님"
            ),
        })

    sort_cov = coverage_matrix(sort_items)["per_class"]
    final_cov = coverage_matrix(final_items)["per_class"]
    gaps = [
        {
            "defect_class": dc,
            "sort_coverage_pct": sort_cov[dc]["coverage_pct"],
            "final_coverage_pct": final_cov.get(dc, {}).get("coverage_pct", 0.0),
            "reason": "wafer sort에서 커버되는 결함 클래스가 final test에서 재확인되지 않음",
        }
        for dc in sorted(sort_cov)
        if dc not in final_cov
    ]
    return {"duplicates": duplicates, "coverage_gaps": gaps}


def revision_compatibility(flow, mask_rev: str | None, package_rev: str | None) -> dict:
    """시험 프로그램 ↔ 실리콘 리비전 호환성 매트릭스 (구현 범위 5, 수용기준 3).

    A mismatch here blocks execution/approval at the gate — the router/gate
    reads `compatible`, this function only computes the matrix row.
    """
    mismatches = []
    if mask_rev and flow.compatible_mask_rev and mask_rev != flow.compatible_mask_rev:
        mismatches.append({
            "axis": "mask_rev", "flow_expects": flow.compatible_mask_rev,
            "actual": mask_rev,
        })
    if package_rev and flow.compatible_package_rev and package_rev != flow.compatible_package_rev:
        mismatches.append({
            "axis": "package_rev", "flow_expects": flow.compatible_package_rev,
            "actual": package_rev,
        })
    return {
        "program_revision": flow.program_revision,
        "silicon_revision": flow.silicon_revision,
        "mask_rev": mask_rev,
        "package_rev": package_rev,
        "compatible": not mismatches,
        "mismatches": mismatches,
    }


def limit_change_impact(item, new_limits: dict, *, lots: list, variants: list,
                        quals: list, measurements: list) -> dict:
    """한계값 변경 영향 자동 표시 (수용기준 2).

    The router queries the candidate rows (lots/products/cert evidence/
    measurement runs anchored to this flow's template or program revision);
    this function only computes the delta and packages who is affected.
    Measurement runs whose `program_revision` predates the change are flagged
    re-ingest/re-bias candidates; qualification evidence is flagged because a
    limit move can invalidate a pass claim (인증 증적).
    """
    old = item.limits or {}
    delta = {}
    for k in sorted(set(old) | set(new_limits)):
        if k == "unit":
            continue
        ov, nv = old.get(k), new_limits.get(k)
        if ov != nv:
            delta[k] = {"old": ov, "new": nv}
    unit_changed = (old.get("unit") or new_limits.get("unit")) and (
        old.get("unit") != new_limits.get("unit")
    )
    return {
        "item_id": str(item.id), "item_name": item.name,
        "unit": new_limits.get("unit", old.get("unit")),
        "delta": delta, "unit_changed": bool(unit_changed),
        "affected_lots": [{"id": str(l.id), "lot_ref": l.lot_ref, "status": l.status} for l in lots],
        "affected_products": [{"id": str(v.id), "name": getattr(v, "name", None)} for v in variants],
        "affected_qualification_evidence": [
            {"id": str(q.id), "status": q.status,
             "note": "한계값 변경으로 pass 판정 근거 재검토 필요"}
            for q in quals
        ],
        "affected_measurement_runs": [
            {"id": str(m.id), "program_revision": getattr(m, "program_revision", None),
             "note": "변경 전 한계값으로 판정된 실측 — 재판정 필요 여부 검토"}
            for m in measurements
        ],
        "review_only": True,
    }


def analyze_wafer_map(bins: list, ground_truth: dict | None) -> dict:
    """Bin/site/오버킬·언더킬 추정 (구현 범위 7).

    bin: 1=good, 2=retest, 3+=fail. ground_truth.bad_xy (SYNTHETIC fixture,
    disclosed) lets overkill/underkill be a plain confusion matrix:
      overkill  = good die binned fail  (수율 손실)
      underkill = bad die binned good   (탈출 결함 — the dangerous one)
    Without a ground truth only bin/site/retest rates are reported.
    """
    total = len(bins)
    if not total:
        return {"tool_version": TOOL_VERSION, "total": 0}
    bin_counts: dict[str, int] = {}
    site_total: dict[str, int] = {}
    site_fail: dict[str, int] = {}
    retest = 0
    bad = set()
    if ground_truth:
        bad = {(int(x), int(y)) for x, y in ground_truth.get("bad_xy", [])}
    overkill: list[list[int]] = []
    underkill: list[list[int]] = []
    for b in bins:
        bnum = int(b.get("bin", 1))
        bin_counts[str(bnum)] = bin_counts.get(str(bnum), 0) + 1
        site = str(b.get("site", "-"))
        site_total[site] = site_total.get(site, 0) + 1
        if bnum >= 3:
            site_fail[site] = site_fail.get(site, 0) + 1
        if bnum == 2:
            retest += 1
        xy = (int(b.get("x", -1)), int(b.get("y", -1)))
        if ground_truth:
            if xy in bad and bnum == 1:
                underkill.append(list(xy))
            elif xy not in bad and bnum >= 3:
                overkill.append(list(xy))
    fail_total = sum(v for k, v in bin_counts.items() if int(k) >= 3)
    result = {
        "tool_version": TOOL_VERSION,
        "total": total,
        "bin_counts": bin_counts,
        "yield_pct": round(100.0 * bin_counts.get("1", 0) / total, 4),
        "retest_rate_pct": round(100.0 * retest / total, 4),
        "fail_rate_pct": round(100.0 * fail_total / total, 4),
        "site_fail_rate_pct": {
            s: round(100.0 * site_fail.get(s, 0) / n, 4)
            for s, n in sorted(site_total.items())
        },
        "ground_truth_used": bool(ground_truth),
    }
    if ground_truth:
        n_bad = len(bad)
        result["confusion"] = {
            "bad_dies": n_bad,
            "detected": n_bad - len(underkill),
            "escaped_underkill": len(underkill),
            "underkill_xy": underkill,
            "overkill_xy": overkill,
            "overkill_count": len(overkill),
            "overkill_pct": round(100.0 * len(overkill) / max(1, total - n_bad), 4),
        }
    return result


def optimization_proposals(flow, twin_items: list | None = None,
                           wafer_maps: list | None = None) -> dict:
    """검토안 전용 (수용기준 4): 시간·커버리지·맵 통계에서 나오는 제안 목록.

    `twin_items` = the OTHER target's items (wafer_sort ↔ final_test pair) so
    duplicates can be found. Every proposal carries `review_only: True` and an
    arithmetic basis; none is auto-applied — the API exposes them read-only and
    applying anything is a human supersedes action.
    """
    items = list(flow.items)
    proposals: list[dict] = []

    # 1) wafer sort ↔ final test 중복 → 시간 절감 후보
    if twin_items:
        # drop_candidate는 final 측 기준이므로, 제안 대상은 "지금 보는 flow 쪽"
        # 항목이다 — wafer_sort flow라면 sort_item_id, final_test면 final_item_id.
        own_is_sort = flow.target == "wafer_sort"
        sort_side, final_side = (
            (items, twin_items) if own_is_sort else (twin_items, items)
        )
        x = cross_target_analysis(sort_side, final_side)
        for dup in x["duplicates"]:
            if not dup["drop_candidate"]:
                continue
            own_id = dup["sort_item_id"] if own_is_sort else dup["final_item_id"]
            it = next(i for i in items if str(i.id) == own_id)
            if it.stage in _ESSENTIAL_STAGES:
                continue  # trim/cal·bin 등 본 측 필수 항목은 제거 검토 대상 아님
            sites = max(1, int(it.site_count or 1))
            proposals.append({
                "kind": "duplicate_removal_review",
                "item_id": own_id, "name": dup["name"],
                "basis": {"wall_time_s_per_die": round(float(it.expected_duration_s) / sites, 3)},
                "rationale": (
                    "final test에서 동일 limits로 재검출 — wafer sort 반복은 검토 후 제거 가능"
                    if own_is_sort else dup["reason"]
                ),
                "review_only": True,
            })

    # 2) 커버리지 없는 항목 → 목적 재확인 후보
    unlinked = coverage_matrix(items)["unlinked_items"]
    for u in unlinked:
        proposals.append({
            "kind": "unlinked_item_review",
            "item_id": u["item_id"], "name": u["name"],
            "basis": {},
            "rationale": "요구사항·고장모드·결함 커버리지 링크가 없음 — 목적 확인 또는 링크 추가 검토",
            "review_only": True,
        })

    # 3) 재시험률이 높은 맵 → 오버킬 원인 분석 후보
    for wm in wafer_maps or []:
        a = wm.analysis if isinstance(wm.analysis, dict) else None
        if not a:
            continue
        retest = float(a.get("retest_rate_pct", 0.0))
        if retest >= 5.0:
            conf = a.get("confusion") or {}
            proposals.append({
                "kind": "high_retest_review",
                "wafer_map_id": str(wm.id), "wafer_ref": wm.wafer_ref,
                "basis": {"retest_rate_pct": retest,
                          "overkill_count": conf.get("overkill_count")},
                "rationale": "재시험률 ≥5% — 한계값 가드밴드·사이트 편향 원인 분석 검토",
                "review_only": True,
            })

    return {
        "tool_version": TOOL_VERSION,
        "flow_id": str(flow.id), "program_revision": flow.program_revision,
        "proposals": proposals,
        "review_only": True,
        "note": "AI는 시험 삭제를 자동 적용하지 않습니다 — 검토안만 생성합니다 (수용기준 4).",
    }
