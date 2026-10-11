"""Case-driven eval runner for the clinic agent (P7 seed; generalises escalation_probe).

Same three-step shape as escalation_probe, deliberately: nothing here reads a server.

  # 1. run  (serialized, fresh session_id per case; prints the --since timestamp)
  python -m scripts.probes.eval_runner run --cases clinic-dental-city.yaml \
      --base-url https://staging-api.zunkireelabs.com --out results.json
  # 2. fetch server logs for the window (a human; read-only)
  ssh vps "docker logs --since <ts> zunkiree-search-api-stage 2>&1" > server.log
  # 3. score  (exit 1 on any failed case, missing server evidence, or surprise pass)
  python -m scripts.probes.eval_runner score --results results.json --log server.log

Scoring is from the server's own `[CLINIC-LATENCY] turn_summary` line for the case's
session_id, never from the reply text. A turn with no server line FAILS — absence of
evidence is not a pass.

Case file (YAML): a list of
  - id, why (incident + date), site_id, [ctx: open|closed], [expect: fail], [reason],
    turns: [{user: "..."}  (+ optional per-turn `assert`)],
    assert: {...}   # applies to the LAST turn unless a turn has its own
Assertions: max_llm_iterations, max_tool_calls, tool_calls_not_containing: [names],
max_tool_calls_by_name: {name: n}, max_wall_ms (server total_ms), reply_language: en|ne|rom.
Booking writes: never put confirm_booking turns on a dental-city case (ClinicMD PROD).
"""
import argparse
import json
import re
import sys
import urllib.request
import uuid
from datetime import datetime, timezone

CTX = {
    "open": {"channel_open": True, "handoff_target": None},
    "closed": {"channel_open": False, "closed_reason": "closed_date", "handoff_target": None},
}

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_SUMMARY = re.compile(
    r"\[CLINIC-LATENCY\] turn_summary trace_id=\S+ site_id=\S+ session_id=(?P<sid>\S+) "
    r"total_ms=(?P<total>\d+) iterations=(?P<iters>\d+) pre_llm_ms=(?P<pre>\d+) "
    r"llm_ms=\[(?P<llm>[^\]]*)\] llm_total_ms=\d+ tools=\[(?P<tools>[^\]]*)\]"
)


def load_cases(path: str, only: list[str] | None = None) -> list[dict]:
    import yaml  # dev-tool dependency; not imported by the app

    cases = yaml.safe_load(open(path, encoding="utf-8")) or []
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case id")
    for c in cases:
        if not c.get("why"):
            raise ValueError(f"case {c['id']}: `why` (incident + date) is required")
    return [c for c in cases if not only or c["id"] in only]


def ask(base_url: str, site_id: str, question: str, session_id: str, ctx: dict) -> str:
    body = {"site_id": site_id, "question": question, "session_id": session_id,
            "channel": "voice", **ctx}
    req = urllib.request.Request(
        f"{base_url}/api/v1/query/stream", json.dumps(body).encode(),
        {"Content-Type": "application/json"},
    )
    tokens, answer = [], None
    for line in urllib.request.urlopen(req, timeout=90).read().decode().split("\n"):
        if not line.startswith("data:"):
            continue
        try:
            e = json.loads(line[5:])
        except ValueError:
            continue
        if e.get("type") == "token":
            tokens.append(e.get("data", ""))
        elif e.get("type") == "done":
            answer = e.get("answer")
    return answer if answer is not None else "".join(tokens)


def run(base_url: str, cases: list[dict], out: str) -> None:
    start = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"--since {start}", flush=True)
    results = []
    for c in cases:
        sid = str(uuid.uuid4())  # fresh per case; turns of one case share it
        answers = []
        for t in c["turns"]:
            ans = ask(base_url, c["site_id"], t["user"], sid, CTX[c.get("ctx", "open")])
            answers.append(ans)
            print(c["id"], sid[:8], ans[:80].replace("\n", " "), flush=True)
        results.append(dict(id=c["id"], sid=sid, answers=answers))
    json.dump({"since": start, "cases": cases, "results": results},
              open(out, "w"), ensure_ascii=False, indent=1)


