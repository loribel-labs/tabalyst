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
| 14 | A name alone never creates a type or a state. In L0 a name rule can only reinforce a type the values already support, break a tie between supported types, or weaken one (`negative_match`). | 5.4 |
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
- Constant: one distinct analytical value among the present ones. It is a
  type, and the trait `constant` is not added to it.
- Detector types win over Enum when the detector covers the field (an email
  column of few addresses stays Email).

### 3.4 Traits

Traits are secondary, never shown as a type. L0 emits only:

| Trait | Emitted when |
| --- | --- |
| `single_pattern`, `multiple_patterns` | `derived.patterns` of the field lists one or several patterns |
| `constant` | one distinct value, on a type other than Constant |
| `high_cardinality` | cardinality known and exact, close to the present values (no threshold is fixed in R0; R3 defines it from the tracked limits, never a percentage of the spec) |
| `observed_unique` | exact analytical distinct count equals the present values |
| `first_column` | first position of a table dataset |
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

The analytical values follow the configured NFC, trim and internal whitespace
stages. Raw `"A"` and `" A "` that become equal under trim are not unique
(CA-06). A comparison by case or accent is not substituted implicitly.

If condition 4 fails after the first pass but the second pass supplies an exact
distinct count (`analyses.deep` with `exact_distinct`), the Report refines the
classification (section 4). Otherwise the field stays ID.

The evidence of Unique ID lists a `scope` (3.9): the dataset, the number of
present occurrences, the excluded records and whether the scan is partial. A
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
| Refinement | `report_classification.py` (R4), pure function `classify(field, analyses)` | the Scan classification, `analyses.deep` when present and valid | `columns[].classification` (final) |

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

## 5. Name engine

Lot R2. Module `scanner/classify/names.py`, rules in the catalogue.

### 5.1 Inputs and outputs

Input: the display name, the path segments (JSON) and the dataset context (the
names of the sibling fields, for supporting context). Output: a list of
`NameHint` entries, each `{rule, version, candidate (family, type) or trait,
strength: exact | token | sequence | affix, polarity: supports | weakens}`. The
hints feed 3.5 steps 3 and 4. They never carry a score.

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
  (correlated hints are not added, specification C.6).

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

The registry has an integer `NAME_RULES_VERSION`, part of `rule_version`
(section 10). Adding or changing a rule increases it.

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
  population  Population    what the count is out of (6.3)
  share       Share | None  numerator, denominator and percentage, or None
  accuracy    exact | lower_bound | sample | estimated | unavailable
  status      detected | none_detected | not_assessed | partial | not_applicable | failed
  basis       list[str]     ids of the observations, detectors or analyses used
  examples    list[Example] already exposed (mask, hide, show)
  overlaps    list[str]     codes whose set is proven to overlap, else empty
