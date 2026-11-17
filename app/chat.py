"""Chat tab for the Streamlit companion apps (R26): replay by default, live only with the viewer's own OpenAI key.

Same file in every portfolio app. The viewer's key lives in their session only: never written to disk, logged, or sent anywhere
but OpenAI. Live questions are capped per session.
"""
from __future__ import annotations

from pathlib import Path

import agent as A

LIVE_LIMIT = 10                  # live questions per session
MATCH_FLOOR = 0.35               # below this, no recorded answer is close enough to show


def _show(st, run: dict, note: str | None = None) -> None:
    with st.chat_message("user"):
        st.markdown(run["question"])
    with st.chat_message("assistant"):
        if note:
            st.caption(note)
        st.markdown(run["answer"] or "_No answer._")
        with st.expander("How it answered: tools, number check, cost"):
            if run["tool_calls"]:
                for i, c in enumerate(run["tool_calls"], 1):
                    args = ", ".join(f"{k}={v}" for k, v in c["arguments"].items())
                    st.markdown(f"{i}. `{c['name']}({args})`" + ("" if c["ok"] else " (returned an error)"))
            else:
                st.markdown("No tools: the question is outside what this agent does.")
            check = ("every number in the answer is in a tool result or the question" if run["grounded"]
                     else f"numbers not found in the tool results: {', '.join(run['ungrounded_numbers'])}")
            st.markdown(f"- **Number check:** {check}\n- **Model:** {run['model']}, {run['steps']} round(s)\n"
                        f"- **Cost:** ${run['cost_usd']:.5f} ({run['tokens']['input']:,} tokens in, {run['tokens']['output']:,} out)\n"
                        f"- **Time:** {run['latency_ms'] / 1000:.1f} s")


def render(st, replays_path: Path, T) -> None:
    """T: the project's agent_tools module (SYSTEM, TOOLS, MODEL, PRICES)."""
    rp = A.load_replays(replays_path)
    runs, s = rp["runs"], rp["summary"]
    mode = st.radio("Mode", ["Replay: recorded answers (free)", "Live: use your own OpenAI key"], horizontal=True, key="chat_mode")
    if mode.startswith("Replay"):
        st.caption(f"Answers recorded from the real agent ({rp['model']}) on the public API, {rp['recorded_utc']} UTC: "
                   f"{s['grounded']} of {s['questions']} pass the number check; about ${s['cost_per_1000_usd']:.2f} per 1,000 questions; "
                   f"p95 {s['latency_ms_p95'] / 1000:.1f} s. No model runs here.")
        pick = st.selectbox("Pick a recorded question", [r["question"] for r in runs], index=None,
                            placeholder="Choose a question the agent answered", key="replay_pick")
        typed = st.chat_input("Or type a question; the closest recorded one is shown", key="replay_input")
        if typed:
            best, score = A.closest(typed, runs)
            if score < MATCH_FLOOR:
                with st.chat_message("user"):
                    st.markdown(typed)
                st.info("No recorded answer is close to that question. Pick one above, or switch to Live and use your own OpenAI key.")
            else:
                _show(st, best, f"Closest recorded question (match {score:.2f}): \"{best['question']}\"")
        elif pick:
            _show(st, next(r for r in runs if r["question"] == pick))
        return

    st.markdown(f"Ask anything in scope; the agent calls the live public API and answers with **{T.MODEL}** "
                f"(about ${s['cost_per_1000_usd'] / 1000:.4f} a question on your account). Up to {LIVE_LIMIT} questions per session.")
    st.caption("Your key stays in this browser session only: it is used to call OpenAI from this app's server and is never stored, "
               "logged or shared. Closing the tab clears it. Use a key with a spending limit.")
    key = st.text_input("Your OpenAI API key", type="password", key="byo_key", placeholder="sk-...")
    history = st.session_state.setdefault("live_history", [])
    q = st.chat_input("Ask the agent" if key else "Enter your key above to ask", key="live_input", disabled=not key)
    if q and key:
        if len(history) >= LIVE_LIMIT:
            st.warning(f"This session has used its {LIVE_LIMIT} live questions. Reload the page to start again.")
        else:
            try:
                from openai import OpenAI
                with st.spinner("The agent is calling the tools..."):
                    history.append(A.run(q, OpenAI(api_key=key, timeout=30, max_retries=1), T.TOOLS, T.SYSTEM, T.MODEL, T.PRICES))
            except Exception as e:  # noqa: BLE001 - bad key, quota, network: say what happened, never echo the key
                st.error(f"The live call failed: {A.redact(str(e), key)[:300]}")
    for run in history:
        _show(st, run)
