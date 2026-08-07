import os
import pandas as pd
import pyodbc
from pyproj import Transformer
from shapely import wkb
import sys
from tqdm import tqdm

import warnings
warnings.filterwarnings('ignore', category=UserWarning)   

METER_ID_COLUMN = "meter_id"
TIMESTAMP_COLUMN = "time"
KVA_COLUMN_NAME = "kwh_usage"
PEAK_KW_COLUMN_NAME = "peak_kw"
KWH_COLUMN_NAME = "total_kwh"
LATITUDE_COLUMN = "latitude"
LONGITUDE_COLUMN = "longitude"


def build_conn_str(server, database):
    return (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={server};"
        f"DATABASE={database};"
        "Trusted_Connection=yes;"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )

def connect_pyodbc(conn_str):
    return pyodbc.connect(conn_str, timeout=10)

def fetch_meter_shapes(conn, database):
    sql = f"""
SELECT
    METERID,
    SHAPE.STAsBinary() AS ewkb_data
FROM [{database}].dbo.meternxt
WHERE METERID IS NOT NULL
  AND ISNUMERIC(METERID) = 1
"""
    df = pd.read_sql(sql, conn)
    df[METER_ID_COLUMN] = pd.to_numeric(df["METERID"], errors="coerce").astype("Int64")
    return df

def coords_from_ewkb(ewkb_bytes):
    if ewkb_bytes is None:
        return None, None

    transformer = Transformer.from_crs("EPSG:2249", "EPSG:4326", always_xy=True)
    geom = wkb.loads(ewkb_bytes)

    if geom.geom_type == "Point":
        lon, lat = transformer.transform(geom.x, geom.y)
        return lat, lon

    from shapely.ops import transform
    geom4326 = transform(transformer.transform, geom)
    return geom4326.centroid.y, geom4326.centroid.x

def _set_server_name(name):
    global SERVER_NAME
    SERVER_NAME = name
    print("INFO: Successfully changed SERVER_NAME.")

def _set_database_name(name):
    global DATABASE_NAME
    DATABASE_NAME = name
    print("INFO: Successfully changed DATABASE_NAME.")

def fetch_meter_coords(conn: pyodbc.Connection, target_db: str) -> pd.DataFrame:
    """Fetch meter coordinates from Meters reference table."""
    sql = f"SELECT meter_id, latitude, longitude FROM [{target_db}].dbo.Meters"
    try:
        df = pd.read_sql(sql, conn)
        df[METER_ID_COLUMN] = pd.to_numeric(df["meter_id"], errors="coerce").astype("Int64")
        return df[[METER_ID_COLUMN, LATITUDE_COLUMN, LONGITUDE_COLUMN]]
    except Exception as e:
        print(f"WARNING: Could not fetch from Meters: {e}. Coords will be NULL.")
        return pd.DataFrame(columns=[METER_ID_COLUMN, LATITUDE_COLUMN, LONGITUDE_COLUMN])


def ensure_table(conn: pyodbc.Connection, table: str):
    ddl = f"""
IF OBJECT_ID('dbo.{table}', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.{table} (
        ID INT IDENTITY(1,1) PRIMARY KEY,
        [{METER_ID_COLUMN}] INT NOT NULL,
        [{TIMESTAMP_COLUMN}] DATETIME2(0) NOT NULL,
        [{KVA_COLUMN_NAME}] FLOAT NOT NULL,
        [{PEAK_KW_COLUMN_NAME}] FLOAT NULL,
        [{KWH_COLUMN_NAME}] FLOAT NULL,
        [{LATITUDE_COLUMN}] FLOAT NULL,
        [{LONGITUDE_COLUMN}] FLOAT NULL
    );
    CREATE UNIQUE INDEX ux_{table}_meter_time ON dbo.{table}([{METER_ID_COLUMN}], [{TIMESTAMP_COLUMN}]) WITH (IGNORE_DUP_KEY = ON);
END
ELSE
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM sys.indexes i
        JOIN sys.objects o ON i.object_id = o.object_id
        WHERE o.object_id = OBJECT_ID('dbo.{table}')
          AND i.name = 'ux_{table}_meter_time'
    )
    BEGIN
        CREATE UNIQUE INDEX ux_{table}_meter_time ON dbo.{table}([{METER_ID_COLUMN}], [{TIMESTAMP_COLUMN}]) WITH (IGNORE_DUP_KEY = ON);
    END
END
"""
    cur = conn.cursor()
    cur.execute(ddl)
    conn.commit()


