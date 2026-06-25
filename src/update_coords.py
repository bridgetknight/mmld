import pandas as pd
from src.export_pipeline import build_conn_str, connect_pyodbc, fetch_meter_shapes, add_latlon

"""
This script is used for updating the coordinates table in the SQL server when new meters
are added (e.g., for new service, replacing meters and receiving a new ID, etc.)
"""

# Configuration
SERVER = "MMLDAPP03"
SOURCE_DB = "MMLDGIS"
TARGET_DB = "GridAnalysis"
TABLE_NAME = "MonthlyKVAReads"


def main():
    src_conn_str = build_conn_str(SERVER, SOURCE_DB)
    tgt_conn_str = build_conn_str(SERVER, TARGET_DB)

    # Fetch shapes and compute lat/lon
    with connect_pyodbc(src_conn_str) as src:
        shapes = fetch_meter_shapes(src, SOURCE_DB)
        shapes = add_latlon(shapes)

    # Prepare coords: deduplicate by meter_id to avoid PK conflicts
    coords = shapes[["meter_id", "latitude", "longitude"]].copy()
    coords["meter_id"] = pd.to_numeric(coords["meter_id"], errors="coerce").astype("Int64")
    coords = coords.dropna(subset=["meter_id"])
    coords = coords.drop_duplicates(subset=["meter_id"], keep="first")  # One row per meter
    coords["latitude"] = pd.to_numeric(coords["latitude"], errors="coerce")
    coords["longitude"] = pd.to_numeric(coords["longitude"], errors="coerce")

    with connect_pyodbc(tgt_conn_str) as tgt:
        cur = tgt.cursor()
        
        # Create table if missing
        cur.execute("""
        IF OBJECT_ID('dbo.MeterCoords', 'U') IS NULL
        BEGIN
          CREATE TABLE dbo.MeterCoords (
            meter_id INT PRIMARY KEY,
            latitude FLOAT NULL,
            longitude FLOAT NULL
          );
        END
        """)
        tgt.commit()

        # Truncate to clear old data
        cur.execute("TRUNCATE TABLE dbo.MeterCoords")
        tgt.commit()

        # Bulk insert deduplicated coords
        cur.fast_executemany = True
        rows = [
            (
                int(r['meter_id']),
                None if pd.isna(r['latitude']) else float(r['latitude']),
                None if pd.isna(r['longitude']) else float(r['longitude'])
            )
            for _, r in coords.iterrows()
        ]
        if rows:
            cur.executemany(
                "INSERT INTO dbo.MeterCoords (meter_id, latitude, longitude) VALUES (?, ?, ?)",
                rows,
            )
            tgt.commit()

        # Apply coords to main reads table
        cur.execute(f"UPDATE t SET latitude = m.latitude, longitude = m.longitude FROM dbo.{TABLE_NAME} t JOIN dbo.MeterCoords m ON t.meter_id = m.meter_id")
        tgt.commit()

    print(f"Inserted {len(rows)} unique meter coords into MeterCoords.")
    print(f"Applied coords to {TABLE_NAME}.")


if __name__ == '__main__':
    main()
