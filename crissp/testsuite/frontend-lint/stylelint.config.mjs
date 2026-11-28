// crissp: the frontend style lint (stylelint standard), run by lib/frontend_lint.py with crissp's own tools.
export default {
  extends: ["stylelint-config-standard"],
  ignoreFiles: ["dist/**", "build/**", "coverage/**"],
};
