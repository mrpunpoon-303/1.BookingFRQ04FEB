from dash import Dash, dcc, html, Input, Output, State, callback_context
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go
import pandas as pd
import base64
import io

# Initialize the Dash app
app = Dash(__name__, 
    external_stylesheets=[
        'https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css'
    ],
    suppress_callback_exceptions=True
)

# Add this line for deployment
server = app.server

def create_frequency_table(data, period=None, start_period=None, end_period=None, max_upper=10):
    """Process data to create frequency table"""
    if period:
        data_filtered = data[data["Start_Date_time"].dt.to_period("M").astype(str) == period]
    elif start_period and end_period:
        periods = data["Start_Date_time"].dt.to_period("M").astype(str)
        data_filtered = data[(periods >= start_period) & (periods <= end_period)]
    else:
        return None

    # Exclude "Self Practice"
    data_filtered = data_filtered[~data_filtered["Class_Name"].str.contains("Self Practice", case=False, na=False)]

    # Calculate booking frequencies
    booking_frequencies = data_filtered.groupby("Id_Person").size()

    # Create frequency table
    table = pd.DataFrame({
        "Freq": list(range(1, max_upper + 1)) + [f">{max_upper}"],
        "#Students": [sum(booking_frequencies == i) for i in range(1, max_upper + 1)] + 
                    [sum(booking_frequencies > max_upper)],
        "Cum 1->": [sum(booking_frequencies <= i) for i in range(1, max_upper + 1)] + 
                  [len(booking_frequencies)],
        "Cum ->End": [len(booking_frequencies) - sum(booking_frequencies <= i) for i in range(1, max_upper + 1)] + 
                    [sum(booking_frequencies > max_upper)]
    })

    # Add student details
    def get_student_details(freq):
        if isinstance(freq, str) and freq.startswith(">"):
            ids = booking_frequencies[booking_frequencies > max_upper].index
        else:
            ids = booking_frequencies[booking_frequencies == freq].index
        
        names = data_filtered[data_filtered["Id_Person"].isin(ids)]["FirstName"].drop_duplicates()
        return ", ".join([f"{name} : {id}" for name, id in zip(names, ids)])

    table["Details"] = [get_student_details(freq) for freq in table["Freq"]]
    return table

def parse_contents(contents):
    """Parse uploaded file contents"""
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    
    try:
        df = pd.read_excel(io.BytesIO(decoded))
        df["Start_Date_time"] = pd.to_datetime(df["Start_Date_time"], errors="coerce")
        return df, None
    except Exception as e:
        return None, str(e)

# App Layout
app.layout = html.Div([
    # Main container
    html.Div([
        html.H1("Booking Frequency Analysis", className="text-2xl font-bold mb-6"),
        
        # File Upload Section
        html.Div([
            dcc.Upload(
                id='upload-data',
                children=html.Div([
                    'Drag and Drop or ',
                    html.A('Select Excel File', className="text-blue-500 hover:text-blue-700")
                ]),
                className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-gray-400",
                multiple=False
            ),
            html.Div(id='upload-feedback', className="mt-2 text-sm")
        ], className="mb-6"),

        # Controls Section
        html.Div([
            # Analysis Type Selection
            html.Div([
                html.Label("Analysis Type:", className="font-medium mr-4"),
                dcc.RadioItems(
                    id='analysis-type',
                    options=[
                        {'label': 'Monthly', 'value': 'Monthly'},
                        {'label': 'Range', 'value': 'Range'}
                    ],
                    value='Monthly',
                    className="space-x-4",
                    inputClassName="mr-2"
                )
            ], className="mb-4"),

            # Period Selection with placeholder dropdowns
            html.Div([
                html.Div(id='period-selector', className="mb-4"),
                # Hidden placeholder dropdowns
                dcc.Dropdown(id='selected-period', style={'display': 'none'}),
                dcc.Dropdown(id='start-period', style={'display': 'none'}),
                dcc.Dropdown(id='end-period', style={'display': 'none'})
            ], className="mb-4"),

            # Max Upper Bound Input
            html.Div([
                html.Label("Max Upper Bound:", className="font-medium mr-4"),
                dcc.Input(
                    id='max-upper',
                    type='number',
                    value=15,
                    min=1,
                    className="border rounded p-1 w-24"
                )
            ], className="mb-4"),

            # Run Analysis Button
            html.Button(
                "Run Analysis",
                id="run-analysis",
                className="bg-blue-500 text-white px-6 py-2 rounded hover:bg-blue-600 mb-4"
            ),
        ], className="mb-6"),

        # Status message
        html.Div(id='status-message', className="mb-4"),

        # Results Section (initially hidden)
        html.Div([
            # Export Button
            html.Div([
                html.Button(
                    "Export Data (XLS)", 
                    id="btn-export-data",
                    className="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600"
                )
            ], className="mb-6"),

            # Graph
            dcc.Graph(id='histogram', className="mb-6"),

            # Table
            html.Div(id='table-container', className="overflow-x-auto")
        ], id='results-section', style={'display': 'none'})

    ], className="max-w-7xl mx-auto p-6"),

    # Store components for data
    dcc.Store(id='stored-data'),
    dcc.Download(id="download-xlsx")
])

@app.callback(
    [Output('stored-data', 'data'),
     Output('upload-feedback', 'children'),
     Output('upload-feedback', 'className')],
    Input('upload-data', 'contents'),
    State('upload-data', 'filename')
)
def store_data(contents, filename):
    if contents is None:
        raise PreventUpdate

    df, error = parse_contents(contents)
    if error:
        return None, f"Error: {error}", "mt-2 text-red-600"
    
    return {
        'data': df.to_json(date_format='iso', orient='split'),
        'filename': filename
    }, f"File uploaded: {filename}", "mt-2 text-green-600"

