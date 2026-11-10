# PR 12189 — duplicating a list item advances its marker

Ctrl/Cmd+D or alt-drag on a text (or a shape/arrow/sticky-note label) that starts with
`1.`, `a)`, `(iv)`… now bumps the marker on the copy. The video shows the parser, the two
places that call it (the action and the alt-drag pointer path), how the bump is kept as its
own undo step, then the sticky-note case running in the app.

Alt-drag can't be filmed — the capture tool has no modifier-drag beat — so that half of the
feature is shown as code and tests only, and called out as such.

```yaml
title: Duplicating a list item advances its marker
app: http://localhost:3001
start: /
settle_ms: 800

layers:
  - {name: List markers (new), paths: ["packages/element/src/listMarker.ts"]}
  - {name: Duplicate path, paths: ["packages/excalidraw/components/App.duplicate.ts", "packages/excalidraw/actions/*", "packages/excalidraw/components/App.tsx"]}
  - {name: Text editing, paths: ["packages/excalidraw/components/App.text.ts", "packages/excalidraw/wysiwyg/*"]}
  - {name: Types and exports, paths: ["packages/excalidraw/types.ts", "packages/element/src/index.ts"]}
  - {name: Tests, paths: ["packages/element/tests/*"]}

review_points:
  - Letters cap at `i`, so duplicating `g.` and `h.` together gives `i.` and `h.` — one item silently keeps its marker, with nothing on screen saying why.
  - Undo ordering rests on `setState({}, cb)` running after React commits, nested twice on the alt-drag path; there is no explicit queue.
  - The `getPointerCount() > 0` guard in `editListItemText` has no test; only the pointercancel path is covered.
  - Every duplicate of a list item now adds an extra history entry — check host integrations that count undo steps.

scenes:
  - id: shape
    beats:
      - id: overview
        do: overview
        say: >-
          Duplicating a list item now advances its marker. A new module in the element package
          parses and renumbers markers, the editor's duplicate path calls it, the text editor
          gains a way to pre-select a range, and one test file grows by over three hundred lines.

  - id: parsing
    beats:
      - id: regexes
        do: code
        file: packages/element/src/listMarker.ts
        lines: [21, 40]
        say: >-
          Two regular expressions decide what counts as a marker. One takes a number or letters,
          in brackets, in parentheses, or followed by a dot or a bracket, and only when whitespace
          or the end of the text follows — so one point five, and e g, are not markers. The other
          treats a bare number as an item. Numbers stop at forty-two, roman numerals at ninety-nine.

      - id: bail-out
        do: code
        file: packages/element/src/listMarker.ts
        lines: [258, 281]
        say: >-
          This is the careful part. Every duplicated element has to be a list item — a text, or a
          shape whose label is one. The moment one isn't, the function returns an empty list and
          nothing is renumbered, so a list item copied together with a rectangle comes out verbatim.

  - id: wiring
    beats:
      - id: after-commit
        do: code
        file: packages/excalidraw/components/App.duplicate.ts
        hunk: 2
        lines: [83, 94]
        say: >-
          The renumbering runs once the duplication is committed, from a setState callback, and
          schedules its own history capture. That makes the marker a separate undo step: undo puts
          the marker back before it removes the copy. You'll see that in a moment.

      - id: alt-drag
        do: code
        file: packages/excalidraw/components/App.duplicate.ts
        hunk: 2
        lines: [130, 150]
        say: >-
          Alt-dragging is handled apart. The marker already advanced when the drag began, so on drop
          it is set back, the drag commits as it was, then the marker is applied again as its own
          step. If exactly one item has text after its marker, the editor opens with that text
          selected, ready to be typed over.

  - id: tests
    beats:
      - id: test-list
        do: tests
        say: >-
          The tests are mostly a table of inputs and expected results: thirty-odd marker shapes, the
          ones deliberately left alone, labels on shapes, undo and redo, and a case where three
          markers continue from the highest of them. Alt-drag is covered here, not in this video —
          the capture tool can't drag with a modifier held.

  - id: live
    beats:
      - id: pick-sticky
        do: click
        target: {role: button, name: Sticky note}
        hold: 1.5
        say: Now the running app, from this branch.

      - id: write-item
        do: type
        target: {css: "canvas.interactive", at: [0.45, 0.42]}
        text: "9. buy milk"
        typing: true
        say: A sticky note whose label starts with a marker — nine, dot, buy milk.

      - id: commit
        do: press
        key: Escape
        hold: 1.5
        crop: [515, 260, 720]

      - id: duplicate
        do: press
        key: Meta+d
        crop: [515, 260, 720]
        caption: "9. buy milk  →  10. buy milk"
        say: >-
          Command-D duplicates it, and the copy's marker has moved on by itself: nine became ten.
          The original is behind it, untouched.

      - id: undo-marker
        do: press
        key: Meta+z
        crop: [515, 260, 720]
        caption: "undo, step 1 of 2: the marker goes back"
        say: The first undo only puts the marker back. The copy is still there, reading nine again.

      - id: undo-copy
        do: press
        key: Meta+z
        crop: [515, 260, 720]
        caption: "undo, step 2 of 2: the copy is gone"
        say: The second undo removes the copy itself.
```
