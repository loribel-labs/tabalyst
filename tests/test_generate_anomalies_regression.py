# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Pin the bytes of every shipped anomaly profile so engine changes cannot alter them."""

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
    "insurance-dirty_realistic": ("insurance", 3000, {}, "dirty_realistic"),
    "computer-dirty_realistic": ("computer", 500, {"output_profile": "extended"}, "dirty_realistic"),
    "computer-dirty_stress": ("computer", 500, {"output_profile": "extended"}, "dirty_stress"),
    "computer-unit_variants": ("computer", 500, {"output_profile": "extended"}, "unit_variants"),
    "computer-unit_variants_extended": (
        "computer", 500, {"output_profile": "extended"}, "unit_variants_extended"),
}

EXPECTED: dict[str, dict[str, str]] = {
    "computer-dirty_realistic": {
        "computers-en.csv":
            "c68820af90808f9a3c5a0d28d0edde857a414db995f45982090361d1d1e045ae",
        "computers-en.dirty_realistic.changes.csv":
            "edd76ab07306cd8ac41f903828d4af922af55dec55f13d910c9fc9bd92d6e044",
        "computers-en.dirty_realistic.csv":
            "ae00f39a40d94cb74361b4f3044a1a78ba7269ab07ab5617b037e5ee77932663",
        "computers-en.dirty_realistic.summary.json":
            "3cdd3167c13726015c15ca15e76e2e781a8799c19dff29bb539004e9d5b9af18",
        "computers-fr.csv":
            "bd7d7082ae3383e8040fba08418a1bcd0c5c11b19dd4d52f0cf378ade5304af4",
        "computers-fr.dirty_realistic.changes.csv":
            "edd76ab07306cd8ac41f903828d4af922af55dec55f13d910c9fc9bd92d6e044",
        "computers-fr.dirty_realistic.csv":
            "413b8f5324a25e7d8b1be79341599bc00e97634654ca7f23ebe88fcf84b0022f",
        "computers-fr.dirty_realistic.summary.json":
            "d3e58754b02b0f8896a270a1fdaaf578161e5925c9b5e6120d19c23511c79a72",
    },
    "computer-dirty_stress": {
        "computers-en.csv":
            "c68820af90808f9a3c5a0d28d0edde857a414db995f45982090361d1d1e045ae",
        "computers-en.dirty_stress.changes.csv":
            "e615e822086ba6a01861047307e2bdf5f0f564d098ddb3069613965dd2b3c6dc",
        "computers-en.dirty_stress.csv":
            "0e167732e901a8b7ade3bdef230300bc29d6e8da6e934e78901a362f2431800d",
        "computers-en.dirty_stress.summary.json":
            "8e3ab1b37d6db0dba9cb5927ef2ac2bd4f882ef5b15b581e34c9a950d2daeab3",
        "computers-fr.csv":
            "bd7d7082ae3383e8040fba08418a1bcd0c5c11b19dd4d52f0cf378ade5304af4",
        "computers-fr.dirty_stress.changes.csv":
            "e615e822086ba6a01861047307e2bdf5f0f564d098ddb3069613965dd2b3c6dc",
        "computers-fr.dirty_stress.csv":
            "bb4a91fcf23973a32e4d657a5e8d112e033386cdaa73df2304f3f699f7028487",
        "computers-fr.dirty_stress.summary.json":
            "4770eed22b0599523868825a5850bc0f5239456a72029328b4df877339be5aaf",
    },
    "computer-unit_variants": {
        "computers-en.csv":
            "c68820af90808f9a3c5a0d28d0edde857a414db995f45982090361d1d1e045ae",
        "computers-en.unit_variants.changes.csv":
            "99f84c30b2b255001fc65f318eaf8f07bdfdee7621b2f2690715567448814b23",
        "computers-en.unit_variants.csv":
            "3de64b71848016f226656436f6ad208b97329a4e634251f7d55def2e5aa9e9e1",
        "computers-en.unit_variants.summary.json":
            "94db7111a4b89b9b95f4ff3287a1f196a112ea960c98a9d19e3c4d3e16724a8e",
        "computers-fr.csv":
            "bd7d7082ae3383e8040fba08418a1bcd0c5c11b19dd4d52f0cf378ade5304af4",
        "computers-fr.unit_variants.changes.csv":
            "738258210eb424a0bc917d3e0ea04dcb08fa6545dd721f83752d41b11f6e2988",
        "computers-fr.unit_variants.csv":
            "96a09af60faf0e58cf8566abada5bdfeb0eaef7f25f59dbdfcde724a973c8545",
        "computers-fr.unit_variants.summary.json":
            "72fcfe8849db2bdb3414b0c677e8aab4e4bcb9d7526a235faad3f8721d8e5608",
    },
    "computer-unit_variants_extended": {
        "computers-en.csv":
            "c68820af90808f9a3c5a0d28d0edde857a414db995f45982090361d1d1e045ae",
        "computers-en.unit_variants_extended.changes.csv":
            "6f0087e1d53d0b7c8d9db80668ae231d08d3980d8076d0c0da7eafea87d82142",
        "computers-en.unit_variants_extended.csv":
            "afd11aa7d8d7befa5a0d9672a3e054e2dfed8d445605fbfd5efc1374355b7357",
        "computers-en.unit_variants_extended.summary.json":
            "d0fcd56ce0cbd89a9558fdc048a2a9b64ab492be15332c0e8e2f3b759f2cc2e5",
        "computers-fr.csv":
            "bd7d7082ae3383e8040fba08418a1bcd0c5c11b19dd4d52f0cf378ade5304af4",
        "computers-fr.unit_variants_extended.changes.csv":
            "3da5931bc505f81a86f9b9796645f00daad7a6b67d7ddda73c2320df73086e26",
        "computers-fr.unit_variants_extended.csv":
            "c1556d8c17170516c020bf3f0f5bfc3543147d0610e1eef93e6d48edbaf7fbf9",
        "computers-fr.unit_variants_extended.summary.json":
            "ff3bf956e4802d0940f22acf8ba39f3fde95d1da08bba5700f5fe11695ba43d1",
    },
    "crm-dirty_realistic": {
        "crm-contacts.csv":
            "6530498b8cb9a82b486dbcfcf93fa9c1e858e3f1aba465405629079f9f532a13",
        "crm-contacts.dirty_realistic.changes.csv":
            "c2bc99609fcd7cdbed65d4f4ff9440cf8270bec47ba5c250368a359582b26f70",
        "crm-contacts.dirty_realistic.csv":
            "d76cfd4d27a21a1139278607e431585afa30dc38fb521f07db0ed751f8106aca",
        "crm-contacts.dirty_realistic.summary.json":
            "0cac916b4f7af32a4224db6e5be29bc0925927dcbd3f015ebeba5bfd7c562621",
    },
    "insurance-dirty_realistic": {
        "insurance-combined.csv":
            "78273be501d01ee2f5bbf4e35b1a5fc0915b972e89d4913c986ec1009f16a5f8",
        "insurance-combined.dirty_realistic.changes.csv":
            "3c80139ef99efdbd97df9d2d848aaca9042ccf38b67270871d23e7031ef2f2f7",
        "insurance-combined.dirty_realistic.csv":
            "869b629b7f9695ddbe14d52861422c1a9c99d90a8d614d2ff82653777107a7ff",
        "insurance-combined.dirty_realistic.summary.json":
            "601527c74362dc3f5560ebcc5f4c96b9e5514b8a9adf4cd1e64e9cc1bce09994",
        "insurance-ontario.csv":
            "69252bca2b365c06213a94a01c840ae37406219834a995ffe24d8eb7059bd545",
        "insurance-principal.csv":
            "ae5323a64a906d0937cd54a787111e012b51d63cab99af67297c13c24d8ad3dc",
        "insurance-quebec.csv":
            "4ddd34572552035106d296168692652d65a69f1582dec66bdb523402b35e390e",
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
