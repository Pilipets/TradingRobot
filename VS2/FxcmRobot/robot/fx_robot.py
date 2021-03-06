import fxcmpy
import pandas as pd
from .common import Portfolio, Trade
import time
import logging
from .fx_config import FxConfig

class FxRobot:
    def __init__(self, config : FxConfig):
        self._setup_logger(logging.getLevelName(config.log_level))

        self.logger.info(f'Configured {FxRobot.__name__} with {config}')
        self.api = fxcmpy.fxcmpy(
            access_token = config.fxcm_config.access_token,
            server= config.fxcm_config.server,
            log_level = config.fxcm_config.log_level)

    def _setup_logger(self, log_level):
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s:%(funcName)s:%(lineno)d:%(levelname)s:%(name)s:%(message)s')
        handler.setLevel(log_level)
        handler.setFormatter(formatter)
        self.logger = logging.getLogger(FxRobot.__name__)
        self.logger.setLevel(log_level)
        self.logger.addHandler(handler)
        self.logger.propagate = False

    def __del__(self):
        self.api.close()

    def get_last_bar(self, symbol, n = 1, columns = ['bids', 'tickqty'], period = 'm1'):
        self.logger.debug(f'Querying last {n} bars for {symbol}')
        bars : pd.DataFrame = self.api.get_candles(
            symbol, period = period, number = n, columns = columns)

        bars.rename(columns={"bidopen": "open", "bidclose": "close",
            "bidhigh": "high", "bidlow" : "low", "tickqty": "volume"},
            inplace=True
        )
        return bars

    def sleep_till_next_bar(self, last_timestamp : pd.Timestamp, timedelta : pd.Timedelta):
        if last_timestamp is None: last_timestamp = pd.Timestamp.utcnow()
        elif last_timestamp.tzinfo is None: last_timestamp = last_timestamp.tz_localize('utc')
        else: last_timestamp = last_timestamp.tz_convert('utc')

        next_timestamp = last_timestamp + timedelta
        delta = (next_timestamp - pd.Timestamp.utcnow()).total_seconds()

        self.logger.debug(f'Sleeping till next data update for {delta} seconds')
        time.sleep(max(0.1, delta))

    def get_api(self):
        return self.api

    def get_logger(self):
        return self.logger

    def create_portfolio(self, symbols, *args, **kwargs):
        portfolio = Portfolio(self, symbols, *args, **kwargs)
        self.logger.info(f'Created new portfolio object: {portfolio}')
        return portfolio

    def __getattr__(self, name):
        return getattr(self.api, name)

    def open_trade(self, trade : Trade, portfolio : Portfolio):
        self.logger.info(f'Opening new trade for portfolio({portfolio.id}): {trade}')

        if trade.get_order_type() == "Entry":
            order = self.api.create_entry_order(**trade.get_fxcm_args())
        else:
            order = self.api.open_trade(**trade.get_fxcm_args())

        id = order.get_orderId() if order else None
        self.logger.info(f"Adding new trade({id}) to the portfolio({portfolio.id})")
        portfolio.add_order(order)
        return id

    def close_trade(self, position, portfolio : Portfolio, **close_args):
        currency, trade_id = position['currency'], position['tradeId']
        self.logger.info(f"Closing position({trade_id}) for currency({currency}) in the portfolio({portfolio.id}) with args {close_args}")
        self.api.close_trade(trade_id, **close_args)

    def get_offers(self, symbols = None, columns = None):
        if symbols is None: symbols = 'all'
        elif type(symbols) == str: symbols = symbols.split(',')
        if columns is None: columns = 'all'
        elif type(columns) == str: columns = columns.split(',')

        self.logger.info(f"Gathering offers({columns}) for {symbols} symbols")
        data = self.api.get_offers()

        if type(symbols) == list: data = data[data['currency'].isin(symbols)]
        if type(columns) == list: data = data[columns]
        return data

    def subscribe_instrument(self, symbols):
        if type(symbols) == str: symbols = list(symbols)
        res = [None] * len(symbols)
        for idx, symbol in enumerate(symbols):
            res[idx] = self.api.subscribe_instrument(symbol)
        return res

    def unsubscribe_instrument(self, symbols):
        if type(symbols) == str: symbols = list(symbols)
        res = [None] * len(symbols)
        for idx, symbol in enumerate(symbols):
            res[idx] = self.api.unsubscribe_instrument(symbol)
        return res

    def subscribe_market_data(self, symbols, callbacks):
        if type(symbols) == str: symbols = list(symbols)
        for symbol in symbols:
            self.api.subscribe_market_data(symbol, callbacks)

    def unsubscribe_market_data(self, symbols):
        if type(symbols) == str: symbols = list(symbols)
        for symbol in symbols:
            self.api.unsubscribe_market_data(symbol)