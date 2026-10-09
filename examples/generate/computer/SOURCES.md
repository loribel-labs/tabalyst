# Computer catalog provenance

This development catalog is fictional. All brands, families, models, and
generations were invented for Tabalyst tests. IDs are stable internal keys;
English and French labels are presentation values. No row claims to describe
a real product or manufacturer.

The package has fictional technical components and tested compatibility and
preference weights. Computer derives specifications and synthetic offer values
from the selected catalog IDs, then writes paired localized CSVs from each
internal offer.

The base type weights are laptop:desktop = 3:1. The `portable_only` generation
profile excludes the desktop branch. These are fixture choices, not measured
market proportions.

The seven generation tables give two candidates per technical field. Four
influence tables model CPU, GPU, and segment preferences. GPU/display and
CPU/operating-system relations restrict supported pairs. Global exclusions
reject discrete graphics with 16 GB memory. Every number is synthetic and
intended to make selection behavior testable, not to estimate real hardware
or sales frequencies.

CPU and GPU brand, family, and model are explicit catalog attributes. The
display type, touch flag, and numeric component capacities are explicit too. The lot 6
price, stock, release date, rating, and review rules are synthetic fixtures;
they are not observations about real products, stores, or markets.

The standard profile adds fictional category/subcategory labels and one typed
specification row per model generation. CPU and display attributes remain in
their component tables. `none` is a real category for unsupported features;
only an inapplicable battery uses an empty cell. Price tier, lifecycle state,
keyboard layout and offer language are deterministic synthetic derivations.

The in-development extended profile adds 25 hardware fields from the
contractual register. Display ratio, HDR, and gamut belong to the selected
panel; NPU identity belongs to the CPU and is absent when it has zero TOPS.
The other connectivity, expansion, dimension, chassis, and multimedia
attributes belong to a generation specification row. Slot use cannot exceed
capacity, the Ethernet port agrees with its declared speed, and notebook and
desktop dimensions and keyboard types follow their form. Copilot Plus is a
synthetic threshold flag derived from NPU TOPS, not a real certification.
The remaining 16 extended fields are deterministic fictional commerce and
distribution signals. Seller and warehouse dictionaries are market-specific;
promotion and shipping labels have English and French forms. Prices summarize
a synthetic 30-day history in the offer currency, while sales, conversion and
returns are bounded illustrative quantities. They are not measured market
statistics or claims about actual sellers.
