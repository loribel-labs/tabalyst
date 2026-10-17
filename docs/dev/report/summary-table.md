# Report summary table: classification, findings, views and name engine

Technical contract of the Report overview work (lots R0 to R11). It is the
reference the next lots implement and the contract tests in
`tests/scan/test_contract_summary.py` check. Maintainer documentation, never
published. Written in lot R0; gate 0 accepted by the maintainer on 2026-10-16, decisions 1 to 15 included.

Sources: the requirements specification `Cahier des charges Tableau Report`
(requirement ids `RF-*`, `RT-*`, `CA-*`, `D-*`, `O-*`) and the plan
`2026-10-16-report-overview-plan.md`, both in the private `tabalyst-gb`
repository. Neighbouring contracts: `docs/dev/scan/design.md` (12.4
interpretations, 18.13 observations, 18.14 the report reads the findings, 19
Scan and Report as one family, 20 second pass). Decisions are recorded in the
ADRs listed in section 13.

## 1. Goal and scope

The Columns table of the Report becomes eight columns:

```text
Column | Type family | Type | Overview | Missing | Errors | Issues | Details
```

Three pieces carry it, each at the lowest layer that can compute it:

| Piece | Where it lives | Persisted |
| --- | --- | --- |
| Classification (family, type, evidence) | `scanner/classify/`, first pass of the Scan, refined by the Report with the second pass | Yes: `fields[].classification` (Scan), `columns[].classification` (Report) |
| Findings (Missing, Errors, Issues) | `report_findings*.py`, from `observations`, detectors and `analyses` | No: views computed at render time |
| Overview, Details, previews and every label | `report_overview.py`, `report_details.py`, `report_labels.py` | No: computed at render time |

The Scan carries codes, the Report carries the words (design 18.14). The HTML
never recomputes a rule and never reads the source (RT-02, RT-05, CA-20).

Out of scope for lots R0 to R11: every type or finding that needs a rule with
no algorithm and no threshold (backlog L1 and L2), a new analyzer, a new CLI
option, the other sections of the Report, an external service (RT-13).

## 2. Decisions

Decisions 1 to 11 were proposed in the plan and validated by the maintainer on
2026-10-16; they are fixed here. Decision 12 was taken by the maintainer during
lot R0. Decisions 13 to 15 were R0 proposals, confirmed at gate 0.

| # | Decision | Where |
| --- | --- | --- |
| 1 | The catalogue (families, types, name rules, finding codes) is a typed Python module, `scanner/classify/catalog.py`. No YAML, no JSON catalogue (RT-08, O-17). | 4, ADR catalogue |
| 2 | `Classification` has `family`, `type`, `basis`, `state`, `traits`, `evidence`, `alternatives`, `rule_version`. No score and no percentage of confidence (O-05, RF-30). | 3.1 |
| 3 | A specific, supported hint wins over a generic one. A persisting conflict gives the explicit fallback, never the first by accidental order (O-04, RF-29). | 3.5 |
| 4 | A credible identifier role needs an identifier name rule and compatible values. A nameless column stays outside ID. First position and strong uniqueness are traits (`first_column`, `observed_unique`), never proof (O-07, O-08, RF-29). | 3.7 |
| 5 | Unique ID is reserved for a field that is not under a JSON array. The scope (partial scan, excluded records) is published in the evidence (RF-07, O-19). | 3.8 |
| 6 | Evaluation states: `None detected`, `Not assessed`, `Partially assessed`, `Not applicable`, `Assessment failed`. The dash is no longer used in Errors and Issues (RF-23, O-12). | 6.4 |
| 7 | Interface: two visible labels then `+N more`, two examples in the preview. Errors red, Issues amber, information grey, contrasts checked (O-13, O-20). | 7.4 |
| 8 | `ColumnProfile.semantic_type` and `DatasetSummary.semantic_type_*` are replaced by `classification` and its counts. `inferred_type` stays. Breaking change accepted in beta, noted in the changelogs. | 9 |
| 9 | One revision bump per published version (rule P3, design section 20). Revision 4 of the Scan and of the Report is still in preparation (the last tag, `v0.6.2`, ships revision 3): the classification joins revision 4 and no revision 5 is created. Amended by the maintainer at the start of lot R1a; the gate 0 wording was "4 to 5". | 9 |
| 10 | No new CLI option and no new analyzer. The second pass is decided as today by `report_chain` (`auto`, `forced`, `off`) and only `scan --deep` runs it. | 8 |
| 11 | The identity of the classification rules is recorded in every classification and compared by `engine_warning`. | 10 |
| 12 | The four Text bounds are one setting, `scan.classification.very_short_max_length`, `short_max_length`, `medium_max_length`, `long_max_length`, with defaults 5 / 20 / 50 / 255 (maintainer, during R0). They replace the specification defaults 10 / 50 / 255 / 1,000 (D-07). | 3.6, 11 |
| 13 | Identifier types have `state = candidate`, never `established`: the role rests on a name and compatible values, not on the values alone. Unique ID adds a proven uniqueness trait. Errors never derive from a candidate (RF-13). | 3.2 |
| 14 | A name alone never creates a type or a state. In L0 a name rule can only reinforce a type the values already support, break a tie between supported types, or weaken one (`negative_match`). A conflict settled by a name has `state = candidate`; a weakened sole type is kept with a `contradicts` evidence (maintainer, R2). | 5.4 |
| 15 | Contract tests of a lot not delivered are skipped with the reason `Report overview lot Rn is not implemented yet`, through the marker `report_lot("Rn")` and `tests/scan/report_gate.py`. | 13 |

## 3. Classification

### 3.1 Model

```text
Classification
  family        str           code of the family (3.3)
  type          str           code of the type inside the family
  basis         declared | inferred | fallback
  state         established | candidate | undetermined
  traits        list[str]     secondary properties (3.4)
  evidence      list[Evidence]
  alternatives  list[Alternative]
  rule_version  int           identity of the rules that decided (section 10)
```

```text
Evidence      source: detector | technical_type | measure | name_rule | position
              id: str             detector id, measure name or rule id
              role: supports | contradicts | context
              scope: Scope        what the fact covers (3.9)
Alternative   family, type, reason: str   a candidate not retained, never a conclusion
```

Rules of the model:

- `basis`: `declared` is reserved for constraints a user declares (backlog L2)
  and is never produced in L0. `inferred`: decided by evidence. `fallback`:
  the technical type or an explicit fallback, because the evidence did not
  allow more.
- `state`: `established` when the values themselves support the type (a
  detector that reaches its minimum share with coverage, or the technical
  type); `candidate` when the type rests on a name hint plus compatible values
  (decision 13); `undetermined` for a fallback taken because of a conflict or
  of insufficient evidence.
- No `confidence`, no score, no percentage (RF-30, O-05). A future qualitative
  level must be a new decision.
- Pydantic model `Classification` in `scanner/classify/models.py` (its parts are
  named `ClassificationEvidence`, `ClassificationAlternative` and
  `ClassificationScope`, so the JSON Schema does not confuse them with the
  detector `Evidence` of the Scan; the specification names are `Evidence`,
  `Alternative` and `Scope`), a member of
  `FieldResult` (`scanner/models.py`). `extra="forbid"`, like the other Scan
  models. The Report copy under `columns[].classification` has the same shape.
- `family` and `type` are stable codes in lower snake case (`identifier`,
  `unique_id`); the words are in `report_labels.py` (Type family `Identifier`,
  Type `Unique ID`).
- The primary pair is one pair (RF-05, CA-24). Secondary properties live in
  `traits`; competing readings live in `alternatives`.

### 3.2 State by type

| Type | Usual state | Why |
| --- | --- | --- |
| Boolean, Integer, Number, Date, Datetime, Time, Enum, Constant | `established` | The technical type or the detector decides from the values. |
| Currency, Percentage, Quantity, Email, Phone, Postal code, URL, IP address, UUID | `established` | A detector reached its minimum share on its eligible values. |
| Text (five lengths) | `established`, except length `undetermined` (3.6) | The median is exact or unavailable. |
| ID, Unique ID | `candidate` | The role is a name plus compatible values (decisions 4 and 13). |
| Other / Mixed, Other / Empty | `established` | Direct reading of the technical type. |
| Other / Unknown | `undetermined` | Fallback of a conflict or of missing evidence. |

### 3.3 Catalogue of the L0 foundation

Only these types are active in L0 (strict foundation). Everything else in the
specification annex A is backlog and is not produced.

