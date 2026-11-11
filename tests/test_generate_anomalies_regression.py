# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Pin the bytes of every shipped anomaly profile so engine changes cannot alter them.

The dirty_stress profile of Insurance (lot G2) was added after the others, with the
digests of its first accepted output.
"""

from __future__ import annotations

import hashlib
from importlib.resources import files
from pathlib import Path

import pytest

from tabalyst import __version__
from tabalyst.generate_service import build_generate_plan, generate_datasets

EXAMPLES = Path(str(files("tabalyst").joinpath("generate_examples")))

# (example, rows, extra build arguments, profile)
CASES = {
    "crm-dirty_realistic": ("crm", 500, {}, "dirty_realistic"),
    "crm-rule_breaks": ("crm", 500, {}, "rule_breaks"),
    "insurance-rule_breaks": ("insurance", 3000, {}, "rule_breaks"),
    "computer-rule_breaks": ("computer", 500, {"output_profile": "extended"}, "rule_breaks"),
    "insurance-dirty_realistic": ("insurance", 3000, {}, "dirty_realistic"),
    "insurance-dirty_stress": ("insurance", 3000, {}, "dirty_stress"),
    "computer-dirty_realistic": ("computer", 500, {"output_profile": "extended"}, "dirty_realistic"),
    "computer-dirty_stress": ("computer", 500, {"output_profile": "extended"}, "dirty_stress"),
    "computer-unit_variants": ("computer", 500, {"output_profile": "extended"}, "unit_variants"),
    "computer-unit_variants_extended": (
        "computer", 500, {"output_profile": "extended"}, "unit_variants_extended"),
}

EXPECTED: dict[str, dict[str, str]] = {
    "computer-dirty_realistic": {
        "computers-en.csv":
            "5a8274c1618c38637d040792a85b1864d54f68bd360a860eb82ea66cd9b51458",
        "computers-en.dirty_realistic.changes.csv":
            "5951bce86f7bc53566e1e306d254182d0b0899c1e0725664a14e174a240f8f81",
        "computers-en.dirty_realistic.csv":
            "362e383056d5a6bbde8590e474c01454c9a4c815abe6baf744c86eaf7cf9575f",
        "computers-en.dirty_realistic.summary.json":
            "cdb5982cec0e5cb23ec5562ce444bbf031518931b50d3878346eb42cebfebe60",
        "computers-fr.csv":
            "c031494c6faab85a9b38ca14fba04364118afcc1550b1c7abae67df327ceb3e3",
        "computers-fr.dirty_realistic.changes.csv":
            "838b2fde6eecab11408701bbba4279c3125879b805fe4d80110e1c2261cceb59",
        "computers-fr.dirty_realistic.csv":
            "433944e4a1a8bfec4a02b5933230720ad4037328c0968d84056f9f21e3bb02b3",
        "computers-fr.dirty_realistic.summary.json":
            "1b160d513232ed260b6661e9113a39a78ce61177840d56f2e9da3a6a5fc008ff",
    },
    "computer-dirty_stress": {
        "computers-en.csv":
            "5a8274c1618c38637d040792a85b1864d54f68bd360a860eb82ea66cd9b51458",
        "computers-en.dirty_stress.changes.csv":
            "5e9ce0c5b904b8ce515fba3a472d0238e4daf0bfaf0549ff06f5b18a627356a9",
        "computers-en.dirty_stress.csv":
            "6736e44a400481d16a6248827d9a9cca3372ad2228ba4b3a29eb88364df0e41e",
        "computers-en.dirty_stress.summary.json":
            "76e1617f2eb8597ff38d5d5f54453385cffd99de4196679e309b523136096bfc",
        "computers-fr.csv":
            "c031494c6faab85a9b38ca14fba04364118afcc1550b1c7abae67df327ceb3e3",
        "computers-fr.dirty_stress.changes.csv":
            "6edef7a330d10547a8a1119f1bb90a1a104a9c5e14b0608a07b5a120f138bba8",
        "computers-fr.dirty_stress.csv":
            "61710cff0168c9f987e898643dba3b8b2fd44c4f83eb1e235aa40b87d4b9ad06",
        "computers-fr.dirty_stress.summary.json":
            "8a41579a21a1d628034e829e8eb9ff3aaf244c62e13cae76c866a941fdacf620",
    },
    "computer-rule_breaks": {
        "computers-en.csv":
            "5a8274c1618c38637d040792a85b1864d54f68bd360a860eb82ea66cd9b51458",
        "computers-en.rule_breaks.changes.csv":
            "58ae418337cc710f9639826e6676e320095484b74fde5f600011697cd8cce2dc",
        "computers-en.rule_breaks.csv":
            "23330f9438d41123ea5dabf57c0b0ca8456ecf9d1524ec97b15582a01782709c",
        "computers-en.rule_breaks.summary.json":
            "1bcd1010556197327bbced5ea7a7e6b5304c9f82ae7c05c8a1f86cd6ac8bbe4e",
        "computers-fr.csv":
            "c031494c6faab85a9b38ca14fba04364118afcc1550b1c7abae67df327ceb3e3",
        "computers-fr.rule_breaks.changes.csv":
            "58ae418337cc710f9639826e6676e320095484b74fde5f600011697cd8cce2dc",
        "computers-fr.rule_breaks.csv":
            "0625120555fc0431b66598d63994816e6631afb111908d97843f232ae688d51c",
        "computers-fr.rule_breaks.summary.json":
            "f842aaabb298fc0934b4b81e118ae048a94ba045ed8b0d0911e5e54a471a7da6",
    },
    "computer-unit_variants": {
        "computers-en.csv":
            "5a8274c1618c38637d040792a85b1864d54f68bd360a860eb82ea66cd9b51458",
        "computers-en.unit_variants.changes.csv":
            "99f84c30b2b255001fc65f318eaf8f07bdfdee7621b2f2690715567448814b23",
        "computers-en.unit_variants.csv":
            "17fe847d4d71df2c080710d499bd61509969494c81d278be54ce52d942ffb9b9",
        "computers-en.unit_variants.summary.json":
            "94db7111a4b89b9b95f4ff3287a1f196a112ea960c98a9d19e3c4d3e16724a8e",
        "computers-fr.csv":
            "c031494c6faab85a9b38ca14fba04364118afcc1550b1c7abae67df327ceb3e3",
        "computers-fr.unit_variants.changes.csv":
            "738258210eb424a0bc917d3e0ea04dcb08fa6545dd721f83752d41b11f6e2988",
        "computers-fr.unit_variants.csv":
            "5ca9bab2a9231a11edd855568c811511d6c240bd3cd642e6547838fa36497369",
        "computers-fr.unit_variants.summary.json":
            "72fcfe8849db2bdb3414b0c677e8aab4e4bcb9d7526a235faad3f8721d8e5608",
    },
    "computer-unit_variants_extended": {
        "computers-en.csv":
            "5a8274c1618c38637d040792a85b1864d54f68bd360a860eb82ea66cd9b51458",
        "computers-en.unit_variants_extended.changes.csv":
            "6f0087e1d53d0b7c8d9db80668ae231d08d3980d8076d0c0da7eafea87d82142",
        "computers-en.unit_variants_extended.csv":
            "539333f44cd016583f7147dc99558901c4461996897fd82096cdb776d865abcd",
        "computers-en.unit_variants_extended.summary.json":
            "d0fcd56ce0cbd89a9558fdc048a2a9b64ab492be15332c0e8e2f3b759f2cc2e5",
        "computers-fr.csv":
            "c031494c6faab85a9b38ca14fba04364118afcc1550b1c7abae67df327ceb3e3",
        "computers-fr.unit_variants_extended.changes.csv":
            "3da5931bc505f81a86f9b9796645f00daad7a6b67d7ddda73c2320df73086e26",
        "computers-fr.unit_variants_extended.csv":
            "3992f60a10c36c4c1aae9c560fe329552656ffeb89440342a69f26291c0b0128",
        "computers-fr.unit_variants_extended.summary.json":
            "ff3bf956e4802d0940f22acf8ba39f3fde95d1da08bba5700f5fe11695ba43d1",
    },
    "crm-dirty_realistic": {
        "crm-contacts.csv":
            "bb99a3736d762a03f7b1be81781df404d454a55e783eaed01cf4f4b4e203dfcf",
        "crm-contacts.dirty_realistic.changes.csv":
            "5838e9c1e8038ac784dce83dd677e28c0efca9d0177816ab65762439213bf109",
        "crm-contacts.dirty_realistic.csv":
            "9f39710ab91ea188bdd899cee7828e3b47f0c1ed36714133eeaa4400ce5d90fb",
        "crm-contacts.dirty_realistic.summary.json":
            "7c6719f9adfbab1da97c52d8518e32c9c21f254575f5c51dd07f5ff771a0ee40",
    },
    "crm-rule_breaks": {
        "crm-contacts.csv":
            "bb99a3736d762a03f7b1be81781df404d454a55e783eaed01cf4f4b4e203dfcf",
        "crm-contacts.rule_breaks.changes.csv":
            "7faefb0e627de24bc6ddbf29e8a0c86d365d4f0c734ed9e4830b67c5b0c10d0e",
        "crm-contacts.rule_breaks.csv":
            "b851eaf11fed42c2bde7d2e8fd0e5f92cc5b4db938a40124d624dcd6ca30959c",
        "crm-contacts.rule_breaks.summary.json":
            "e0641c38cbae7d2f117bb00a59fada49e717e0e366b8d446f9648a538f8c6909",
    },
    "insurance-dirty_realistic": {
        "insurance-combined.csv":
            "a012c2832926b85332df9370a3814af4dcb92d8671113a4cf5039038d053afef",
        "insurance-combined.dirty_realistic.changes.csv":
            "2ba6dd0b153c67358d632194f0069f64a89d60abf86ec3d2c9307cfac96119bc",
        "insurance-combined.dirty_realistic.csv":
            "15f140afb381c52c1e0044a931e828833b3a4d96c697da44433845fd2bbb2916",
        "insurance-combined.dirty_realistic.summary.json":
            "b45e9265584a810756b02c1d1a65d564ccd7c5667bbe2ce21f61aa51d6046d43",
        "insurance-ontario.csv":
            "2df6a543b016b6dc0de720827b0d688dbfa4dc9b773aac33635e76b808361066",
        "insurance-principal.csv":
            "eb59985ff105eed321500a0df2304b86dc7cc31d8cc95c28f5c05e752afb5bea",
        "insurance-quebec.csv":
            "c9af71aefa79e17056f375e4e88ef71fdd803504679b7fcf4e647d4d68e26e88",
    },
    "insurance-dirty_stress": {
        "insurance-combined.csv":
            "a012c2832926b85332df9370a3814af4dcb92d8671113a4cf5039038d053afef",
        "insurance-combined.dirty_stress.changes.csv":
            "da834c3fca763822a8c7428d303ee464357b7101d7eb5fab2a692161ee80d78f",
        "insurance-combined.dirty_stress.csv":
            "562cc6d49b723456ad1119a260343804e2a036a124fa3e73049f57f589094e0d",
        "insurance-combined.dirty_stress.summary.json":
            "c9089a9c725acf3d97822a3dab1255fa666379f87a38e616225dc270f941bf12",
        "insurance-ontario.csv":
            "2df6a543b016b6dc0de720827b0d688dbfa4dc9b773aac33635e76b808361066",
        "insurance-principal.csv":
            "eb59985ff105eed321500a0df2304b86dc7cc31d8cc95c28f5c05e752afb5bea",
        "insurance-quebec.csv":
            "c9af71aefa79e17056f375e4e88ef71fdd803504679b7fcf4e647d4d68e26e88",
    },
    "insurance-rule_breaks": {
        "insurance-combined.csv":
            "a012c2832926b85332df9370a3814af4dcb92d8671113a4cf5039038d053afef",
        "insurance-combined.rule_breaks.changes.csv":
            "7b03f8ac61a37db384574613703470b9dde2dabad450ca42b63f6c2610727099",
        "insurance-combined.rule_breaks.csv":
            "88effb23db706520c8769b1d0504ceb182a87b6125c985396170e8c0d439740f",
        "insurance-combined.rule_breaks.summary.json":
            "68820e51ee60d9d4de7e2565fb3f9da43e302e02a08155c01853e383865c1b02",
        "insurance-ontario.csv":
            "2df6a543b016b6dc0de720827b0d688dbfa4dc9b773aac33635e76b808361066",
        "insurance-principal.csv":
            "eb59985ff105eed321500a0df2304b86dc7cc31d8cc95c28f5c05e752afb5bea",
        "insurance-quebec.csv":
            "c9af71aefa79e17056f375e4e88ef71fdd803504679b7fcf4e647d4d68e26e88",
    },
}


def collect(case: str, directory: Path) -> dict[str, str]:
    """Generate one profile and return the SHA-256 of each artifact by file name.

    The summary carries the Tabalyst version, which changes at every release, so
    its digest is taken with that value masked.
    """
    example, rows, extra, profile = CASES[case]
    generate_datasets(build_generate_plan(
        EXAMPLES / example, rows=rows, seed=42, anomaly_profile=profile,
        output_dir=directory, **extra,
    ))
    digests: dict[str, str] = {}
    for path in sorted(directory.iterdir()):
        if path.name.endswith(".meta.json"):
            continue  # records engine and resource digests, not the anomaly output
        data = path.read_bytes()
        if path.name.endswith(".summary.json"):
            data = data.replace(__version__.encode(), b"<version>")
        digests[path.name] = hashlib.sha256(data).hexdigest()
    return digests


@pytest.mark.parametrize("case", sorted(CASES))
def test_shipped_anomaly_profiles_keep_their_bytes(case: str, tmp_path: Path) -> None:
    """Existing profiles (rate based, no class) write the same files as before the lot G1."""
    assert collect(case, tmp_path) == EXPECTED[case]