```

Catalogue entries (in `catalog.py`) have `code`, `cls`, `status`
(`active` or `recommended`), `unit`, `population kind`, `algorithm reference`,
`prerequisites`. A `recommended` entry produces nothing in a real report
(CA-29). No rule without an algorithm and a threshold is activated (B.1 of the
specification).

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
  `occurrences`.

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

The mapping from the Scan: detector `state` `complete` with no invalid gives
`none_detected` when `tested == eligible`, else `partial`; `disabled` gives
`not_assessed`; `not_applicable` gives `not_applicable`; `failed` gives `failed`.
`adaptive` with `not_tested > 0` gives `partial`.

### 6.5 Deduplication

Distinct proofs are kept. Two findings are presented as one only when the
overlap is proven: same rule, same scope, same population, or an observation
that carries the covered record indices (RF-24, CA-26). Two counts of 36 prove
nothing. No deduplicated total is fabricated. `overlaps` stays empty without
proof.

### 6.6 L0 findings, from existing facts only

| Class | Findings | Existing source |
| --- | --- | --- |
| Missing | the five components `absent`, `null`, `empty`, `blank`, `marker` | `missing.components` |
| Error | impossible calendar dates in an established Temporal field | `date` detector `invalid`, `temporal` |
| Error | `invalid` of a detector whose semantics is established (Email, Phone, Postal code, URL, IP address, UUID) | `detectors[].coverage.invalid` |
| Error | values outside the family of an established technical type | `technical_type.outside_count` (re-qualifies `type_error_count`, section 9) |
| Issue | ambiguous dates | observation `ambiguous_dates` |
| Issue | ambiguous numbers | `number` detector `ambiguous` |
| Issue | case variants | observation `variant_groups` |
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

### 6.7 Entry points

Fixed here so the contract tests can target them (R5 may add helpers, not
rename these):

- `tabalyst.report_findings.column_findings(column: ColumnView) -> ColumnFindings`
  where `ColumnFindings` has `missing: MissingFinding`, `errors: FindingList` and
  `issues: FindingList`. A `FindingList` has `items: list[Finding]` and `state`
  (the evaluation state of 6.4, `detected` when `items` is not empty).
- `tabalyst.scanner.classify.classify_field(field, context) -> Classification`
  (first pass) and `classification_versions() -> tuple[int, ...]`.
- `tabalyst.report_classification.refine(field, analyses) -> Classification`
  (R4).

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
- Report: `columns[].classification`, the final version (R4), in revision 4.
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
  and `NAME_RULES_VERSION`: a function `classification_versions()` in
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
  (R1a: `{"catalogue": 1}`; R2 adds `"names"`), so the value is in the Scan
  document and not only in each classification. `classification_versions()`
  returns the tuple in the order of `catalog.VERSION_NAMES`, `version_record()`
  the dict. `Classification.rule_version` is the catalogue version in R1a; R2
  decides how the name rules version combines with it.

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
| `report_profile.py:491` `semantic_type()`, `:683`, `:950` to `:995` | builds the value and the counts | R4 | replace by the classification block and counts |
| `models.py:151`, `:178`, `:179` | `ColumnProfile.semantic_type`, `DatasetSummary.semantic_type_counts`, `semantic_type_percents` | R4 | remove, add the classification and counts |
| `reporting.py:370` | `semantic_colors` palette | R9a | replace by family colours inside the existing themes |
| `templates/report.html` (columns table, dashboard card, filters, `data-pill`) | Semantic type column and filter | R9a | eight columns |
| `templates/column.html:50`, `:51`, `:57` | Interpretation card shows the semantic type and detector rows | R10 | show family, type and evidence |
| `schemas/tabalyst.report.schema.json` | generated | R4 | regenerate |
| `docs/en/report/json-profile.md`, `read-report.md`, `reference/types-and-patterns/types.md`, `patterns.md`, `report/index.md`, `scan/index.md`, `reference/glossary.md` | wording and tables | R4, R11 | rewrite |
| `tests/test_reporting.py:294`, `tests/scan/test_scan_report.py` | `column.semantic_type == "enumeration"` | R4 | replace by classification assertions |
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
| R1b | 3.3, 3.5 | CA-10, M/F stays Enum, two credible candidates, no bare-number Currency or Percentage |
| R2 | 5 | CA-12, CA-22, CA-23, units of the dictionary, no substring, name alone never established |
| R3 | 3.7, 3.8 | CA-04, CA-05, CA-06, CA-07, partial scan, JSON array |
| R4 | 4, 9 | refinement, absent or stale Deep, rendering without the source |
| R5 | 6 | CA-14, CA-16, CA-17, CA-18, CA-26, CA-29, CA-30, A,A,A,B |
| R6a | 6.6 | CA-11, CA-13, CA-21, CA-30 |
| R6b | 6.6 | CA-14, CA-15, CA-26 |
| R7, R8 | 7.1, 7.2 | CA-25, CA-19, CA-28 |
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

- Thresholds for the trait `high_cardinality`: defined in R3 from the tracked
  limits.
- Exact `type` code for the Text with an undetermined length (`text`): confirm
  with the label in the Type filter (R9a).
- Backlog: L1a types, L1b rarity, L1c single-column controls, L2 declared
  constraints (`basis = declared`), L3 history and drift.
