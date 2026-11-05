# Design principles

Every round of the UX team judges against these, every proposal is designed to them, and the moderator checks each
proposal against them (`proposal.json` → `principles` says, per principle, how the design meets it). They are about
**how** a feature is presented, never about **whether** it exists: nothing is cut to meet them; what is not needed now
moves one step further away (a fold, a tab, a "More"), it does not disappear. A product changes them here, in its own
words; the team reads this file at the start of every run.

## 1. Nothing important behind a scroll

What a person needs to do the task on a screen is visible without scrolling on a laptop (1440 × 900) and on a phone
(390 × 844), and the primary action is never below the fold. Long content (lists, logs, documentation) may scroll
inside its own area; the screen itself does not make the person search.

## 2. A screen gives time to understand

A screen has one purpose, one primary action, and as few elements as that purpose needs; secondary information is
folded or one click deeper. Density is earned only where a professional works in it every day, and even there the
first view is calm.

## 3. Three clicks

Within three clicks a person is where they need to be: from the start to the task, from a problem to its fix, from a
finding to the thing it is about. Search and links in context count; a hunt through menus does not.

## 4. Ask and explain only what is needed

A screen asks only what is needed from the person right now: no fields that can be derived, no settings before they
matter (sensible defaults, change later). It always says, in one sentence, what the person must decide and what happens
when they do.

## 5. Everything stays possible

The principles never remove a capability. Power features stay one step away (a fold, a tab, a shortcut), and an expert
still reaches everything quickly. The test: a new person is not burdened by it, an expert does not miss it.

## 6. No text overflows

Every text fits its place, in every language the product has and with real data (long names, large numbers): it wraps,
or it is shortened with an ellipsis and its full text on hover and for screen readers. Nothing runs out of its card,
button, chip, cell or panel, and nothing is cut off without a way to read it.

## 7. Dialogs are solid

A dialog (and a menu or panel that lies over content) has a solid, opaque surface, so what is behind it never shows
through its text; the content behind is dimmed by the backdrop, not by the dialog.

## 8. Accessible by default

Text contrast meets WCAG 2.2 AA in both themes, every control can be reached and used with the keyboard and has a
visible focus, tap targets on a phone are at least 44 × 44 points, and nothing is said by colour alone.
