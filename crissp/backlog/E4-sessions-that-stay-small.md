# E4 · Sessions that stay small

Why: The sessions report showed that 42% of requests started with more than 300k tokens of history and used 37% of all
tokens (F-18): every step resends the whole conversation, so a long session gets more expensive with every step. The
fixed context is small; keeping sessions short saves the most. The product owner: build it in.

## E4-F1 · The habits in the agreement, the history in sight                             [todo]
Why        Every Claude session in a crissp project knows how to keep itself small, and the product owner sees live when
           a session's history passes 300k tokens, with what to do.

### E4-F1-01 · The agreement says how a session stays small                              [review] [S]
Why        Nothing told Claude or the product owner how to keep a session small; the habits lived in one session's
           advice.
What       CRISSP.md gets a section "Sessions that stay small" and the template's crissp/CLAUDE.md (and this
           repository's) the same rules: a fresh session per item (/clear; brief, backlog and git bring back what is
           needed), /compact mid-task, browser checks and screenshots in a subagent that reports, checks through run and
           status with only the failures, searches in an Explore agent, narrow questions naming the file, agents briefed
           on separate parts, the lighter model for routine work.
Done when  The framework, the template and this repository's agreement name these rules; a new project from crissp init
           has them.
Tests      test_template: the framework and the template's agreement name /clear, /compact, the subagent for browser
           checks and run/status.
Depends    —

### E4-F1-02 · The Activity page shows each session's history and when to start fresh    [review] [S]
Why        The sessions report says afterwards that a request started on a long history; while it happens nobody sees
           it.
What       activity.py gives each session the history its last request carried (input + cache read + cache write,
           measured as the sessions report does, measure.history) and whether it is past 300k (measure.LONG). The page
           shows the size on each session and, past the line, a mark: "long history: /clear between items, /compact in
           the middle of one".
Done when  A session whose last request carried more than 300k tokens shows its size and the mark with the advice; a
           short one shows its size only.
Tests      test_activity: stand-in transcripts with a short and a long last request: the history and the long flag.
Depends    —
