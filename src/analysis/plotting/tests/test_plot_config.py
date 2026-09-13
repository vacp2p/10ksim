from src.analysis.data.data_file_handler import DataPath
from src.analysis.plotting.config import PlotConfigBuilder


def test_with_include_files_stores_metric_folder_file_filter():
    config = PlotConfigBuilder(name="in").with_include_files(["mplex", "quic", "yamux"]).build()

    assert config.include_files == ["mplex", "quic", "yamux"]


def test_with_group_adds_data_paths(tmp_path):
    data_paths = [
        DataPath(name="mplex", path=tmp_path / "asd_run_0", file_name="mplex"),
        DataPath(name="quic", path=tmp_path / "asd_run_1", file_name="quic"),
    ]

    config = PlotConfigBuilder(name="in").with_group("scrapes", data_paths).build()

    assert len(config.groups) == 1
    assert config.groups[0].name == "scrapes"
    assert [(path.name, path.path, path.file_name) for path in config.groups[0].data_paths] == [
        ("mplex", tmp_path / "asd_run_0", "mplex"),
        ("quic", tmp_path / "asd_run_1", "quic"),
    ]


def test_with_groups_adds_existing_groups(tmp_path):
    group = (
        PlotConfigBuilder(name="source")
        .with_group(
            "scrapes", [DataPath(name="mplex", path=tmp_path / "asd_run_0", file_name="mplex")]
        )
        .build()
        .groups[0]
    )

    config = PlotConfigBuilder(name="target").with_groups(group).build()

    assert len(config.groups) == 1
    assert config.groups[0].name == "scrapes"


def test_with_x_order_sets_plot_order():
    config = PlotConfigBuilder(name="in").with_x_order(["mplex", "yamux", "quic"]).build()

    assert config.x_order == ["mplex", "yamux", "quic"]


def test_with_folders_adds_folder_group(tmp_path):
    config = PlotConfigBuilder(name="in").with_folders([tmp_path / "v1", tmp_path / "v2"]).build()

    assert len(config.groups) == 1
    assert config.groups[0].name == "folders"
    assert [(path.name, path.path) for path in config.groups[0].data_paths] == [
        ("v1", tmp_path / "v1"),
        ("v2", tmp_path / "v2"),
    ]
