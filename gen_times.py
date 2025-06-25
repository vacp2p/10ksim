from datetime import datetime, timedelta
import os
import re


data = {
    "v0.36.0-rc.0": {
        "1k_1s_1KB": {
            "wide": ("2025-06-23 18:36:44", "2025-06-23 18:59:09"),
            "narrow": ("2025-06-23 18:45:00", "2025-06-23 18:53:00"),
        },
        "1k_5s_1KB": {
            "wide": ("2025-06-23 19:01:04", "2025-06-23 20:21:38"),
            "narrow": ("2025-06-23 19:26:52", "2025-06-23 20:13:42"),
        },
        "1k_10s_1KB": {
            "wide": ("2025-06-23 20:22:57", "2025-06-23 22:32:38"),
            "narrow": ("2025-06-23 20:42:03", "2025-06-23 22:16:55"),
        },
        "2k_1s_1KB": {
            "wide": ("2025-06-23 22:35:15", "2025-06-23 23:09:16"),
            "narrow": ("2025-06-23 22:52:44", "2025-06-23 23:00:56"),
        },
        "2k_5s_1KB": {
            "wide": ("2025-06-23 23:08:20", "2025-06-24 00:21:30"),
            "narrow": ("2025-06-23 23:24:37", "2025-06-24 00:12:46"),
        },
        "2k_10s_1KB": {
            "wide": ("2025-06-24 00:19:33", "2025-06-24 02:29:44"),
            "narrow": ("2025-06-24 00:37:05", "2025-06-24 02:12:57"),
        },
        "3k_1s_1KB": {  # questionable.
            "wide": ("2025-06-24 03:22:18", "2025-06-24 04:23:57"),
            "narrow": ("2025-06-24 03:47:49", "2025-06-24 03:55:46"),
        },
        "3k_5s_1KB": {
            "wide": ("2025-06-24 05:33:01", "2025-06-24 06:45:14"),
            "narrow": ("2025-06-24 05:48:38", "2025-06-24 06:38:17"),
        },
        "3k_10s_1KB": {
            "wide": ("2025-06-24 15:33:51", "2025-06-24 16:14:10"),
            "narrow": ("2025-06-24 15:51:12", "2025-06-24 15:58:26"),
        },
    }
}

def subtract_hours(time : str, hours=2) -> str:
    dt = datetime.strptime(time, "%Y-%m-%d %H:%M:%S")
    new_dt = dt - timedelta(hours=hours)
    return new_dt.strftime("%Y-%m-%d %H:%M:%S")

def scrape_yaml_line(version, experiment, time_interval):
    base_dump_scrape = "test/nwaku/" # Must match your `scrape.yaml`
    start, end = time_interval
    start = subtract_hours(start)
    end = subtract_hours(end)
    # example output: - [ "2025-06-24 05:48:38", "2025-06-24 06:38:17", "3K-5mgs-s-1KB" ]
    return f"- [ \"{start}\", \"{end}\", \"{experiment}\" ]"

def log_analysis_line(version, experiment, time_interval):
    def transform_date(text):
        return re.sub(r'(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})', r'\1T\2', text)
    base_dump_log_analysis = "local_data/simulations_data/"
    start_time, end_time = time_interval
    start_time = transform_date(start_time)
    end_time = transform_date(end_time)
    # example output: ("2025-06-23T18:36:44", "2025-06-23T18:59:09", "v0.36.0-rc.0", "1k_1s_1KB"),
    path = os.path.join(base_dump_log_analysis, experiment, version)
    return f"(\"{start_time}\", \"{end_time}\", \"{path}/\"),"


def main():
    example_log_analysis = []
    scrape_yaml = []
    for version, version_dict in data.items():
        for experiment, experiment_dict in version_dict.items():
            example_log_analysis.append( log_analysis_line( version, experiment, experiment_dict["wide"] ) )
            scrape_yaml.append( scrape_yaml_line( version, experiment, experiment_dict["narrow"]) )

    for line in example_log_analysis:
        print(line)

    print("\n")

    for line in scrape_yaml:
        print(line)


if __name__ == "__main__":
    main()