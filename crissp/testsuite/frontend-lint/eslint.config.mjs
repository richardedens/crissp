// crissp: the frontend lint (ESLint 9, flat config), run by lib/frontend_lint.py with crissp's own tools.
import js from "@eslint/js";
import { defineConfig } from "eslint/config";
import jsxA11y from "eslint-plugin-jsx-a11y";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

// No ignores: lib/frontend_lint.py names the files, the project's own (git lists them), never a build folder (F-150).
// React's hooks: their two rules of correctness (F-151). The React Compiler's rules (set-state-in-effect, refs,
// immutability, purity, …: the plugin's whole recommended set) only for a project that uses the compiler and says so
// (frontend_lint --react-compiler, which sets CRISSP_REACT_COMPILER).
const hooks =
  process.env.CRISSP_REACT_COMPILER === "1"
    ? reactHooks.configs.flat.recommended
    : {
        plugins: { "react-hooks": reactHooks },
        rules: { "react-hooks/rules-of-hooks": "error", "react-hooks/exhaustive-deps": "error" },
      };

export default defineConfig([
  js.configs.recommended,
  tseslint.configs.recommended,
  hooks,
  jsxA11y.flatConfigs.recommended,
  {
    files: ["**/*.{js,jsx,mjs,ts,tsx}"],
    languageOptions: { globals: globals.browser, parserOptions: { ecmaFeatures: { jsx: true } } },
    plugins: { react },
    settings: { react: { version: "detect" } },
    rules: { "react/no-danger": "error" },
  },
]);
