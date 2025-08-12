# Python Imports
from dash import dcc, html

layout = html.Div([
    html.H1("Message Trace Viewer", style={'textAlign': 'center'}),

    html.Label("Upload CSV File"),
    dcc.Upload(
        id='upload-data',
        children=html.Button('Upload File'),
        multiple=False
    ),

    html.Label("Select Message Hash:"),
    dcc.Dropdown(
        id='hash-dropdown',
        options=[],
        value=None,
        placeholder="Select a message hash"
    ),

    html.Label("Selected Timestamp:"),
    dcc.Dropdown(
        id='timestamp-dropdown',
        options=[],
        value=None,
        placeholder="Select a timestamp"
    ),

    html.Div([
        html.Button('Previous', id='previous-button', n_clicks=0),
        html.Button('Next', id='next-button', n_clicks=0),
    ], style={'marginTop': '10px'}),

    dcc.Graph(
        id='networkx-trace-graph',
        config={'scrollZoom': True},
        style={'width': '100%', 'height': '800px'}
    ),

    html.Div(id='df-storage', style={'display': 'none'}),
    html.Div(id='positions-storage', style={'display': 'none'}),
    dcc.Store(id='timestamp-index-store', storage_type='memory')
])
