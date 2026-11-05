# {{PRODUCT}} — for agents working in this repository

The agreement is **crissp/CLAUDE.md**: read it first, it applies to every agent. This file only adds what is specific to
working as an agent next to the main session.

- You work in your own git worktree, on one part. Run that part's tests before you report.
  <!-- CRISSP: the test command of each part. -->
- Every fix starts with a test that fails without it. Commit per finding or item (`F-xx: …`) with what was wrong,
  how it was fixed and the proof.
- Never edit `crissp/backlog/`, the release notes or the version: the main session keeps those, after review.
- Never push, deploy, or touch production, secrets or `.env`. Never print a secret.
- Report what was wrong, how you fixed it and how it is proven — plus anything you noticed that belongs in
  `crissp/backlog/FINDINGS.md`.
