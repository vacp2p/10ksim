# Python Imports
import asyncio
import os
import shutil
import sys
import traceback
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Self

import pandas as pd
from result import Err, Ok

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Project Imports
from mix.nimlibp2p_plots import (
    plot_in_out_mix_times,
    plot_message_distribution_libp2pmix,
    plot_message_distribution_libp2pmix_2,
    plot_message_distribution_libp2pmix_3,
    plot_message_distribution_libp2pmix_4,
    violation_checks,
)
from src.mesh_analysis.analyzers.custom_analyzer import CustomAnalyzer
from src.mesh_analysis.analyzers.nimlibp2p_analyzer import Nimlibp2pAnalyzer

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "deployments")))

import logging

from deployments.deployment.nimlibp2p.experiments.mix.regression import NimMixNodes

logger = logging.getLogger(__name__)


def get_name(exp):
    counts = exp["nodes_per_statefulset"]
    sets = exp["stateful_sets"]
    nodes_str = "__".join(f"{set}_{count}" for set, count in zip(sets, counts))
    return f"{exp['subdir']}_{nodes_str}__delay_{exp['delay']}_jitter_{exp['jitter']}"


def get_experiment_folders(base_dir: Path) -> List[str]:
    result = []
    for dirpath, dirnames, filenames in os.walk(base_dir):
        if "events.log" in filenames:
            rel_path = os.path.relpath(dirpath, base_dir)
            result.append(rel_path)
    return result


def get_nimlibp2p_mix_exps() -> List[dict]:
    start_dir = Path("../deployments/")
    subdirs = []

    # Relative paths to parent of experiments.
    start_subs = [
        # Example
        # Path("/workdir_multi/27c1e0b8546e12247f1c6ecd6fc1a09e0cb5ade7"),
    ]
    for start_sub in start_subs:
        subdirs += [start_sub / path for path in get_experiment_folders(start_dir / start_sub)]

    logger.info(f"found {len(subdirs)} paths")
    for path in subdirs:
        logger.info(f"path: {path}")

    exps = []
    for subdir in subdirs:
        try:
            exp = {}
            events_log_path = start_dir / subdir / "events.log"
            metadata = NimMixNodes.get_metadata_event(events_log_path)
            params = metadata["experiment"]["params"]

            exp = {
                "stateful_sets": ["pod", "mix"],
                "nodes_per_statefulset": [params["num_gossip_nodes"], params["mix_nodes"]],
                "mix_node_name": "mix",
                "gossip_node_name": "pod",
                "num_gossip_nodes": params["num_gossip_nodes"],
                "num_mix_nodes": params["mix_nodes"],
                "delay": params["delay"],
                "jitter": params["jitter"],
                "start": metadata["times"]["start"],
                "end": metadata["messages"]["end"],
                "subdir": subdir,
                "events_log": events_log_path,
            }
            exp["name"] = get_name(exp)

            exps.append(exp)
        except Exception as e:
            full_trace = traceback.format_exc()
            logger.error(f"exception: {full_trace}")
            raise
    return exps