def _canonicalize_column_name(column_name: str) -> str:
    """Map common CSV header variants to the canonical names used by the pipeline."""
    normalized = str(column_name).strip().lower()
    mapping = {
        "serial": METER_ID_COLUMN,
        "meter id": METER_ID_COLUMN,
        "meter_id": METER_ID_COLUMN,
        "meterid": METER_ID_COLUMN,
        "time": TIMESTAMP_COLUMN,
        "timestamp": TIMESTAMP_COLUMN,
        "kwh usage": KVA_COLUMN_NAME,
        "kwh_usage": KVA_COLUMN_NAME,
        "peak kW": PEAK_KW_COLUMN_NAME,
        "peak kw": PEAK_KW_COLUMN_NAME,
        "peak_kw": PEAK_KW_COLUMN_NAME,
        "kWh": KWH_COLUMN_NAME,
        "kwh": KWH_COLUMN_NAME,
        "total kwh": KWH_COLUMN_NAME,
        "total_kwh": KWH_COLUMN_NAME,
    }
    return mapping.get(normalized, column_name)


def normalize_meter_data(df: pd.DataFrame) -> pd.DataFrame:
    # Standardize the incoming columns to the canonical names the rest of the script expects.
    df = df.rename(columns={column: _canonicalize_column_name(column) for column in df.columns})

    if {METER_ID_COLUMN, TIMESTAMP_COLUMN, KVA_COLUMN_NAME} - set(df.columns):
        return pd.DataFrame(columns=[METER_ID_COLUMN, TIMESTAMP_COLUMN, KVA_COLUMN_NAME, PEAK_KW_COLUMN_NAME, KWH_COLUMN_NAME])

    # Keep the canonical columns we expect the source file to provide
    required_columns = [METER_ID_COLUMN, TIMESTAMP_COLUMN, KVA_COLUMN_NAME, PEAK_KW_COLUMN_NAME, KWH_COLUMN_NAME]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise KeyError(f"Expected columns missing after normalization: {', '.join(missing_columns)}")
    df = df[required_columns].copy()

    # Convert the incoming values to strings first so numeric parsing is consistent.
    df = df.astype(str)

    # Convert the normalized fields to their final pandas/numeric types.
    df[METER_ID_COLUMN] = pd.to_numeric(df[METER_ID_COLUMN], errors="coerce").astype("Int64")
    df[TIMESTAMP_COLUMN] = pd.to_datetime(
        df[TIMESTAMP_COLUMN].str.strip(),
        format="%Y/%m/%d %I:%M:%S %p",
        errors="coerce",
    )

    # Clean up formatting and blank values before writing to SQL.
    kva_series = (
        df[KVA_COLUMN_NAME]
        .str.replace(",", "", regex=False)
        .str.strip()
        .replace("", pd.NA)
    )
    df[KVA_COLUMN_NAME] = pd.to_numeric(kva_series, errors="coerce")

    peak_kw_series = (
        df[PEAK_KW_COLUMN_NAME]
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.strip()
        .replace("", pd.NA)
    )
    df[PEAK_KW_COLUMN_NAME] = pd.to_numeric(peak_kw_series, errors="coerce")

    kwh_series = (
        df[KWH_COLUMN_NAME]
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.strip()
        .replace("", pd.NA)
    )
    df[KWH_COLUMN_NAME] = pd.to_numeric(kwh_series, errors="coerce")

    return df.dropna(subset=[METER_ID_COLUMN, TIMESTAMP_COLUMN, KVA_COLUMN_NAME])[
        [METER_ID_COLUMN, TIMESTAMP_COLUMN, KVA_COLUMN_NAME, PEAK_KW_COLUMN_NAME, KWH_COLUMN_NAME]
    ]


def process_file(
    filepath: str,
    conn: pyodbc.Connection,
    coords_df: pd.DataFrame | None = None,
    database: str | None = None,
    chunk_size: int = 10000,
) -> pd.DataFrame:
    """
    Read one meter CSV, normalize it, optionally join GIS coords,
    and return a cleaned DataFrame.
    """

    if coords_df is None and database is not None:
        coords_df = fetch_meter_shapes(conn, database)

    #def merge_new_reads(new_reads, reads_db, engine):
    #    return new_reads.merge(reads_db, on="METERID", how="inner")

    # Read the CSV, normalize it, and add it to a temporary collection of chunks
    parts = []
    for chunk in pd.read_csv(filepath, chunksize=chunk_size, dtype=str):
        part = normalize_meter_data(chunk)
        if not part.empty:
            parts.append(part)

    # Concatenate the chunks into a DataFrame using the correct columns
    result = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=[METER_ID_COLUMN, TIMESTAMP_COLUMN, KVA_COLUMN_NAME, PEAK_KW_COLUMN_NAME, KWH_COLUMN_NAME]
    )

    # Merge with coordinates from MeterCoords if provided
    if coords_df is not None and not result.empty:
        result = result.merge(coords_df, on=METER_ID_COLUMN, how="left")

    return result

