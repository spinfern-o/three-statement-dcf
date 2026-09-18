"""Phase 14, items 138-144: the four exports, and what they must agree with.

21.8 is the requirement everything else here is arranged around: "Exported
values must equal website values at the same model version and display
precision." Four formats built independently would satisfy it only by
coincidence, and a coincidence that held on the fixture would stop holding on
the first filing nobody tested.

So the export is a *gather* step and four *renderers*.
[`gather.py`](gather.py) calls the same view functions the screens call and
produces one `ExportModel`; JSON, CSV, XLSX and PDF each render that object and
never reach past it. 21.8 then holds by construction, and the tests assert the
construction rather than sampling the values.
"""
