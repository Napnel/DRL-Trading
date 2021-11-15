import os
import pathlib
import glob
from typing import Dict, List, Any, Optional

from ray import tune
from ray.tune.logger import UnifiedLogger
from ray.tune.schedulers.pb2 import PB2
from ray.rllib.agents import dqn, a3c, ppo, sac, ddpg
from src.envs import BaseTradingEnv
from src.utils import DataLoader, Preprocessor, backtest


class ExperimentCV(tune.Trainable):
    def setup(self, config):
        self.ticker = config.pop("_ticker")
        self.n_splits = config.pop("_n_splits")
        self.algo = config.pop("_algo")

        data, features = self.load_data()
        agent_class, algo_config = self.get_agent_class()
        algo_config.update(config)
        # self.agent = agent_class(config=algo_config)
        self.agent = None
        for i, (data_train, features_train, data_eval, features_eval) in enumerate(
            Preprocessor.blocked_cross_validation(data, features, n_splits=self.n_splits)
        ):
            algo_config["env_config"]["data"] = data_train
            algo_config["env_config"]["features"] = features_train
            algo_config["evaluation_config"]["env_config"]["data"] = data_eval
            algo_config["evaluation_config"]["env_config"]["features"] = features_eval
            if self.agent:
                self.agent.reset(algo_config, logger_creator=lambda config: UnifiedLogger(config, os.path.join(self.logdir, f"splits_{i}")))
            else:
                self.agent = agent_class(
                    config=algo_config, logger_creator=lambda config: UnifiedLogger(config, os.path.join(self.logdir, f"splits_{i}"))
                )
            self.agent.save()

    def load_data(self):
        if len(glob.glob(f"./data/{self.ticker}/*.csv")) != 0:
            data = DataLoader.load_data(f"./data/{self.ticker}/ohlcv.csv")
            features = DataLoader.load_data(f"./data/{self.ticker}/features.csv")
        else:
            os.makedirs(f"./data/{self.ticker}", exist_ok=True)
            data = DataLoader.fetch_data(f"{self.ticker}", interval="1d")
            data, features = Preprocessor.extract_features(data)
            data.to_csv(f"./data/{self.ticker}/ohlcv.csv")
            features.to_csv(f"./data/{self.ticker}/features.csv")

        return data, features

    def average_results(self, n_total: int, results: Dict[str, Any], avg_res: Optional[dict]):
        partial_avg_res = avg_res if avg_res else {}

        for key, value in results.items():
            if isinstance(value, (int, float)):
                partial_avg_res[key] = (n_total * partial_avg_res[key] + value) / (n_total + 1) if partial_avg_res.get(key) else value
            elif isinstance(value, dict):
                partial_avg_res[key] = self.average_results(n_total, value, partial_avg_res.get(key))

        return partial_avg_res

    def get_agent_class(self):
        if self.algo == "DQN":
            agent = dqn.DQNTrainer
            config = dqn.DEFAULT_CONFIG.copy()

        elif self.algo == "A2C":
            agent = a3c.A2CTrainer
            config = a3c.DEFAULT_CONFIG.copy()

        elif self.algo == "PPO":
            agent = ppo.PPOTrainer
            config = ppo.DEFAULT_CONFIG.copy()

        elif self.algo == "SAC":
            agent = sac.SACTrainer
            config = sac.DEFAULT_CONFIG.copy()

        elif self.algo == "DDPG":
            agent = ddpg.DDPGTrainer
            config = ddpg.DEFAULT_CONFIG.copy()

        else:
            raise ValueError

        return agent, config

    def step(self):
        averaged_results = {}
        for i in range(self.n_splits):
            agent_path = os.path.join(self.logdir, f"splits_{i}")
            checkpoint_list = glob.glob(os.path.join(agent_path, "checkpoint_*"))
            print("===" * 5, self.iteration, "===" * 5)
            print(checkpoint_list)
            print(os.path.join(checkpoint_list[-1], f"checkpoint-{self.iteration}"))
            print("agent logdir: ", self.agent.logdir)
            # self.agent.resource_help()
            # self.agent.update_resources()
            self.agent.restore(os.path.join(checkpoint_list[-1], f"checkpoint-{self.iteration}"))
            results = self.agent.train()
            self.agent.save(os.path.join(agent_path, ""))
            averaged_results = self.average_results(i, results, averaged_results)

        return averaged_results

    # def save_checkpoint(self, checkpoint_dir: str):
    #     for i, agent in enumerate(self.agents):
    #         # agent.save(os.path.join(checkpoint_dir, f"splits_{i}"))
    #         agent.save()

    #     return checkpoint_dir

    # def load_checkpoint(self, checkpoint_dir: str):
    #     log_dir = str(pathlib.Path(checkpoint_dir).parent)
    #     iteration = checkpoint_dir.split("_")[-1][:-1]
    #     for i, agent in enumerate(self.agents):
    #         checkpoint_path = os.path.join(log_dir, f"splits_{i}", f"checkpoint_{iteration}", f"checkpoint-{int(iteration)}")
    #         agent.restore(checkpoint_path)

    # def reset_config(self, new_config):
    #     self.config = new_config
    #     return True