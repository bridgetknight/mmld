import os
import pandas as pd
from datetime import datetime
import time
import pyodbc
from typing import Optional
import json

"""CSV -> SQL Server ingestor.

Configure your SQL Server and credentials below, then run:
        python collect_meter_data.py

Assumptions:
- The specified SQL login has permissions to create the database (if missing)
    and to create/alter tables within it.
"""

# ------------- Simple configuration (edit these) -------------
# SQL Server instance hostname. Examples:
#   'localhost'                    -> local default instance
#   'MMLDAPP03\MPOWER'           -> named instance
#   'server.example.com'           -> remote server
SERVER_HOST = '.\MPOWER'

# Optional TCP port (leave as None to use default / named instance resolution)
SERVER_PORT: Optional[str] = None  # e.g., '1433'

# Database name to use/create
DEFAULT_DB_NAME = 'GridAnalysis'

# ODBC driver name installed on this machine
DEFAULT_DRIVER = '{ODBC Driver 17 for SQL Server}'

# Single SQL authentication login used for both setup and ingestion
SQL_LOGIN = 'Ari'
SQL_PASSWORD = 'test'

# Input CSV folder and chunking
DATA_FOLDER = 'C:\mPowerSave\HoulyReadsByMonth'  # set to your CSV directory (e.g., r'C:\mPowerSave\data')
CHUNK_SIZE = 10000      # rows per chunk/batch (affects speed)
# -------------------------------------------------------------

# retained for potential filtering
METERS = None

def _sleep_backoff(attempt):
    time.sleep(1 + 0.5 * attempt)  # 1.0s, 1.5s, 2.0s, ...

def _pyodbc_deadlock_or_busy(e: Exception) -> bool:
    msg = str(e).lower()
    return isinstance(e, pyodbc.Error) and (
        'deadlock' in msg or 'timeout' in msg or 'could not open a connection' in msg
    )

def _build_connection_string(database: Optional[str], use_admin: bool) -> str:
    server = SERVER_HOST if not SERVER_PORT else f"{SERVER_HOST},{SERVER_PORT}"
    parts = [
        f"DRIVER={DEFAULT_DRIVER}",
        f"SERVER={server}",
    ]
    if database:
        parts.append(f"DATABASE={database}")
    # Always use SQL authentication with single login
    if not SQL_LOGIN or not SQL_PASSWORD:
        raise RuntimeError("Please set SQL_LOGIN and SQL_PASSWORD at the top of the file.")
    parts.append(f"UID={SQL_LOGIN}")
    parts.append(f"PWD={SQL_PASSWORD}")
    # Encrypt recommended for remote servers; set explicitly to avoid DSN reliance
    parts.append("Encrypt=yes")
    parts.append("TrustServerCertificate=yes")
    return ";".join(parts)

def _connect(database: Optional[str], use_admin: bool) -> pyodbc.Connection:
    cs = _build_connection_string(database, use_admin)
    return pyodbc.connect(cs, timeout=10)

