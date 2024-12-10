# Python Imports
import base64
import io
import networkx as nx
import pandas as pd


def read_csv_from_file(contents):
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    return pd.read_csv(io.StringIO(decoded.decode('utf-8')))


def get_fixed_positions(df):
    graph = nx.DiGraph()

    for _, row in df.iterrows():
        sender = row['sender_peer_id']
        receiver = row['receiver_peer_id']

        if not graph.has_node(sender):
            graph.add_node(sender)
        if not graph.has_node(receiver):
            graph.add_node(receiver)

    # Generate fixed positions for the nodes using a layout algorithm
    fixed_pos = nx.spring_layout(graph, seed=0)
    fixed_pos_serializable = {node: pos.tolist() for node, pos in fixed_pos.items()}

    return fixed_pos_serializable
