# Retrieval error analysis

Best method by MRR: **es_hybrid_rerank** (2 misses out of 105 answerable questions).

## Misses by question category

- test_definition: 1
- comparison_support: 1

## Individual misses

### q026 (test_definition)
- Question: How is the data for colonoscopy waiting times collected?
- Expected: ['test-definition-COLONOSCOPY']
- Retrieved top 5: ['metric-waiting-six-weeks-or-longer', 'profile-NID-COLONOSCOPY', 'profile-RGP-COLONOSCOPY', 'profile-RN3-COLONOSCOPY', 'profile-RK9-COLONOSCOPY']

### q094 (comparison_support)
- Question: How much did the waiting list for non-obstetric ultrasound change from March to May 2026?
- Expected: ['profile-NT403-NON_OBSTETRIC_ULTRASOUND']
- Retrieved top 5: ['profile-NEM-NON_OBSTETRIC_ULTRASOUND', 'profile-AY1-NON_OBSTETRIC_ULTRASOUND', 'profile-NHA-NON_OBSTETRIC_ULTRASOUND', 'profile-NEP-NON_OBSTETRIC_ULTRASOUND', 'profile-NNV-NON_OBSTETRIC_ULTRASOUND']
