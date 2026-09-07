# 缠论计算引擎说明（v4.4 — czsc + FinRL）

## 引擎架构（v4.4）

```
                    ┌─────────────────────────────────────────┐
                    │         analyze(bars_raw, level)         │  ← 统一入口（签名不变）
                    └──────────────────┬──────────────────────┘
                                       │
                          ┌────────────┴────────────┐
                          │                         │
                   ┌──────▼──────┐          ┌──────▼──────┐
                   │  czsc 引擎   │          │ legacy 引擎  │
                   │ （主，推荐）  │          │（fallback）  │
                   │  pip install │          │  自研 v3.0   │
                   │  czsc -U    │          │  无需依赖    │
                   └──────┬──────┘          └──────┬──────┘
                          │                         │
                          └────────────┬────────────┘
                                       │
                          ┌────────────▼────────────┐
                          │   structures.json 输出    │  ← 格式 100% 兼容
                          │   4号交易员直接读取        │
                          └────────────┬────────────┘
                                       │
                          ┌────────────▼────────────┐
                          │  FinRL 信号增强（可选）    │  ← 灰色地带 AI 第二意见
                          │  pip install finrl       │
                          │  stable-baselines3       │
                          └─────────────────────────┘
```

## 为什么必须用代码计算

LLM 无法准确做：
- K 线包含关系处理（数学规则）
- 笔的延伸/线段破坏（图论）
- MACD 柱面积累积比较（数值计算）

→ 用 Python 算法计算，4 号交易员只读 JSON 做逻辑推演，**幻觉风险归零**。

---

## czsc 引擎（主引擎，v4.4 默认）

### 安装
```bash
pip install czsc -U
```

### 优势 vs 旧版自研
| 维度 | 自研 v3.0 | czsc |
|------|-----------|------|
| 性能 | 纯 Python | Rust 加速，**10-100x 快** |
| 信号数 | 6 种 | **220+ 预置信号** |
| 多级别 | 不支持 | BarGenerator 自动合成 |
| 线段 | 不支持 | ✅ 支持 |
| 中枢扩展 | 简化版 | 严格实现 |
| 社区维护 | 无 | 活跃开源社区 |

### 核心 API
```python
from czsc import CZSC, RawBar, Freq, BarGenerator

# 单级别分析
c = CZSC(raw_bars)
c.bi_list       # 笔列表
c.fx_list       # 分型列表
c.zs_list       # 中枢列表（如可用）

# 多级别联立分析（czsc 独有）
from chanlun import analyze_multi_level
result = analyze_multi_level(bars_1min, levels=["5min", "30min", "daily"])
```

### Fallback 机制
```python
try:
    from czsc import CZSC, RawBar, Freq
    USE_CZSC = True
except ImportError:
    USE_CZSC = False  # 自动切换到旧版 legacy 引擎
```

---

## FinRL 信号增强（可选模块）

### 安装
```bash
pip install finrl gymnasium stable-baselines3 pandas numpy
```

### 定位
FinRL 不是替代 4 号的规则引擎，而是**灰色地带的 AI 第二意见**：

| 信号强度 | 处理方式 |
|---------|---------|
| ≥ 4（高确信） | 4号直接执行，不问 RL |
| 2-3（灰色地带） | **询问 RL agent** |
| < 2（低确信） | 直接放弃，不浪费 RL |

### 工作流
```
4号缠论规则引擎 → strength=3 → 灰色地带
    ↓
FinRL agent 评估（基于历史缠论结构特征训练的 PPO/A2C/SAC）
    ↓
RL confidence > 0.7 且方向同 → 信号 +1 → 执行
RL confidence < 0.3 或方向反 → 信号 -1 → 放弃
RL 中性 → 维持原判
```

### 训练
```bash
# 首次训练（需要历史 structures.json 至少 50 天）
python3 scripts/calc/finrl_augment.py --train sh510300 --algo PPO --steps 50000

# 模型保存位置
./engine/data/models/finrl_sh510300_ppo.zip
```

### 铁律
- ❌ FinRL 不能独立构成交易理由
- ❌ 未训练模型不参与决策
- ❌ RL 不能推翻高确信缠论信号

---

## 输入/输出 schema（不变）

### 输入（K 线 list）
```json
[
  {"dt": "2026-05-20", "open": 100.0, "close": 102.5, "high": 103.0, "low": 99.5, "volume": 1000000},
  ...
]
```
要求：≥ 30 根；老→新顺序

### 输出（缠论结构 JSON）
```json
{
  "engine": "czsc",
  "engine_version": "0.9.x",
  "level": "daily",
  "bars_count": 120,
  "processed_bars": 95,
  "fractal_count": 18,
  "bi_count": 12,
  "center_count": 1,
  "current_structure": "向上笔延伸中",
  "last_bi": {"direction": "UP", "high": 280.5, "low": 250.3, ...},
  "last_center": {"zg": 270.0, "zd": 260.0, ...},
  "divergence": {
    "has_divergence": false,
    "direction": "UP",
    "energy_ratio": 0.85,
    "last_macd_area": 12.5,
    "prev_macd_area": 14.7
  },
  "support": 260.0,
  "resistance": 270.0
}
```

新增字段 `engine` 和 `engine_version` 标识使用的引擎，不影响 4号读取逻辑。

## 使用方法

### 单只标的
```bash
python3 scripts/calc/chanlun.py kline.json
```

### 多只标的（接 westock-data）
```bash
python3 scripts/calc/structure_pipeline.py sh510300 hk03033 usNVDA.OQ
```

### 多级别联立（需要 czsc + 1min K线）
```bash
python3 scripts/calc/structure_pipeline.py sh510300 --multi-level
```

---

## 依赖清单

| 包 | 用途 | 必需 |
|---|------|------|
| czsc | 缠论主引擎 | 推荐（无则 fallback） |
| finrl | RL 框架（元包） | 可选 |
| stable-baselines3 | PPO/A2C/SAC | 可选（FinRL 用） |
| gymnasium | RL 环境 | 可选（FinRL 用） |
| pandas | 数据处理 | 可选（训练用） |
| numpy | 数值计算 | 可选（FinRL 用） |
