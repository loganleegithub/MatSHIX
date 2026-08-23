from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from matshix.constants import (
    CARRIER_TO_INDEX,
    CARRIER_TO_OPTION_CODE,
    CARRIER_TO_UNDERLYING,
    EXCLUDED_OPTION_CODES,
)


@dataclass(frozen=True)
class AetfPaths:
    root: Path
    option_minutes: str
    option_daily: str
    option_contracts: Path
    etf_minutes: str
    etf_daily: str
    readme: Path

    @classmethod
    def from_root(cls, root: Path) -> AetfPaths:
        resolved = root.expanduser().resolve()
        return cls(
            root=resolved,
            option_minutes=str(resolved / "OPTION/1m_opt/*/*.parquet"),
            option_daily=str(resolved / "OPTION/1d_opt_price/*/*.parquet"),
            option_contracts=resolved / "OPTION/opt_basic.parquet",
            etf_minutes=str(resolved / "ETF/1m_etf/*/*.parquet"),
            etf_daily=str(resolved / "ETF/1d_etf_price/*/*.parquet"),
            readme=resolved / "README.md",
        )

    def validate(self) -> None:
        required = [self.option_contracts, self.readme]
        missing = [str(path) for path in required if not path.is_file()]
        patterns = [self.option_minutes, self.option_daily, self.etf_minutes, self.etf_daily]
        for pattern in patterns:
            parent = Path(pattern.split("*")[0]).parent
            if not parent.exists():
                missing.append(pattern)
        if missing:
            raise FileNotFoundError(f"AETF source is incomplete: {missing}")


@dataclass(frozen=True)
class AetfExtraction:
    option_prices: pd.DataFrame
    etf_marks: pd.DataFrame
    start_session: str
    end_session: str
    session_count: int


def _connection() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    connection.execute("SET threads TO 4")
    connection.execute("SET preserve_insertion_order TO false")
    return connection


def contract_master(paths: AetfPaths) -> pd.DataFrame:
    paths.validate()
    option_codes = tuple(CARRIER_TO_OPTION_CODE.values())
    connection = _connection()
    try:
        frame = connection.execute(
            """
            SELECT
                code AS contract_id,
                opt_code AS option_underlying_code,
                call_put AS option_type,
                exercise_price AS strike,
                maturity_date AS expiry,
                coalesce(per_unit, opt_multiplier) AS contract_unit,
                symbol,
                list_date,
                delist_date,
                CASE
                    WHEN per_unit = 10000
                     AND opt_multiplier = 10000
                     AND symbol NOT LIKE '%A%'
                    THEN true ELSE false
                END AS is_standard
            FROM read_parquet(?)
            WHERE opt_code IN (?, ?, ?, ?)
            """,
            [str(paths.option_contracts), *option_codes],
        ).fetchdf()
    finally:
        connection.close()
    reverse = {value: key for key, value in CARRIER_TO_OPTION_CODE.items()}
    frame["carrier_id"] = frame["option_underlying_code"].map(reverse)
    frame["economic_index_id"] = frame["carrier_id"].map(CARRIER_TO_INDEX)
    frame["underlying_symbol"] = frame["carrier_id"].map(CARRIER_TO_UNDERLYING)
    frame["expiry"] = pd.to_datetime(frame["expiry"].astype(str), format="%Y%m%d")
    frame["list_date"] = pd.to_datetime(frame["list_date"].astype(str), format="%Y%m%d")
    frame["delist_date"] = pd.to_datetime(frame["delist_date"].astype(str), format="%Y%m%d")
    return frame.sort_values(
        ["carrier_id", "expiry", "strike", "option_type", "contract_id"], kind="stable"
    ).reset_index(drop=True)


