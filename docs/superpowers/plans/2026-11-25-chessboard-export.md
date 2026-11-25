# Chessboard Export Implementation Plan

The approved v5 sample defines the layout: colored half-day spans, frozen room labels, Excel notes, and A4 landscape sheets in the order Шахматка, Легенда, Список броней.

- Exercise the new export endpoint with a filtered month and all three existing visibility levels. Use the board projection and derive one list row per visible booking. Verify that excluded data is absent from notes as well as cells.
- Render the workbook in exchange. Exercise date boundaries, concurrent spans in one room, and notes preserved by the local Gotenberg conversion.
- Connect the controls to the displayed month and filters. Print from the generated PDF, using the existing authenticated-download guard and invalidating open previews on session changes.
- Regenerate the API contract, update the printing handbook, run tests, and open a PR. Production deployment is out of scope.
