# fda-drug-biologic-kg on FRINK, November 18, 2026

Tag v0.0.1 created November 18, 20:28 EST on stable_v0_0_1 (commit ba350292), built by FRINK from main 6df366cf. The pre-create-tag check and the post-create-tag deploy both completed.

Endpoint: https://apps.okn.us/fda-drug-biologic-kg/sparql

- Total triples on the endpoint: 55,365,710. VoID data triples: 55,352,200 (November 5 TDB2 count 55,352,190 plus the 10 triples of l2_stubs_faers.ttl). The remaining 13,510 are FRINK's VoID metadata.
- Battery (scripts/run_frink.py, one query at a time): 9 queries, all ok, each under 0.3 s.

| Query | Rows | Check against the November 5 local run |
|---|---|---|
| common_counts | 53 | same counts, except NdcPackage 711,147 (was 711,145): the 2 FAERS package stubs added November 9 |
| common_provenance | 31 | same |
| q1 applications seen in both views | 1 | same (29,383) |
| q2 TE codes | 15 | same (AB 17,802 first) |
| q3 shortage to application | 15 | ok. The query has LIMIT 15 and no ORDER BY, so the 15 rows shown are not the same rows. Not a difference in the data |
| q4 CRL with sponsor | 15 | same |
| q5 substance links | 5 | same |
| q6 Purple Book products by applicant | 15 | same (Amgen 110 first) |
| q7 stub nodes | 4 | same, except NdcPackage stubs 3,579 (was 3,577), the same 2 stubs |

Results on the VM: work/frinkq/results_fda-drug-biologic-kg.md.
