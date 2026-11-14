"""Real archive excerpts exercised through the generated conditions contract.

RAD: RAD_RDR_2025_196_01_01_4600_V00.TXT, observation 00.
REMS: RME_805808741RMD46000000000_______P1.TAB, first good 06:00 record.
Product URLs and full-file checksums are in data-manifest.yaml.
"""

import pytest

from conditions.gen_conditions import gen_conditions

RAD_SAMPLE = """[FILE]
START_SOL=4600
[OBSERVATION: 00]
START_OBS_MARS="4600 0:30:10"
OBS_DURATION=961
QC="00000000"
[DOSIMETRY_TOTAL_DOSE_B: 00]

7.27702

[DOSIMETRY_TOTAL_DOSE_E: 00]

6.54638
"""

REMS_SAMPLE = (
    ' 805830927,"04600M06:00:00.035","04600 06:20:48",'
    '-999.00,-999.00,-999.00,"  XXXXXX", 184.90,  13.05,   0.53,"    0111",'
    ' 192.61,"101XX001", 139.66,"001XX000", 192.61,"   101XX0011",'
    "   0.03,   0.01,   0.01,   0.06,   0.01,   0.02,"
    '-999.00,-999.00,-999.00,-999.00,-999.00,-999.00,"   01110",'
    '  80.44, 193.22,  20.00,   59.00,-999.00,"     0X1","2H",'
    ' 755.28,   9.30,"      11"\n'
)


def test_conditions_use_real_pds_measurements(tmp_path, monkeypatch):
    """Known E dose and ambient Kelvin value, not the B dose or model defaults."""
    rad = tmp_path / "rad"
    rems = tmp_path / "rems"
    rad.mkdir()
    rems.mkdir()
    (rad / "RAD_RDR_2025_196_01_01_4600_V00.TXT").write_text(RAD_SAMPLE)
    (rems / "RME_805808741RMD46000000000_______P1.TAB").write_text(REMS_SAMPLE)
    monkeypatch.setenv("REDMARK_DATA", str(tmp_path))

    result = gen_conditions(4600)

    # RAD SIS specifies microgray/hour; the contract uses a 24-hour daily rate.
    assert result["radiation_ugy_per_day"] == pytest.approx(157.11312)
    assert result["steps"][0]["temperature_c"] == -80.5
    assert result["steps"][0]["pressure_pa"] == 755.3
    assert len(result["provenance"]["inputs"]) == 2
    # The other hours are absent in this excerpt, so it must remain a stub.
    assert result["provenance"]["script"] == "stub"
