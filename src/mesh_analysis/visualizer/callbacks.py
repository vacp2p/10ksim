# Python Imports
import io
import json
import networkx as nx
import pandas as pd
import plotly.graph_objects as go

# Project Imports
from dash import Input, Output, State, ctx
from utils import read_csv_from_file, get_fixed_positions


def register_callbacks(app):
    @app.callback(
        [Output('df-storage', 'children'),
         Output('positions-storage', 'children')],
        [Input('upload-data', 'contents')],
    )
    def upload_files(content):
        if content is None:
            return None, None

        df = read_csv_from_file(content)
        positions = get_fixed_positions(df)
        positions_json = json.dumps(positions)

        return df.to_json(date_format='iso', orient='split'), positions_json

    @app.callback(
        [Output('timestamp-dropdown', 'options'),
         Output('timestamp-dropdown', 'value'),
         Output('hash-dropdown', 'options'),
         Output('hash-dropdown', 'value'),
         Output('timestamp-index-store', 'data')],
        [Input('df-storage', 'children'),
         Input('previous-button', 'n_clicks'),
         Input('next-button', 'n_clicks')],
        [State('timestamp-index-store', 'data')]
    )
    def update_dropdowns_and_index(df_json, prev_clicks, next_clicks, timestamp_index):
        if df_json is None:
            return [], None, [], None, {'index': 0}

        df = pd.read_json(io.StringIO(df_json), orient='split')

        hash_options = [{'label': h, 'value': h} for h in df['msg_hash'].unique()]
        hash_value = hash_options[0]['value'] if hash_options else None

        if hash_value:
            timestamps = df.loc[df['msg_hash'] == hash_value, 'timestamp']
            timestamp_options = [{'label': str(ts), 'value': str(ts)} for ts in timestamps]
            total_timestamps = len(timestamp_options)
        else:
            timestamp_options = []
            total_timestamps = 0

        if timestamp_index is None:
            timestamp_index = {'index': 0}

        index = timestamp_index.get('index', 0)
        if ctx.triggered_id == 'next-button' and index + 1 < total_timestamps:
            index += 1
        elif ctx.triggered_id == 'previous-button' and index - 1 >= 0:
            index -= 1

        timestamp_value = timestamp_options[index]['value'] if total_timestamps > 0 else None

        return timestamp_options, timestamp_value, hash_options, hash_value, {'index': index}

    @app.callback(
        Output('networkx-trace-graph', 'figure'),
        [Input('hash-dropdown', 'value'),
         Input('timestamp-dropdown', 'value')],
        [State('df-storage', 'children'),
         State('positions-storage', 'children')]
    )
    def update_graph(selected_hash, selected_timestamp, df_json, positions):
        if not selected_hash or not selected_timestamp or df_json is None or positions is None:
            return go.Figure()

        positions = json.loads(positions)

        df = pd.read_json(io.StringIO(df_json), orient='split')
        filtered_df = df[(df['msg_hash'] == selected_hash) & (df['timestamp'] <= pd.to_datetime(selected_timestamp))]

        directed_graph = nx.DiGraph()
        for _, row in filtered_df.iterrows():
            sender = row['sender_peer_id']
            receiver = row['receiver_peer_id']

            if not directed_graph.has_node(sender):
                directed_graph.add_node(sender)
            if not directed_graph.has_node(receiver):
                directed_graph.add_node(receiver)

            directed_graph.add_edge(sender, receiver, timestamp=row['timestamp'], pod=row['pod-name'])

        edge_x = []
        edge_y = []
        node_x = []
        node_y = []
        node_text = []

        for edge in directed_graph.edges():
            x0, y0 = positions[edge[0]]
            x1, y1 = positions[edge[1]]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

        for node in directed_graph.nodes(data=True):
            x, y = positions[node[0]]
            node_x.append(x)
            node_y.append(y)
            node_text.append(f"{node[0]}")

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=edge_x, y=edge_y,
            marker=dict(size=10, symbol="arrow-bar-up", angleref="previous"),
            hoverinfo='none'
        ))
        fig.add_trace(go.Scatter(
            x=node_x, y=node_y,
            mode='markers+text',
            text=node_text,
            textposition='top center',
            hoverinfo='text',
            marker=dict(
                color='blue',
                size=12,
                line=dict(color='black', width=1)
            )
        ))
        fig.update_layout(
            title=f"Message Trace for {selected_hash}",
            showlegend=False,
            margin=dict(l=40, r=40, t=60, b=40),
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            height=800,
            uirevision=True
        )

        return fig
