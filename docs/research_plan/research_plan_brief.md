# Open-World Continually Evolving LLM Traffic Agent（导师简版）

> DEC-0025/DEC-0026/DEC-0027，2026-08-16。完整规则见[研究计划详细版](research_plan_detailed.md)，正式实验见[Experiment Protocol v1](experiment_protocol_v1.md)。

## 一、核心研究问题

网络样本在基础信息不足时分类不可靠，并不等于它是新攻击。新方法先区分：

- 基础信息已经足够的已知攻击；
- 补充合法网络证据后可以恢复的已知攻击；
- 训练阶段完整留出的真正未知攻击。

系统只把补充证据后仍不能归入Known的样本送入Unknown路径，目标是减少“信息暂时不足”造成的false Unknown。

方法核心为：

```text
Evidence-Conditioned Open-World Traffic Recognition
+ Empirically Grounded Typed-Evidence Acquisition
+ Evidence-Gated Continual Evolution
```

## 二、为什么现在可以继续

官方NF3-ToN-IoT final processed artifact已通过身份、schema和标签核验，不需要从raw数据重制。24,000条先导实验确认：

- Basic和补充Temporal/Relation后的Full之间存在可测分类增益；
- 约12%的样本属于可通过补充证据恢复的Known；
- “哪些样本值得补证据”具有很强的可预测信号；
- 先补证据再做Unknown判断，整体上减少了recoverable Known被误拒绝。

结果仍有类别差异，特别是Recon_Scanning、Web_Injection和Credential，因此当前结论是`PASS_WITH_LIMITATIONS`，不是最终论文结果。

## 三、Dataset-v4与Model B

Dataset-v4核心使用NF3-ToN-IoT，七类taxonomy（Benign及六类攻击机制）、grouped 70/15/15 split与Credential/Recon_Scanning/Web_Injection whole-class rotations已经冻结。七类TRAIN/VALIDATION/FINAL_TEST为19,858,267/3,809,983/3,842,026，identity、exact-duplicate group与activity-group cross-split均为0。

Model B候选由Qwen traffic representation、Known Fine Head和小型Evidence utility selector组成。Unknown不是普通的第K+1类，而是在证据恢复状态与Known representation/logits基础上独立判断。Model A保留为单域基线和可选replay来源，不默认warm-start。

## 四、Agent如何工作

```text
Basic Evidence
→ 分类与Evidence utility估计
→ 足够则停止并分类
→ 值得则获取Temporal或Relation Evidence
→ 重新评价
→ 只有剩余novelty才进入Unknown Buffer
```

Controller基线采用确定性或监督式utility策略；随后以低成本fast policy Gate比较Double DQN。DeepSeek可做离线语义审查、解释、示范或可选Supervisor基线，但不提供Model B的utility真值。fast RL失败可作为negative result，不影响核心方法；LLM级RL不进入core。

## 五、模型如何获得新能力

Unknown样本只有在获得可靠人工/外部verified label后才能注册新类。随后使用监督式continual adaptation和旧类replay更新参数，并通过旧类、新类、Unknown和domain-stress回归Gate；Memory增加或模型自信不能代替学习与验证。

## 六、正式阶段

1. NF3-ToN Dataset-v4、taxonomy、split和Unknown协议已完成冻结；
2. 建立Model B static foundation，完成fresh-vs-warm和Qwen-vs-small Gate；
3. 分别验证Temporal、Relation及组合Evidence的OOF utility和robustness；
4. 比较Direct novelty、Always acquire和Utility-conditioned acquisition；
5. 用offline Evidence episode比较heuristic、supervised utility、Teacher（如有）与Double DQN；
6. static foundation稳定后，以相同adaptation/replay比较direct与Evidence-gated continual evolution；
7. 最后才做multi-Unknown、slow policy、missing-Evidence和external-domain辅助实验。

正式论文固定五个主实验：Model/representation、typed utility、open world、continual、fast Agent-policy RL；使用至少三seed和group/temporal-block统计。`1,816,137`个duplicate copies不改master split，但训练和primary evaluation必须使用预注册的duplicate-aware派生视图。

其他NF3数据集只作secondary external-domain stress/replication；CICIoT2023与raw CIC/ToN不是core依赖，当前不下载。

下一动作是在researcher显式授权下生成已冻结的2,000项pre-price Teacher cache与63项semantic reference；Model-B低成本design Gate已解除B1阻塞但尚未启动，正式训练仍未授权。
