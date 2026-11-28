// crissp: the frontend lint (ESLint 9, flat config), run by lib/frontend_lint.py with crissp's own tools.
import js from "@eslint/js";
import { defineConfig } from "eslint/config";
import jsxA11y from "eslint-plugin-jsx-a11y";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

// No ignores: lib/frontend_lint.py names the files, the project's own (git lists them), never a build folder (F-150).
export default defineConfig([
  js.configs.recommended,
  tseslint.configs.recommended,
  reactHooks.configs.flat.recommended,
  jsxA11y.flatConfigs.recommended,
  {
    files: ["**/*.{js,jsx,mjs,ts,tsx}"],
    languageOptions: { globals: globals.browser, parserOptions: { ecmaFeatures: { jsx: true } } },
    plugins: { react },
    settings: { react: { version: "detect" } },
    rules: { "react/no-danger": "error" },
  },
]);
