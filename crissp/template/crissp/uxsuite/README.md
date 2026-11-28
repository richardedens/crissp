# The UX suite of {{PRODUCT}}

Virtual people walk the running product, debate it, and a moderator advises per walk; on request a designer makes a
proposal, and an approved one becomes a PBI. The engine is the C.R.I.S.S.P. framework's (`crissp/uxsuite/*.py`, `web/`,
`crissp/ux.sh`); this folder holds what is {{PRODUCT}}'s own.

To fill in when CRISSPifying (the `CRISSP:` hints in `team.json`):

1. `team.json`: what {{PRODUCT}} is, who uses it, the language of its texts, and the URL it runs on locally (the
   Compose stack, `http://127.0.0.1:8080` by default; not a dev server, not a prototype). Change the
   five personas into the product's own people; keep one moderator.
2. `walks/`: one file per path a person takes through the product (`goto`, `click`, `fill`, `press`, `wait`, `shot`).
   `first-visit.json` is the first.
3. `PRINCIPLES.md`: the design principles, in the product owner's words. A line `Measured by the browser: <checks>.`
   under a principle has the browser check that part itself at every shoot.
4. Optional: let the E2E tests list the screenshots they take in `results/test-shots/screens.json`
   (`[{"path", "file", "title", "device", "test"}]`, each picture beside it); the map adds them as screens.

Then:

```bash
crissp/ux.sh --list                    # check the configuration
crissp/ux.sh --map                     # every screen: a read-only crawl, your E2E tests' screenshots, the walks
crissp/ux.sh --shoot first-visit       # the screenshots (the product must be running)
crissp/ux.sh --round first-visit       # the first round
crissp/ux.sh --discover                # can every persona do their jobs on the mapped screens? what is missing?
crissp/ux.sh                           # the suite, next to the Tests dashboard
```

In the suite, the **Review** tab goes through the screens that wait for the product owner, one at a time, with the
keyboard (`1 2 3` decide, `← →` screens, `↑ ↓` items, `s` decides for the whole screen, area or rule).

What the suite makes goes to `results/` (git-ignored by `.gitignore` here): screenshots, rounds, designs, the queue and
the verdicts. No real customer data goes into a walk.
