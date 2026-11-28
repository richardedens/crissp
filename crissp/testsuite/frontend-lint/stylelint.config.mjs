// crissp: the frontend style lint (stylelint standard), run by lib/frontend_lint.py with crissp's own tools.
// No ignoreFiles: stylelint reads them from this file's folder (crissp's cache), so they never matched a project's
// build output. lib/frontend_lint.py names the files instead: the project's own, never a build folder (F-150).
export default {
  extends: ["stylelint-config-standard"],
};
