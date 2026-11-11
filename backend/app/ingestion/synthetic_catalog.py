"""Code-reviewed canonical fixture digests; client assertions cannot add entries.

This is a closed test catalog, not a rights registry or a production feature flag.
Changing it requires source review of the complete non-sensitive synthetic input.
"""

from types import MappingProxyType

# tests/fixtures/synthetic_imports.json; hashes cover every unmasked input field.
APPROVED_FIXTURES = MappingProxyType({
    "synthetic-phase2b-base": "c3df9eb0b4ebd36dc56abaf7bd400b84dbb95d8e6b7bd5db2fdd9b6a0183a7f6",
    "synthetic-phase2b-reacquisition": "cb5ec07349a15892cfb6ded29b60bb0ab05b3dc7fec3300615814c1850cecab8",
    "synthetic-phase2b-new-version": "d1b5acffcc8c983ac9eeea4fbbc5bab16370107ebba77edf27c1ca0b22790374",
    "synthetic-phase2b-same-content-new-key": "001ff88cb068c4a9a5b66c39fad343af313fbd9387f6e85585d85e9969233968",
    "synthetic-phase2b-within-batch": "1056fabd0420394ce6d058abbf0cdb9ea6c2a0c95394c8deefc313dd009a132a",
    "synthetic-phase2b-other-source": "181f8e74d0a35b963c670f845c3c8a6e8419ab2c7410f4b3fbdfadf3c2e0bf35",
    "synthetic-phase2b-reference": "ec581fe1b6cf7f33674fac00f8b318cf40a0519f64b2c227148da4a608959189",
})