def parse_summaries(log_lines: list[str]) -> dict[str, list[dict]]:
    """session_id -> turn summaries in log order."""
    out: dict[str, list[dict]] = {}
    for ln in log_lines:
        m = _SUMMARY.search(ln)
        if not m:
            continue
        tools = []
        for part in filter(None, m["tools"].split(",")):
            it, name, ms = part.split(":")
            tools.append((int(it), name, int(ms)))
        out.setdefault(m["sid"], []).append(dict(
            total_ms=int(m["total"]), iterations=int(m["iters"]),
            llm_ms=[int(x) for x in filter(None, m["llm"].split(","))], tools=tools))
    return out


def check(turn_assert: dict, summary: dict, answer: str) -> list[str]:
    """Return failure strings for one turn; empty = pass."""
    fails = []
    names = [t[1] for t in summary["tools"]]
    a = turn_assert
    if "max_llm_iterations" in a and summary["iterations"] > a["max_llm_iterations"]:
        fails.append(f"iterations {summary['iterations']} > {a['max_llm_iterations']}")
    if "max_tool_calls" in a and len(names) > a["max_tool_calls"]:
        fails.append(f"tool_calls {len(names)} > {a['max_tool_calls']} {names}")
    for bad in a.get("tool_calls_not_containing", []):
        if bad in names:
            fails.append(f"forbidden tool called: {bad}")
    for name, cap in a.get("max_tool_calls_by_name", {}).items():
        if names.count(name) > cap:
            fails.append(f"{name} x{names.count(name)} > {cap}")
    if "max_wall_ms" in a and summary["total_ms"] > a["max_wall_ms"]:
        fails.append(f"total_ms {summary['total_ms']} > {a['max_wall_ms']}")
    lang = a.get("reply_language")
    if lang:
        has_dev = bool(_DEVANAGARI.search(answer))
        if (lang == "ne") != has_dev:
            fails.append(f"reply script is not {lang}")
    return fails


def score_case(case: dict, result: dict, summaries: dict[str, list[dict]]) -> tuple[str, list[str]]:
    seen = summaries.get(result["sid"], [])
    fails = []
    if len(seen) < len(case["turns"]):
        fails.append(f"no server evidence: {len(seen)}/{len(case['turns'])} turn_summary lines")
    else:
        for i, t in enumerate(case["turns"]):
            last = i == len(case["turns"]) - 1
            a = t.get("assert") or (case.get("assert") if last else None)
            if a:
                fails += [f"turn {i + 1}: {f}" for f in check(a, seen[i], result["answers"][i])]
    expect_fail = case.get("expect") == "fail"
    if expect_fail:
        return ("XFAIL", fails) if fails else ("XPASS", ["expected to fail but passed; remove expect"])
    return ("FAIL", fails) if fails else ("PASS", [])


def score(results_path: str, log_path: str) -> int:
    data = json.load(open(results_path))
    log = open(log_path, encoding="utf-8", errors="replace").read().splitlines()
    summaries = parse_summaries(log)
    cases = {c["id"]: c for c in data["cases"]}
    bad = 0
    for r in data["results"]:
        status, fails = score_case(cases[r["id"]], r, summaries)
        print(f"{status:6} {r['id']}" + ("".join(f"\n         - {f}" for f in fails)))
        bad += status in ("FAIL", "XPASS")
    print(f"{len(data['results'])} cases, {bad} failing")
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--cases", required=True)
    r.add_argument("--base-url", required=True)
    r.add_argument("--only", nargs="*")
    r.add_argument("--out", default="results.json")
    s = sub.add_parser("score")
    s.add_argument("--results", required=True)
    s.add_argument("--log", required=True)
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.base_url.rstrip("/"), load_cases(a.cases, a.only), a.out)
    else:
        sys.exit(score(a.results, a.log))
