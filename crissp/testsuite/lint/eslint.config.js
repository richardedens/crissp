// ESLint for this repository's plain JavaScript (lint.sh): the shared look, the Tests dashboard and the UX suite's page.
// Browser scripts (no modules, no build), each wrapped in its own function; what they share goes through window:
// window.Look (crissp/look/look.js).
import js from "@eslint/js";
import globals from "globals";

export default [
  js.configs.recommended,
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: { ...globals.browser, Look: "readonly" },
    },
    linterOptions: { reportUnusedDisableDirectives: "error" },
  },
];
