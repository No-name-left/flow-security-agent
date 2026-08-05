# 三份正式计划一致性矩阵

| topic | detailed_section | timeline_section | brief_section | previous_statement | final_statement | consistency_status | action_taken |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 研究问题 | 0.1、1 | 1 | 一 | Flow可观察ATT&CK父Technique识别 | 原生标签下Unknown→候选→few-shot生命周期与自适应决策 | 一致 | 三份重写 |
| 输入数据 | 2 | 1—2 | 二 | 多源统一ATT&CK Flow | Flow-only；不同数据集原生Schema | 一致 | 移除强制统一 |
| 样本单位 | 2.1—2.4 | 2 | 二 | 统一Flow/Episode | Adapter必须声明Flow或窗口摘要语义 | 一致 | 明确CIC固定包窗口 |
| 数据集角色 | 0.2 | 1 | 二 | UWF/Casino条件主线 | CIC工程、UWF专项、Casino历史、主数据待Gate | 一致 | 写入冻结表 |
| coarse/fine标签 | 2.1 | 3.1 | 二—三 | ATT&CK父Technique统一 | 每库保留原生层次 | 一致 | 统一接口而非统一名称 |
| K_known | 3.1 | 3.1 | 三 | 旧K撤回为空 | 主数据通过后预注册 | 一致 | 保留未冻结状态 |
| U_dev | 3.1 | 3.1 | 三 | pseudo-unknown定义分散 | 仅开发阈值/策略 | 一致 | 统一命名和权限 |
| U_final | 3.1—3.2 | 3.1 | 三 | final-held-out但知识隔离不足 | 训练、RAG、Prompt、策略和人工调参完全隔离 | 一致 | 明确禁入项 |
| Unknown rejection | 3.2 | 3.1 | 三 | 可能与候选归因混合 | 阶段A独立拒识，不要求命名 | 一致 | 分三阶段 |
| RAG候选识别 | 3.2、4.4 | 3.1 | 三 | ATT&CK固定检索 | 拒识后才使用full frozen RAG | 一致 | 分离知识域 |
| 1/5/10-shot | 3.2 | 3.1 | 三 | 1/3/5或data-dependent | 固定评价1/5/10，必须独立活动 | 一致 | 冻结shot语义 |
| support/query | 3.2 | 2—3 | 二—三 | mission不足则暂停 | 独立capture/run；否则仅工程实验 | 一致 | 增加Gate |
| Adaptive Agent | 5 | 3.2 | 三 | 固定/受约束工作流扩展 | Evidence-Decision Tree动态动作 | 一致 | 升级为核心方法 |
| agent状态 | 5.1 | 3.2 | 三 | 模块状态机 | 置信、证据、工具、预算、深度 | 一致 | 详细版完整定义 |
| agent动作 | 5.1 | 3.2 | 三 | 路由/检索/分类/验证 | A0—A9十类动态动作 | 一致 | 固定白名单 |
| agent奖励 | 5.3 | 3.2 | 三 | 未冻结 | 分类/拒识/层次效用减成本与非法动作 | 一致 | 详细版定义，派生版概括 |
| feedback归因 | 5.3 | 3.2 | 三 | 错误回收但组件边界弱 | 组件级归因和定向更新 | 一致 | 禁止称数学反传 |
| LightGBM/XGBoost | 4.1、7 | 3.2—3.3 | 三—四 | 基线与Reviewer候选 | 主基础模型、OOF数据源和强基线 | 一致 | 强化角色 |
| Qwen3.5-9B | 4.3、6 | 3.2 | 三 | Stage A-D主模型 | Tree-aware Security Reviewer，SFT有Gate | 一致 | 27B降为可选 |
| SFT | 4.3、6 | 1、5 | 三、五 | 正式训练暂停 | 仅数据/split/KU/隔离冻结后启动 | 一致 | 保持暂停 |
| DPO | 6 | 1、5 | 三、五 | 优先偏好分支 | 明确偏好问题时条件性小试 | 一致 | 非必做 |
| PPO边界 | 5.2、6 | 3.2、4 | 三、五 | RLAIF/PPO候选 | 当前不采用复杂PPO | 一致 | 移出最低范围 |
| RAG来源 | 4.4 | 3.1—3.2 | 三 | 主要ATT&CK | 官方类别、协议、行为、ATT&CK/CAPEC、原型 | 一致 | 保留分域 |
| 四组实验 | 7 | 3.3 | 四 | 旧Track A/B及Agent扩展 | 闭集、开放Agent、few-shot、多数据集 | 一致 | 统一编号 |
| 评价指标 | 7—8 | 3.3 | 四 | 分类/候选/成本分散 | Known、Unknown、接入、任务、恢复、成本 | 一致 | 对应研究问题 |
| 数据Gate | 2.2 | 2、6 | 二、五 | Gate 0依赖ATT&CK连接 | 原生标签、group、捷径、K/U、few-shot | 一致 | CIC判ENGINEERING_ONLY |
| 时间安排 | 9 | 5 | 五 | 数据补充后再训练但路径较散 | T0后四周，T0=主数据和协议冻结 | 一致 | 明确依赖 |
| 风险/降级 | 10 | 6—7 | 四—五 | 数据不足、模型无增益 | 不降泄漏标准；Static/Reviewer/Unknown分级收缩 | 一致 | 明确负结果 |

结论：三份计划在研究对象、数据角色、实验编号、启动Gate与负结果边界上语义一致；详细版包含完整规范，时间表只派生任务，简版不引入额外承诺。
