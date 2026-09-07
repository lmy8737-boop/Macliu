"""
FinRL 信号增强模块 — 4号交易员的"AI 第二意见"
================================================
职责：
  - 当4号缠论信号强度处于灰色地带（2-3分）时，用 RL agent 提供第二意见
  - 高确信信号（≥4）直接通过，不消耗 RL 推理资源
  - 低确信信号（<2）直接 HOLD，不浪费时间
  - RL agent 基于历史 K线 + 缠论结构特征做决策

核心原则（铁律）：
  - FinRL 信号不能独立构成交易理由（必须与缠论共振）
  - 未训练的 RL agent 不参与决策（模型不存在时跳过）
  - RL 只做辅助增强，最终决策权在4号规则引擎

安装：
  pip install finrl gymnasium stable-baselines3 pandas numpy

用法：
  # 查询 RL 增强
  from finrl_augment import augment_signal
  result = augment_signal("sh510300", signal_strength=3, direction="LONG", features={...})

  # 训练 RL agent（首次/定期更新）
  python3 finrl_augment.py --train sh510300 --data ./engine/data/structures/

  # 自测
  python3 finrl_augment.py --test
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# ─── 依赖检测 ─────────────────────────────────────────────────────────
try:
    import numpy as np
    import pandas as pd
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from stable_baselines3 import PPO, A2C, SAC
    from stable_baselines3.common.vec_env import DummyVecEnv
    HAS_SB3 = True
except ImportError:
    HAS_SB3 = False

try:
    import gymnasium as gym
    from gymnasium import spaces
    HAS_GYM = True
except ImportError:
    HAS_GYM = False

FINRL_AVAILABLE = HAS_NUMPY and HAS_SB3 and HAS_GYM

# 模型存储路径
MODEL_DIR = Path(os.environ.get(
    "INVESTMENT_TEAM_DATA_DIR",
    Path.cwd() / "engine" / "data"
)) / "models"


# ═══════════════════════════════════════════════════════════════════════
#  核心 API：信号增强
# ═══════════════════════════════════════════════════════════════════════

def augment_signal(
    ticker: str,
    signal_strength: int,
    direction: str,
    features: dict,
    algo: str = "PPO"
) -> dict:
    """
    4号交易员调用：灰色地带信号增强

    Args:
        ticker: 标的代码
        signal_strength: 4号缠论信号强度（1-5）
        direction: 4号初步方向判断 "LONG" / "SHORT" / "HOLD"
        features: 缠论结构特征 dict（来自 structures.json）
        algo: RL 算法 "PPO" / "A2C" / "SAC"

    Returns:
        {
            "action": "CONFIRM" / "BOOST" / "HOLD" / "REJECT" / "SKIP",
            "rl_confidence": float 0-1 or None,
            "rl_action": "LONG" / "SHORT" / "HOLD" or None,
            "final_strength_delta": int,  # 对信号强度的调整
            "reason": str,
        }
    """
    # ── 高确信：直接通过 ──
    if signal_strength >= 4:
        return {
            "action": "CONFIRM",
            "rl_confidence": None,
            "rl_action": None,
            "final_strength_delta": 0,
            "reason": f"信号强度 {signal_strength} ≥ 4，高确信免查 RL",
        }

    # ── 低确信：直接放弃 ──
    if signal_strength < 2:
        return {
            "action": "HOLD",
            "rl_confidence": None,
            "rl_action": None,
            "final_strength_delta": 0,
            "reason": f"信号强度 {signal_strength} < 2，不足以触发 RL 查询",
        }

    # ── 灰色地带（2-3）：查询 RL agent ──
    if not FINRL_AVAILABLE:
        return {
            "action": "SKIP",
            "rl_confidence": None,
            "rl_action": None,
            "final_strength_delta": 0,
            "reason": "FinRL 依赖未安装（pip install finrl stable-baselines3 gymnasium）",
        }

    # 检查模型是否存在
    model_path = MODEL_DIR / f"finrl_{ticker}_{algo.lower()}.zip"
    if not model_path.exists():
        return {
            "action": "SKIP",
            "rl_confidence": None,
            "rl_action": None,
            "final_strength_delta": 0,
            "reason": f"模型不存在: {model_path}（需先训练: --train {ticker}）",
        }

    # 加载模型并推理
    try:
        rl_result = _query_rl_agent(model_path, features, algo)
    except Exception as e:
        return {
            "action": "SKIP",
            "rl_confidence": None,
            "rl_action": None,
            "final_strength_delta": 0,
            "reason": f"RL 推理失败: {e}",
        }

    rl_confidence = rl_result["confidence"]
    rl_action = rl_result["action"]

    # ── 融合决策 ──
    if rl_confidence > 0.7 and rl_action == direction:
        # RL 高度同意 → 信号强度 +1
        return {
            "action": "BOOST",
            "rl_confidence": rl_confidence,
            "rl_action": rl_action,
            "final_strength_delta": +1,
            "reason": f"RL {algo} 高确信({rl_confidence:.2f})同意 {direction}，信号+1",
        }
    elif rl_confidence < 0.3 or (rl_action != direction and rl_action != "HOLD"):
        # RL 强烈反对 → 信号降级
        return {
            "action": "REJECT",
            "rl_confidence": rl_confidence,
            "rl_action": rl_action,
            "final_strength_delta": -1,
            "reason": f"RL {algo} 反对({rl_confidence:.2f})，方向 {rl_action} vs 缠论 {direction}，信号-1",
        }
    else:
        # RL 中性 → 维持原判
        return {
            "action": "CONFIRM",
            "rl_confidence": rl_confidence,
            "rl_action": rl_action,
            "final_strength_delta": 0,
            "reason": f"RL {algo} 中性({rl_confidence:.2f})，维持缠论原判",
        }


# ═══════════════════════════════════════════════════════════════════════
#  交易环境（Gymnasium）
# ═══════════════════════════════════════════════════════════════════════

class ChanlunTradingEnv(gym.Env):
    """
    基于缠论结构特征的交易环境

    Observation Space（12 维）：
    - [0] 当前结构方向（1=向上, -1=向下, 0=盘整）
    - [1] 笔数（归一化）
    - [2] 中枢数（归一化）
    - [3] 是否背驰（0/1）
    - [4] 能量比（0-2）
    - [5] 距支撑位的距离%
    - [6] 距阻力位的距离%
    - [7] 5日收益率
    - [8] 10日收益率
    - [9] 20日收益率
    - [10] 成交量变化率
    - [11] 持仓状态（0=空仓, 1=多头, -1=空头）

    Action Space：
    - 0: HOLD（观望）
    - 1: LONG（做多）
    - 2: SHORT（做空/平多）
    """
    metadata = {"render_modes": []}

    def __init__(self, data: pd.DataFrame):
        super().__init__()
        self.data = data.reset_index(drop=True)
        self.current_step = 0
        self.position = 0  # 0=空仓, 1=多, -1=空
        self.entry_price = 0
        self.total_pnl = 0

        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(12,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(3)  # HOLD, LONG, SHORT

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.current_step = 0
        self.position = 0
        self.entry_price = 0
        self.total_pnl = 0
        return self._get_obs(), {}

    def step(self, action):
        row = self.data.iloc[self.current_step]
        price = row.get("close", 0)
        reward = 0

        # 执行动作
        if action == 1 and self.position <= 0:  # LONG
            if self.position == -1:  # 平空
                reward = (self.entry_price - price) / self.entry_price * 100
            self.position = 1
            self.entry_price = price
        elif action == 2 and self.position >= 0:  # SHORT
            if self.position == 1:  # 平多
                reward = (price - self.entry_price) / self.entry_price * 100
            self.position = -1
            self.entry_price = price
        else:  # HOLD
            if self.position == 1:
                reward = (price - self.entry_price) / self.entry_price * 0.1  # 持仓浮盈微奖励
            elif self.position == -1:
                reward = (self.entry_price - price) / self.entry_price * 0.1

        self.total_pnl += reward
        self.current_step += 1

        terminated = self.current_step >= len(self.data) - 1
        truncated = False

        return self._get_obs(), reward, terminated, truncated, {"pnl": self.total_pnl}

    def _get_obs(self):
        if self.current_step >= len(self.data):
            return np.zeros(12, dtype=np.float32)

        row = self.data.iloc[self.current_step]
        obs = np.array([
            row.get("structure_dir", 0),
            row.get("bi_count", 0) / 20.0,
            row.get("center_count", 0) / 5.0,
            row.get("has_divergence", 0),
            row.get("energy_ratio", 1.0),
            row.get("dist_support_pct", 0),
            row.get("dist_resistance_pct", 0),
            row.get("ret_5d", 0),
            row.get("ret_10d", 0),
            row.get("ret_20d", 0),
            row.get("vol_change", 0),
            self.position,
        ], dtype=np.float32)
        return obs


# ═══════════════════════════════════════════════════════════════════════
#  训练与推理
# ═══════════════════════════════════════════════════════════════════════

def train_agent(
    ticker: str,
    data_dir: str = None,
    algo: str = "PPO",
    total_timesteps: int = 50000,
) -> str:
    """
    训练 RL agent

    Args:
        ticker: 标的代码
        data_dir: structures.json 所在目录
        algo: "PPO" / "A2C" / "SAC"
        total_timesteps: 训练步数

    Returns:
        模型保存路径
    """
    if not FINRL_AVAILABLE:
        raise RuntimeError("请先安装依赖: pip install finrl stable-baselines3 gymnasium pandas numpy")

    data_dir = Path(data_dir or (Path.cwd() / "engine" / "data" / "structures"))
    training_data = _prepare_training_data(ticker, data_dir)

    if training_data is None or len(training_data) < 50:
        raise ValueError(f"训练数据不足（需要≥50条，当前{len(training_data) if training_data is not None else 0}条）")

    # 创建环境
    env = DummyVecEnv([lambda: ChanlunTradingEnv(training_data)])

    # 选择算法
    algo_map = {"PPO": PPO, "A2C": A2C, "SAC": SAC}
    AlgoClass = algo_map.get(algo.upper(), PPO)

    # 训练
    print(f"🏋️ 训练 {algo} agent for {ticker}... ({total_timesteps} steps)")
    model = AlgoClass("MlpPolicy", env, verbose=0, learning_rate=3e-4)
    model.learn(total_timesteps=total_timesteps)

    # 保存
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / f"finrl_{ticker}_{algo.lower()}.zip"
    model.save(str(model_path))
    print(f"✅ 模型已保存: {model_path}")

    return str(model_path)


def _query_rl_agent(model_path: Path, features: dict, algo: str = "PPO") -> dict:
    """加载模型并推理"""
    algo_map = {"PPO": PPO, "A2C": A2C, "SAC": SAC}
    AlgoClass = algo_map.get(algo.upper(), PPO)

    model = AlgoClass.load(str(model_path))

    # 构建观测向量
    obs = np.array([
        1 if features.get("current_structure", "").startswith("向上") else
        (-1 if features.get("current_structure", "").startswith("向下") else 0),
        features.get("bi_count", 0) / 20.0,
        features.get("center_count", 0) / 5.0,
        1 if features.get("divergence", {}).get("has_divergence", False) else 0,
        features.get("divergence", {}).get("energy_ratio", 1.0) or 1.0,
        features.get("dist_support_pct", 0),
        features.get("dist_resistance_pct", 0),
        features.get("ret_5d", 0),
        features.get("ret_10d", 0),
        features.get("ret_20d", 0),
        features.get("vol_change", 0),
        0,  # position = 空仓（新信号评估）
    ], dtype=np.float32)

    # 推理
    action, _ = model.predict(obs, deterministic=True)

    # 获取动作概率（confidence）
    action_probs = _get_action_probs(model, obs)

    action_map = {0: "HOLD", 1: "LONG", 2: "SHORT"}
    confidence = float(action_probs[int(action)]) if action_probs is not None else 0.5

    return {
        "action": action_map.get(int(action), "HOLD"),
        "confidence": round(confidence, 3),
        "all_probs": {action_map[i]: round(float(p), 3) for i, p in enumerate(action_probs)} if action_probs is not None else None,
    }


def _get_action_probs(model, obs):
    """从模型获取各动作的概率分布"""
    try:
        import torch
        obs_tensor = torch.as_tensor(obs.reshape(1, -1)).float()
        with torch.no_grad():
            dist = model.policy.get_distribution(obs_tensor)
            probs = dist.distribution.probs.numpy().flatten()
        return probs
    except Exception:
        return np.array([0.33, 0.34, 0.33])


def _prepare_training_data(ticker: str, data_dir: Path) -> Optional[pd.DataFrame]:
    """
    从历史 structures.json 准备训练数据

    每天一条记录，特征来自缠论结构输出
    """
    rows = []

    # 扫描所有 structures_YYYY-MM-DD.json
    for f in sorted(data_dir.glob("structures_*.json")):
        try:
            with open(f) as fh:
                data = json.load(fh)
            tickers_data = data.get("tickers", {})
            if ticker not in tickers_data:
                continue

            t_data = tickers_data[ticker]
            daily = t_data.get("levels", {}).get("daily", {})
            if "error" in daily or not daily:
                continue

            # 提取特征
            div = daily.get("divergence", {})
            last_bi = daily.get("last_bi", {})

            row = {
                "date": data.get("date", ""),
                "close": last_bi.get("high", 0) if last_bi.get("direction") == "UP" else last_bi.get("low", 0),
                "structure_dir": 1 if daily.get("current_structure", "").startswith("向上") else -1,
                "bi_count": daily.get("bi_count", 0),
                "center_count": daily.get("center_count", 0),
                "has_divergence": 1 if div.get("has_divergence", False) else 0,
                "energy_ratio": div.get("energy_ratio", 1.0) or 1.0,
                "dist_support_pct": 0,
                "dist_resistance_pct": 0,
                "ret_5d": 0,
                "ret_10d": 0,
                "ret_20d": 0,
                "vol_change": 0,
            }
            rows.append(row)
        except (json.JSONDecodeError, KeyError):
            continue

    if not rows:
        return None

    df = pd.DataFrame(rows)

    # 计算收益率特征
    if "close" in df.columns and len(df) > 20:
        df["ret_5d"] = df["close"].pct_change(5).fillna(0)
        df["ret_10d"] = df["close"].pct_change(10).fillna(0)
        df["ret_20d"] = df["close"].pct_change(20).fillna(0)

    return df


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("FinRL 信号增强模块 (4号交易员 AI 第二意见)")
        print(f"  依赖状态: numpy={'✅' if HAS_NUMPY else '❌'} "
              f"stable-baselines3={'✅' if HAS_SB3 else '❌'} "
              f"gymnasium={'✅' if HAS_GYM else '❌'}")
        print(f"  模型目录: {MODEL_DIR}")
        print()
        print("用法:")
        print("  python3 finrl_augment.py --test              # 自测（模拟灰色地带查询）")
        print("  python3 finrl_augment.py --train sh510300    # 训练 agent")
        print("  python3 finrl_augment.py --train sh510300 --algo SAC --steps 100000")
        sys.exit(0)

    if sys.argv[1] == "--test":
        print("=" * 60)
        print("🧪 FinRL 信号增强模块 — 自测")
        print("=" * 60)

        # 模拟不同强度的信号
        test_cases = [
            {"ticker": "sh510300", "strength": 5, "direction": "LONG", "desc": "高确信多"},
            {"ticker": "sh510300", "strength": 3, "direction": "LONG", "desc": "灰色地带多"},
            {"ticker": "sh510300", "strength": 1, "direction": "SHORT", "desc": "低确信空"},
        ]

        features = {
            "current_structure": "向上笔延伸中",
            "bi_count": 8,
            "center_count": 2,
            "divergence": {"has_divergence": False, "energy_ratio": 0.85},
        }

        for tc in test_cases:
            print(f"\n--- {tc['desc']} (强度={tc['strength']}, 方向={tc['direction']}) ---")
            result = augment_signal(tc["ticker"], tc["strength"], tc["direction"], features)
            print(json.dumps(result, ensure_ascii=False, indent=2))

    elif sys.argv[1] == "--train":
        if len(sys.argv) < 3:
            print("❌ 用法: python3 finrl_augment.py --train <ticker> [--algo PPO] [--steps 50000]")
            sys.exit(1)

        ticker = sys.argv[2]
        algo = "PPO"
        steps = 50000

        for i, arg in enumerate(sys.argv[3:], 3):
            if arg == "--algo" and i + 1 < len(sys.argv):
                algo = sys.argv[i + 1]
            elif arg == "--steps" and i + 1 < len(sys.argv):
                steps = int(sys.argv[i + 1])

        train_agent(ticker, algo=algo, total_timesteps=steps)
