import os
import pandas as pd
import pyodbc
from pyproj import Transformer
from shapely import wkb
import sys

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
    meter_id,
    SHAPE.STAsBinary() AS ewkb_data
FROM [{database}].dbo.meternxt
WHERE meter_id IS NOT NULL
  AND ISNUMERIC(meter_id) = 1
"""
    df = pd.read_sql(sql, conn)
    # Ensure meter_id is numeric and use pandas nullable integer type to match processed CSVs
    df["meter_id"] = pd.to_numeric(df["meter_id"], errors="coerce").astype("Int64")
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

def add_latlon(df):
    df[["latitude", "longitude"]] = df["ewkb_data"].apply(
        lambda x: pd.Series(coords_from_ewkb(x))
    )
    return df.drop(columns=["ewkb_data"])

def _set_server_name(name):
    global SERVER_NAME
    SERVER_NAME = name
    print("Successfully changed SERVER_NAME.")

def _set_database_name(name):
    global DATABASE_NAME
    DATABASE_NAME = name
    print("Successfully changed DATABASE_NAME.")

# IN PROGRESS FUNCTIONS
def fetch_meter_coords(conn: pyodbc.Connection, target_db: str) -> pd.DataFrame:
    """Fetch meter coordinates from MeterCoords reference table."""
    sql = f"SELECT meter_id, latitude, longitude FROM [{target_db}].dbo.MeterCoords"
    try:
        df = pd.read_sql(sql, conn)
        df["meter_id"] = pd.to_numeric(df["meter_id"], errors="coerce").astype("Int64")
        return df
    except Exception as e:
        print(f"Warning: Could not fetch from MeterCoords: {e}. Coords will be NULL.")
        return pd.DataFrame(columns=["meter_id", "latitude", "longitude"])


def ensure_table(conn: pyodbc.Connection, table: str):
    ddl = f"""
