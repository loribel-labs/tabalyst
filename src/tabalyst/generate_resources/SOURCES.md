# Common Generate reference provenance

These 13 UTF-8 CSV tables are bundled for synthetic data generation. Their
`weight` fields are editorial relative weights, not official statistics.
The generated addresses are fictional and are not verified deliverable addresses.

| Table | Provenance and redistribution |
| --- | --- |
| `people/first_names_fr_qc.csv` | Project editorial selection, 2026-09-16; project data. |
| `people/first_names_en_ca.csv` | Project editorial selection, 2026-09-16; project data. |
| `people/family_names_ca.csv` | Project editorial selection, 2026-09-16; project data. |
| `geography/provinces_ca.csv` | Editorial province labels and weights, based on [Natural Resources Canada geographical names](https://natural-resources.canada.ca/maps-tools-publications/maps/geographical-names-canada/download-geographical-names-data), Open Government Licence – Canada. |
| `geography/cities_ca.csv` | Editorial subset of Canadian place names, regions, profiles and weights, based on the same Natural Resources Canada source and licence. |
| `geography/postal_prefixes_ca.csv` | **Replaced.** The prototype attributed real forward sortation areas to Canada Post and Statistics Canada; redistribution of that mixed subset was not established. This table is generated editorially, one synthetic prefix per city, preserving city/province links and Canadian syntax. It is not a postal directory. |
| `addresses/street_types_ca.csv` | Project editorial selection, 2026-09-16; project data. |
| `addresses/street_names_ca.csv` | Project synthetic names, 2026-09-16; project data. |
| `addresses/street_directions_ca.csv` | Project editorial selection, 2026-09-16; project data. |
| `addresses/unit_types_ca.csv` | Project editorial selection, 2026-09-16; project data. |
| `contact/email_providers_ca.csv` | Project editorial selection, 2026-09-16; runtime uses only reserved `.example` domains. |
| `contact/email_patterns.csv` | Project synthetic templates, 2026-09-16; project data. |
| `contact/phone_area_codes_ca.csv` | **Replaced.** The prototype attributed real area codes to CNAC, whose redistribution terms were not established. This table uses distinct editorial, synthetic 2xx codes per province. Numbers use NANPA's reserved `555-0100`–`555-0199` fiction range. Codes are not a directory of assigned area codes. |

Natural Resources Canada data is offered under the [Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada). Contains information licensed under the Open Government Licence – Canada. This project is not endorsed by the data provider.

The [Statistics Canada 2021 FSA reference guide](https://www150.statcan.gc.ca/n1/pub/92-179-g/92-179-g2021001-eng.htm) identifies Canada Post content within its product. [Canada Post's service terms](https://www.canadapost-postescanada.ca/cpc/en/support/kb/company-policies/terms-conditions/legal-terms-of-use-and-conditions.page) limit reuse of postal lookup data. The prototype's provenance did not identify which individual prefixes came from which source. The postal table was therefore rebuilt rather than copied. [NANPA](https://www.nanpa.com/numbering/555-line-numbers) identifies the fiction range used for line numbers.

The source prototype manifest is `tabalyst-generate/resources/common/SOURCES.md` (2026-09-16). Imported project tables retain their text and weights. The two replacement tables retain the original schemas but have synthetic identifiers and intentionally reduced coverage: 71 postal prefixes (one per city) and 13 area codes (one per province).