def extract_history(
    paths: AetfPaths,
    *,
    start: str | None = None,
    end: str | None = None,
) -> AetfExtraction:
    """Extract the four-carrier 14:56 research panel from local AETF parquet.

    The query reads only the columns needed by the business engine and never
    copies the full source corpus into the project.
    """

    paths.validate()
    start_value = "00000000" if start is None else pd.Timestamp(start).strftime("%Y%m%d")
    end_value = "99999999" if end is None else pd.Timestamp(end).strftime("%Y%m%d")
    option_codes = tuple(CARRIER_TO_OPTION_CODE.values())
    underlyings = tuple(CARRIER_TO_UNDERLYING.values())
    connection = _connection()
    try:
        option_prices = connection.execute(
            """
            WITH contracts AS (
                SELECT
                    code AS contract_id,
                    opt_code AS option_underlying_code,
                    call_put AS option_type,
                    exercise_price AS strike,
                    maturity_date AS expiry,
                    coalesce(per_unit, opt_multiplier) AS contract_unit,
                    symbol,
                    list_date,
                    delist_date,
                    CASE
                        WHEN per_unit = 10000
                         AND opt_multiplier = 10000
                         AND symbol NOT LIKE '%A%'
                        THEN true ELSE false
                    END AS is_standard
                FROM read_parquet(?)
                WHERE opt_code IN (?, ?, ?, ?)
            ), daily AS (
                SELECT code, date, vol, amount, oi
                FROM read_parquet(?, union_by_name=true)
                WHERE date BETWEEN ? AND ?
            )
            SELECT
                m.date AS session_date,
                m.code AS contract_id,
                c.option_underlying_code,
                c.option_type,
                c.strike,
                c.expiry,
                c.contract_unit,
                c.is_standard,
                m.close AS price,
                m.vol AS minute_volume,
                coalesce(d.vol, 0) AS daily_volume,
                coalesce(d.amount, 0) AS daily_amount,
                coalesce(d.oi, m.oi, 0) AS open_interest
            FROM read_parquet(?, union_by_name=true) AS m
            JOIN contracts AS c ON c.contract_id = m.code
            LEFT JOIN daily AS d ON d.code = m.code AND d.date = m.date
            WHERE m.date BETWEEN ? AND ?
              AND substr(m.trade_time, 12, 8) = '14:56:00'
              AND c.list_date <= m.date
              AND c.delist_date >= m.date
            """,
            [
                str(paths.option_contracts),
                *option_codes,
                paths.option_daily,
                start_value,
                end_value,
                paths.option_minutes,
                start_value,
                end_value,
            ],
        ).fetchdf()
        etf_marks = connection.execute(
            """
            WITH daily AS (
                SELECT code, date, adj_factor
                FROM read_parquet(?, union_by_name=true)
                WHERE date BETWEEN ? AND ?
                  AND code IN (?, ?, ?, ?)
            )
            SELECT
                m.date AS session_date,
                m.code AS underlying_symbol,
                m.close AS etf_mark,
                d.adj_factor,
                m.close * d.adj_factor AS tr_mark
            FROM read_parquet(?, union_by_name=true) AS m
            JOIN daily AS d ON d.code = m.code AND d.date = m.date
            WHERE m.date BETWEEN ? AND ?
              AND m.code IN (?, ?, ?, ?)
              AND substr(m.trade_time, 12, 8) = '14:56:00'
            """,
            [
                paths.etf_daily,
                start_value,
                end_value,
                *underlyings,
                paths.etf_minutes,
                start_value,
                end_value,
                *underlyings,
            ],
        ).fetchdf()
    finally:
        connection.close()
    reverse_codes = {value: key for key, value in CARRIER_TO_OPTION_CODE.items()}
    option_prices["carrier_id"] = option_prices["option_underlying_code"].map(reverse_codes)
    option_prices["economic_index_id"] = option_prices["carrier_id"].map(CARRIER_TO_INDEX)
    if option_prices["option_underlying_code"].isin(EXCLUDED_OPTION_CODES).any():
        raise AssertionError("excluded 588080 option entered the extracted panel")
    reverse_underlyings = {value: key for key, value in CARRIER_TO_UNDERLYING.items()}
    etf_marks["carrier_id"] = etf_marks["underlying_symbol"].map(reverse_underlyings)
    etf_marks["economic_index_id"] = etf_marks["carrier_id"].map(CARRIER_TO_INDEX)
    for frame in (option_prices, etf_marks):
        frame["session_date"] = pd.to_datetime(frame["session_date"].astype(str), format="%Y%m%d")
    option_prices["expiry"] = pd.to_datetime(option_prices["expiry"].astype(str), format="%Y%m%d")
    common_sessions = sorted(
        set(option_prices["session_date"]).intersection(etf_marks["session_date"])
    )
    if not common_sessions:
        raise ValueError("AETF extraction has no common option/ETF sessions")
    option_prices = option_prices.loc[option_prices["session_date"].isin(common_sessions)].copy()
    etf_marks = etf_marks.loc[etf_marks["session_date"].isin(common_sessions)].copy()
    actual_indices = set(option_prices["economic_index_id"].dropna().astype(str))
    if actual_indices != set(CARRIER_TO_INDEX.values()):
        raise ValueError(f"four-carrier extraction incomplete: {sorted(actual_indices)}")
    option_prices["evidence_tier"] = "RESEARCH_ONLY"
    option_prices["vintage_kind"] = "PROVIDER_RECONSTRUCTED"
    option_prices["licence_scope"] = "LOCAL_RESEARCH_RIGHTS_UNVERIFIED"
    etf_marks["evidence_tier"] = "RESEARCH_ONLY"
    etf_marks["vintage_kind"] = "PROVIDER_RECONSTRUCTED"
    etf_marks["licence_scope"] = "LOCAL_RESEARCH_RIGHTS_UNVERIFIED"
    return AetfExtraction(
        option_prices=option_prices.sort_values(
            ["session_date", "carrier_id", "expiry", "strike", "option_type"], kind="stable"
        ).reset_index(drop=True),
        etf_marks=etf_marks.sort_values(["session_date", "carrier_id"], kind="stable").reset_index(
            drop=True
        ),
        start_session=pd.Timestamp(common_sessions[0]).date().isoformat(),
        end_session=pd.Timestamp(common_sessions[-1]).date().isoformat(),
        session_count=len(common_sessions),
    )


