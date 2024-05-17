import pandas as pd
from datetime import timedelta


def add_elapsed_time(df: pd.DataFrame):
    first_timestamps = df.groupby('msg_hash').apply(
        lambda x: x.index.get_level_values('timestamp').min())
    df['elapsed_time'] = df.index.get_level_values('timestamp') - df.index.get_level_values(
        'msg_hash').map(first_timestamps)
    df['elapsed_time'] = df['elapsed_time'] // timedelta(milliseconds=1)

    return df
