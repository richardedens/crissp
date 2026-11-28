# E6 · Security and quality like Sonar

Why: crissp tests and lints, and audits dependencies when a project names them, but a project brought in with crissp
init gets no security scan at all, and nothing looks for secrets, unsafe code, duplication or complexity. SonarQube-
style coverage, done the crissp way: pinned tools crissp brings itself, steps in suites.json, results on the dashboard,
nothing written into the project's files.

## E6-F1 · Scans that exist, switched on and pinned                                      [todo]
Why        The audit (pip-audit, npm audit, trivy) exists but the template has no audit step, crissp's own audit skips
           its chart, and trivy is whatever a machine has on its PATH.

### E6-F1-01 · Pinned scanners: trivy and gitleaks fetched once, checksum-checked        [review] [S]
Why        trivy runs as whatever version a machine has (a compromised or old trivy decides what is green).
What       lib/tools.py: one pinned version per tool and per system with its SHA-256, downloaded once from the release
           into the crissp cache, refused when the checksum differs; audit.py runs that trivy.
Done when  A wrong checksum is refused and nothing is kept; a cached tool is not fetched again; an unknown system says
           so; audit runs the cached trivy.
Tests      tests/test_tools.py, tests/test_audit.py
Depends    —

### E6-F1-02 · The audit in every project, and on crissp's own chart                     [review] [S]
Why        A project brought in with crissp init has no audit step; crissp's own audit never runs trivy config on its
           chart and Terraform.
What       The template gets a full-run audit step and an audit section naming the default places (D-02), with missing:
           skip so a place a project does not have yet is said, not red; crissp's suites.json audits
           crissp/deploy/helm/app and crissp/deploy/terraform.
Done when  A fresh project's full run runs the audit; a missing place is listed as not there; crissp's own audit lists
           its chart's misconfigurations.
Tests      tests/test_audit.py, tests/test_template.py, package_tests/test_package.py
Depends    —

## E6-F2 · Secrets never in git, tested                                                  [todo]
Why        'Secrets never in git' is a rule without a test: nothing scans the history.

### E6-F2-01 · A secrets step: gitleaks over the history                                 [review] [M]
Why        Nothing proves no secret reached git.
What       audit.py secrets: the pinned gitleaks over the git history (the files when there is no git), redacted, never
           printing a value; a project's own gitleaks configuration (.gitleaks.toml, .gitleaksignore, gitleaks:allow) is
           used, never replaced; a step in crissp and in the template.
Done when  A planted key turns the step red without its value in the log or the results; a fingerprint in
           .gitleaksignore is not reported; a project without git is scanned as files.
Tests      tests/test_audit.py, tests/test_template.py
Depends    E6-F1-01

## E6-F3 · SAST: unsafe code found before review                                         [todo]
Why        Nothing looks for eval, shell injection, unsafe deserialisation, disabled TLS checks or HTML injection in a
           project's code or crissp's own.

### E6-F3-01 · SAST: ruff's Bandit rules and Semgrep with crissp's rules                 [review] [M]
Why        Unsafe code (eval, shell=True, pickle, yaml.load, verify=False, innerHTML, child_process.exec) passes every
           step.
What       The template's backend-lint adds ruff's S rules on top of the project's own ruff configuration (asserts
           allowed in tests); audit.py sast runs the pinned Semgrep with crissp's own rules (crissp/testsuite/sast,
           offline, metrics off) plus the rules folders the project names, on the places suites.json names; the rules
           have their own tests (semgrep --test).
Done when  Every rule has a test that matches and one that must not; an ERROR blocks, a WARNING is listed; crissp's own
           code passes.
Tests      tests/test_audit.py, crissp/testsuite/sast/tests (semgrep --test)
Depends    —

## E6-F4 · Sonar-style metrics and a quality gate                                        [review]
Why        Complexity and duplication are not measured; a quality gate that only lets them get better, like coverage,
           keeps old code from blocking.

### E6-F4-01 · Complexity and duplication, held by a ratchet                             [review] [M]
Why        nothing measured how complex or copied the code is (F-150)
What       lib/quality.py: the pinned lizard's cyclomatic complexity per function, crissp's own copy count across
           languages, a baseline that only goes down; a quality step in crissp and the template, and a Code quality tile
Done when  a new complex function, a more complex one or more duplicated lines fail the step; a green run lowers the
           baseline
Tests      test_quality, test_dashboard_page, test_collect, test_template
Depends    —

## E6-F5 · DAST: the running app scanned                                                 [review]
Why        A passive OWASP ZAP baseline against the app docker-compose starts on localhost finds missing headers, cookie
           flags and leaks the code scans cannot see.

### E6-F5-01 · The passive ZAP baseline against the running app                          [review] [M]
Why        nothing scanned the running app (F-151)
What       audit dast: zap-baseline.py in the pinned ZAP image against audit.dast.targets, compose started and stopped
           when the app is down, the project's rules file; HIGH and FAIL rules block
Done when  a high risk or a FAIL rule blocks the full run; an app that does not answer is a problem
Tests      test_dast, test_template
Depends    —

## E6-F6 · SBOM and licences per release                                                 [review]
Why        A CycloneDX SBOM with every release and a licence check of the dependencies.

### E6-F6-01 · Licences checked and an SBOM per run                                      [review] [M]
Why        no licence check, no SBOM (F-152)
What       audit licenses: npm lock files and resolved pip requirements, licences from the lock file or PyPI, a policy
           (forbidden and copyleft block, allow and block per project), a CycloneDX 1.6 SBOM
Done when  a GPL or AGPL dependency the product ships blocks; results/sbom.cdx.json lists every component
Tests      test_licenses, test_template
Depends    —
