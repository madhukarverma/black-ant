# Instructions for assistants working in this repo

1. Read `CONTEXT.md` first. It replaces chat history: rules, deliverables, scoring, current state, the ordered
   feature checklist, branches, visual renditions and the prompt log.
2. Work on the feature's branch (CONTEXT.md §7). Never commit to `main`.
3. Numbers come from `config.yaml` and `results/`, never typed in by hand.
4. Before finishing: run `uv run pytest -m "not slow"`, then update CONTEXT.md — §5 state, §6 checkbox,
   §8 renditions if visual, and one row in §10 prompt log.