# Process a folder of CSV files from Nexgrid
def process_folder(
    table: str,
    directory: str,
    conn: pyodbc.Connection,
    coords_df: pd.DataFrame | None = None,
    database: str | None = None,
    chunk_size: int = 10000,
):
    for file in os.listdir(directory):
        path = os.path.join(directory, file)
        if path.lower().endswith(".csv"):
            df = process_file(path, conn, coords_df=coords_df, database=database) # Returns a cleaned DF from a CSV
            insert_meter_rows(conn, df, table=table)

# Insert rows into table in SQL database
def insert_meter_rows(conn: pyodbc.Connection, df: pd.DataFrame, table: str):
    if df.empty:
        return
    cur = conn.cursor()
    cur.fast_executemany = True

    rows = []
    # Check whether the processed frame already includes coordinate columns.
    has_coords = LATITUDE_COLUMN in df.columns and LONGITUDE_COLUMN in df.columns

    # Build the row payload from the normalized columns.
    cols_to_extract = [METER_ID_COLUMN, TIMESTAMP_COLUMN, KVA_COLUMN_NAME]
    for optional_col in [PEAK_KW_COLUMN_NAME, KWH_COLUMN_NAME]:
        if optional_col in df.columns:
            cols_to_extract.append(optional_col)
    if has_coords:
        cols_to_extract.extend([LATITUDE_COLUMN, LONGITUDE_COLUMN])

    subset = df[cols_to_extract]
    for _, r in tqdm(subset.iterrows(), desc=f"Normalizing rows", bar_format="{l_bar}{bar:10}{r_bar}", total=len(subset)):
        # Normalize the meter ID to a plain integer or null.
        mid = r[METER_ID_COLUMN]
        if pd.isna(mid):
            mid_py = None
        else:
            try:
                mid_py = int(mid)
            except Exception:
                mid_py = None

        # Normalize the timestamp to a Python datetime or null.
        ts = r[TIMESTAMP_COLUMN]
        if pd.isna(ts):
            ts_py = None
        else:
            try:
                ts_py = ts.to_pydatetime()
            except Exception:
                ts_py = pd.to_datetime(ts).to_pydatetime()

        # Normalize the primary usage value to a float or null.
        kva = r[KVA_COLUMN_NAME]
        if pd.isna(kva):
            kva_py = None
        else:
            try:
                kva_py = float(kva)
            except Exception:
                kva_py = None

        row_values = [mid_py, ts_py, kva_py]
        for optional_col in [PEAK_KW_COLUMN_NAME, KWH_COLUMN_NAME]:
            if optional_col in r.index:
                value = r[optional_col]
                row_values.append(None if pd.isna(value) else float(value))
            else:
                row_values.append(None)

        if has_coords:
            lat = r[LATITUDE_COLUMN]
            lat_py = None if pd.isna(lat) else float(lat)
            lon = r[LONGITUDE_COLUMN]
            lon_py = None if pd.isna(lon) else float(lon)
            row_values.extend([lat_py, lon_py])
        else:
            row_values.extend([None, None])

        rows.append(tuple(row_values))

    if rows:
        for row in tqdm(rows, bar_format="{l_bar}{bar:10}{r_bar}", total=len(rows)):
            params = list(row)
            cur.execute(
                f"""
                MERGE INTO dbo.{table} AS target
                USING (
                    SELECT
                        ? AS {METER_ID_COLUMN},
                        ? AS {TIMESTAMP_COLUMN},
                        ? AS {KVA_COLUMN_NAME},
                        ? AS {PEAK_KW_COLUMN_NAME},
                        ? AS {KWH_COLUMN_NAME},
                        ? AS {LATITUDE_COLUMN},
                        ? AS {LONGITUDE_COLUMN}
                ) AS source
                ON target.{METER_ID_COLUMN} = source.{METER_ID_COLUMN}
                   AND target.{TIMESTAMP_COLUMN} = source.{TIMESTAMP_COLUMN}
                WHEN MATCHED THEN
                    UPDATE SET
                        {KVA_COLUMN_NAME} = source.{KVA_COLUMN_NAME},
                        {PEAK_KW_COLUMN_NAME} = source.{PEAK_KW_COLUMN_NAME},
                        {KWH_COLUMN_NAME} = source.{KWH_COLUMN_NAME},
                        {LATITUDE_COLUMN} = source.{LATITUDE_COLUMN},
                        {LONGITUDE_COLUMN} = source.{LONGITUDE_COLUMN}
                WHEN NOT MATCHED THEN
                    INSERT ({METER_ID_COLUMN}, {TIMESTAMP_COLUMN}, {KVA_COLUMN_NAME}, {PEAK_KW_COLUMN_NAME}, {KWH_COLUMN_NAME}, {LATITUDE_COLUMN}, {LONGITUDE_COLUMN})
                    VALUES (source.{METER_ID_COLUMN}, source.{TIMESTAMP_COLUMN}, source.{KVA_COLUMN_NAME}, source.{PEAK_KW_COLUMN_NAME}, source.{KWH_COLUMN_NAME}, source.{LATITUDE_COLUMN}, source.{LONGITUDE_COLUMN});
                """,
                params,
            )
        conn.commit()