def _server_and_db_setup():
    """Ensure database and schema exist. Requires the SQL login to have sufficient permissions.

    Note: This cannot create a brand-new SQL Server host. A running SQL Server instance must be reachable.
    """
    # Connect to master and create database if needed, then create user mapping and schema from master
    conn = _connect(database='master', use_admin=True)
    try:
        conn.autocommit = True
        cur = conn.cursor()

        # Create database if missing
        cur.execute(
            """
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = ?)
BEGIN
    DECLARE @sql nvarchar(max) = 'CREATE DATABASE [' + REPLACE(?, ']', ']]') + ']';
    EXEC(@sql);
END
""",
            (DEFAULT_DB_NAME, DEFAULT_DB_NAME),
        )

        # Ensure user mapping for the configured SQL login and grant basic roles
        cur.execute(
            """
DECLARE @db sysname = ?;
DECLARE @login sysname = ?;
IF DB_ID(@db) IS NOT NULL
BEGIN
    DECLARE @sql nvarchar(max) = N'USE ' + QUOTENAME(@db) + N';\n'
        + N'DECLARE @loginSid varbinary(85) = SUSER_SID(@login);\n'
        + N'DECLARE @dbUser sysname = (SELECT name FROM sys.database_principals WHERE sid = @loginSid);\n'
        + N'IF @dbUser IS NULL\n'
        + N'BEGIN\n'
        + N'    DECLARE @stmt nvarchar(max) = N''CREATE USER '' + QUOTENAME(@login) + N'' FOR LOGIN '' + QUOTENAME(@login) + N'';'';\n'
        + N'    EXEC(@stmt);\n'
        + N'    SET @dbUser = @login;\n'
        + N'END;\n'
        + N'EXEC sp_addrolemember N''db_datareader'', @dbUser;\n'
        + N'EXEC sp_addrolemember N''db_datawriter'', @dbUser;\n'
        + N'EXEC sp_addrolemember N''db_ddladmin'', @dbUser;\n';
    EXEC sp_executesql @sql, N'@login sysname', @login=@login;
END
""",
            (DEFAULT_DB_NAME, SQL_LOGIN),
        )

        # Create schema objects inside the target database
        cur.execute(
            """
DECLARE @db sysname = ?;
DECLARE @sql nvarchar(max) = N'USE ' + QUOTENAME(@db) + N';\n'
    + N'IF OBJECT_ID(N''dbo.MeterData'', N''U'') IS NULL\n'
    + N'BEGIN\n'
    + N'    CREATE TABLE dbo.MeterData (\n'
    + N'        Id INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_MeterData PRIMARY KEY,\n'
    + N'        MeterID INT NOT NULL,\n'
    + N'        Timestamp DATETIME2(0) NOT NULL,\n'
    + N'        HourlyAvgPower FLOAT NOT NULL\n'
    + N'    );\n'
    + N'END\n'
    + N'\n'
    + N'IF NOT EXISTS (\n'
    + N'    SELECT 1 FROM sys.indexes WHERE name = ''ux_MeterData_meter_time'' AND object_id = OBJECT_ID(''dbo.MeterData'')\n'
    + N')\n'
    + N'BEGIN\n'
    + N'    CREATE UNIQUE INDEX ux_MeterData_meter_time ON dbo.MeterData(MeterID, Timestamp) WITH (IGNORE_DUP_KEY = ON);\n'
    + N'END\n'
    + N'\n'
    + N'IF NOT EXISTS (\n'
    + N'    SELECT 1 FROM sys.indexes WHERE name = ''ix_MeterData_time'' AND object_id = OBJECT_ID(''dbo.MeterData'')\n'
    + N')\n'
    + N'BEGIN\n'
    + N'    CREATE INDEX ix_MeterData_time ON dbo.MeterData(Timestamp);\n'
    + N'END\n'
    + N'\n'
    + N'IF OBJECT_ID(N''dbo.RawCsv'', N''U'') IS NULL\n'
    + N'BEGIN\n'
    + N'    CREATE TABLE dbo.RawCsv (\n'
    + N'        Id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_RawCsv PRIMARY KEY,\n'
    + N'        FileName NVARCHAR(260) NOT NULL,\n'
    + N'        RowNumber BIGINT NOT NULL,\n'
    + N'        RowJson NVARCHAR(MAX) NOT NULL,\n'
    + N'        IngestedAt DATETIME2(0) NOT NULL CONSTRAINT DF_RawCsv_IngestedAt DEFAULT SYSUTCDATETIME()\n'
    + N'    );\n'
    + N'END\n'
    + N'\n'
    + N'IF NOT EXISTS (\n'
    + N'    SELECT 1 FROM sys.indexes WHERE name = ''ix_RawCsv_File_Row'' AND object_id = OBJECT_ID(''dbo.RawCsv'')\n'
    + N')\n'
    + N'BEGIN\n'
    + N'    CREATE INDEX ix_RawCsv_File_Row ON dbo.RawCsv(FileName, RowNumber);\n'
    + N'END\n';
EXEC(@sql);
""",
            (DEFAULT_DB_NAME,),
        )
    finally:
        try:
            conn.close()
        except:
            pass

def init_db():
    """Wrapper to ensure server/database/login/schema are present."""
    for attempt in range(6):
        try:
            _server_and_db_setup()
            return
        except Exception as e:
            if _pyodbc_deadlock_or_busy(e) and attempt < 5:
                _sleep_backoff(attempt)
                continue
            raise

