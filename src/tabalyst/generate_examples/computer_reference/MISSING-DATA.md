# Data still needed for an executable six-type Computer package

The source tables in `data/` are a transcription of the Computer brainstorm.
They are not an executable dataset definition. The current `../computer/`
package still generates its fictional two-branch fixture.

The brainstorm names six computer types but gives complete CPU, memory,
storage, GPU, display, color, and OS selection rows only for these generations:

- `thinkpad_t14_gen5`
- `thinkpad_t14_gen6`
- `legion_5_gen9`
- `legion_5_gen10`

All four are laptops. Seven other named generations lack one or more of those
seven selection tables. Twenty-six named models have no generation row. No
complete generation is supplied for `desktop`, `all_in_one`, `mini_pc`,
`single_board_computer`, or `server`.

For every generation intended for output, the following source rows are still
needed before it can replace the test fixture:

1. The seven weighted `generation_*` choice sets, with at least one compatible
   CPU, memory, storage, GPU, display, color, and operating system.
2. The physical and connectivity specifications used by the 70/111-column
   profiles (`standard_specs` and `extended_specs` in the current package),
   including a clear representation of inapplicable features for headless
   devices and servers.
3. Technical compatibility and exclusion rules for those choices. The seven
   exclusions in `configuration_constraint.csv` include fields that the
   current selector does not choose, such as `drive_bay_type` and
   `motherboard_form_factor`.
4. The intended interpretation of named real products: illustrative examples
   or manufacturer-verified specifications. The brainstorm alone does not
   establish factual accuracy.

No placeholder rows have been added for these gaps. The private Computer plan
records the exact implementation delta and the decision required to proceed.
