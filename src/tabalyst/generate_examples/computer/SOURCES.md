# Computer catalog provenance

This development catalog uses real brand, family, and model names. Generations
use published codes where available and a model-year label otherwise.
The selected technical configurations, compatibility links, physical templates,
weights, prices, and offers are illustrative test data. They do not claim to
reproduce a manufacturer's exact SKU or published configuration. IDs are stable
internal keys; English and French labels are presentation values.

Representative manufacturer references for edition names and underrepresented
device types: [Lenovo ThinkPad P14s Gen 5](https://psref.lenovo.com/syspool/Sys/PDF/ThinkPad/ThinkPad_P14s_Gen_5_Intel/ThinkPad_P14s_Gen_5_Intel_Spec.PDF),
[HP ZBook Firefly 14 G11](https://support.hp.com/rs-en/document/ish_10284082-10284129-16),
[ASUS NUC 14 Pro](https://press.asus.com/news/press-releases/asus-unveils-nuc-14-pro-latest-mini-pc-release),
[Apple Mac Studio with M4 Max](https://www.apple.com/newsroom/2025/03/apple-unveils-new-mac-studio-the-most-powerful-mac-ever/),
[Supermicro SYS-221H-TNR](https://www.supermicro.com/en/products/system/hyper/2u/sys-221h-tnr),
[Raspberry Pi 5](https://www.raspberrypi.com/products/raspberry-pi-5/), and
[Samsung Galaxy Book5 Pro 14](https://news.samsung.com/us/samsung-diversifies-ai-pc-lineup-with-new-galaxy-book5-pro-galaxy-book5-360-ces2025/).

The starting catalog did not supply complete executable relations. This
package gives every model at least one edition with seven technical-choice
relations and physical specifications for the 70/111-column profiles.

The package has illustrative technical components and tested compatibility and
preference weights. Computer derives specifications and synthetic offer values
from the selected catalog IDs, then writes paired localized CSVs from each
internal offer.

The base type weights are 40:25:8:12:5:10 for laptop, desktop, all-in-one,
mini PC, single-board computer, and server. The `portable_only` generation
profile excludes every non-laptop branch. These are fixture choices, not
measured market proportions.

The seven generation tables give at least one candidate per technical field. Four
influence tables model CPU, GPU, and segment preferences. GPU/display and
CPU/operating-system relations restrict supported pairs. Global exclusions
restrict implausible segment/component combinations. Every number is synthetic and
intended to make selection behavior testable, not to estimate real hardware
or sales frequencies.

CPU and GPU brand, family, and model are explicit catalog attributes. The
display type, touch flag, and numeric component capacities are explicit too. The lot 6
price, stock, release date, rating, and review rules are synthetic fixtures;
they are not observations about real products, stores, or markets.

The standard profile adds category/subcategory labels and one typed
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
