# 研究计划同步修改摘要

本轮依据Gate 0实际审计同步修订三份canonical计划；研究主线仍为Flow-only、父Technique开放识别、证据约束Top-k候选与独立活动少样本接入，未增加新模型任务。

## 冻结或收紧的口径

1. CasinoLimit从“第一主训练来源”改为“条件主训练/活动归因候选”：明确114个system-label实例、140个Flow文件、73个relation文件和间接label-to-Flow连接。
2. UWF从预设的2024训练池/2025独立时间外测改为按周和来源家族的条件角色：同周文件不得视为独立域，后续Sum25-1只评价实际共同Technique。
3. CAM-LDS从预设冻结外测改为主线NO-GO、可选运行级案例候选，直到找到直接NetFlow与标签连接。
4. 将名义Technique数替换为实际审计层次：CasinoLimit 66原始ID、65 active exact、24个非doubt且≥20实例；当前保守`K_core`只有2类，`K_fewshot`3类。
5. Gate 0改为“条件通过但禁止直接启动正式Qwen训练”；先完成adapter连接与防捷径验证。
6. 资源段补充Qwen3.5-9B官方多模态/混合注意力结构、17.98 GiB BF16权重和RTX 5090 QLoRA条件可行边界；27B仍非核心。
7. Open Questions删除已由审计回答的名义问题，保留relation连接、UWF活动分组、CAM NetFlow和目标GPU运行时四类真正阻塞项。

外部镜像仅从canonical单向复制，最终以SHA256确认一致；没有把镜像中的内容反向覆盖仓库。

## 最终镜像校验

| 文件 | canonical与镜像共同SHA256 |
| --- | --- |
| `research_plan_detailed.md` | `153C33F9E150B64D7DBE3153CADD1ABB0074CA3E49B7D658958ACD7E61DA45C3` |
| `research_plan_and_timeline.md` | `062284140067A9B45731B4EB2C94F3EC29CD1F9F67A1FBFEA1A4BD06299F213C` |
| `research_plan_brief.md` | `8FE7FF5D1AB30B9BCDBCA550D3037D5833624116644707E957A9AC2985167F69` |
