# prep/tests fixtures

Small excerpts of public NASA files, committed so the tests run without `REDMARK_DATA`. The full files are listed with checksums in `prep/data-manifest.yaml`.

| File | Excerpt of | Source |
| --- | --- | --- |
| `m20_heli_waypoints.json` | Waypoints of flights 8 to 10 | https://mars.nasa.gov/mmgis-maps/M20/Layers/json/m20_heli_waypoints.json (NASA/JPL-Caltech) |
| `m20_heli_flight_path.json` | Paths of flights 9 and 10 | https://mars.nasa.gov/mmgis-maps/M20/Layers/json/m20_heli_flight_path.json (NASA/JPL-Caltech) |
| `collection_data_inventory.csv` | 20 rows, sols 133 and 152 | https://pds-imaging.jpl.nasa.gov/data/mars2020/mars2020_helicam/data/collection_data_inventory.csv |
| `HNM_0152_0680432615_348FDR_N0100001HELI03026_0000LUJ05.xml` | One whole Navcam label, flight 10 | https://pds-imaging.jpl.nasa.gov/data/mars2020/mars2020_helicam/data/sol/00152/ids/fdr/heli/ |

The Helicam files are from the Mars 2020 Helicopter Camera bundle, NASA PDS Imaging Node, NASA/JPL-Caltech.
