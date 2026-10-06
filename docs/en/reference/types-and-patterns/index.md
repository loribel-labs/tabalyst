---
title: Types and patterns
description: Understand the native, inferred and semantic types and the value patterns shared by Tabalyst Scan and Report.
---

**Tabalyst Scan** reads source values, infers a technical type for each field
and runs detectors for possible meanings. **Tabalyst Report** presents the
same results as an inferred type, an optional semantic type and a table of
detected formats. These are separate answers to three questions:

| Question | Result | Example |
| --- | --- | --- |
| How was the value stored? | Native source type | `"12.5"` is a CSV string; a JSON `12.5` is a native number. |
| What kind of values does the field contain? | Inferred technical type | Strings such as `"12.5"` can give a field inferred type `number`. |
| What recognizable meaning or form do the values have? | Semantic type and detector evidence | A `text` field of email addresses can have semantic type `email`. |

Read [Types](types.md) for every native, inferred and semantic type and the
selection rules. Read [Recognized patterns](patterns.md) for every built-in
detector, configured patterns, format labels and coverage states. The
[report guide](../../report/read-report.md) explains the HTML tables; the
[Scan format](../../scan/format.md) and
[Report JSON profile](../../report/json-profile.md) give the machine-readable
fields.
