# UWF活动边界审计

官方数据入口：https://datasets.uwf.edu/ ；Data24论文：https://www.mdpi.com/2306-5729/10/5/59

## 可恢复信息

UWF-ZeekData24论文说明：每次攻击由mission log记录Technique、源/目的IP与端口、UTC起止时间，发布流程以约一分钟余量把日志关联到网络记录；论文报告29,550条mission log。然而当前官方公开下载树只暴露按周CSV/Parquet及汇总指标，未发现原始mission log、稳定activity ID或可复算的攻击脚本运行ID。

因此，公开Flow中的`label_technique`可用于逐Flow标签分析，但无法回答“同一Technique一周内执行了几次”“哪些Flow属于同一次mission”或“support/query是否来自独立活动”。本轮在已有六个Parquet样本上按Technique、源IP和60秒间隔形成的簇仅为诊断：`T1018=1`、`T1046=1`、`T1210=3`、`T1595=28`。这些簇可能把长任务切开或把连续任务合并，全部标记为`shot_eligible=false`。

## 使用边界

- week/capture只能作为保守split group和时间漂移单位，不能把同一周Flow当独立shot。
- 无mission边界时，UWF不承担正式few-shot、Episode监督或最终held-out query。
- past-only上下文可在工程上构造，但不能证明属于同一攻击活动；只能作为固定窗口统计或敏感性分析。
- Data24/Fall24-2受控攻击周与正常周的时间分布不同，存在类别—时间捷径；不得据此给出普通随机拆分主结果。

## 2025时间外测

Sum25-1在2025-06-15之后包含`T1016/T1046/T1190/T1210/T1548/T1595`，但周级分布被`T1595`大规模扫描主导，且缓存的官方周统计没有可比的同周Benign背景。`T1046`只在一个后续周出现。它最多承担有限共同Technique或校准漂移的描述性测试，不能称为完整开放集时间外测。

解除阻塞的首选不是下载更多周Flow，而是从作者或官方仓库获得mission log/活动映射及其版本说明；获得前不得把启发式簇升级为金标准。