| Family | Types | Source of the decision |
| --- | --- | --- |
| Identifier | ID, Unique ID | name rule + values (3.7), cardinality (3.8) |
| Categorical | Enum, Boolean, Constant | `enumeration` and `boolean` detectors, cardinality |
| Numeric | Integer, Number, Currency, Percentage, Quantity | technical type, `currency`, `percentage`, `quantity` detectors |
| Temporal | Date, Datetime, Time | technical type `date`, `date` detector and its parts |
| Contact | Email, Phone | `email`, `phone` detectors |
| Geographic | Postal code | `postal_code` detector |
| Web / Network | URL, IP address, UUID | `url`, `ip_address`, `uuid` detectors |
| Text | Very short, Short, Medium, Long, Very long | `string_lengths` median (3.6) |
| Other | Mixed, Empty, Unknown | technical type `mixed`, `empty`, otherwise fallback |

The family `Web / Network` has the code `web_network`, label `Web / Network`.
Year, House number, Unit number, Status, Count, Person name and the other types
of annex A.3 to A.7 are the backlog L1a. Their codes are not reserved in the
catalogue: the catalogue lists active entries only, with a `status` field
(`active`, `recommended`) kept for the findings (6.2), because a catalogue entry
does not mean an active detector (D-10, CA-29).

Mapping rules (checked in R1b against the detector ids of
`docs/en/reference/types-and-patterns/patterns.md`):

- Boolean needs the `boolean` detector or a two-state technical `boolean`. Two
  categories never make a Boolean (`M/F` stays Enum, CA-10 of the plan).
- Currency needs the `currency` detector; a bare number is never Currency.
  Percentage needs the `percentage` detector, so `%` is present; a bare number
  is never Percentage.
- Number is the numeric fallback; Integer is the fallback of exact integers
  when no detector refines them. Quantity is the `quantity` detector
  (number plus unit-shaped suffix).
- Date, Datetime, Time: the technical type `date` plus the parts the Scan
  already carries; a column that mixes date and datetime forms keeps the
  dominant nature and lists the other as an alternative.
