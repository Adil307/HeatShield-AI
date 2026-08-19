# Day 10.7.2 — Clean UTF-8 Recovery

The Day 10.7.1 cleanup used Windows PowerShell `Get-Content` / `Set-Content`
against an originally UTF-8-without-BOM HTML file. In Windows PowerShell 5.1
this can misread Unicode characters before writing the file back, producing
mojibake such as corrupted inequality or ellipsis characters and adding a BOM.

Day 10.7.2 fixes the problem by restoring a clean Day 10.7 HTML file byte-for-byte
from the verified source and applying the tiny UI cleanup before packaging.

It also updates old tests to validate stable semantics rather than exact legacy
Unicode wording.

No FortyGuard evidence, planning score, recommendation logic, satellite map
logic, assistant behavior, or backend data is changed.