def extract_settlement_history(
    paths: AetfPaths,
    *,
    start: str | None = None,
    end: str | None = None,
) -> AetfExtraction:
    """Extract provider-reconstructed option settlement and ETF 15:00 marks."""

    paths.validate()
    start_value = "00000000" if start is None else pd.Timestamp(start).strftime("%Y%m%d")
    end_value = "99999999" if end is None else pd.Timestamp(end).strftime("%Y%m%d")
    option_codes = tuple(CARRIER_TO_OPTION_CODE.values())
    underlyings = tuple(CARRIER_TO_UNDERLYING.values())
    connection = _connection()
    try:
        option_prices = connection.execute(
            """
            WITH contracts AS (
                SELECT
                    code AS contract_id,
                    opt_code AS option_underlying_code,
                    call_put AS option_type,
                    exercise_price AS strike,
                    maturity_date AS expiry,
                    coalesce(per_unit, opt_multiplier) AS contract_unit,
                    symbol,
                    list_date,
                    delist_date,
                    CASE
                        WHEN per_unit = 10000
                         AND opt_multiplier = 10000
                         AND symbol NOT LIKE '%A%'
                        THEN true ELSE false
                    END AS is_standard
                FROM read_parquet(?)
                WHERE opt_code IN (?, ?, ?, ?)
            )
            SELECT
                d.date AS session_date,
                d.code AS contract_id,
                c.option_underlying_code,
                c.option_type,
                c.strike,
                c.expiry,
                c.contract_unit,
                c.is_standard,
                d.settle AS price,
                d.close AS daily_close,
                d.vol AS daily_volume,
                d.amount AS daily_amount,
                d.oi AS open_interest
            FROM read_parquet(?, union_by_name=true) AS d
            JOIN contracts AS c ON c.contract_id = d.code
            WHERE d.date BETWEEN ? AND ?
              AND c.list_date <= d.date
              AND c.delist_date >= d.date
              AND isfinite(d.settle)
              AND d.settle > 0
            """,
            [
                str(paths.option_contracts),
                *option_codes,
                paths.option_daily,
                start_value,
                end_value,
            ],
        ).fetchdf()
        etf_marks = connection.execute(
            """
            WITH daily AS (
                SELECT code, date, adj_factor
                FROM read_parquet(?, union_by_name=true)
                WHERE date BETWEEN ? AND ?
                  AND code IN (?, ?, ?, ?)
            )
            SELECT
                m.date AS session_date,
                m.code AS underlying_symbol,
                m.close AS etf_mark,
                d.adj_factor,
                m.close * d.adj_factor AS tr_mark
            FROM read_parquet(?, union_by_name=true) AS m
            JOIN daily AS d ON d.code = m.code AND d.date = m.date
            WHERE m.date BETWEEN ? AND ?
              AND m.code IN (?, ?, ?, ?)
              AND substr(m.trade_time, 12, 8) = '15:00:00'
            """,
            [
                paths.etf_daily,
                start_value,
                end_value,
                *underlyings,
                paths.etf_minutes,
                start_value,
                end_value,
                *underlyings,
            ],
        ).fetchdf()
    finally:
        connection.close()
    reverse_codes = {value: key for key, value in CARRIER_TO_OPTION_CODE.items()}
    option_prices["carrier_id"] = option_prices["option_underlying_code"].map(reverse_codes)
    option_prices["economic_index_id"] = option_prices["carrier_id"].map(CARRIER_TO_INDEX)
    if option_prices["option_underlying_code"].isin(EXCLUDED_OPTION_CODES).any():
        raise AssertionError("excluded 588080 option entered the settlement panel")
    reverse_underlyings = {value: key for key, value in CARRIER_TO_UNDERLYING.items()}
    etf_marks["carrier_id"] = etf_marks["underlying_symbol"].map(reverse_underlyings)
    etf_marks["economic_index_id"] = etf_marks["carrier_id"].map(CARRIER_TO_INDEX)
    for frame in (option_prices, etf_marks):
        frame["session_date"] = pd.to_datetime(frame["session_date"].astype(str), format="%Y%m%d")
    option_prices["expiry"] = pd.to_datetime(option_prices["expiry"].astype(str), format="%Y%m%d")
    common_sessions = sorted(
        set(option_prices["session_date"]).intersection(etf_marks["session_date"])
    )
    if not common_sessions:
        raise ValueError("AETF settlement extraction has no common option/ETF sessions")
    option_prices = option_prices.loc[option_prices["session_date"].isin(common_sessions)].copy()
    etf_marks = etf_marks.loc[etf_marks["session_date"].isin(common_sessions)].copy()
    actual_indices = set(option_prices["economic_index_id"].dropna().astype(str))
    if actual_indices != set(CARRIER_TO_INDEX.values()):
        raise ValueError(f"four-carrier settlement extraction incomplete: {sorted(actual_indices)}")
    option_prices["evidence_tier"] = "RESEARCH_ONLY"
    option_prices["vintage_kind"] = "PROVIDER_RECONSTRUCTED"
    option_prices["licence_scope"] = "LOCAL_RESEARCH_RIGHTS_UNVERIFIED"
    etf_marks["evidence_tier"] = "RESEARCH_ONLY"
    etf_marks["vintage_kind"] = "PROVIDER_RECONSTRUCTED"
    etf_marks["licence_scope"] = "LOCAL_RESEARCH_RIGHTS_UNVERIFIED"
    return AetfExtraction(
        option_prices=option_prices.sort_values(
            ["session_date", "carrier_id", "expiry", "strike", "option_type"], kind="stable"
        ).reset_index(drop=True),
        etf_marks=etf_marks.sort_values(["session_date", "carrier_id"], kind="stable").reset_index(
            drop=True
        ),
        start_session=pd.Timestamp(common_sessions[0]).date().isoformat(),
        end_session=pd.Timestamp(common_sessions[-1]).date().isoformat(),
        session_count=len(common_sessions),
    )


