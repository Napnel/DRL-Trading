import warnings
from typing import Optional

import numpy as np
import pandas as pd

with warnings.catch_warnings():
    warnings.simplefilter("ignore", UserWarning)
    from backtesting import Strategy, Backtest
from stable_baselines3.common.base_class import BaseAlgorithm

from .utils import get_action_prob


class DRLStrategy(Strategy):
    model: Optional[BaseAlgorithm] = None
    env = None

    def init(self):
        self.observation = self.env.reset()
        self.max_step = len(self.data.df) - 1
        self.history_action_prob = np.zeros(self.max_step)

    def next(self):
        self.step = len(self.data.df) - 1
        self.env.current_step = self.step  # BacktestのステップとEnvironmentのステップを同期させる
        
        if self.step < self.env.window_size:
            pass

        elif self.step + 1 >= self.max_step:
            self.env.position.close()
            self.position.close()

        else:
            assert self.data.Close[-1] == self.env.current_price, f"Step:{self.step}: {self.data.Close[-1]} != {self.env.current_price}"
            assert self._broker._cash == self.env.wallet.assets, f"Step:{self.step}: {self._broker._cash} != {self.env.wallet.assets}"
            assert self.equity == self.env.wallet.equity, f"Step{self.step}: {self.equity} != {self.env.wallet.equity}"
            action, _ = self.model.predict(self.env.next_observation, deterministic=True)
            action_prob = get_action_prob(self.model, self.env, self.env.next_observation)
            self.history_action_prob[self.step] = action_prob[action]

            if action == self.env.actions.Buy.value and not self.position.is_long:
                if self.position.is_short:
                    self.position.close()
                else:
                    self.buy()
                self.env.buy()

            elif action == self.env.actions.Sell.value and not self.position.is_short:
                if self.position.is_long:
                    self.position.close()
                else:
                    self.sell()
                self.env.sell()


def backtest(model: BaseAlgorithm, env, plot=False, plot_filename=None) -> pd.DataFrame:
    bt = Backtest(
        env._df,
        DRLStrategy,
        cash=env.wallet.initial_assets,
        commission=env.fee,
        trade_on_close=True,
        exclusive_orders=False,
    )
    stats = bt.run(model=model, env=env)
    if plot:
        bt.plot(filename=plot_filename)
    return stats