class StackGen:
    _args: dict = {}

    def vaclab(self) -> Self:
        self._args.update(
            {
                "url": "https://vlselect.vaclab.org/select/logsql/query",
                "type": "vaclab",
            }
        )
        return self

    def libp2p_mix(self, exp) -> Self:
        self._args.update(
            {
                "container_name": "container-0",
                "extra_fields": ["kubernetes.pod_name", "kubernetes.pod_node_name"],
            }
        )

        def convert_timestamp(input_timestamp: str) -> str:
            # Parse the ISO 8601 timestamp string including the 'Z' as UTC
            dt = datetime.strptime(input_timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
            # Format to the desired output without milliseconds and timezone
            return dt.strftime("%Y-%m-%dT%H:%M:%S")

        start = convert_timestamp(exp["start"])
        end = convert_timestamp(exp["end"])

        self._args.update(
            {
                "start_time": start,
                "end_time": end,
                "reader": "victoria",
                "stateful_sets": exp["stateful_sets"],
                "nodes_per_statefulset": exp["nodes_per_statefulset"],
            }
        )
        return self

    def build(self) -> dict:
        required_fields = [
            "type",
            "url",
            "start_time",
            "end_time",
            "reader",
            "stateful_sets",
            "nodes_per_statefulset",
            "container_name",
            "extra_fields",
        ]
        for key in required_fields:
            assert key in self._args

        return self._args


@contextmanager
def extra_log_handler(logger, handler):
    logging.getLogger().setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        yield
    finally:
        for handler in logger.handlers:
            handler.flush()
        logger.removeHandler(handler)
        handler.close()


@contextmanager
def log_to_path(log_path):
    """
    Warning: Removes previous log.
    """
    try:
        os.makedirs(log_path.parent, exist_ok=True)
        os.remove(log_path)
    except Exception:
        pass

    file_handler = logging.FileHandler(log_path)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    with extra_log_handler(logging.getLogger(), file_handler):
        yield


async def plots(base_data_path, exp):
    logger.info("-- plots --")
    base_out_path = Path("local_data/simulations_data/out")
    exp_name = exp["name"]
    plots_base_data_path = base_data_path / exp_name / "summary"
    # plot_compare_message_distribution_libp2pmix(path1, path2, dumppath)
    # plot_in_out_mix_times(base_data_path / "received.csv", base_out_path / "out.png")

    # refresh out plots folder
    try:
        shutil.rmtree(base_out_path / exp_name)
    except FileNotFoundError:
        pass

    tasks = []

    title = "plot_message_distribution_libp2pmix"

    received_summary_path = Path(plots_base_data_path / "received.csv")
    sent_summary_path = Path(plots_base_data_path / "sent.csv")
    mix_summary_path = Path(plots_base_data_path / "mix.csv")

    received_df = pd.read_csv(received_summary_path, parse_dates=["timestamp", "sentAt"])
    sent_df = pd.read_csv(sent_summary_path, parse_dates=["timestamp"])
    mix_df = pd.read_csv(mix_summary_path, parse_dates=["timestamp"])

    def ensure_utc_aware(df, col):
        if not pd.api.types.is_datetime64tz_dtype(df[col]):
            # if tz-naive, localize as UTC
            df[col] = pd.to_datetime(df[col], utc=True)
        return df

    received_df = ensure_utc_aware(received_df, "sentAt")
    received_df = ensure_utc_aware(received_df, "timestamp")
    sent_df = ensure_utc_aware(sent_df, "timestamp")
    mix_df = ensure_utc_aware(mix_df, "timestamp")

    dump_path = base_out_path / exp_name

    tasks.append(
        asyncio.create_task(
            plot_message_distribution_libp2pmix(
                received_df,
                sent_df,
                dump_path,
            )
        )
    )

    tasks.append(
        asyncio.create_task(
            plot_message_distribution_libp2pmix_2(
                received_df,
                sent_df,
                mix_df,
                base_out_path / exp_name,
                exp,
            )
        )
    )

    tasks.append(
        asyncio.create_task(
            plot_in_out_mix_times(
                Path(plots_base_data_path / "received.csv"),
                base_out_path / exp_name,
                exp,
            )
        )
    )

    tasks.append(
        asyncio.create_task(
            plot_message_distribution_libp2pmix_3(
                received_df,
                sent_df,
                mix_df,
                base_out_path / exp_name,
                exp,
            )
        )
    )

    tasks.append(
        asyncio.create_task(
            plot_message_distribution_libp2pmix_4(
                Path(plots_base_data_path / "received.csv"),
                Path(plots_base_data_path / "sent.csv"),
                Path(plots_base_data_path / "mix.csv"),
                base_out_path / exp_name,
                exp,
            )
        )
    )

    tasks.append(
        plot_message_distribution_libp2pmix_4(
            Path(plots_base_data_path / "received.csv"),
            Path(plots_base_data_path / "sent.csv"),
            Path(plots_base_data_path / "mix.csv"),
            base_out_path / exp_name,
            exp,
        )
    )

    await asyncio.gather(*tasks)


def scrape(base_data_path, exp, stack):
    logger.info("-- scrape --")
    log_analyzer = Nimlibp2pAnalyzer(
        dump_analysis_dir=base_data_path / exp["name"],
        # local_folder_to_analyze="local_data/simulations_data/mix_intermediate/",
        **stack,
    )
    log_analyzer.analyze_mix_trace(n_jobs=4)

    custom_analyzer = CustomAnalyzer(
        dump_analysis_dir=base_data_path / exp["name"],
        **stack,
    )
    custom_analyzer.scrape(n_jobs=4)

    print("-- reliability --")
    log_analyzer.analyze_reliability(n_jobs=4)


def setup_logger():
    logging.getLogger().setLevel(logging.INFO)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(stream_handler)


async def process_experiment(exp) -> dict:
    base_data_path = Path("local_data/simulations_data/mix_intermediate")
    log_path = base_data_path / exp["name"] / "out.log"

    results_dict = {"exp": exp}

    with log_to_path(log_path):
        logger.info(log_path)
        print("\n\n\n\n")
        exp_name = exp["name"]
        logger.info(f"experiment: {exp_name}\n")
        logger.info("---")
        logger.info(f"full experiment: {exp}\n")

        stack = StackGen().vaclab().libp2p_mix(exp).build()
        logger.info(f"stack: {stack}")

        scrape(base_data_path, exp, stack)

        plots_base_data_path = base_data_path / exp_name / "summary"
        total_nodes = exp["num_gossip_nodes"] + exp["num_mix_nodes"]
        for k, v in exp.items():
            print(f"{k}: {v}")

        # Failure checks
        custom_analyzer = CustomAnalyzer(
            dump_analysis_dir=base_data_path / exp["name"],
            **stack,
        )
        analyzer_results = custom_analyzer.analyze(n_jobs=4)

        violation_results = violation_checks(
            Path(plots_base_data_path / "received.csv"),
            Path(plots_base_data_path / "sent.csv"),
            Path(plots_base_data_path / "mix.csv"),
            total_nodes,
        )

        results_dict.update(analyzer_results)
        results_dict.update(violation_results)

        try:
            await plots(base_data_path, exp)
            results_dict["plots"] = Ok(None)
        except Exception as e:
            results_dict["plots"] = Err(f"Failed ({e})")

    return results_dict


def unwrap_err_or(result, default):
    if result.is_err():
        return result.unwrap_err()
    return default


def print_table(results_list: List[dict]):
    if not results_list:
        print("No results")
        return
    new_list = []
    for result in results_list:
        new_list.append(
            {
                "mix": result["exp"]["num_mix_nodes"],
                "non-mix": result["exp"]["num_gossip_nodes"],
                "delay": result["exp"]["delay"],
                "jitter": result["exp"]["jitter"],
                "failed_to_connect": unwrap_err_or(result["failed_to_connect"], "Ok"),
                "any_failure": unwrap_err_or(result["any_failure"], "Ok"),
                "too_many_connections": unwrap_err_or(result["too_many_connections"], "Ok"),
                "plots": unwrap_err_or(result["plots"], "Ok"),
            }
        )

    columns = [
        "mix",
        "non-mix",
        "delay",
        "jitter",
        "failed_to_connect",
        "any_failure",
        "too_many_connections",
    ]
    df = pd.DataFrame(new_list)
    print(df[columns].to_string(index=False))


async def main():
    setup_logger()

    succeeded = 0
    failed = 0

    all_results = []
    exps = get_nimlibp2p_mix_exps()
    for exp in exps:
        logger.info("--- loop ---")
        results = await process_experiment(exp)
        all_results.append(results)
        passed = not any([isinstance(item, Err) for item in results.values()])
        if passed:
            succeeded += 1
        else:
            failed += 1

    print(f"Succeeded: {succeeded}\tFailed: {failed}")

    print_table(all_results)

    if failed:
        logger.error("At least one check failed!")


if __name__ == "__main__":
    asyncio.run(main())
