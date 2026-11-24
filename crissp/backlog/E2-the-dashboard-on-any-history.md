# E2 · The dashboard on any history

Why: The Tests dashboard must open in every project, whatever its history holds. A single old commit with a file in
another encoding (saved on Windows, F-16) stops it before it serves anything, and a project cannot rewrite its history
to get past that: new commit ids, a broken release certificate, a force-push.

## E2-F1 · The dashboard reads and writes text the same way on every machine             [todo]
Why        The product owner sees what the runs proved and the backlog board in every project, on macOS, Linux and WSL,
           under any locale.

### E2-F1-01 · git's output read leniently, as UTF-8                                     [review] [S]
Why        F-16: git() in lib/measure.py decodes `git show <sha>:<file>` strictly in the locale's encoding; one byte
           that is not UTF-8 in any old backlog version ends the dashboard with a UnicodeDecodeError.
What       git() passes encoding="utf-8", errors="replace" to subprocess.run, so an undecodable byte becomes U+FFFD and
           the item's status is still read. Every other text read and write of the dashboard (measure.py's read_text and
           write_text, serve.py, sessionview.py, collect.py) names encoding="utf-8", so the locale never decides.
Done when  In a repository with a commit holding a cp1252 backlog file the dashboard builds and serves; the board shows
           that file's items with their statuses; under LC_ALL=en_US.ISO8859-1 it builds and serves as well; the
           reporting project's dashboard opens on the new version.
Tests      test_measure: a throwaway repository with one commit of a cp1252 backlog file, item_history reads it (fails
           without the fix, passes with it); the page built under a Latin-1 locale (fails without encoding="utf-8").
Depends    —

### E2-F1-02 · No text file that is not UTF-8 reaches a commit                           [todo] [S]
Why        Once in a commit, a file in another encoding stays in the history forever; a guard keeps new ones out on
           every machine.
What       A check step (in the template's suites.json, and crissp's own): every tracked text file of the commit under
           test (*.md, *.py, *.ts, *.tsx, *.json, *.yaml, *.yml, *.css, *.html, *.sh) is valid UTF-8, each file that is
           not named with its first bad byte. `crissp init` and `crissp repair` add an .editorconfig with charset =
           utf-8.
Done when  check fails with the file's name and position when a committed text file is not UTF-8, and passes once it is;
           a new project from crissp init has the .editorconfig; repair adds it to an existing one.
Tests      test_check: a throwaway repository with a cp1252 file committed (red, named) and fixed (green); test_init and
           test_repair for the .editorconfig.
Depends    —
