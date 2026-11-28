// crissp: the frontend style lint, run by lib/frontend_lint.py with crissp's own tools. The same rules as crissp's own
// CSS (testsuite/lint/stylelint.config.mjs, F-96): the recommended ones, likely mistakes (unknown properties and units,
// invalid colours, deprecated values, duplicates); the layout stays as written (F-151).
// No ignoreFiles: stylelint reads them from this file's folder (crissp's cache), so they never matched a project's
// build output. lib/frontend_lint.py names the files instead: the project's own, never a build folder (F-150).
export default {
  extends: ["stylelint-config-recommended"],
  rules: {
    // sheets are often ordered by component, not by specificity: a later, weaker selector styles another element,
    // and reordering them safely needs a look at every screen
    "no-descending-specificity": null,
  },
};
