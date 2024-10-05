# app.py
import dash
from dash import html, dcc, Output, Input, State, callback_context
import dash_bootstrap_components as dbc
import pandas as pd
import logging
import io

from order_management.order_manager import BotManager
from rewards_dashboard.rewardsDashboard import run_rewardsDash
from utils.utils import shorten_id

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize the Dash app with a Bootstrap theme
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server  # For deployment purposes

# Initialize BotManager
bot_manager = BotManager()

# Layout of the app
app.layout = dbc.Container([
    html.H1("Polymarket Bot Management Dashboard", style={'textAlign': 'center', 'margin-top': '20px'}),

    # Bot Control Section
    dbc.Row([
        dbc.Col([
            html.H3("Bot Control", style={'textAlign': 'center'}),
            dbc.Button(
                id='start-button',
                n_clicks=0,
                children='Start Bot',
                color='success',
                className='w-100',
                style={'margin-bottom': '10px'}
            ),
            dbc.Button(
                id='stop-button',
                n_clicks=0,
                children='Stop Bot',
                color='danger',
                className='w-100',
                style={'margin-bottom': '10px'}
            ),
            html.Div(id='bot-status', style={'margin-top': '20px'})
        ], width=6, className='offset-md-3'),
    ], justify='center'),

    html.Hr(),

    # Rewards Dashboard Section
    dbc.Row([
        dbc.Col([
            html.H3("Rewards Dashboard", style={'textAlign': 'center'}),
            dbc.Button(
                id='see-open-orders-button',
                n_clicks=0,
                children='Get Orders',
                color='primary',
                className='w-100',
                style={'margin-bottom': '10px'}
            ),
            dcc.Loading(
                id="loading-rewards-dashboard",
                type="default",
                children=html.Div(id='rewards-dashboard', style={'margin-top': '20px'})
            )
        ], width=6, className='offset-md-3'),
    ], justify='center'),

    html.Hr(),

    # (Optional) Any additional sections can be added here

], fluid=True)

# Callback to control the bot (Start/Stop)
@app.callback(
    Output('bot-status', 'children'),
    [Input('start-button', 'n_clicks'),
     Input('stop-button', 'n_clicks')]
)
def control_bot(start_clicks, stop_clicks):
    ctx = callback_context

    if not ctx.triggered:
        return ""

    button_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if button_id == 'start-button':
        if not bot_manager.is_running:
            bot_manager.start_bot()
            logger.info("Bot started.")
            return dbc.Alert("Bot started successfully.", color="success")
        else:
            logger.info("Bot already running.")
            return dbc.Alert("Bot is already running.", color="info")

    elif button_id == 'stop-button':
        if bot_manager.is_running:
            bot_manager.stop_bot()
            logger.info("Bot stopped.")
            return dbc.Alert("Bot stopped successfully.", color="danger")
        else:
            logger.info("Bot is not running.")
            return dbc.Alert("Bot is not running.", color="info")

    return ""
   
# Callback to fetch rewards data
@app.callback(
    Output('rewards-dashboard', 'children'),
    [Input('see-open-orders-button', 'n_clicks')]
)
def fetch_rewards(n_clicks):
    if n_clicks > 0:
        logger.debug("Get Orders button clicked.")
        # Call the run_rewardsDash() function
        try:
            data_response = run_rewardsDash()
            logger.debug("Fetched rewards data successfully.")

            if data_response['status'] == 'success':
                traders_data = data_response['data']['Traders']
                aggregate = data_response['data']['aggregate_apr']

                # Convert trader data to DataFrame
                df = pd.DataFrame(traders_data)

                # Shorten IDs if necessary
                if 'Name' in df.columns:
                    df['Name'] = df['Name'].apply(lambda x: shorten_id(x) if isinstance(x, str) else x)

                # Create a table with the trader data
                trader_table = dbc.Table.from_dataframe(
                    df,
                    striped=True,
                    bordered=True,
                    hover=True,
                    responsive=True,
                    style={'margin-bottom': '20px'}
                )

                # Display aggregate data
                aggregate_display = html.Div([
                    html.H5("Aggregate APR Information"),
                    html.P(f"Total Daily Rewards: {aggregate.get('Total Daily Rewards', 'N/A')}"),
                    html.P(f"Max Liquidity Provided: {aggregate.get('Max Liquidity Provided', 'N/A')}"),
                    html.P(f"Average Daily APR: {aggregate.get('Average Daily APR', 'N/A')}"),
                    html.P(f"Average Annual APR: {aggregate.get('Average Annual APR', 'N/A')}")
                    # Include other aggregate fields as needed
                ], style={'margin-top': '10px'})

                # Organize into a card
                rewards_card = dbc.Card([
                    dbc.CardHeader("Rewards Dashboard"),
                    dbc.CardBody([
                        trader_table,
                        aggregate_display
                    ])
                ], style={'margin-bottom': '20px'})

                return rewards_card

            elif data_response['status'] == 'error':
                error_message = data_response.get('message', 'An unknown error occurred.')
                logger.error(f"Error fetching rewards data: {error_message}")
                return dbc.Alert(f"Error: {error_message}", color="danger")

            else:
                logger.warning("No rewards data available.")
                return dbc.Alert("No rewards data available.", color="info")

        except Exception as e:
            logger.error(f"Error fetching rewards data: {e}")
            return dbc.Alert(f"Error: {e}", color="danger")

    return ""

if __name__ == '__main__':
    app.run_server(host='0.0.0.0', port=8050, debug=True)