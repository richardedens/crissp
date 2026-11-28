// stylelint for this repository's own CSS (lint.sh, F-96): the shared look, the Tests dashboard and its session pages,
// the UX suite's page and the website. The recommended rules: likely mistakes (unknown properties and units, invalid
// colours, deprecated values, duplicates); the layout stays as written, as ESLint leaves the JavaScript's.
export default {
  extends: ["stylelint-config-recommended"],
  rules: {
    // the sheets are ordered by component, not by specificity: a later, weaker selector styles another element
    "no-descending-specificity": null,
  },
};