- Constant: one exact distinct analytical value among at least two present
  occurrences (the threshold of the `constant_column` observation). It is the
  type of a column nothing else types: a constant text is Constant, while a
  constant Email, Integer or Date keeps its type and takes the trait `constant`
  (R1b, maintainer's answer). A limited or estimated cardinality never proves a
  constant.
- Enum is the `enumeration` detector over a `text` technical type. A numeric,
  boolean or date technical type keeps its type and lists Enum in `alternatives`
  with the reason `numeric_type_kept` or `outranked_by_<type>` (R1b, maintainer's
  answer). There is no cardinality threshold of the Scan's own: the detector
  already has its configured `minimum_values` and `maximum_distinct`.
- Detector types win over Enum when the detector covers the field (an email
  column of few addresses stays Email). "Covers" means the detector is in
  `interpretations.candidates` (share of the eligible values at or above
  `detection.minimum_share`), not that it is the `primary` interpretation.
- A numeric technical type (`integer`, `number`) that a detector type also
  reads, as `postal_code` or `phone` over whole numbers of five or ten digits, is
  one more contender, not a loser: the result is the technical pair with
  `state = undetermined` and both in `alternatives` (R1b, maintainer's answer).
  Only the names (R2) can tell them apart.
- Date, Datetime, Time: a `date` technical type gives Date. Otherwise a credible
  `date` detector reads the kinds of `temporal` (`datetime_naive` and
  `datetime_aware` are both Datetime); the type with the most values is kept and
  the others are `alternatives` with the reason `minority_kind`. A tie leaves two
  contenders (a conflict, 3.5).

### 3.4 Traits

Traits are secondary, never shown as a type. L0 emits only:

| Trait | Emitted when |
| --- | --- |
| `single_pattern`, `multiple_patterns` | `derived.patterns` of the field is complete and lists one pattern with no value outside it, or several patterns (R1b: added by `with_pattern_traits` after the discovery, which runs after the fields) |
| `constant` | one distinct value, on a type other than Constant (R1b) |
| `high_cardinality` | not emitted (R3, maintainer's answer): "close to the present values" needs a percentage, and no threshold comes from the tracked limits. The entry stays in `TRAITS` for a later lot |
| `observed_unique` | exact analytical distinct count equals the present values, with at least two present values (R3: one value is not uniqueness) |
| `first_column` | first column of a table dataset: the path starts with `ColumnSegment` 1 (CSV and Excel number their columns from 1; a JSON field never has it) (R3) |
| `fixed_length` | all analytical lengths equal |

`observed_unique`, `first_column` and `high_cardinality` never prove a role
(RF-29, CA-07).

### 3.5 Priority and conflicts

Decision procedure of `classify(field, context)`, a pure function of the facts
of the field and of the dataset context (position, kind of source). Steps in
this order, the first that decides ends the procedure:

1. No present value: `Other / Empty` (`established`, `basis = fallback`).
2. Technical type `mixed`: candidates are still gathered (step 3); if none
   qualifies the result is `Other / Mixed`.
3. Gather the candidates: value-side first (detectors that qualify, technical
   type, cardinality classes), then name-side (name rules of section 5).
4. Remove the candidates a `negative_match` weakens or whose compatible
   technical types exclude the field. Removed candidates go to `alternatives`
   with the reason.
5. Specific before generic: a detector type outranks Enum, Text and the numeric
   fallbacks; an Identifier candidate never overrides an established Temporal,
   Numeric or detector type (CA-07).
6. If exactly one top candidate remains, it is the result. If two credible
   candidates remain with no way to separate them, the result is the explicit
   fallback (`Other / Unknown` for conflicting detector types; the technical
   type pair otherwise), `state = undetermined`, and both candidates are listed
   in `alternatives`. Never the first in registry order.
7. No candidate: the fallback from the technical type (Integer, Number,
   Boolean, Date, Text, Other / Mixed).

   R1b implements steps 3 to 6 (`classify/candidates.py` gathers, `rules.py`
   ranks). The contenders are the credible detector types, the Boolean, the
   temporal types and, when one of those exists, the numeric technical type.
   One contender is the result (`established`, `basis = inferred` unless the
   technical type alone decided, in which case `fallback`). Several contenders
   are a conflict: the numeric technical pair if it is among them, otherwise
   `other/unknown`, `state = undetermined`, every contender in `alternatives`
   with the reason `conflicting_candidates` and its evidence with the role
   `context`; the contenders are sorted by (family, type), never by registry
   order. Without a contender: the numeric technical type, then Constant, then
   Enum, then Text, then `other/mixed`.

   R2 adds the name side (steps 3 and 4, section 5.4): `classify_field` reads
   the hints of the name once, settles the conflicts of step 6 with
   `names.break_tie` (a supported contender wins, a weakened one is removed while
   another stays; the result is `candidate`, `basis = inferred`, the others are
   `outranked_by_name` or `weakened_by_name`), and annotates the result with the
   name evidence and the `name_only` alternatives. A name that settles nothing
   leaves the conflict of R1b unchanged.

   R1a implements steps 1, 2 and 7: the technical types `integer`, `number`,
   `boolean` and `date` give `numeric/integer`, `numeric/number`,
   `categorical/boolean` and `temporal/date` (`basis = fallback`,
   `state = established`). A JSON object or array has no analyzed value and gets
   `other/empty`.

The procedure is deterministic: same facts, same rules, same result, with one
or several workers (RT-11). The registry order may not influence a result.

### 3.6 Text and its length class

Text is the fallback of a `text` technical type with no detector type. Its
length type is decided on the **exact median** of the analytical string lengths
of the present values, weighted by occurrences (`string_lengths.length_histogram`
with `median_length`), not on the maximum (RF-08).

| Type | Condition with the defaults of decision 12 |
| --- | --- |
| Very short | median <= 5 |
| Short | 5 < median <= 20 |
| Medium | 20 < median <= 50 |
| Long | 50 < median <= 255 |
| Very long | median > 255 |

- Missing values contribute no length. A median of 5.5 is Short; 20.5 is
  Medium.
- `string_lengths` not complete (limited, disabled, failed): the result is
  `Text`, a Text type `undetermined` and an `Alternative` explaining the
  unavailability. The maximum is never used as a silent replacement (O-09).
  Concretely the type code is `text` with `state = undetermined`; the label is
  `Text` for Type and the Overview says the length is not determined.
  Today the Scan always completes `string_lengths` for a field with text values,
  so this case only arises for a document written by another version or built
  by hand; the alternatives list the five lengths with the reason
  `string_lengths_<status>`. The test builds the unavailable measure by hand: there
  is no setting that turns the measure off, and none is added.
- Length never overrides a more specific type (CA-10): Email, ID, UUID and so on
  are decided first.
- The same four bounds drive the String analysis section, which stays based on
  the **maximum** and says `longest value` (section 11.3). A column can be
  Short as a type and Medium in that section; the documentation explains it.

The type codes are `text_very_short`, `text_short`, `text_medium`, `text_long`,
`text_very_long` and `text` (undetermined), all in the family `text`.

### 3.7 Identifier role (ID)

Identifier / ID is attributed only when both hold:

1. a name rule of the identifier group fires (`name.identifier`,
   `name.id_suffix`, `name.id_prefix`, `tokens.*_id` of section 5.5) and no
   negative rule weakens it (`customer_id_length`, `validity`);
2. the values are compatible: no present value outside the family of the
   technical type, no established Temporal or detector type contradicting the
   role (3.5 step 5), at least two present values.

The state is `candidate` (decision 13). Without a name rule the column stays
outside Identifier even when it is the first column and unique: those are
traits (decision 4). A `uuid` column keeps UUID; the role is then an
`alternatives` entry (`ID`, reason `uuid_name`), per the specification C.4.

R3 (`scanner/classify/identifiers.py`, `with_role`, run after the types of the
values and before the name evidence), precisions answered by the maintainer:

- "Compatible values" is a technical type `text` or `integer` with
  `outside_count == 0` and at least two present values.
- The role replaces a Text of any length and a plain Integer, and nothing else:
  Enum, Constant (and an Integer with the trait `constant`), Number, every
  detector type, Temporal, Boolean, Other keep their type (3.5 step 5). An Integer
  left `undetermined` against `postal_code` or `phone` is replaceable: the
  identifier name settles it (decision 14), the contenders stay in `alternatives`.
- The replaced type is an `alternatives` entry with the reason `replaced_by_role`
  (unless the conflict already listed it). Its measures become evidence with the
  role `context`; the technical type stays `supports`; the name rule is one
  `supports` evidence.
- A role the values or a more specific type do not allow is a `name_only`
  alternative when the identifier rule's technical types (`text`, `integer`) allow
  it; a date, a number or a boolean named `*_id` lists nothing.
- A weakening hint (`name.derived_measure`, `customer_id_length`) removes the role.

### 3.8 Unique ID

Identifier / Unique ID is an ID (3.7) for which all of the following hold
(RF-07, D-15):

1. the field is not under a JSON array (decision 5);
2. no missing position in the evaluated scope: `missing.count == 0`;
3. at least one present value;
4. the distinct count of the **analytical** values is exact and complete: the
   field `cardinality` is complete for the analytical domain (it is not limited,
   estimated, sampled or failed);
5. that count equals the number of present occurrences.

R3 precision: "no missing position" also requires `presence.absent` to be 0 or
unknown, so a record that lacks the field is a missing position even when the
configuration (`values.missing`) does not count `absent`.

The analytical values follow the configured NFC, trim and internal whitespace
stages. Raw `"A"` and `" A "` that become equal under trim are not unique
(CA-06). A comparison by case or accent is not substituted implicitly.

If condition 4 fails after the first pass but the second pass supplies an exact
distinct count (`analyses.deep` with `exact_distinct`), the Report refines the
classification (section 4). Otherwise the field stays ID.

The evidence of Unique ID lists a `scope` (3.9): the dataset, the number of
present occurrences, the excluded records and whether the scan is partial. R3: two
`measure` evidence items with the role `supports`, `values.cardinality` (scope
`present_values`, `of` = present values) and `missing.count` (scope `positions`,
`of` = `presence.parent_count`), both `accuracy = exact` and `partial = true` when
the scan excluded records of the dataset (`ClassifyContext.excluded_records`,
counted per dataset by the engine on each `RecordExcluded`). A
uniqueness seen in the analysed scope does not guarantee a business key, future
uniqueness, or uniqueness in excluded records. The documentation says so.

### 3.9 Scope in the evidence

```text
Scope   population: positions | present_values | eligible | tested | records
        of: int | null          size of the population, null when unknown
        partial: bool           records excluded or scan limited
        accuracy: exact | lower_bound | sample | estimated
```

The vocabulary of `population` and `accuracy` extends the one of observations
(18.13) and is shared with the findings (6.3). In R1a `partial` is `false` for a
complete measure; R3 adds the excluded records and the limited scan.

## 4. Where the classification is computed

| Step | Module | Input | Output |
| --- | --- | --- | --- |
| First pass | `scanner/classify/` called after the field blocks are built | the `FieldResult` blocks, the dataset context | `fields[].classification` |
| Refinement | `report_classification.py` (R4), pure function `refine(field, analyses, *, dataset, base, excluded_records)` | the Scan classification, `analyses.deep` when present and valid | `columns[].classification` (final) |

- The Scan always carries a classification. The Report starts from it and
  refines only where `analyses.deep` supplies a fact the first pass lacked
  (exact distinct count for Unique ID, exact frequencies for Enum edge cases).
- `analyses.deep` absent, stale, incompatible or `failed`: the Report keeps the
  Scan classification unchanged and invents nothing (section 8 of the
  specification).
- A refinement never contradicts an established fact of the first pass; it can
  turn an `ID` into a `Unique ID` and list the fact that did it in `evidence`.
- The function is pure and reads only the document. The Report rendering from a
  JSON alone (no source) gets the same classification (CA-20).

R4 (`report_classification.refine`, called by `report_profile.build_dataset`), precisions
answered by the maintainer and decided while building:

- Signature `refine(field, analyses, *, dataset=None, base=None, excluded_records=0)`: the
  two-argument call of 6.7 stays valid. `base` is the `PlanBase` of the Scan; when given, a
  second pass whose `base` differs is stale and changes nothing, and `build_profile` always
  gives it (computed once with the digest of `base_scan`). `base=None` skips the check for a
  caller that vouches for the document. `dataset` picks the analysis among the datasets that
  share a field id; without it the field id must appear in one dataset only.
  `excluded_records` is `scope.records_excluded` of the whole scan (the document does not
  count them per dataset), so the scope of a refined Unique ID is `partial` as soon as any
  record was left out: conservative, never the other way.
- The only refinement is `identifier/id` to `identifier/unique_id`, for a field without
  `observed_unique` whose analytical distinct count is not exact (`analytical_distinct` is
  `None`). `exact_distinct` must be `complete` with a `DistinctCount` (a `DistinctLimited` is a
  lower bound), `unique` true, and `values` equal to the present values of the field; the
  conditions of 3.8 other than the cardinality still hold (`positions_complete`: not under a
  JSON array, `missing.count == 0`, `presence.absent` 0 or unknown) with at least two values.
- `exact_distinct` counts the **original** values, Unique ID is judged on the **analytical**
  ones. An original count proves analytical uniqueness only when no enabled analytical stage
  (`nfc`, `trim`, `collapse_whitespace`) changed a value (`changed == 0`). Otherwise the field
  stays `identifier/id` and the count is added as `context` evidence (`exact_distinct.distinct`):
  `"A"` and `" A "` are two original values and one analytical value (CA-06).
- The refined result keeps `state = candidate`, `basis = inferred`, `rule_version`, the
  alternatives and every evidence of the first pass, and adds the trait `observed_unique` and the
  two `supports` measures of 3.8 (`exact_distinct.distinct` in place of `values.cardinality`,
  and `missing.count`), with the scope of the excluded records.
- Absent, `disabled`, `failed` or stale second pass, an analysis that is not `complete`, or a
  count of other values than the field has: the Scan classification, unchanged.
  No other refinement exists yet (exact frequencies for Enum edge cases remain open).

## 5. Name engine

Lot R2. Module `scanner/classify/names.py`, rules in the catalogue.

### 5.1 Inputs and outputs

Input: the name of the field (the header, or the key segments of the JSON path)
as `NameParts`: the original untouched, the segments, the tokens of the last
segment and the tokens of the segments before it as context. The names of the
sibling fields are not read in L0 (they belong to the backlog L1a rules).
Output: a tuple of `NameHint` entries `{rule, family, type, strength, polarity,
technical, via}`: `type` is `None` for a whole family (Text, whose length is the
median's), `strength` is `exact | sequence | affix | token`, `polarity` is
`supports | weakens`, `technical` the technical types a name-only alternative is
worth listing for, `via` the rule whose support a derived-measure token turned
into a weakening. The hints feed 3.5 steps 3 and 4. They never carry a score. A
hint has no per-rule version in R2: the registry has one, `NAME_RULES_VERSION`.
No rule produces a trait in L0.

### 5.2 Normalisation

The original name is kept untouched. A comparison form is built separately, in
this order (tested, because the order matters):

1. Unicode NFC.
2. Split CamelCase and acronyms before lowercasing: `CustomerID` gives
   `Customer`, `ID`; `ZIPCode` gives `ZIP`, `Code`; `idClient` gives `id`,
   `Client`.
3. Strip accents for comparison (NFD, remove marks).
4. Lowercase.
5. Replace every non alphanumeric run (space, `-`, `_`, `.`, `/`) by a single
   separator.
6. Split on the separator into tokens. Digits stay in their token.

`CustomerID`, `customer_id` and `CUSTOMER-ID` give the same tokens
(`customer`, `id`), hence equivalent hints (CA-22). Names are never changed in
the document.

Implemented by `names.segment_tokens`, `name_parts`, `name_tokens` and
`field_name_parts` (the key segments of a JSON path, else the header).

For JSON, the comparison runs on the last path segment, and the preceding
segments are kept as context tokens (`billing.address.city` keeps `city` as the
candidate token and `billing`, `address` as context). A literal key containing
a dot is not confused with a nested path: the Scan path segments decide (O-18).

### 5.3 Operators

| Operator | Contract | Guard |
| --- | --- | --- |
| `exact` | the whole token sequence equals an expression | `postal_code_status` is not `postal_code` |
| `exact_any` | `exact` over a set of synonyms | no substring search |
| `starts_with` | the first tokens equal a token sequence | `identity` is not `id_*` |
| `ends_with` | the last tokens equal a token sequence | `valid` is not `*_id` |
| `contains_token` | a whole token is present | `id` inside `validity` is not a token |
| `contains_sequence` | contiguous, ordered tokens | scattered tokens are not a sequence |
| `tokens_all` | all tokens present, order free | can be contradicted by a derived-measure token |
| `negative_match` | weakens or excludes a candidate, with a reason | never erases the evidence, never imposes a type |

The `regex` operator of the specification is not added: nothing in L0 needs it.

`negative_match` is the function `names.negative_match(tokens)`: true when the
name ends with a token of `DERIVED_MEASURE_TOKENS` (`status`, `statut`,
`length`, `longueur`, `count`, `format`, `type`, `valid`, `error`, `flag`...)
after at least another token. Then every match of the operators `starts_with`,
`contains_token`, `contains_sequence` and `tokens_all` that does not use that
last token gives a weakening under the rule `name.derived_measure` (`via` names
the rule) instead of support: `email_status`, `customer_id_length`,
`postal_code_status`, `date_format`. The Boolean prefix and flag rules opt out
(`is_valid` is a Boolean).

"Contains" always means a whole token, never an arbitrary substring.

### 5.4 Role of a name in L0

Names reinforce or break ties among types the values already support; they do
not create types (decision 14):

- A name that agrees with a value-supported type is an evidence item with
  `role = supports`.
- A name that agrees with no value-supported type is recorded as an
  `Alternative` (reason `name_only`), never as the result. The exception is the
  ID role (3.7) which needs a name by definition but also compatible values.
- A name that contradicts a value-supported type is an evidence item with
  `role = contradicts`; the type stays.
- Two name hints for the same candidate are one piece of evidence, not two
  (correlated hints are not added, specification C.6): the most specific
  strength is kept, ties by rule id, so the order of the registry changes
  nothing.
- Roles in the result (`rules._with_names`): a hint for the result is evidence
  `supports` (or `contradicts` for a weakening) and changes neither type nor
  state; a hint for a type listed in `alternatives` is evidence `context`; a
  supported type that is neither, when the technical type is in the hint's
  `technical`, becomes the alternative `name_only`. A `other/empty` result is
  not annotated. The evidence of a name has the source `name_rule`, the rule id
  as `id`, and the scope `{population: positions, of: null, partial: false,
  accuracy: exact}`: the name belongs to the whole field.
- A conflict (3.5 step 6) is settled by `names.break_tie`. A weakened contender is
  removed only while another stays. If exactly one of the rest is supported by the
  name it wins; with none supported, a sole survivor wins; otherwise the conflict
  goes on among the supported contenders, or the survivors. The winner is
  `candidate` with `basis = inferred`; the facts of the others stay as `context`.
- The identifier rules are evaluated by `name_hints` and read by
  `identifiers.with_role` (R3), which turns them into the ID role (3.7). Their
  `technical` types are `text` and `integer` (name rules version 2).

### 5.5 Rules of L0

Versioned registry of the rules that touch the foundation types (annex C.4 to
C.6 restricted to them), French and English. A rule has `id`, `version`,
operators and expressions, candidate or trait, compatible technical types,
exclusions.

| Rule | Operators and expressions | Candidate in L0 |
| --- | --- | --- |
| `name.identifier` | `exact_any`: `id`, `identifiant`, `identifier` | ID (3.7) |
| `name.id_suffix` | `ends_with`: `id` after a token | ID |
| `name.id_prefix` | `starts_with`: `id` before a token | ID |
| `name.reference_suffix` | `ends_with`: `ref`, `key` | ID |
| `tokens.customer_id` and similar | `tokens_all`: (`client`, `customer`) + `id`; (`order`, `commande`) + `id` | ID |
| `name.uuid` | `exact_any`: `uuid`, `guid`; `ends_with`: `uuid`, `guid` | UUID |
| `name.email` | `exact_any`: `email`, `e_mail`, `courriel`; `ends_with`: `email` | Email |
| `name.phone` | `exact_any`: `telephone`, `phone`; `ends_with`: `phone`, `telephone` | Phone |
| `name.postal` | `exact_any`: `postal_code`, `code_postal`, `zipcode`, `zip_code`; `contains_sequence`: `postal`, `code` | Postal code |
| `name.url` | `exact_any`: `url`, `website`, `site_web`; `ends_with`: `url` | URL |
| `name.boolean_prefix` | `starts_with`: `is`, `has`, `can`, `est` | Boolean (only with Boolean values) |
| `name.birth_date`, `name.datetime`, `name.date_suffix`, `name.at_suffix` | date expressions | Date or Datetime (only with temporal values) |
| `name.sex_category` | `exact_any`: `sexe`, `sex`, `gender` | Enum, never Boolean |
| `name.text` | `exact_any`: `description`, `commentaire`, `comments`, `notes` | Text (length by median) |
| `name.amount`, `name.quantity`, `name.percentage_suffix` | amount and quantity expressions | trait or reinforcement of Number, Currency, Quantity, Percentage only when values already support them |

The registry `names.NAME_RULES` (version 1) is the reference for the exact
expressions. Beyond the table: `name.date` (the exact name `date`),
`name.time_suffix` (`time`, `heure`), `name.flag_suffix` (`*_flag`, Boolean),
`tokens.postal_code` (`postal` and `code`, correlated with `name.postal`),
`tokens.birth_date`, and `name.calendar_part`, a purely negative rule: a name
with the token `year`, `annee`, `month`, `mois`, `day` or `jour` weakens
Date, Datetime and Time, so `birth_year` is no generic Date. The rule `name.sex_category`
supports Enum and weakens Boolean. Amount, quantity and percentage names have
Currency, Quantity and Percentage as candidates: with bare numbers they are
`name_only` alternatives, never the result.

The year, house number, unit number, status, count, age, score, person name,
organization name and similar rules of annex C are backlog L1a: they would
create types that are not active in L0.

### 5.6 Exclusions (annex C.7) that become tests

`validity` is not an identifier. `email_status` and `customer_email_status`
are not Email. `customer_id_length` is not an ID. `date_format` is not a Date.
`birth_year` is not a generic Date (it is outside the L0 catalogue, so it stays
numeric or integer). `postal_code_status` is not `postal_code`. `street_name`
is not a person name. `sexe` with `M`/`F` is Enum. A very distinct `column_1`
is not a confirmed Unique ID. A distinct first-column `timestamp` or `price`
is not an Identifier.

### 5.7 Versioning

The registry has an integer `NAME_RULES_VERSION` (`names.py`), part of
`rule_version` (section 10). Adding or changing a rule, an expression, an
operator or the list of derived-measure tokens increases it. The tests of the
dictionary (`tests/scan/test_classification_names.py`) give every rule its
examples and the adverse names of 5.6.

## 6. Findings

Lots R5 (contract, Missing, states), R6a (Errors), R6b (Issues). Module
`report_findings.py` (view models and builders), `report_findings_*.py` per
group if needed. Computed at render time from the document alone (ADR findings).

### 6.1 Classes

| Class | Meaning | Where shown |
| --- | --- | --- |
| Error | A deterministic rule proves an invalidity and the meaning of the value is established, or a declared constraint is violated (RF-13) | Errors column |
| Issue | An ambiguity, rarity, variant or deviation to inspect (RF-15) | Issues column |
| Information | A fact for Overview, Details or an explanation | never a badge |
| Missing | Positions with no present value (RF-12) | Missing column, separate |

An absence is never an Error or an Issue by itself (CA-16). A name alone never
produces an Error (D-14, CA-12). A detector or a pattern is not a constraint
(RF-14, CA-13). A technical `failed` is an assessment failure, never an invalid
value (CA-30).

### 6.2 Finding model

```text
Finding
  code        str           stable, catalogue entry (e.g. temporal.invalid_calendar)
  cls         error | issue | information
  field       str           field id (dataset id and field id identify the row)
  count       int | None    None when the count is not defined
  unit        occurrences | distinct_values | categories | patterns | groups
              | positions | records | formats
  population  Population    kind and size of what the count is out of (6.3)
  share       Share | None  numerator, denominator and percent, or None
  accuracy    exact | lower_bound | sample | estimated | unavailable
  status      detected | none_detected | not_assessed | partial | not_applicable | failed
  basis       list[str]     ids of the observations, detectors or analyses used
  examples    list[Example] already exposed (mask, hide, show); filled by lot R8
  overlaps    list[str]     codes whose set is proven to overlap, else empty
```

Catalogue entries (`FindingCode` in `scanner/classify/catalog.py`, listed in
`FINDINGS`) have `code`, `cls`, `status` (`active` or `recommended`), `unit`,
`population` (kind), `algorithm` (the Scan fact or section it reads),
`prerequisites` and `downgrades_to_issue`. A `recommended` entry produces
nothing in a real report (CA-29): `column_findings` only runs active codes. No
rule without an algorithm and a threshold is activated (B.1 of the specification).
The catalogue of findings is not part of any document, so a change to it does not
change `CATALOGUE_VERSION` (which identifies the rules that write a
classification into a Scan).

Population kinds: `positions`, `present_values`, `content_strings`,
`occurrences`, `distinct_values`, `groups`, `records`, `eligible_values`
(`coverage.eligible` of a detector). An observation's `population` becomes a unit
and a kind by one table (`value_slots` gives positions, `content_strings` gives
occurrences out of text values); `finding_from_observation` states an observation
as it is and recomputes nothing.

Active codes in R5 (the checks come with R6a and R6b): Error `temporal.invalid_calendar`,
`semantic.invalid` (one code for every semantic detector, the detector in `basis`),
`type.outside_family`; Issue `temporal.ambiguous_date`, `number.ambiguous`,
`categorical.case_variants`, `pattern.minority`, `length.minority`, `type.mixed`,
`identifier.repetition`, `text.surrounding_whitespace`, `text.repeated_whitespace`;
Information `presence.empty_column`, `values.constant_column`. Recommended
(documented, never produced): `categorical.rare`, `pattern.rare`, `format.rare`,
the single-column controls of backlog L1c and the declared constraints of L2.

### 6.3 Populations, counts and shares

Reference counts for a field (specification 7.6): `P` positions, `M` missing,
`N` present occurrences, `D` exact distinct count of the analytical values.

- Missing: `100 * M / P` if `P > 0`.
- Cardinality ratio `D / N` if `N > 0` and `D` exact. It is not the share of
  values that occur once.
- Repetitions beyond the first: `N - D`. It is not the number of duplicated
  occurrences nor the number of duplicated groups. For `A, A, A, B`: 4
  occurrences, 2 distinct, 2 repetitions beyond the first, 1 duplicated group,
  3 occurrences in that group (CA-15). Labels reflect the metric actually
  available.
- A share is `count / population`, only with compatible unit and population.
  Division by zero gives `share = None` with accuracy `unavailable`, never NaN
  or infinity (RF-22).
- A JSON field repeated inside a record: occurrences are not rows. A finding on
  3 occurrences is not shown as 3 affected rows (CA-21); the unit says
  `occurrences`. The same holds for Missing: its unit is `positions`, and
  `occurrences` for a field under a JSON array (maintainer, R5).
- `share(count, population)` gives `percent = None` and accuracy `unavailable`
  for a zero or negative population or a count the population cannot hold; the
  percentage is 0 to 100, never a share over 100 %.

### 6.4 Evaluation states

| State | Label | Meaning |
| --- | --- | --- |
| detected | the count with the finding label | the check ran and found something |
| none_detected | `None detected` | the check ran, completely, and found nothing |
| not_assessed | `Not assessed` | the check was disabled or never ran |
| partial | `Partially assessed` | the check covered only part of the eligible values (adaptive detector, limited measure) |
| not_applicable | `Not applicable` | the check has no meaning for this population |
| failed | `Assessment failed` | the check raised a diagnostic |

The five labels are the wording of decision 6; the code values are the table's
first column. `None detected` appears only after a complete check. A detector
that tests 100 of 1,000 eligible values and finds nothing is `partial`, never
`none_detected` (CA-17). Null, disabled and failed stay distinguishable (CA-18).
The dash is not used in Errors and Issues (RF-23).

The mapping from the Scan (`evaluation_state(detector_state, eligible, tested,
found)`), in this order:

| Detector `state` | Coverage | State |
| --- | --- | --- |
| `failed` | any, whatever it counted | `failed` |
| `disabled` | | `not_assessed` |
| `not_applicable` | | `not_applicable` |
| `complete` | `found > 0` | `detected` |
| `complete` | `eligible == 0` | `not_applicable` |
| `complete` | `tested == 0` | `not_assessed` |
| `complete` | `tested < eligible` (adaptive: `not_tested > 0`) | `partial` |
| `complete` | `tested == eligible` | `none_detected` |

The count of a check that tested part of the values is a lower bound
(`assess_detector`). A code with no check behind it has not run: its state is
`not_assessed` with the reason `no_check`, never `none_detected`; this is the
state of a code whose check is not registered in `report_findings.CHECKS`; the three
Errors have theirs since lot R6a and the nine Issues since lot R6b.

State of a whole list (`FindingList.state`, `list_state`): `detected` when it holds
findings; otherwise the checks that apply (those not `not_applicable`) decide: all
in one state give that state; a mix that includes a check that completed or went
part of the way is `partial`; a mix of `failed` and `not_assessed` is `failed`; no
check that applies is `not_applicable`. An Error code that downgrades to an Issue
counts, in the Issues list, as a check of that list too; a finding of such a check
that went to the other list does not make the first list `detected`.

Missing has its own state: `detected` when `count > 0`, `none_detected` when it
is 0, `not_applicable` for a field with no position. It is always exact: the Scan
counts every position.

### 6.5 Deduplication

Distinct proofs are kept. Two findings are presented as one only when the
overlap is proven: same rule, same scope, same population, or an observation
that carries the covered record indices (RF-24, CA-26). Two counts of 36 prove
nothing. No deduplicated total is fabricated. `overlaps` stays empty without
proof.

`merge_proven(findings)` groups for presentation only: two findings share a
`FindingGroup` when one names the other in `overlaps` (closed by transitivity);
the group keeps each count (`counts`) and has no total, and the findings are not
changed. `records_overlap(first, second)` is the proof an observation can give: both
list every record they count (the list length is the count), both are exact and
the lists meet. `prove_overlaps` (R6b, called by `column_findings`) sets `overlaps` from it,
between Issues of different codes only; no field observation of the Scan lists its records
today, so in a real report `overlaps` stays empty and nothing is merged.

### 6.6 L0 findings, from existing facts only

| Class | Findings | Existing source |
| --- | --- | --- |
| Missing | the five components `absent`, `null`, `empty`, `blank`, `marker` | `missing.components` |
| Error | invalid dates in a Temporal field | `date` detector `invalid`, every reason (6.8) |
| Error | `invalid` of the detector that gives the field its type (Email, Phone, Postal code, URL, IP address, UUID) | `detectors[].coverage.invalid` |
| Error | values outside the family of an Integer or a Number | `technical_type.outside_count` (re-qualifies `type_error_count`, section 9) |
| Issue | ambiguous dates | observation `ambiguous_dates` |
| Issue | ambiguous numbers | `number` detector `ambiguous` |
| Issue | spelling variants (case, accents or spacing) | observation `variant_groups` |
| Issue | minority patterns and lengths | observations `minority_pattern`, `minority_length` |
| Issue | mixed types | observation `mixed_types` |
| Issue | repetition in an identifier | `D`, `N`, cardinality exact (ID and Unique-ID candidates) |
| Issue | surrounding or repeated whitespace | observations `trimmed_cells`, `collapsed_whitespace` |
| Information | empty column, constant column | `empty_column`, `constant_column` |

Rarity of categories and of patterns (`categorical.rare`, `pattern.rare`) does
not exist in the Scan: backlog L1b, measure first. No illustrative value of the
specification (2 %, factor 5) is a parameter.

An Error requires a field with `state = established` (RF-13); on a `candidate`
or `undetermined` classification the same fact is an Issue. This changes the
meaning of today's `type_error_count`, as the plan noted.

### 6.8 Errors (lot R6a)

The checks are `invalid_dates`, `invalid_semantic_values` and
`values_outside_family` of `report_findings.py`, registered in `CHECKS` under the
three codes. Each reads the Scan's facts and the classification of the column
(`ColumnView.classification`, refined by the second pass when it ran) and nothing
else: no source, no `analyses` of its own, so an absent, stale or failed second pass
invents nothing. A check answers `not_applicable` (reason `not_temporal`,
`not_semantic_type`, `not_numeric_type`) for a column its code does not concern.
A Text, Enum, ID or Boolean field therefore has the Errors list `not_applicable`: no
deterministic rule applies to it.

- **`temporal.invalid_calendar`**: classification family `temporal` (Date, Datetime,
  Time) and the `date` detector. Count `coverage.invalid`, unit `occurrences`,
  population `eligible_values` (`coverage.eligible`). The detector does not split
  its `invalid` by reason, so every one is counted: an impossible calendar date
  (`2025-02-30`), an impossible time (`25:00`) or offset, mixed separators
  (`2025/01-15`) and a malformed component width. The label says `invalid date`.
  A value that is not date-shaped is `not_matched` and is not counted (CA-13).
  Known limit: a narrowed `detectors.date.orders` makes a date of an order left out
  invalid (`unsupported_order`); the check does not see the configuration.
- **`semantic.invalid`**: the classification is one of Email, Phone, Postal code,
  URL, IP address or UUID, and only the detector of that type answers (its id is
  in `basis`). Count `coverage.invalid`, unit `occurrences`, population
  `eligible_values`. A detector of another type that finds some values in a field
  of a different type is not a constraint on it (RF-14). A `not_matched` value is
  not counted (CA-13). A purely numeric value is never `invalid` for Phone (the
  detector leaves identifiers alone), so an unformatted phone column has no
  `invalid`.
- **`type.outside_family`**: the classification is `numeric/integer` or
  `numeric/number` and the technical type is the same. Count
  `technical_type.outside_count` (less the decimals of an Integer: they are numbers),
  exact over the values the Scan read, unit
  `occurrences`, population `present_values` (`values.count`). Date and Boolean
  are not covered: a `yes` is a Boolean for the detector and a datetime in a Date
  field is a format, not an invalidity; the impossible dates have their own code.
  A `Text` field has no family to fall outside of (maintainer, R6a).
- **Accuracy and states.** `assess_detector` gives the state and the accuracy of a
  detector: a detector that tested part of the eligible values gives a lower bound
  and, without a finding, `Partially assessed` (CA-17); a `failed` detector gives
  `Assessment failed` whatever it counted (CA-30); a `disabled` one `Not assessed`.
  A detector missing from the field is `not_assessed` with the reason
  `detector_missing`.
- **Overlap.** The three checks apply to disjoint classifications (Temporal, one
  of the six semantic types, Integer or Number), so a field never has two of
  them and `overlaps` stays empty.

Audit of the detectors (R6a, real Scans): the six semantic detectors each produce a
real `invalid` for a value with the shape of the type that fails its syntax, and a
`not_matched` for a value without that shape. Email: a space in the local part,
a leading hyphen or a double dot in the domain. Phone: an area or exchange code that
no number has (`(014) 555-1234`), in a formatted number. Postal code: a Canadian
code that starts with or contains a letter Canada Post does not use (`D1A 0B1`).
URL: a space, a port above 65,535, an unclosed bracket. IP address: an octet above
255, a leading zero. UUID: a non-hexadecimal digit in the layout. `a@x`,
`bad address` (Email), `call me`, `K1A 0B` and `123e4567e89b` are `not_matched`.
The detectors check syntax only (a code is never looked up), so an `invalid` is a
proof of invalidity of the value and not a likelihood.

### 6.9 Issues (lot R6b)

The checks are `ambiguous_dates`, `ambiguous_numbers`, `case_variants`,
`minority_patterns`, `minority_lengths`, `mixed_types`, `identifier_repetition`,
`surrounding_whitespace` and `repeated_whitespace` of `report_findings.py`,
registered in `CHECKS` under the nine codes of the Issues. An Issue needs no
established classification (RF-13 is about Errors): it states what the Scan found on
whatever column it found it, so an ambiguous date in a Text or Other / Mixed column is
an Issue (maintainer, R6b). The facts are read, never recomputed: seven checks state
an observation of the Scan as it is (count, `of`, accuracy, in the unit of the
observation, `finding_from_observation`; the population kind is the catalogue's, which
only changes `type.mixed`, `present_values` instead of `occurrences`), one reads a
detector and one the cardinality.

| Code | Source | Count, unit, population |
| --- | --- | --- |
| `temporal.ambiguous_date` | observation `ambiguous_dates`; the `date` detector gives the state | ambiguous dates, `occurrences`, out of the date values |
| `number.ambiguous` | `number` detector, `coverage.ambiguous` | `occurrences`, `eligible_values` |
| `categorical.case_variants` | observation `variant_groups` | groups of values that differ by case, accents or spacing (label "spelling-variant groups"), never the occurrences in them (CA-14); no population size, so no share |
| `pattern.minority` | observation `minority_pattern` | distinct values in the minority patterns (maintainer, R6b), `distinct_values`; the pattern ids follow the observation id in `basis`; accuracy `sample` when the discovery read a sample |
| `length.minority` | observation `minority_length` | `occurrences`, `content_strings` |
| `type.mixed` | observation `mixed_types` (technical type `mixed`) | values outside the closest type, `occurrences`, `present_values` |
| `identifier.repetition` | classification `identifier` and the exact analytical `D` | `N - D` (contract 6.3), `occurrences`, `present_values`; never duplicated groups or occurrences (CA-15) |
| `text.surrounding_whitespace`, `text.repeated_whitespace` | observations `trimmed_cells`, `collapsed_whitespace` | values the stage changed, `occurrences`, `content_strings` |

What an absent observation means. An observation that exists is a finding. Without one
(`ColumnView.observations_state` says whether the list of the Scan is `complete`,
`truncated` by `scan.observations.max_items` or `unavailable`), the measure behind the
rule decides, and `None detected` needs a measure that completed:

- `not_applicable` when the rule has no meaning (no text value, no value, fewer than
  `MINORITY_LENGTH_MIN_VALUES` strings, no length that holds `DOMINANT_LENGTH_MIN_SHARE` of
  them (reason `no_dominant_length`: two legitimate lengths leave the Scan's rule without
  meaning, which is not the same as finding nothing), a field that is not an identifier, a
  pattern discovery that does not apply); `failed` when the measure failed (CA-30); `not_assessed`
  when it was turned off or never ran (a normalization stage off, a detector missing,
  no pattern discovery in the document).
- A measure that is itself a count (the variant groups, the changes of a stage, the
  ambiguous values of a detector, the technical type) proves an absence when it is zero,
  whatever the list of observations. Rules with a threshold the Scan alone evaluated
  (`minority_pattern`, `minority_length`) cannot be told from the facts: a `truncated`
  list gives `Partially assessed` (reason `observations_truncated`) and an `unavailable`
  one `Not assessed` (reason `observations_unavailable`). A measure that holds a count
  with no observation behind it is `Partially assessed` for the same reason.
- A detector that tested part of the eligible values (CA-17) or a pattern discovery
  that read a sample or hit a limit gives `Partially assessed`, and the count of an
  observation behind a partly tested detector is a `lower_bound`.
- `identifier.repetition`: `D` must be exact. Not exact, the check is `Not assessed`
  (reason `cardinality_not_exact`); R6b does not read `analyses.deep`. A Unique ID, or
  an ID with the trait `observed_unique` (refined by R4), has proved its uniqueness:
  `None detected`.

Overlap. `prove_overlaps` sets `overlaps` between two Issues of different codes only when
`records_overlap` holds for the observations they rest on (both list every record they
count, both exact, the lists meet). Two counts of 36 prove nothing (CA-26); the findings
are never changed beyond `overlaps`, and `merge_proven` keeps each count.

Known gaps, for gate B. `type_outliers` on a Date or Boolean field (and any other
technical type that is neither Integer nor Number) is an observation of the Scan that no
active finding states (R6a excluded those fields from `type.outside_family`). The
rareness of categories and patterns stays in the backlog (L1b). On the demo the
`pattern.minority` check is `Partially assessed` on the columns whose pattern discovery
read a sample (high cardinality).

### 6.7 Entry points

Fixed here so the contract tests can target them (R5 may add helpers, not
rename these):

- `tabalyst.report_findings.column_findings(column: ColumnView) -> ColumnFindings`
  where `ColumnFindings` has `missing: MissingFinding`, `errors: FindingList` and
  `issues: FindingList`. A `FindingList` has `items: list[Finding]` and `state`
  (the evaluation state of 6.4, `detected` when `items` is not empty) and
  `assessments`, the check behind each code. `MissingFinding` has `count`,
  `unit`, `population`, `share`, `accuracy`, `state`, `definition` and
  `components` (the five of the Scan). `column_findings(column, checks=None)`
  takes the registry `CHECKS` by default; R6a and R6b registered their checks there.
  A check answers only for its own code and class: another code or class is a
  `ValueError`, and an Error finding on a classification that is not `established`
  is turned into an Issue by `column_findings` itself (RF-13), not left to each check.
- Helpers (R5): `evaluation_state`, `assess_detector`, `detector_of`, `list_state`,
  `share`, `repetition_figures`, `repetition_from_counts`, `finding_from_observation`,
  `records_overlap`, `merge_proven`, `label_for` (the nouns are in `report_labels.py`).
- `tabalyst.scanner.classify.classify_field(field, context) -> Classification`
  (first pass) and `classification_versions() -> tuple[int, ...]`.
- `tabalyst.report_classification.refine(field, analyses, *, dataset=None, base=None,
  excluded_records=0) -> Classification` (R4, section 4).

## 7. Views

### 7.1 Overview

`report_overview.py` (R7). One short, deterministic sentence per profile from
the classification and from the measures already computed at render time
(`report_measures.py`, `report_insights.py`), never recomputed. Rules:

- Facts only, with the accuracy of each figure; a limited measure is never said
  exact (RF-10).
- No business meaning (no "street numbers", no currency for bare numbers).
- Profiles: Unique ID, ID, Enum, Boolean, Constant, Numeric types, Temporal
  types, Email, Phone and other detector types, Text (median length and
  diversity), Other / Mixed, Other / Empty.
- No average for codes and identifiers. No sentence repeats an Error or an
  Issue.
- No test freezes a wording still open (specification 10.2); tests check the
  facts the sentence uses.

Implementation (lot R7). `overview_for(column)` returns an `Overview` (`text`
and `facts`, each `OverviewFact` with `name`, `value` and `accuracy` `exact` or
`lower_bound`); `overview_text(column)` returns the sentence. The words are in
`report_labels.py` (`OVERVIEW_*`). Nothing is serialized and no HTML reads it
before R9a.

- Unique ID, ID: distinct values (`at least` when the cardinality is limited) and
  the recurring formats of the patterns (`at least` when the discovery read a
  sample or left values outside the patterns). Unique ID adds "in the records the
  scan accepted" when its evidence is partial.
- Enum, Boolean: the number of categories and the share of the most frequent one.
  The frequency listing is ranked by count, so the share is exact even when the
  table is cut. No threshold of dominance; Boolean does not name its states. A
  share that rounds to 100.0% without being 1 is worded "more than 99.9%".
- Constant: the number of present positions, never the value.
- Numeric: range and median (median left out when limited), no mean. Currency
  and Quantity add the dominant marker or unit, only from the detector that
  classified the column and only when the exposure of the column is `show`.
- Temporal: one range per kind, never a common range. The Scan excludes ambiguous
  dates from the range, including those whose day and month are equal
  (`05-05-2020`), so the sentence says "ambiguous dates left out of the range"
  without their number (an Issue says it).
- Email, Phone, Postal code, URL, IP address, UUID: "shaped" like the kind and the
  recognized formats of the detector, never an address or a domain (exposure is
  Details, R8).
- Text: class, median length (exact) and distinct values. Other: Mixed lists the
  representations it combines, Empty says there is no present value, Unknown says
  that no type is established.

### 7.2 Details

`report_details.py` (R8). Representative examples and complementary measures per
profile. Alert examples belong to the preview, not to Details (RF-18). Exposure
`mask`, `hide`, `show` applies in the cell, the preview, the HTML attributes and
the embedded data (RF-19, CA-19). A limited list is never said exhaustive. Links
to `--details` pages only when the page exists (CA-28). Values are escaped
(RT-14).

### 7.3 Table and filters

R9a. Eight columns in the order above. A row is identified by dataset id and
field id, never by the displayed name alone (RF-02, CA-03). Type family and Type
have independent filters and sorts; a family filter cannot select a type of the
same name in another family; options come from the classifications present
(RF-03, CA-02). The "All / Quality issues / With observations" segment reads the
new Errors and Issues. Distinct, Inferred type and Examples leave the table; the
technical type stays in the JSON and the column page (O-11).

### 7.4 Previews and styling

R9b. Two labels then `+N more`; the preview gives nature, unit, count,
population, share with denominator, exposed examples (two) and the limit of the
reading (RF-17). Errors red, Issues amber, information grey, within the existing
themes; the state is never carried by colour alone; keyboard, touch, focus,
Escape, 200 % zoom, dark theme, small screen (RT-16, CA-27). WCAG 2.2 AA is
the target, with no claim of certification.

## 8. Second pass and cost

Decision 10. The classification reads `analyses.deep` as it is (`mode` `auto`,
`forced`, `off`; `outcome` `ran`, `reused`, `unavailable`, `failed`, ...). The
Report builds the final classification from the Scan plus the refinement of
section 4, and performs no extra reading. No new option, no new analyzer. First
pass work added by the classification is rule evaluation on blocks already
computed: no extra pass over the source (RT-09, RT-10). R11 measures before and
after on the same parameters and cache state; no threshold is set before
measurement (RT-12, O-21).

## 9. Persistence and format

- Scan: `fields[].classification` (R1a), in revision 4, still in preparation.
- Report: `columns[].classification`, the final version (R4, done), in revision 4.
- Removed from the Report: `columns[].semantic_type`,
  `summary.semantic_type_counts`, `summary.semantic_type_percents`. Added
  `summary.type_family_counts` and `summary.type_counts`, keyed by the codes
  `family` and `family/type`, with their percents (R4).
- Kept: `inferred_type`, `type_counts`, `type_confidence`, `type_error_count`
  (its meaning is re-qualified: it counts values outside the technical family;
  the Error of the table is derived from the findings, not from this field).
- Findings, Overview, Details, labels: not persisted, no new JSON member
  (design 18.14, 19.3).
- Changelogs updated by the lot that changes the format: R1a for the Scan
  (`docs/en/scan/format-changelog.md`, whose example showed revision 3 and was
  corrected in R1a), R4 for the Report (`docs/en/report/profile-changelog.md`).
  The entry "revision 4 (in preparation)" of each changelog holds the changes
  (decision 9).
- Schemas regenerated by `python scripts/scan_schema.py`.

## 10. Rule identity and cache

Findings of the inventory (R0, verified in code):

- There is no content-addressed cache of Scans. `scan_reuse` accepts a Scan
  document when `format_version` and `format_revision` match, and checks the
  source (`compare_source`, size then SHA-256) and the configuration
  (`config_sha256`). A different engine version, or a different version of the
  pattern discovery (`discovery_versions()`), gives a **warning** from
  `engine_warning`, not a refusal.
- `ScanConfig` changes `config_sha256`; presentation settings (`report.*`) do
  not.

Decision 11:

- `Classification.rule_version` is an integer built from the catalogue version
  and `NAME_RULES_VERSION` as `CATALOGUE_VERSION * 1000 + NAME_RULES_VERSION` (R2:
  3001 is catalogue 3, name rules 1; decodable, strictly increasing, no collision
  while the name rules stay below 1000 versions; R3: 4002 is catalogue 4, name
  rules 2): a function `classification_versions()` in
  `scanner/classify/` returns the tuple, read through a function and not
  imported as constants, like `discovery_versions()`, so the cache identity, the
  identity of a Scan and the stored results see one value.
- `engine_warning` compares the version recorded in the Scan with the current
  one and tells the user to scan again, the same way it does for the patterns.
  This is needed because rule changes can ship between published versions of the
  engine.
- `config_sha256` already covers the four Text bounds once they live in
  `scan.classification` (decision 12). The identity of the Scan
  (`scan_identity`) and the key of the second pass do not change, because the
  second pass does not read the classification.
- `EngineInfo.classification` is a dict of versions by name next to `detectors`
  (R2: `{"catalogue": 3, "names": 1}`; R3: `{"catalogue": 4, "names": 2}`), so the value is in the Scan document and
  not only in each classification. `classification_versions()` returns the tuple
  in the order of `catalog.VERSION_NAMES` (`catalogue`, `names`), `version_record()`
  the dict. `CATALOGUE_VERSION` rose to 3 in R2 because the decision of
  `classify_field` changed; the catalogue entries did not.

## 11. Settings

### 11.1 Text bounds

```json
{
  "scan": {
    "classification": {
      "very_short_max_length": 5,
      "short_max_length": 20,
      "medium_max_length": 50,
      "long_max_length": 255
    }
  }
}
```

- Strictly increasing, each >= 1 (the validation of today's
  `StringAnalysisConfig`, moved).
- Lives in `scan` because the Text type is persisted in the Scan; a setting in
  `report` would not invalidate a Scan, which would then carry a classification
  inconsistent with its settings. The cost of that choice: changing a bound now
  changes `config_sha256` and asks for a new scan, where it only changed the
  Report before.
- The defaults are the ones the String analysis section already uses
  (5 / 20 / 50 / 255). They differ from the specification defaults (10 / 50 /
  255 / 1,000); the specification examples CA-08 and CA-09 are tested with the
  defaults in force (table in the contract tests).

### 11.2 Migration of `report.string_analysis`

- `very_short_max_length`, `short_max_length`, `medium_max_length`,
  `long_max_length` move to `scan.classification.*`.
- `length_distribution_max_length` and `examples_per_length` stay in
  `report.string_analysis`.
- The old keys under `report.string_analysis` are refused with their new place,
  through `MOVED_SETTINGS` in `config.py` (specific paths first), like the
  settings that moved between `scan` and `report` before (design 19.4b). The
  error message names `scan.classification.<key>`. No silent acceptance
  (project rule: a setting that no longer applies is an error).
- `length_distribution_max_length <= medium_max_length` becomes a cross-check
  when the effective `ReportConfig` is assembled, since the two values now live
  in different objects.
- `report_profile.build_string_profile` reads the bounds from the Scan
  configuration carried by the document (`config.scan.classification`), so a
  Report rendered from a Scan document uses the bounds the Scan was written with.
  The cross-check is `report_config.check_length_distribution`, called by
  `ReportConfig.from_presentation` and by `build_profile` (the config of a
  document is copied onto the report config without validation).
- Documentation: `docs/en/reference/configuration.md` (table by tool and the
  moved-settings list), `docs/en/report/json-profile.md` (`config`), the String
  analysis page. R1a does the code, the documentation and the tests of this
  point.

### 11.3 Relation with the String analysis section

Unchanged on purpose (plan, string analysis): the section is based on the
maximum and says `longest value`; the Text type is based on the median. Same
bounds, different statistic. The documentation states the difference
(specification 10.4).

## 12. Inventory of consumers of `semantic_type`

Verified in code on 2026-10-16 (`main`, `9013373`).

| Consumer | Reads | Lot | Action |
| --- | --- | --- | --- |
| `report_profile.py:491` `semantic_type()`, `:683`, `:950` to `:995` | builds the value and the counts | R4 | replace by the classification block and counts (done in R4) |
| `models.py:151`, `:178`, `:179` | `ColumnProfile.semantic_type`, `DatasetSummary.semantic_type_counts`, `semantic_type_percents` | R4 | remove, add the classification and counts (done in R4) |
| `reporting.py:370` | `semantic_colors` palette | R9a | replace by family colours inside the existing themes |
| `templates/report.html` (columns table, dashboard card, filters, `data-pill`) | Semantic type column and filter | R9a | eight columns (R4: the column and the card read `type_label` and the family counts, `ColumnView.type_label`) |
| `templates/column.html:50`, `:51`, `:57` | Interpretation card shows the semantic type and detector rows | R10 | show family, type and evidence (R4: shows `type_label`, the enumeration list reads `classification.type`) |
| `schemas/tabalyst.report.schema.json` | generated | R4 | regenerate (done in R4) |
| `docs/en/report/json-profile.md`, `read-report.md`, `reference/types-and-patterns/types.md`, `patterns.md`, `report/index.md`, `scan/index.md`, `reference/glossary.md` | wording and tables | R4, R11 | rewrite (R4: json-profile, read-report, types, configuration, deep; the rest in R11) |
| `tests/test_reporting.py:294`, `tests/scan/test_scan_report.py` | `column.semantic_type == "enumeration"` | R4 | replace by classification assertions (done in R4) |
| `examples/showcase/*/report.json` and `report.html` | generated | each lot | regenerated by `regenerate.py --fresh` |
| `projects/_queries.py`, `projects/_schema.py` | nothing (their `semantics_version` is the record semantics) | none | no action; R10 only re-checks |
| `generate_columns_package.py` | nothing (the word is in a docstring) | none | no action |
| Public API (`__init__`, `report_schema`, `ReportProfile`) | the models above, through `ColumnProfile` | R10 | the signatures of `scan()`, `generate_scans()`, `analyze_scan()`, `generate_reports()` and `render_report()` do not change; the model fields do |
| `scanner/pattern_eligibility.py:152` | `interpretations.candidates` | none | unaffected, keeps reading interpretations |

`interpretations` (design 12.4) stays in the Scan unchanged: the classification
reads `candidates` and does not replace them.

## 13. Lot map, tests and ADRs

| Lot | Contract sections | Tests of `test_contract_summary.py` it enables |
| --- | --- | --- |
| R1a | 3.1, 3.6, 9, 11 | CA-08, CA-09, CA-24, median unavailable, empty column, determinism |
| R1b | 3.3, 3.4, 3.5 | CA-10, M/F stays Enum, two credible candidates (five digits: `number` and `postal_code`), no bare-number Currency or Percentage; `tests/scan/test_classification_types.py` (one test per type, conflicts, traits) |
| R2 | 5 | CA-12, CA-22, CA-23, units of the dictionary, no substring, name alone never established |
| R3 | 3.7, 3.8 | CA-04, CA-05, CA-06, CA-07, partial scan, JSON array |
| R4 | 4, 9 | refinement, absent or stale Deep, rendering without the source; `tests/scan/test_classification_refinement.py` |
| R5 | 6 | CA-14 (the nouns), CA-16, CA-17, CA-18, CA-26, CA-29, CA-30, A,A,A,B; `tests/scan/test_report_findings.py` (Missing, states, shares, merging, words) |
| R6a | 6.6, 6.8 | CA-11 (Error half; the Issue half is R6b), CA-12, CA-13, CA-21, CA-30; `tests/scan/test_report_errors.py` (each semantic detector, each invalid reason of the date detector, Integer and Number, no Error on Boolean, Date, Text, ID, candidate and undetermined turned into Issues, failed, disabled and partly tested detectors, repeated JSON field) |
| R6b | 6.6, 6.9 | CA-11 (the Issue half), CA-14 (the figures), CA-15, CA-26; `tests/scan/test_report_issues.py` (each of the nine checks, three groups over twenty occurrences, `A, A, A, B`, two observations of 36 without proof, states of an absent observation: disabled, cut, stage off, partly tested detector, failed detector, limited cardinality) |
| R7 | 7.1 | CA-25, a limited measure never said exact; `tests/scan/test_report_overview.py` (facts and accuracy per profile, no mean, no value of a constant or an address, ambiguous dates left out, no Missing, Error or Issue figure repeated) |
| R8 | 7.2 | CA-19, CA-28 |
| R9a, R9b | 7.3, 7.4 | CA-01, CA-02, CA-03, CA-20, CA-27 |

Gating: the marker `report_lot("Rn")` and `tests/scan/report_gate.py`
(`ENABLED_LOTS`, `KNOWN_LOTS`). A lot adds its name when it starts. A test of a
lot not enabled is skipped with the reason
`Report overview lot Rn is not implemented yet`. Skipped, not strict-xfail,
because these tests import modules that do not exist yet.

ADRs written in R0 (`docs/dev/adr/`):

- `2026-10-16-classification-persisted-in-scan.md`
- `2026-10-16-classification-catalogue-in-python.md`
- `2026-10-16-findings-computed-at-render.md`
- `2026-10-16-assessment-state-vocabulary.md`

## 14. Open points carried forward

- The trait `high_cardinality`: not emitted (R3). A later lot may define it from a
  tracked limit (for instance a cardinality limited by `distinct_limit`); it needs
  a decision because 3.4 says "exact".
- Exact `type` code for the Text with an undetermined length (`text`): confirm
  with the label in the Type filter (R9a).
- Backlog: L1a types, L1b rarity, L1c single-column controls, L2 declared
  constraints (`basis = declared`), L3 history and drift.
