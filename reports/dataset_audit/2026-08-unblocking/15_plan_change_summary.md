# 计划变更摘要

| 项目 | 旧口径 | 本轮冻结口径 |
| --- | --- | --- |
| CasinoLimit | `T1018/T1046`为保守核心候选，待扩大连接 | 无正式Known；`T1046`仅为人工确认后可能成立的单类候选 |
| UWF | 可能恢复活动并承担训练/few-shot | 当前公开资料无mission ID；只作周级有限分析，不承担shot |
| 跨源K_core | 待交集审计 | 名义交集8，可靠活动级交集0，不冻结K_core |
| Unknown与shot | 待冻结1/3/5或1/5/10 | Known/pseudo/final均暂空；shot不释放，恢复后先1/3/5 |
| RAG | ATT&CK语义与证据原型 | 保留，但明确不能替代Flow监督或few-shot |
| Episode | 待验证主输入 | Gate失败；回退Anchor Flow/固定past-only聚合 |
| 总体状态 | Gate 0条件通过 | NO-GO / 数据补充，暂停正式SFT |

时间线由“第2—3周开始Stage A/SFT”改为先完成人工连接验证、UWF mission元数据获取或替代数据小probe。RTX 5090加载和单步反传冒烟可独立进行，因为它只验证环境可行性；不得下载模型权重或开始正式训练，除非另获授权且数据Gate随后通过。

三份canonical计划据此同步更新，保留原方法路线作为数据补充后的目标，不把当前失败伪装成已完成实验。