@app.callback(
    [Output('period-selector', 'children'),
     Output('selected-period', 'style'),
     Output('start-period', 'style'),
     Output('end-period', 'style')],
    [Input('stored-data', 'data'),
     Input('analysis-type', 'value')]
)
def update_period_selector(stored_data, analysis_type):
    if not stored_data:
        raise PreventUpdate

    data = pd.read_json(stored_data['data'], orient='split')
    periods = sorted(data["Start_Date_time"].dt.to_period("M").astype(str).unique())
    
    if analysis_type == 'Monthly':
        return (
            dcc.Dropdown(
                id='selected-period',
                options=[{'label': p, 'value': p} for p in periods],
                value=periods[-1],
                className="w-full"
            ),
            {'display': 'block'},
            {'display': 'none'},
            {'display': 'none'}
        )
    else:
        return (
            html.Div([
                dcc.Dropdown(
                    id='start-period',
                    options=[{'label': p, 'value': p} for p in periods],
                    value=periods[0],
                    className="w-full mb-2"
                ),
                dcc.Dropdown(
                    id='end-period',
                    options=[{'label': p, 'value': p} for p in periods],
                    value=periods[-1],
                    className="w-full"
                )
            ]),
            {'display': 'none'},
            {'display': 'block'},
            {'display': 'block'}
        )

@app.callback(
    [Output('histogram', 'figure'),
     Output('table-container', 'children'),
     Output('results-section', 'style'),
     Output('status-message', 'children'),
     Output('status-message', 'className')],
    Input('run-analysis', 'n_clicks'),
    [State('stored-data', 'data'),
     State('analysis-type', 'value'),
     State('max-upper', 'value'),
     State('selected-period', 'value'),
     State('start-period', 'value'),
     State('end-period', 'value')],
    prevent_initial_call=True
)
def update_outputs(n_clicks, stored_data, analysis_type, max_upper, selected_period, start_period, end_period):
    if not n_clicks or not stored_data:
        raise PreventUpdate

    try:
        data = pd.read_json(stored_data['data'], orient='split')
        
        # Get frequency table based on analysis type
        if analysis_type == 'Monthly':
            table = create_frequency_table(data, period=selected_period, max_upper=max_upper)
        else:
            table = create_frequency_table(data, start_period=start_period, end_period=end_period, max_upper=max_upper)

        if table is None:
            return dash.no_update, dash.no_update, {'display': 'none'}, "Error: No data available for selected period", "text-red-600"

        # Create histogram
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=table["Freq"].astype(str),
            y=table["#Students"],
            text=table["#Students"],
            textposition='auto',
            hovertemplate="<b>Frequency:</b> %{x}<br>" +
                         "<b>Students:</b> %{y}<br>" +
                         "<b>Details:</b> %{customdata}<extra></extra>",
            customdata=table["Details"]
        ))

        # Calculate and add mean and median lines
        freq_data = []
        for freq, count in zip(table["Freq"], table["#Students"]):
            if isinstance(freq, str):
                freq = int(freq.replace('>', ''))
            freq_data.extend([freq] * count)

        if freq_data:
            mean_val = sum(freq_data) / len(freq_data)
            median_val = sorted(freq_data)[len(freq_data)//2]
            
            # Add mean line
            fig.add_vline(x=mean_val, line_dash="dash", line_color="red",
                         annotation_text=f"Mean: {mean_val:.2f}",
                         annotation_position="top right",
                         annotation_y=1.1)
            
            # Add median line
            fig.add_vline(x=median_val, line_dash="dash", line_color="green",
                         annotation_text=f"Median: {median_val:.2f}",
                         annotation_position="bottom right",
                         annotation_y=0.9)

        fig.update_layout(
            title='Booking Frequency Distribution',
            xaxis_title='Frequency of Bookings',
            yaxis_title='Number of Students',
            height=500
        )

        # Create table
        table_component = html.Table([
            html.Thead(
                html.Tr([
                    html.Th(col, className="p-3 text-left font-medium text-gray-600 border") 
                    for col in table.columns
                ], className="bg-gray-50")
            ),
            html.Tbody([
                html.Tr([
                    html.Td(row[col], className="p-3 border") 
                    for col in table.columns
                ], className="hover:bg-gray-50")
                for _, row in table.iterrows()
            ])
        ], className="min-w-full divide-y divide-gray-200")

        return fig, table_component, {'display': 'block'}, "Analysis completed successfully", "text-green-600"

    except Exception as e:
        return dash.no_update, dash.no_update, {'display': 'none'}, f"Error: {str(e)}", "text-red-600"

@app.callback(
    Output("download-xlsx", "data"),
    Input("btn-export-data", "n_clicks"),
    [State('stored-data', 'data'),
     State('analysis-type', 'value'),
     State('max-upper', 'value'),
     State('selected-period', 'value'),
     State('start-period', 'value'),
     State('end-period', 'value')],
    prevent_initial_call=True
)
def export_data(n_clicks, stored_data, analysis_type, max_upper, selected_period, start_period, end_period):
    if not n_clicks or not stored_data:
        raise PreventUpdate

    data = pd.read_json(stored_data['data'], orient='split')
    if analysis_type == 'Monthly':
        table = create_frequency_table(data, period=selected_period, max_upper=max_upper)
    else:
        table = create_frequency_table(data, start_period=start_period, end_period=end_period, max_upper=max_upper)

    return dcc.send_data_frame(table.to_excel, "booking_frequency.xlsx", sheet_name="Frequency Analysis")

# Modified server run line for deployment
if __name__ == '__main__':
    app.run_server(debug=False, host='0.0.0.0')