IF OBJECT_ID('dbo.{table}', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.{table} (
        ID INT IDENTITY(1,1) PRIMARY KEY,
        meter_id INT NOT NULL,
        [timestamp] DATETIME2(0) NOT NULL,
        hourly_avg_power FLOAT NOT NULL,
        latitude FLOAT NULL,
        longitude FLOAT NULL
    );
    CREATE UNIQUE INDEX ux_{table}_meter_time ON dbo.{table}(meter_id, [timestamp]) WITH (IGNORE_DUP_KEY = ON);
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
        CREATE UNIQUE INDEX ux_{table}_meter_time ON dbo.{table}(meter_id, [timestamp]) WITH (IGNORE_DUP_KEY = ON);
    END
    
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.{table}') AND name = 'latitude')
    BEGIN
        ALTER TABLE dbo.{table} ADD latitude FLOAT NULL, longitude FLOAT NULL;
    END
END
"""
    cur = conn.cursor()
    cur.execute(ddl)
    conn.commit()

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
    #    return new_reads.merge(reads_db, on="meter_id", how="inner")
    
    def normalize(df: pd.DataFrame) -> pd.DataFrame:
        df = df.rename(columns={c: c.strip().lower() for c in df.columns})
        if "serial" in df.columns:
            df = df.rename(columns={"serial": "meter_id"})
            
        if {"meter_id", "time", "kwh usage"} - set(df.columns):
            return pd.DataFrame(columns=["meter_id", "timestamp", KVA_COLUMN_NAME])

        df = df[["meter_id", "time", "kwh usage"]].astype(str)
        # Normalize meter_id to numeric and use pandas nullable integer type so merges succeed
        df["meter_id"] = pd.to_numeric(df["meter_id"], errors="coerce").astype("Int64")

        df["timestamp"] = pd.to_datetime(
            df["time"].str.strip(),
            format="%Y/%m/%d %I:%M:%S %p",
            errors="coerce",
        )

        kva_series = (
            df["kwh usage"]
            .str.replace(",", "", regex=False)
            .str.strip()
            .replace("", pd.NA)
        )
        df[KVA_COLUMN_NAME] = pd.to_numeric(kva_series, errors="coerce")

        return df.dropna(subset=["meter_id", "timestamp", KVA_COLUMN_NAME])[
            ["meter_id", "timestamp", KVA_COLUMN_NAME]
        ]

    parts = []
    for chunk in pd.read_csv(filepath, chunksize=chunk_size, dtype=str):
        part = normalize(chunk)
        if not part.empty:
            parts.append(part)

    result = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=["meter_id", "timestamp", KVA_COLUMN_NAME]
    )

    if coords_df is not None and not result.empty:
        result = result.merge(coords_df, on="meter_id", how="left")

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
            df = process_file(path, conn, coords_df=coords_df, database=database) # Returns a cleaned DF from a CSV using SOURCE_DB
            insert_meter_rows(conn, df, table=table)

def clean_nexgrid_data(df):
    # Get percentage null of each column
    def remove_unused_cols(df):
        percent_missing = df.isnull().sum() * 100 / len(df)
        missing_value_pct = pd.DataFrame({"column_name": df.columns,
                                        "percent_missing": percent_missing})
        missing_value_pct.sort_values('percent_missing', inplace=True)
        print(missing_value_pct)

        removed_cols = []
        print("Removing unused columns...")
        for idx, row in missing_value_pct.iterrows():
            # Remove columns that are more than 90% empty for now and list them
            if row["percent_missing"] > 90.0:
                column = row["column_name"]
                df.drop([column], axis=1, inplace=True)
                removed_cols += [column]
        #print(*items, sep=", ")   
        print(f"The following rows were removed:{', '.join(removed_cols)}")   
        return df
    
    def remove_invalids(df):
        # Remove duplicates
        df = df.dropna(subset=['meter_id'])  
        return df

    df = remove_unused_cols(df)
    df = remove_invalids(df)
    
    return df

# Insert rows into table in SQL database
def insert_meter_rows(conn: pyodbc.Connection, df: pd.DataFrame, table: str):
    if df.empty:
        return
    cur = conn.cursor()
    cur.fast_executemany = True

    rows = []
    # Check if latitude/longitude columns exist in dataframe
    has_coords = "latitude" in df.columns and "longitude" in df.columns
    
    cols_to_extract = ["meter_id", "timestamp", KVA_COLUMN_NAME]
    if has_coords:
        cols_to_extract.extend(["latitude", "longitude"])
    
    subset = df[cols_to_extract]
    for _, r in subset.iterrows():
        # Convert pandas/numpy types to native Python types that pyodbc understands
        mid = r["meter_id"]
        if pd.isna(mid):
            mid_py = None
        else:
            try:
                mid_py = int(mid)
            except Exception:
                mid_py = None

        ts = r["timestamp"]
        if pd.isna(ts):
            ts_py = None
        else:
            try:
                ts_py = ts.to_pydatetime()
            except Exception:
                ts_py = pd.to_datetime(ts).to_pydatetime()

        kva = r[KVA_COLUMN_NAME]
        if pd.isna(kva):
            kva_py = None
        else:
            try:
                kva_py = float(kva)
            except Exception:
                kva_py = None

        if has_coords:
            lat = r["latitude"]
            lat_py = None if pd.isna(lat) else float(lat)
            lon = r["longitude"]
            lon_py = None if pd.isna(lon) else float(lon)
            rows.append((mid_py, ts_py, kva_py, lat_py, lon_py))
        else:
            rows.append((mid_py, ts_py, kva_py))

    if rows:
        if has_coords:
            col_list = "meter_id, timestamp, hourly_avg_power, latitude, longitude"
            placeholders = "?, ?, ?, ?, ?"
        else:
            col_list = "meter_id, timestamp, hourly_avg_power"
            placeholders = "?, ?, ?"
        
        cur.executemany(
            f"INSERT INTO dbo.{table} ({col_list}) VALUES ({placeholders})",
            rows,
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
    KVA_COLUMN_NAME = "hourly_avg_power"

    # build connections
    src_conn_str = build_conn_str(SERVER, SOURCE_DB)
    tgt_conn_str = build_conn_str(SERVER, TARGET_DB)

    # fetch coords once from MeterCoords reference table in target DB
    with connect_pyodbc(tgt_conn_str) as tgt_conn:
        coords_df = fetch_meter_coords(tgt_conn, TARGET_DB)

    csv_paths = _find_csv_paths(sys.argv[1:], DATA_DIR)
    if not csv_paths:
        raise SystemExit(
            f"Error: No .csv files located in the input folder {DATA_DIR}."
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

