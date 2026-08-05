"""scaffold -- the three-statement model Edgardly builds out of a filer's XBRL.

Two halves, deliberately separate:

  three_statement.py  decides what the model contains: which rows, on which
                      statement, in which order, tied to which periods, with
                      which provenance, and which arithmetic connects them. It
                      knows finance and knows nothing about Excel.

  excel.py            turns that into a workbook. It knows openpyxl and knows
                      nothing about finance: every formula it writes comes from
                      the expression the model spec handed it.

The split is what lets Phases 3 and 4 reuse the writer for a comps sheet and a
DCF without either one inheriting a three-statement model's assumptions.
"""
