# prep/tests fixtures

Small excerpts of public NASA files, committed so the tests run without `REDMARK_DATA`. The full files are listed with checksums in `prep/data-manifest.yaml`.

| File | Excerpt of | Source |
| --- | --- | --- |
| `m20_heli_waypoints.json` | Waypoints of flights 8 to 10 | https://mars.nasa.gov/mmgis-maps/M20/Layers/json/m20_heli_waypoints.json (NASA/JPL-Caltech) |
| `m20_heli_flight_path.json` | Paths of flights 9 and 10 | https://mars.nasa.gov/mmgis-maps/M20/Layers/json/m20_heli_flight_path.json (NASA/JPL-Caltech) |
| `collection_data_inventory.csv` | 20 rows, sols 133 and 152 | https://pds-imaging.jpl.nasa.gov/data/mars2020/mars2020_helicam/data/collection_data_inventory.csv |
| `HNM_0152_0680432615_348FDR_N0100001HELI03026_0000LUJ05.xml` | One whole Navcam label, flight 10 | https://pds-imaging.jpl.nasa.gov/data/mars2020/mars2020_helicam/data/sol/00152/ids/fdr/heli/ |
| `apxs_concentrations_3193_4133_excerpt.csv` | The header, with its Notes column, and the first row (Bregout, sol 3194), whose source files name sol 3900 | https://pds-geosciences.wustl.edu/msl/msl-m-apxs-4_5-rdr-v1/mslapx_1xxx/extras/msl_apxs_concentrations_3193_4133.csv |
| `apxs_concentrations_4489_4612_excerpt.csv` | The header and 2 rows (sols 4498 and 4500) | https://pds-geosciences.wustl.edu/msl/msl-m-apxs-4_5-rdr-v1/mslapx_1xxx/extras/msl_apxs_concentrations_4489_4612.csv (MSL APXS RDR, NASA/JPL-Caltech, PDS Geosciences Node) |
| `apxs_concentrations_4710_4843_excerpt.csv` | The header, which names the source-file column, and the last row (sol 4842) | https://pds-geosciences.wustl.edu/msl/msl-m-apxs-4_5-rdr-v1/mslapx_1xxx/extras/msl_apxs_concentrations_4710_4843.csv |
| `places_localized_interp_excerpt.csv` | 8 rows of PLACES' every-drive positions: the APXS stops above, the last pose before sol 3194 and the pose Bregout's files name, site 114's SITE row, and the two poses of drive 121/0 | https://planetarydata.jpl.nasa.gov/img/data/msl/msl_places/data_localizations/localized_interp.csv (MSL PLACES localization archive, NASA/JPL-Caltech, PDS Imaging Node) |
| `places_localized_pos_excerpt.csv` | 11 rows of Curiosity's PLACES positions: the landing, sols 299 and 1800, and the boxwork drive (sols 4600 to 4662) | https://planetarydata.jpl.nasa.gov/img/data/msl/msl_places/data_localizations/localized_pos.csv (MSL PLACES localization archive, NASA/JPL-Caltech, PDS Imaging Node) |

The Helicam files are from the Mars 2020 Helicopter Camera bundle, NASA PDS Imaging Node, NASA/JPL-Caltech.
