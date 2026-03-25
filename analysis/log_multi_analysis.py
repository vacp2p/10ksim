import asyncio
import json
import logging
import os
import sys
import traceback
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Self

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "deployments")))


from src.mesh_analysis.analyzers.analyzer import Analyzer
from src.mesh_analysis.analyzers.data_puller import DataPuller
from src.mesh_analysis.analyzers.nimlibp2p_analyzer import Nimlibp2pAnalyzer
from src.mesh_analysis.analyzers.table_builders import TableBuilder

logger = logging.getLogger(__name__)


@contextmanager
def extra_log_handler(logger, handler, level=logging.INFO):
    logging.getLogger().setLevel(level)
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

    current_level = logger.getEffectiveLevel()
    with extra_log_handler(logging.getLogger(), file_handler, current_level):
        yield


def setup_logger():
    level = logging.DEBUG
    logging.getLogger().setLevel(level)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(level)
    logging.getLogger().addHandler(stream_handler)


def get_folders(base_dir: Path, file_name: str) -> Iterator[str]:
    """Yield folders under `base_dir` containing files with the given `file_name`"""
    for dirpath, _dirnames, filenames in os.walk(base_dir):
        if file_name in filenames:
            yield os.path.relpath(dirpath, base_dir)


def get_experiments(*, experiment_name: Optional[str] = None) -> Iterator[dict]:
    start_dir = Path("../deployments/")
    subdirs = []

    # Relative paths to parent of experiments.
    start_subs = [
        # TODO: Put your paths here.
    ]

    for start_sub in start_subs:
        subdirs += [
            start_sub / path for path in get_folders(start_dir / start_sub, "metadata.json")
        ]
    for d in subdirs:
        logger.info(d)

    logger.info(f"found {len(subdirs)} paths")
    for path in subdirs:
        logger.info(f"path: {path}")

    for subdir in subdirs:
        try:
            metadata_log_path = start_dir / subdir / "metadata.json"
            logger.info(f"Events log path: {metadata_log_path}")
            with open(metadata_log_path, "r", encoding="utf-8") as f:
                exp = json.load(f)
            yield exp
        except Exception as e:
            full_trace = traceback.format_exc()
            logger.error(f"exception: {full_trace}")
            raise


class StackGen:
    _args: dict = {}

    def vaclab(self) -> Self:
        self._args.update(
            {
                "url": "https://vlselect.lab.vac.dev/select/logsql/query",
                "type": "vaclab",
                "reader": "victoria",
            }
        )
        return self

    def local(self, folder) -> Self:
        self._args.update({"local_folder": folder})
        return self

    def with_experiment(self, exp: dict) -> Self:
        self._args.update(exp["stack"])
        return self

    def build(self) -> dict:
        required_fields = [
            "type",
            "url",
            "start_time",
            "end_time",
            "stateful_sets",
            "nodes_per_statefulset",
            "container_name",
            "extra_fields",
        ]
        for key in required_fields:
            assert key in self._args, f"Missing key in stack. key: `{key}` stack: `{self._args}`"

        return self._args


async def process_experiment(exp: dict) -> dict:
    exp_name = exp["stack"]["name"]
    base_data_path = Path(f"local_data/simulations_data/{exp_name}")
    log_path = base_data_path / exp_name / "out.log"

    results_dict = {"exp": exp}
    with log_to_path(log_path):
        logger.info(f"log_path: {log_path}")
        logger.info(f"Processing experiment: {exp_name}\n")
        exp["stack"] = StackGen().vaclab().with_experiment(exp).build()
        new_analyzer = get_analyzer_for_dev_testing(exp)
        results_dict["results"] = new_analyzer.run()

    return results_dict


def get_analyzer_for_dev_testing(exp) -> Analyzer:
    stack = exp["stack"]
    params = exp["params"]
    data_puller = DataPuller().with_kwargs(stack)
    stateful_sets = stack["stateful_sets"]
    nodes_per_statefulset = stack["nodes_per_statefulset"]

    # TODO: We search for all StatefulSets in our exp["stack"],
    # but the bootstrap nodes are relay=False, so they are filtered here.
    reliability = [
        ss
        for ss in zip(stack["stateful_sets"], stack["nodes_per_statefulset"])
        if "bootstrap" not in ss[0]
    ]

    return (
        Nimlibp2pAnalyzer()
        .with_data_puller(data_puller)
        .with_ss_check(stateful_sets, nodes_per_statefulset)
        .with_reliability_check(
            stateful_sets=[ss[0] for ss in reliability],
            nodes_per_ss=[ss[1] for ss in reliability],
            expected_num_peers=params["num_nodes"],
            expected_num_messages=params["num_messages"],
        )
        .with_dump_analysis_dir(f"local_data/simulations_data/{exp['stack']['name']}/")
    )


async def main():
    setup_logger()

    all_statuses = defaultdict(int)
    summary = defaultdict(int)

    all_results = []
    for exp in get_experiments():
        try:
            results = await process_experiment(exp)
            all_results.append(results)
            passed = True
            for item in results["results"]:
                all_statuses[item.status] += 1
                if item.status != "passed":
                    passed = False

            if passed:
                summary["passed"] += 1
        except Exception as e:
            # Catch all exceptions so we can still print results table
            # even if an experiment had a problem.
            logger.error(f"exception: {e}")
            full_trace = traceback.format_exc()
            logger.error(f"exception: {full_trace}")

    table_builder = TableBuilder()
    for result in all_results:
        table_builder.add_experiment(result["exp"]["stack"]["name"], results["results"])

    table_builder.csv("./out_table.csv")
    table_builder.excel("./out_excel_table.xlsx")
    logger.info(table_builder.tree())

    not_passed = len(all_results) - summary["passed"]
    logger.info(f"Passed: {summary['passed']}\nNot Passed: {not_passed}\nTotal: {len(all_results)}")
    logger.info(f"All results:\n{json.dumps(all_statuses, indent=2)}")

    if not_passed:
        logger.error("At least one check failed!")


if __name__ == "__main__":
    asyncio.run(main())
