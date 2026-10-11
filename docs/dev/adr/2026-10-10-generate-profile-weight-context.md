# Make the generation profile available to catalog weights

Status: accepted on 2026-10-10 for the development package format.

## Context

Computer's named generation profiles carry weights for computer types and
product segments. The catalog selector previously used a profile only to scope
exclusions. An influence relation could read only fields selected by earlier
steps, so neither of the first two choices could depend on the profile.

## Decision

Expose `generation_profile_id` as reserved execution context to catalog steps
when the package declares generation profiles. Relation `where` mappings may
refer to it before the first selection. Its value is the requested profile ID,
or an empty string for an unscoped selection, and it is removed from the
selected row. Profile weight tables use the same positive multiplicative
influence rule as other weighted relations; missing rows contribute factor 1.
Computer's base type weights are neutral so the profile tables express the
type proportions directly. `portable_only` remains an exclusion profile, and
`mixed` has no preference rows.

## Consequences

Packages can condition early choices on a profile without adding a generated
column or provider code. Profile weights do not prohibit unspecified types or
segments; strict restrictions still require constraints. Existing packages
without profile-aware relations keep their selection behavior.
