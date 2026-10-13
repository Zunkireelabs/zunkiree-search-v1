import json

from scripts.probes import eval_runner as er

SID = "11111111-1111-1111-1111-111111111111"


def line(sid=SID, total=1200, iters=1, llm="900", tools="0:search_knowledge:150"):
    return (f"[CLINIC-LATENCY] turn_summary trace_id=t site_id=dental-city session_id={sid} "
            f"total_ms={total} iterations={iters} pre_llm_ms=50 llm_ms=[{llm}] "
            f"llm_total_ms=900 tools=[{tools}]")


def case(**kw):
    c = {"id": "x", "why": "w", "site_id": "dental-city", "turns": [{"user": "q"}],
         "assert": {"max_llm_iterations": 1, "max_wall_ms": 2000}}
    c.update(kw)
    return c


def res(answers=("ok",)):
    return {"id": "x", "sid": SID, "answers": list(answers)}


def test_parse_and_pass():
    s = er.parse_summaries([line()])
    assert s[SID][0]["tools"] == [(0, "search_knowledge", 150)]
    assert er.score_case(case(), res(), s)[0] == "PASS"


def test_budget_and_forbidden_tool_fail():
    s = er.parse_summaries([line(total=5000, iters=4, llm="1,2,3,4",
                                 tools="1:check_availability:9,2:list_services:9,3:check_availability:9")])
    c = case(assert_={})
    c["assert"] = {"max_llm_iterations": 2, "tool_calls_not_containing": ["list_services"],
                   "max_tool_calls_by_name": {"check_availability": 1}, "max_wall_ms": 2500}
    status, fails = er.score_case(c, res(), s)
    assert status == "FAIL" and len(fails) == 4


def test_missing_server_evidence_fails():
    status, fails = er.score_case(case(), res(), {})
    assert status == "FAIL" and "no server evidence" in fails[0]


def test_expect_fail_and_surprise_pass():
    bad = er.parse_summaries([line(iters=2)])
    assert er.score_case(case(expect="fail"), res(), bad)[0] == "XFAIL"
    good = er.parse_summaries([line()])
    assert er.score_case(case(expect="fail"), res(), good)[0] == "XPASS"


def test_language_and_multiturn_last_turn_scoring():
    s = er.parse_summaries([line(), line(total=9999)])
    c = case(turns=[{"user": "a"}, {"user": "b"}])
    assert er.score_case(c, res(["x", "y"]), s)[0] == "FAIL"  # assert hits the LAST turn
    c2 = case(assert_=None)
    c2["assert"] = {"reply_language": "ne"}
    assert er.score_case(c2, res(["hello"]), er.parse_summaries([line()]))[0] == "FAIL"
    assert er.score_case(c2, res(["नमस्ते"]), er.parse_summaries([line()]))[0] == "PASS"


def test_why_required_and_shipped_cases_load(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("- id: a\n  site_id: s\n  turns: [{user: q}]\n")
    try:
        er.load_cases(str(p))
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_score_cli_exit_code(tmp_path):
    r = tmp_path / "r.json"
    r.write_text(json.dumps({"since": "t", "cases": [case()], "results": [res()]}))
    lg = tmp_path / "s.log"
    lg.write_text(line() + "\n")
    assert er.score(str(r), str(lg)) == 0
    lg.write_text("")
    assert er.score(str(r), str(lg)) == 1
