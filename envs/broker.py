from math import copysign
import numpy as np
import pandas as pd

from typing import List, Optional


class Broker:
    def __init__(self, data: pd.DataFrame, assets: float, fee: float):
        self.data: pd.DataFrame = data
        self.current_step = 0
        self.assets = assets
        self.fee = fee
        self.position: Position = Position(self)
        self.closed_trades = pd.DataFrame(columns=["size", "entry_price", "exit_price", "PnL", "entry_time", "exit_time"])

    def new_order(self, size, limit_price):
        if size != 0:
            if self.position.size == 0:
                self.position.size = size
                self.position.entry_price = limit_price * (1 + copysign(self.fee, size))
                self.position.entry_time = self.data.index[self.current_step]
            else:
                assert self.position.size == -size, f"position don't close: {self.position.size}, {size}"
                self.position.close()

    def get_candles(self, start, end) -> np.ndarray:
        return self.data.iloc[start:end, :].values

    def adjusted_price(self, size, price):
        return price * (1 + copysign(self.fee, size))

    @property
    def equity(self):
        return self.assets + self.position.profit_or_loss

    @property
    def free_assets(self):
        used_assets = abs(self.position.size) * self.current_price
        return max(0, self.equity - used_assets)
        # return self.equity if self.position.size == 0 else max(0, self.equity - abs(self.position.size) * self.current_price)

    @property
    def latest_candle(self) -> np.ndarray:
        return self.data.iloc[self.current_step, :].values

    @property
    def current_datetime(self):
        return self.data.iloc[self.current_step, :].name

    @property
    def current_price(self) -> np.ndarray:
        return self.data["Close"][self.current_step]

    @property
    def account_state(self) -> np.ndarray:
        return np.array([self.free_assets > (self.current_price * (1 + self.fee)), self.position.profit_or_loss_pct])


class Position:
    def __init__(self, broker: Broker):
        self.__broker = broker
        self.__size = 0
        self.__entry_price = None
        self.__entry_time = None

    def __repr__(self) -> str:
        return f"Position(size: {self.size}, entry_price: {self.entry_price}, pl: {self.profit_or_loss:.0f})"

    @property
    def size(self) -> float:
        return self.__size

    @property
    def entry_price(self) -> float:
        return self.__entry_price

    @property
    def entry_time(self):
        return self.__entry_time

    @size.setter
    def size(self, size):
        self.__size = size

    @entry_price.setter
    def entry_price(self, price):
        self.__entry_price = price

    @entry_time.setter
    def entry_time(self, time):
        self.__entry_time = time

    @property
    def is_long(self) -> bool:
        return True if self.__size > 0 else False

    @property
    def is_short(self) -> bool:
        return True if self.__size < 0 else False

    @property
    def profit_or_loss(self):
        if self.__size == 0:
            return 0
        return self.__size * (self.__broker.current_price - self.__entry_price)

    @property
    def profit_or_loss_pct(self):
        if self.__size == 0:
            return 0
        return copysign(1, self.__size) * (self.__broker.current_price - self.__entry_price) / self.__entry_price

    def close(self):
        self.__broker.assets += self.profit_or_loss
        trade = {
            "size": self.size,
            "entry_price": self.entry_price,
            "exit_price": self.__broker.current_price,
            "PnL": self.profit_or_loss,
            "entry_time": self.entry_time,
            "exit_time": self.__broker.current_datetime,
        }
        self.__broker.closed_trades = self.__broker.closed_trades.append(trade, ignore_index=True)
        self.__size = 0
        self.__entry_price = None
        self.__entry_time = None