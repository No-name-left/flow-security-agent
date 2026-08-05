# CasinoLimit人工复核队列说明

`04_casinolimit_manual_review_queue.csv`包含45条优先样本，覆盖20个实例、16个Technique和B/C/D三类可观察性；其中30条为doubt标签、15条为非doubt。队列包含零命中、多义命中、通配/缺失端口命中和地址异常诊断，并提供relation原文、system label、候选Flow、邻近Flow、方向、时间差与待回答问题。

由于全部relation均使用通配源IP且缺失源端口，数据中不存在可抽取的R0严格命中；R1/R2也不能在不违背relation原文的情况下单独成立。队列因此不伪造这些层级，明确记录实际的`R3+R4`或R5。

`automatic_judgement_not_gold`只是机器建议。`human_decision`、`human_selected_flow_ids`、`reviewer`、`reviewed_at`和`review_notes`留空，必须由人工填写。当前4,865条relation全部被标为需人工复核；45条是用于先判断规则是否值得继续的分层入口，不是全部金标准。若该批复核不能证明候选具有足够精确率，应停止扩大人工标注，而不是默认接受其余样本。

建议人工决策值为`accept_unique`、`accept_anchor_subset`、`reject_relation`、`metadata_error`或`uncertain`。只有经确认且能按独立instance/activity隔离的记录才可进入后续监督统计。
