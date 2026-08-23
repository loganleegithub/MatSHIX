from __future__ import annotations

import json
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Any

import typer

from matshix.dashboard import export_dashboard as render_dashboard
from matshix.data.aetf import AetfPaths, source_summary
from matshix.pipeline import build_research_project
from matshix.research.shortvol import run_shortvol_backtest
from matshix.research.shortvol_timing import run_shortvol_timing_diagnostic
from matshix.research.weather_v2_audit import run_weather_v2_business_audit
from matshix.serialization import write_json
from matshix.v2.outcomes import run_v2_outcome_build
from matshix.validation import verify_research_outputs

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="MatSHIX 上交所 ETF 期权市场叙事与概率引擎",
)


def _emit(payload: Any) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.command()
def doctor(
    project_dir: Annotated[Path, typer.Option("--project-dir")] = Path("."),
    aetf_root: Annotated[Path | None, typer.Option("--aetf-root")] = None,
) -> None:
    """Check the frozen runtime and optional local real-data source."""

    expected = {
        "duckdb": "1.5.0",
        "exchange-calendars": "4.13.1",
        "numpy": "2.3.5",
        "pandas": "2.2.3",
        "plotly": "6.5.2",
        "pyarrow": "25.0.0",
        "scikit-learn": "1.7.2",
        "scipy": "1.17.0",
    }
    installed: dict[str, str | None] = {}
    for package in expected:
        try:
            installed[package] = version(package)
        except PackageNotFoundError:
            installed[package] = None
    runtime_ok = all(installed[name] == value for name, value in expected.items())
    project = project_dir.expanduser().resolve()
    payload: dict[str, Any] = {
        "runtime_contract_ok": runtime_ok,
        "expected": expected,
        "installed": installed,
        "project_contracts_present": all(
            (project / path).is_file()
            for path in (
                "MATSHIX_PRE_DEVELOPMENT_REPORT.md",
                "configs/model_v1.yaml",
                "configs/source_manifest_v1.yaml",
                "schemas/daily_snapshot.schema.json",
            )
        ),
    }
    if aetf_root is not None:
        try:
            payload["aetf"] = source_summary(AetfPaths.from_root(aetf_root))
            payload["aetf_source_ok"] = True
        except (FileNotFoundError, ValueError) as exc:
            payload["aetf_source_ok"] = False
            payload["aetf_error"] = str(exc)
    _emit(payload)
    if not runtime_ok or payload.get("aetf_source_ok") is False:
        raise typer.Exit(code=1)


@app.command("build-research-history")
def build_research_history(
    aetf_root: Annotated[Path, typer.Option("--aetf-root")],
    project_dir: Annotated[Path, typer.Option("--project-dir")] = Path("."),
    start: Annotated[str | None, typer.Option("--start")] = None,
    end: Annotated[str | None, typer.Option("--end")] = None,
) -> None:
    """Run the complete real AETF research chain without claiming formal publication."""

    result = build_research_project(
        aetf_root=aetf_root,
        project_dir=project_dir,
        start=start,
        end=end,
        progress=lambda message: typer.echo(f"[MatSHIX] {message}", err=True),
    )
    _emit(asdict(result))


@app.command("export-dashboard")
def export_dashboard_command(
    project_dir: Annotated[Path, typer.Option("--project-dir")] = Path("."),
) -> None:
    """Export the standalone trader dashboard from verified engine outputs."""

    project = project_dir.expanduser().resolve()
    output = render_dashboard(
        dashboard_data=project / "outputs/research/dashboard_data.json",
        output=project / "outputs/dashboard/index.html",
    )
    _emit({"dashboard": str(output), "standalone": True})


@app.command("accept-real-research")
def accept_real_research(
    project_dir: Annotated[Path, typer.Option("--project-dir")] = Path("."),
) -> None:
    """Reconcile JSON, normalized Parquet, replay history and the formal boundary."""

    project = project_dir.expanduser().resolve()
    result = verify_research_outputs(project)
    payload = asdict(result)
    write_json(project / "outputs/acceptance/verification.json", payload)
    _emit(payload)
    if not result.passed:
        raise typer.Exit(code=1)


@app.command("audit-weather-v2")
def audit_weather_v2(
    aetf_root: Annotated[Path, typer.Option("--aetf-root")] = Path(
        "/Users/logan/OptiMatrix_DATA/AETF"
    ),
    project_dir: Annotated[Path, typer.Option("--project-dir")] = Path("."),
) -> None:
    """Run the strategy-blind Stage A business audit against the frozen V1 baseline."""

    artifacts = run_weather_v2_business_audit(project_dir=project_dir, aetf_root=aetf_root)
    _emit(
        {
            "audit_status": artifacts.summary["audit_status"],
            "daily": str(artifacts.daily_path),
            "summary": str(artifacts.summary_path),
            "audit": str(artifacts.audit_path),
            "defect_counts": artifacts.summary["defect_counts"],
            "semantic_implementation_started": False,
        }
    )


