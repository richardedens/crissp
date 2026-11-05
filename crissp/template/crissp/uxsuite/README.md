# The UX suite of {{PRODUCT}}

Virtual people walk the running product, debate it, and a moderator advises per walk; on request a designer makes a
proposal, and an approved one becomes a PBI. The engine is the C.R.I.S.S.P. framework's (`crissp/uxsuite/*.py`, `web/`,
`crissp/ux.sh`); this folder holds what is {{PRODUCT}}'s own.

To fill in when CRISSPifying (the `CRISSP:` hints in `team.json`):

1. `team.json`: what {{PRODUCT}} is, who uses it, the language of its texts, and the URL it runs on locally. Change the
   five personas into the product's own people; keep one moderator.
2. `walks/`: one file per path a person takes through the product (`goto`, `click`, `fill`, `press`, `wait`, `shot`).
   `first-visit.json` is the first.
3. `PRINCIPLES.md`: the design principles, in the product owner's words.

Then:

```bash
crissp/ux.sh --list                    # check the configuration
crissp/ux.sh --shoot first-visit       # the screenshots (the product must be running)
crissp/ux.sh --round first-visit       # the first round
crissp/ux.sh                           # the suite, next to the Tests dashboard
```

What the suite makes goes to `results/` (git-ignored by `.gitignore` here): screenshots, rounds, designs, the queue and
the verdicts. No real customer data goes into a walk.
