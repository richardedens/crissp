# E7 · A UX suite that discovers, with your own team and rules

Why: The product owner's verdict on the UX suite (2026-11-28): it is oddly designed, does not help with discovery, and
the personas and rules cannot be changed. The redesign: Map, look, decide, design, build, accept around one screen list,
with personas and rules as files the project owns and edits in the page.

## E7-F1 · Personas the project edits                                                    [todo]
Why        Who looks at the product is the product owner's choice: personas must be easy to add, change and switch off,
           and carry the jobs they come to do.

### E7-F1-01 · Personas as files, and a Team tab to edit them                            [review] [M]
Why        team.json's persona array can only be edited by hand, in JSON.
What       crissp/uxsuite/personas/<key>.md per persona (frontmatter: name, role, device, moderator, on; the body is the
           brief, and a Jobs list). The page's Team tab lists them, and adds, edits, switches off and removes one
           through the suite's own POST (127.0.0.1 only, same-origin). team.json's personas still load (older projects)
           until the project has personas/.
Done when  A persona added or changed in the Team tab is a file in personas/, the next round reads it, a switched-off
           persona takes no part, and a wrong file is a clear error.
Tests      uxsuite tests at 100%: parse and write a persona file, the POSTs (add, edit, off, remove, refused input),
           team.json fallback, a round's prompt with only the personas that are on.
Depends    —

## E7-F2 · Rules the project adds                                                        [todo]
Why        The rules the team judges by are the product's own: added, weighed and switched off by the product owner,
           some measured by the browser itself.

### E7-F2-01 · Rules as files, and a Rules tab to edit them                              [review] [M]
Why        PRINCIPLES.md is one prose file: a rule cannot be added, weighed or switched off, and advice never says which
           rule it is about.
What       crissp/uxsuite/rules/<id>.md per rule (frontmatter: title, severity must, should or could, on; the body says
           what it asks). The Rules tab lists, adds, edits and switches them off. Rounds and designs read the rules that
           are on (PRINCIPLES.md still read when there is no rules/), and the advice names the rule it is about.
Done when  A rule added in the Rules tab is a file in rules/, the next round and design judge by it, a switched-off rule
           is left out.
Tests      uxsuite tests at 100%: parse and write a rule file, the POSTs, the PRINCIPLES.md fallback, the prompts list
           only rules that are on.
Depends    —

### E7-F2-02 · Measured rules: what the browser checks at every shoot                    [todo] [M]
Why        Overflowing text, small tap targets, an action below the fold and low contrast cost tokens to find by reading
           screenshots, and are found unevenly.
What       A rule may be kind: measured with a check the shoot runs in the page (overflow, tap targets under 44x44,
           primary action below the fold at the device's size, a dialog that is not opaque, focus not visible); its
           findings are listed per shot, with where on the screen, before any round.
Done when  A shoot lists the measured findings per shot and rule, with no Claude run.
Tests      uxsuite tests at 100%, the page checks run against fixture pages in the pinned Playwright.
Depends    E7-F2-01

## E7-F3 · Discovery: find the screens, and what is missing                              [todo]
Why        The suite should not only judge the walks someone wrote: it finds the product's screens, shows the ones
           nothing reaches, and asks per persona whether their job can be done.

### E7-F3-01 · One screen list from a crawl and the project's own test screenshots       [review] [L]
Why        Only screens someone wrote a walk for are ever looked at.
What       crissp ux --map crawls the running product read-only (same-origin links, laptop and phone) and reads a
           screenshot manifest the project's E2E tests may write; screens.json lists every screen with its area, how it
           is reached and its shots; a screen that nothing reaches is a gap.
Done when  The UX page shows every screen with its status and the gaps.
Tests      uxsuite tests at 100%, the crawl against a fixture site in the pinned Playwright.
Depends    E7-F1-01

### E7-F3-02 · Jobs per persona and a discovery round: done, hard or impossible          [review] [L]
Why        Nothing asks whether a persona can actually do what they come for, so missing screens are never found.
What       A discovery round asks each persona, per job, whether and where it can be done and where they would give up;
           the job map shows done, hard and impossible with the screens involved; an impossible job becomes a need, and
           an approved need a design request (a brief) that enters at Design.
Done when  A round returns a job map, and a need approved in the page is a design request.
Tests      uxsuite tests at 100% with a stand-in Claude run.
Depends    E7-F1-01 E7-F3-01

## E7-F4 · Deciding one screen at a time                                                 [todo]
Why        The product owner decides fast and once: one screen with before and after, findings pinned on it, and a
           verdict on a rule that holds for every screen under it.

### E7-F4-01 · The review screen: status per screen, before and after, pinned findings   [todo] [L]
Why        The page lists walks with advice; there is no status per screen, no progress and no before and after in one
           view.
What       Per screen its status (seen, discussed, decided, designed, approved, built, accepted), a progress bar, before
           and after side by side, findings pinned to a region of the shot, advice must first, and the verdict bar
           always in one place (keys 1 2 3, arrows).
Done when  The product owner can go through every open screen with the keyboard only.
Tests      uxsuite tests at 100%, and the page walked by the suite itself.
Depends    E7-F3-01

### E7-F4-02 · Decide once on a rule; advice that keeps coming back becomes a rule       [todo] [M]
Why        Hundreds of pieces of advice each need their own verdict, and agreed advice is never turned into a rule.
What       A decision tree: rule, area, screen, advice; a verdict higher up holds below it unless changed; agreed advice
           seen on several screens is proposed as a rule, which the product owner approves into rules/.
Done when  A verdict on a rule covers its advice, and an approved proposal is a rule file.
Tests      uxsuite tests at 100%.
Depends    E7-F2-01 E7-F4-01

## E7-F5 · Accepting what was built                                                      [todo]
Why        An approved design is only done when the built screen matches it.

### E7-F5-01 · Built next to the approved design, accept or send back                    [todo] [M]
Why        After a build nobody compares the screen with the design that was approved.
What       After a build, the walk's new shots sit next to the approved design; accept marks the PBI ready for the
           product owner's review, not good (with a reason) sends it back with that reason.
Done when  A built screen can be accepted or sent back from the page, and the PBI shows it.
Tests      uxsuite tests at 100%.
Depends    E7-F4-01