def source_summary(paths: AetfPaths) -> dict[str, Any]:
    paths.validate()
    contracts = contract_master(paths)
    return {
        "root": str(paths.root),
        "contract_rows": len(contracts),
        "contracts_by_carrier": {
            str(key): int(value)
            for key, value in contracts.groupby("carrier_id").size().to_dict().items()
        },
        "standard_contracts_by_carrier": {
            str(key): int(value)
            for key, value in contracts.loc[contracts["is_standard"]]
            .groupby("carrier_id")
            .size()
            .to_dict()
            .items()
        },
        "excluded_588080": True,
        "price_kind": "14:56 minute close",
        "evidence_tier": "RESEARCH_ONLY",
        "formal_bid_ask_available": False,
        "fields": list(contracts.columns),
    }


def extraction_metadata(extraction: AetfExtraction) -> dict[str, Any]:
    return {
        "start_session": extraction.start_session,
        "end_session": extraction.end_session,
        "session_count": extraction.session_count,
        "option_price_rows": len(extraction.option_prices),
        "etf_mark_rows": len(extraction.etf_marks),
        "carriers": sorted(extraction.option_prices["carrier_id"].unique().tolist()),
        "economic_indices": sorted(extraction.option_prices["economic_index_id"].unique().tolist()),
    }


def metadata_asdict(paths: AetfPaths) -> dict[str, str]:
    return {key: str(value) for key, value in asdict(paths).items()}
