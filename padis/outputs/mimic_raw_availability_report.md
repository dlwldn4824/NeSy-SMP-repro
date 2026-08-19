# MIMIC-IV raw availability (Phase 1)

DB: `C:\Users\dlwld\Downloads\MIMIC4-hosp-icu.db`

## Coverage summary (adult ICU admissions, based on `icustays` + `patients.anchor_age>=18`)
- total_adult_icu_admissions: 85242
- mechanically_ventilated_hadm: 37589
- mechanically_ventilated_ratio: 0.44096806738462263
- rass_hadm: 433
- rass_ratio: 0.0050796555688510355
- cam_icu_hadm: 66005
- cam_icu_ratio: 0.7743248633302832
- ventilation_and_rass_and_cam_hadm: 260
- ventilation_and_rass_and_cam_ratio: 0.003050139602543347
- sedative_exposure_hadm: 53469
- sedative_exposure_ratio: 0.6272612092630393
- ventilation_and_rass_and_cam_and_sedative_hadm: 198
- ventilation_and_rass_and_cam_and_sedative_any_hadm: 242
- ventilation_and_rass_and_cam_and_sedative_any_ratio: 0.0028389760915980386
- ventilation_and_rass_and_cam_and_sedative_plus_opioid_hadm: 249
- ventilation_and_rass_and_cam_and_sedative_plus_opioid_ratio: 0.0029210952347434363

## Per-variable availability
- RASS: availability=available_in_raw_mimic (hadm=433)
  - itemids_found=1 sample=[228302]
- CAM-ICU: availability=available_in_raw_mimic (hadm=66005)
  - itemids_found=15 sample=[228300, 228301, 228302, 228303, 228334, 228335, 228336, 228337, 229324, 229325]
- MechanicalVentilation: availability=available_in_raw_mimic (hadm=37589)
  - itemids_found=8 sample=[223848, 223849, 225303, 225792, 225794, 227565, 227566, 229314]
- Propofol: availability=available_in_raw_mimic (hadm=30586)
  - rows_matched=68205 drug_patterns=['propofol']
- Dexmedetomidine: availability=available_in_raw_mimic (hadm=10771)
  - rows_matched=18028 drug_patterns=['dexmedetomidine', 'dexmed', 'precedex']
- Benzodiazepines: availability=available_in_raw_mimic (hadm=39172)
  - rows_matched=334063 drug_patterns=['lorazepam', 'midazolam', 'diazepam', 'benzodiazep']
- Opioids: availability=available_in_raw_mimic (hadm=56413)
  - rows_matched=641628 drug_patterns=['morphine', 'fentanyl', 'hydromorphone', 'opioid']
- HR: availability=available_in_raw_mimic (hadm=85241)
  - itemids_found=3 sample=[220045, 220046, 220047]
- RR: availability=available_in_raw_mimic (hadm=85234)
  - itemids_found=113 sample=[220210, 220866, 223780, 223828, 223881, 224019, 224076, 224345, 224348, 224422]
- SpO2: availability=available_in_raw_mimic (hadm=85213)
  - itemids_found=18 sample=[220227, 220277, 223769, 223770, 226253, 226860, 226861, 226862, 226863, 226865]
- BP: availability=available_in_raw_mimic (hadm=85190)
  - itemids_found=25 sample=[220050, 220051, 220052, 220056, 220058, 220059, 220060, 220179, 220180, 224167]
