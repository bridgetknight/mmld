import os
import sys

import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
import export_pipeline as ep


def test_normalize_meter_data_preserves_optional_columns():
    df = pd.DataFrame(
        {
            "Serial": ["1001"],
            "Time": ["2024/01/01 01:00:00 AM"],
            "kWh Usage": ["1,234.5"],
            "Peak kW": ["5.5"],
            "kWh": ["44.0"],
        }
    )

    result = ep.normalize_meter_data(df)

    assert result["meter_id"].tolist() == [1001]
    assert result["kwh_usage"].iloc[0] == 1234.5
    assert result["peak_kw"].iloc[0] == 5.5
    assert result["total_kwh"].iloc[0] == 44.0
