import pandas as pd
import networkx as nx
from datetime import timedelta
import ipywidgets as widgets


def add_elapsed_time(df: pd.DataFrame):
    first_timestamps = df.groupby('msg_hash').apply(
        lambda x: x.index.get_level_values('timestamp').min())
    df['elapsed_time'] = df.index.get_level_values('timestamp') - df.index.get_level_values(
        'msg_hash').map(first_timestamps)
    df['elapsed_time'] = df['elapsed_time'] // timedelta(milliseconds=1)

    return df


def prepare_dropdowns(dataf: pd.DataFrame):
    msg_dropdown = widgets.SelectMultiple(
        options=dataf.index.get_level_values(0).drop_duplicates(),
        description='Msg hash',
        disabled=False,
        layout={'height': '100px', 'width': '100%'})

    timestamp_dropdown = widgets.SelectMultiple(
        options=[],
        description='Timestamp',
        disabled=False,
        layout={'height': '100px', 'width': '100%'})

    def update_timestamps(change):
        selected_hashes = change['new']
        timestamps = dataf.loc[selected_hashes[0]].index.get_level_values(
            'timestamp').drop_duplicates()
        timestamp_dropdown.options = timestamps

    msg_dropdown.observe(update_timestamps, names='value')

    return msg_dropdown, timestamp_dropdown


def get_node_position(df: pd.DataFrame):
    data_prepared = df.reset_index()
    complete_graph = nx.from_pandas_edgelist(data_prepared, 'sender_peer_id', 'receiver_peer_id',
                                             edge_attr=['timestamp', 'msg_hash', 'elapsed_time'],
                                             create_using=nx.DiGraph)
    g_pos_layout = nx.kamada_kawai_layout(complete_graph)

    return g_pos_layout


def display_msg_trace(x, y, g_pos_layout, data_, ax_):
    # todo maintain limits?
    ax_.clear()
    ax_.set_xlim(-2, 2)
    ax_.set_ylim(-2, 2)

    data_ = data_[data_.index.get_level_values(0) == x[0]]
    first_timestamp = data_.index.get_level_values(1)[0]
    df_ = data_.loc[(x[0], first_timestamp,):(x[0], y[0])]
    df_.reset_index(inplace=True)

    selected_graph = nx.from_pandas_edgelist(df_, 'sender_peer_id', 'receiver_peer_id',
                                             edge_attr=['timestamp', 'msg_hash',
                                                        'elapsed_time'],
                                             create_using=nx.DiGraph)

    g_pos_layout_selected = {key: g_pos_layout[key] for key in list(selected_graph.nodes)}

    nx.draw(selected_graph, g_pos_layout_selected, ax=ax_, with_labels=True)
    edge_labels = {}
    for u, v, data in selected_graph.edges(data=True):
        edge_labels[u, v] = f"{data['elapsed_time']}ms"

    nx.draw_networkx_edge_labels(selected_graph, g_pos_layout_selected, edge_labels=edge_labels,
                                 ax=ax_)