def process_chunk(chunk, conn, file_name: str, offset: int):
    # raw logging preserves full CSV row content
    raw_df = chunk.copy()
    raw_df = raw_df.where(pd.notna(raw_df), None)
    raw_records = []
    for i, r in enumerate(raw_df.to_dict(orient='records')):
        raw_records.append((file_name, offset + i + 1, json.dumps(r, ensure_ascii=False)))

    c = chunk.copy()
    c.columns = [col.strip().lower() for col in c.columns]
    ser = c.get('serial'); tim = c.get('time'); kwh = c.get('kwh usage')
    if ser is None or tim is None or kwh is None:
        # still write raw rows (no fast_executemany for NVARCHAR(MAX))
        if raw_records:
            rcur = conn.cursor()
            rcur.executemany(
                "INSERT INTO dbo.RawCsv (FileName, RowNumber, RowJson) VALUES (?, ?, ?)",
                raw_records,
            )
            conn.commit()
        return
    meter = ser.astype(str).str.replace('R1:', '', regex=False).str.strip()
    meter = pd.to_numeric(meter, errors='coerce')
    ts = pd.to_datetime(tim.astype(str).str.strip(), format="%Y/%m/%d %I:%M:%S %p", errors='coerce')
    power = pd.to_numeric(kwh.astype(str).str.replace(',', '', regex=False).str.strip(), errors='coerce')
    df2 = pd.DataFrame({'MeterID': meter, 'Timestamp': ts, 'HourlyAvgPower': power}).dropna()
    # Insert raw first without fast_executemany, then normalized with fast_executemany
    if raw_records:
        rcur = conn.cursor()
        rcur.executemany(
            "INSERT INTO dbo.RawCsv (FileName, RowNumber, RowJson) VALUES (?, ?, ?)",
            raw_records,
        )
    if not df2.empty:
        rows = list(df2.itertuples(index=False, name=None))
        mcur = conn.cursor(); mcur.fast_executemany = True
        mcur.executemany(
            "INSERT INTO dbo.MeterData (MeterID, Timestamp, HourlyAvgPower) VALUES (?, ?, ?)",
            rows
        )
    if raw_records or not df2.empty:
        conn.commit()

def _open_conn_with_retries():
    for attempt in range(6):
        try:
            conn = _connect(database=DEFAULT_DB_NAME, use_admin=False)
            return conn
        except Exception as e:
            if _pyodbc_deadlock_or_busy(e) and attempt < 5:
                _sleep_backoff(attempt)
                continue
            raise

def parse_csv_and_insert(filepath):
    print(f"[Start] {os.path.basename(filepath)}")
    t0 = time.time()
    total_rows = 0
    conn = _open_conn_with_retries()
    try:
        for i, chunk in enumerate(pd.read_csv(filepath, chunksize=CHUNK_SIZE)):
            process_chunk(chunk, conn, os.path.basename(filepath), total_rows)
            total_rows += len(chunk)
            if (i+1) % 10 == 0 or len(chunk) < CHUNK_SIZE:
                elapsed = time.time() - t0
                print(f"[Progress] {os.path.basename(filepath)}: {total_rows} rows in {elapsed/60:.1f} min")
    except Exception as e:
        print(f"[CSV Error] {filepath}: {e}")
    finally:
        try:
            conn.close()
        except:
            pass
    print(f"[Done] {os.path.basename(filepath)}. Total rows: {total_rows}")

def main():
    # Normalize data folder path
    global DATA_FOLDER
    DATA_FOLDER = os.path.normpath(os.path.expanduser(str(DATA_FOLDER).strip()))

    # Startup info for troubleshooting
    target_server = SERVER_HOST if not SERVER_PORT else f"{SERVER_HOST},{SERVER_PORT}"
    print(f"[Info] Target server: {target_server} | Database: {DEFAULT_DB_NAME}")

    try:
        init_db()
    except Exception as e:
        print("[Error] Database/server initialization failed.")
        print("Reason:", e)
        print("Ensure a SQL Server instance is reachable. This script can create a database and schema, but not the SQL Server host itself.")
        raise
    files = [f for f in os.listdir(DATA_FOLDER) if f.lower().endswith('.csv')]
    print(f"[Info] Found {len(files)} CSV files in {DATA_FOLDER}")
    for file in files:
        path = os.path.join(DATA_FOLDER, file)
        parse_csv_and_insert(path)

if __name__ == "__main__":
    main()