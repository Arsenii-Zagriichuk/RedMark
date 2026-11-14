# Synthetic Navcam fixture

`vicar-navcam.png` is a frozen 16-bit synthetic frame. Each pixel was
back-projected with NASA JPL's [VICAR CAHVORE reference implementation](https://github.com/NASA-AMMOS/VICAR/blob/1fc47be4745f279eac27ca4bbc8be0f55bb0bf59/vos/p2/sub/cahvor/cmod_cahvore.c)
using the flight 10 PDS label from `prep/tests/fixtures/`. The label was
parsed with ElementTree, and the ray was rotated by the two label quaternions
and intersected with flat ground. Its brightness was sampled from the seeded
map in `test_drone_pipeline.py` at the prescribed camera position
(4354112.5, 1092287.5). The renderer did not import the drone pipeline.