@app.command("build-v2-outcomes")
def build_v2_outcomes(
    aetf_root: Annotated[Path, typer.Option("--aetf-root")] = Path(
        "/Users/logan/OptiMatrix_DATA/AETF"
    ),
    project_dir: Annotated[Path, typer.Option("--project-dir")] = Path("."),
    start: Annotated[str | None, typer.Option("--start")] = None,
    end: Annotated[str | None, typer.Option("--end")] = None,
) -> None:
    """Build the Authority-bound H1 era and H2 strategy-blind outcome ledgers."""

    artifacts = run_v2_outcome_build(
        project_dir=project_dir,
        aetf_root=aetf_root,
        start=start,
        end=end,
    )
    _emit(
        {
            "outcome_integrity": artifacts.coverage["gates"]["outcome_integrity"],
            "era_registry": str(artifacts.era_registry_path),
            "outcome_ledger": str(artifacts.outcome_ledger_path),
            "issue_ledger": str(artifacts.issue_ledger_path),
            "coverage": str(artifacts.coverage_path),
            "handcheck": str(artifacts.handcheck_path),
            "strategy_inputs_used": False,
        }
    )
    if artifacts.coverage["gates"]["outcome_integrity"] != "PASS":
        raise typer.Exit(code=1)


@app.command("backtest-510300-shortvol")
def backtest_510300_shortvol(
    aetf_root: Annotated[Path, typer.Option("--aetf-root")] = Path(
        "/Users/logan/OptiMatrix_DATA/AETF"
    ),
    project_dir: Annotated[Path, typer.Option("--project-dir")] = Path("."),
    output_dir: Annotated[Path | None, typer.Option("--output-dir")] = None,
) -> None:
    """Run the 2023+ 510300 ETF versus minute-proxy short-vol comparison."""

    artifacts = run_shortvol_backtest(
        project_dir=project_dir,
        aetf_root=aetf_root,
        output_dir=output_dir,
        progress=lambda message: typer.echo(f"[MatSHIX backtest] {message}", err=True),
    )
    _emit(
        {
            "research_status": artifacts.report["research_status"],
            "report": str(artifacts.report_path),
            "daily_ledger": str(artifacts.daily_ledger_path),
            "trade_ledger": str(artifacts.trade_ledger_path),
            "rejection_ledger": str(artifacts.rejection_ledger_path),
            "html": str(artifacts.html_path),
            "periods": artifacts.report["periods"],
        }
    )


@app.command("diagnose-510300-shortvol-timing")
def diagnose_510300_shortvol_timing(
    aetf_root: Annotated[Path, typer.Option("--aetf-root")] = Path(
        "/Users/logan/OptiMatrix_DATA/AETF"
    ),
    project_dir: Annotated[Path, typer.Option("--project-dir")] = Path("."),
    output_dir: Annotated[Path | None, typer.Option("--output-dir")] = None,
) -> None:
    """Test whether known MatSHIX states separate future good and bad iron-condor outcomes."""

    artifacts = run_shortvol_timing_diagnostic(
        project_dir=project_dir,
        aetf_root=aetf_root,
        output_dir=output_dir,
        progress=lambda message: typer.echo(f"[MatSHIX timing] {message}", err=True),
    )
    _emit(
        {
            "research_status": artifacts.report["research_status"],
            "conclusion": artifacts.report["conclusion"],
            "report": str(artifacts.report_path),
            "opportunity_panel": str(artifacts.panel_path),
            "market_stress_panel": str(artifacts.market_stress_panel_path),
            "state_path_ledger": str(artifacts.state_path_ledger_path),
            "worst_scenarios": str(artifacts.worst_scenarios_path),
            "html": str(artifacts.html_path),
            "primary_horizon": artifacts.report["primary_horizon"],
        }
    )


@app.command("build-all")
def build_all(
    aetf_root: Annotated[Path, typer.Option("--aetf-root")],
    project_dir: Annotated[Path, typer.Option("--project-dir")] = Path("."),
    start: Annotated[str | None, typer.Option("--start")] = None,
    end: Annotated[str | None, typer.Option("--end")] = None,
) -> None:
    """Build history, export the dashboard, and run real-data reconciliation."""

    project = project_dir.expanduser().resolve()
    result = build_research_project(
        aetf_root=aetf_root,
        project_dir=project,
        start=start,
        end=end,
        progress=lambda message: typer.echo(f"[MatSHIX] {message}", err=True),
    )
    dashboard = render_dashboard(
        dashboard_data=project / "outputs/research/dashboard_data.json",
        output=project / "outputs/dashboard/index.html",
    )
    verification = verify_research_outputs(project)
    write_json(project / "outputs/acceptance/verification.json", asdict(verification))
    _emit(
        {
            "build": asdict(result),
            "dashboard": str(dashboard),
            "verification": asdict(verification),
        }
    )
    if not verification.passed:
        raise typer.Exit(code=1)
