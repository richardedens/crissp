# E1 · Parallel testing sized to the machine

Why: The testsuite should take full advantage of parallel testing: the tests divided amongst the processors and memory
the system actually has, and a /workers page that shows it while it runs.

## E1-F1 · Workers: a step's tests spread over the machine, and seen live                [todo]
Why        A run uses the CPUs and memory this machine (or CI runner) has, and the product owner sees on /workers which
           worker runs what, how far each step is, and why it got that many workers.

### E1-F1-01 · The machine's capacity and the worker count                               [review] [S]
Why        A fixed worker count is wrong for every machine but one: too many on a small CI runner, too few on a large
           laptop.
What       lib/workers.py (stdlib): the usable CPUs (process_cpu_count, a cgroup cpu.max), the memory there is and what
           is available (macOS sysctl hw.memsize and vm_stat; Linux /proc/meminfo; a cgroup memory.max). A step's
           workers = the smallest of: the CPUs less one, the available memory (three quarters of it) divided by the
           step's memory_mb (default 256), and the step's test files; at least 1. CRISSP_WORKERS overrides it. `python3
           lib/workers.py` and crissp check --plan say the count and why.
Done when  On a 16-CPU, 23 GB-free machine a step with 40 test files gets 15 workers; on a 2-CPU, 7 GB runner it gets 1;
           with 3 test files it gets 3; CRISSP_WORKERS=4 gives 4; the reason names what limited it.
Tests      test_workers: every source read from stand-in files and commands (no real machine), each limit winning once,
           the override, unreadable sources falling back.
Depends    —

### E1-F1-02 · A step's tests in parallel processes, coverage still whole                [doing] [M]
Why        The steps run their tests one at a time on one CPU.
What       suites.json: a step may say `parallel: true` (and `memory_mb`). Then `covered` runs pytest with pytest-xdist
           (pinned in requirements.txt) on the worker count of E1-F1-01, --dist loadfile (a test file stays on one
           worker), and coverage measures every worker (an rcfile with parallel and patch = subprocess, then coverage
           combine), so the gate sees the same numbers. This project's tools step and the template's backend step are
           parallel.
Done when  The tools step runs on several workers, its coverage is still 100% lines and branches and the gate passes; a
           step without parallel runs as before; a parallel step on 1 worker runs without xdist.
Tests      test_run (the command and the rcfile per step), test_project (parallel and memory_mb checked), the package
           test's full run with a parallel backend step.
Depends    E1-F1-01

### E1-F1-03 · Every test as it finishes, per worker                                     [todo] [S]
Why        Without a trace per test there is nothing to show live: which worker runs what, since when, and what failed.
What       A pytest plugin (loaded by `covered`) writes results/timing/<step>.jsonl: start (with the worker count and
           why), collected, every test as it finishes (outcome, seconds, worker), finish. Each xdist worker replaces
           results/timing/<step>.now.<worker>.json with the test it runs now. It only writes: it never changes an
           outcome, and a failed write is dropped.
Done when  A parallel run leaves one line per test with its worker, and the now files; a failing write never fails a
           test.
Tests      test_timing_plugin: a real pytest run on a tiny project, with and without xdist; a folder that cannot be
           written.
Depends    E1-F1-02

### E1-F1-04 · The /workers page                                                         [todo] [M]
Why        The product owner wants to see the tests divided amongst the processors and memory, while it runs.
What       On the dashboard server: /workers (and /dashboard/workers.json). The machine (CPUs, memory, available) and
           per running or recent step its worker count and why, progress (done of collected, an estimate of what is
           left), outcomes, and one lane per worker: what it runs now and since when (quiet when long), what it
           finished, how busy it was, what failed. Live (refreshes every two seconds), in the shared look, linked from
           the dashboard.
Done when  During crissp check-all the page shows the tools step's workers filling in; after it, the last run's lanes;
           with no run, the machine and how many workers a step would get.
Tests      test_workers (the lanes from stand-in timing files: running, finished, stopped, quiet), test_serve (/workers
           and /dashboard/workers.json served, nothing else).
Depends    E1-F1-03