def _find_csv_paths(inputs: list[str], data_dir: str) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()

    def add_csv_file(csv_path: str) -> None:
        abs_path = os.path.abspath(csv_path)
        if abs_path not in seen:
            seen.add(abs_path)
            files.append(abs_path)

    def add_csvs_from_dir(directory: str) -> None:
        if not os.path.isdir(directory):
            raise SystemExit(f"Error: directory not found: {directory}")
        for name in os.listdir(directory):
            if name.lower().endswith(".csv"):
                add_csv_file(os.path.join(directory, name))

    if not inputs:
        add_csvs_from_dir(data_dir)
        return files

    for input_path in inputs:
        if input_path in (".", ""):
            add_csvs_from_dir(data_dir)
            continue

        expanded = os.path.expanduser(input_path)
        candidate = expanded if os.path.isabs(expanded) else os.path.abspath(expanded)

        if os.path.exists(candidate):
            if os.path.isdir(candidate):
                add_csvs_from_dir(candidate)
                continue
            if candidate.lower().endswith(".csv"):
                add_csv_file(candidate)
                continue
            raise SystemExit(
                "Error: input must be a .csv file or a folder containing .csv files"
            )

        alt_candidate = os.path.join(data_dir, input_path)
        if os.path.exists(alt_candidate):
            if os.path.isdir(alt_candidate):
                add_csvs_from_dir(alt_candidate)
                continue
            if alt_candidate.lower().endswith(".csv"):
                add_csv_file(alt_candidate)
                continue

        raise SystemExit(
            f"Error: path not found: {input_path}\n"
            f"Use a full path, a file in {data_dir}, a folder containing .csv files, or no path to process all CSVs in {data_dir}."
        )
    print("Files to process: ")
    print(files)
    return files


if __name__ == "__main__":
    # config
    SERVER = "MMLDAPP03"
    SOURCE_DB = "MMLDGIS" 
    TARGET_DB = "GridAnalysis"
    ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(ROOT_DIR, "nexgrid_hourly_reports_monthly")
    TABLE_NAME = "MonthlyKVAReads"

    # build connection
    tgt_conn_str = build_conn_str(SERVER, TARGET_DB)

    # fetch coords once from Meters reference table in target DB
    with connect_pyodbc(tgt_conn_str) as tgt_conn:
        coords_df = fetch_meter_coords(tgt_conn, TARGET_DB)

    csv_paths = _find_csv_paths(sys.argv[1:], DATA_DIR)
    if not csv_paths:
        raise SystemExit(
            f"ERROR: No .csv files located in the input folder {DATA_DIR}."
        )

    with connect_pyodbc(tgt_conn_str) as tgt_conn:
        ensure_table(tgt_conn, TABLE_NAME)
        for path in csv_paths:
            print(f"Processing {path}...")

            try:
                df = process_file(path, tgt_conn, coords_df = coords_df)
            except Exception as e:
                print(f"An error occured processing file {path}.\n{e}")

            df = process_file(path, tgt_conn, coords_df=coords_df)
            if not df.empty:
                df = df.drop_duplicates(subset=["meter_id", "timestamp"])
                insert_meter_rows(tgt_conn, df, TABLE_NAME)
                print(f"[Done] {path} -> processed {len(df)} rows!")
            else:
                print(f"No reads were added from {path}. Check the report file and its contents.")

