# Derive Computer category from the selected machine

Status: accepted on 2026-10-10 for the development Computer example.

## Context

The Computer catalog now includes laptops, desktops, all-in-ones, mini PCs,
servers, and single-board computers. A product segment such as `business` or
`workstation` can describe several machine types. Its former single
`product_subcategory_id` cannot classify every selected offer correctly.

## Decision

Keep segment as a market position. Derive the output subcategory from the
selected computer type, form factor, and segment, then read its category from
`product_subcategory.csv`. Use specific form factors and workstation/gaming
segments where they distinguish an existing catalog subcategory. Continue to
validate the referenced subcategory through the packaged dictionary.

## Consequences

An offer's category and subcategory describe its selected machine even when
multiple machine types share a segment. The mapping is Computer provider logic,
so adding a type or form factor requires updating that logic and its tests.
The package format and published examples are unaffected until release.
