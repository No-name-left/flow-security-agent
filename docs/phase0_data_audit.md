# Phase 0：NF-ToN-IoT-v3 数据审计

## 1. 当前结论

**状态：阻塞于官方原始文件获取，尚未进入数据级审计。**

已核验昆士兰大学（UQ）官方记录的对象身份、开放状态和基本描述，但当前网络无法安全、可靠地连接官方签名下载地址。因此，本轮没有使用第三方镜像，没有生成未经实际数据验证的 Schema、feature-role contract、group 定义或 70/15/15 split。

```text
Phase 0 official record verified.
Raw dataset not acquired because the official object-storage endpoint
could not be safely resolved and reached from the current network.
Data audit and final split are not frozen.
```

## 2. 已完成的真实核验

### 2.1 项目与本地状态

| 项目 | 核验结果 |
| --- | --- |
| 项目目录 | `flow_security_agent` |
| 本地正式数据 | 未发现 `data/raw/` 或其他 NF-ToN-IoT-v3 原始文件 |
| 大文件 Git 隔离 | `.gitignore` 已排除 `data/`、`artifacts/`、Parquet、Arrow 等数据与产物 |
| 可用磁盘空间 | 审计时 C 盘约 108.9 GB |
| 既有数据模块 | 尚未实现数据适配、Schema、grouping 或 split |

### 2.2 官方对象身份

| 项目 | 官方元数据 |
| --- | --- |
| 数据集名称 | NF-ToN-IoT-v3 |
| 发布机构 | The University of Queensland |
| DOI | `10.48610/44d7c5e` |
| UQ RDM UUID | `343e2e8c-6e6e-4a0c-813d-a46acea1b7f4` |
| eSpace PID | `UQ:44d7c5e` |
| 数据集状态 | `PUBLISHED` |
| 访问类型 | `OPEN` |
| 打包状态 | `Available`（API 值为 `0`） |
| 官方打包 UUID | `02934b58528a226b` |
| 创建/发布年份 | 2025 |

UQ 官方记录描述该数据集为 CSV 格式，每行代表一个 Flow，包含二分类和九类攻击的多分类标签。官方说明还称其包含 53 个提取特征，其中包括 Flow 起止时间和双向 IPAT 统计。以上是**发布方元数据**，不是对本地 CSV 的实测结论。

### 2.3 官方下载链路核验

1. UQ 官方页面能够正常显示 NF-ToN-IoT-v3、Open Access、发布者、许可和“Download file”入口。
2. UQ RDM 官方 API 在携带正常网页来源标头后返回：
   - 正确的数据集 UUID；
   - `PUBLISHED`、`OPEN` 和可下载打包状态；
   - 指向 UQ RDM S3 对象存储的临时签名 URL。
3. 签名 URL 对应的文件名表明其为 UQ RDM 打包 ZIP，但当前环境无法建立到该 S3 主机的 HTTPS 连接。
4. DNS 复核中，该 `*.s3.ap-southeast-2.amazonaws.com` 主机被解析到与 AWS 对象存储身份不一致的地址；不同解析路径还返回了不同地址。由于无法确认这是本地网络重写、安全网关还是错误解析，继续下载不能满足来源完整性要求。

因此，本轮按“来源或文件身份不能可靠确认时停止”的约束终止下载，没有尝试修改签名主机、绕过 DNS 或改用 Kaggle 等第三方镜像。

## 3. 尚不能声称完成的项目

由于没有取得官方 ZIP/CSV，以下项目均没有实际运行结果：

| 审计项 | 状态 |
| --- | --- |
| 文件数量、格式、大小和 SHA-256 | 未完成 |
| 实际 Flow 总数 | 未完成 |
| 实际列数、列名和 dtype | 未完成 |
| “53 个特征”与实际 CSV 的一致性 | 未完成 |
| Binary 与原始十分类实际分布 | 未完成 |
| 缺失值、NaN、±inf、重复行和异常值 | 未完成 |
| timestamp、IP、端口、协议与标识字段 | 未完成 |
| feature-role contract | 未冻结 |
| 自然 capture/scenario/activity 字段 | 未确认 |
| group 候选策略及统计 | 未开展 |
| group-aware 70/15/15 split | 未生成 |
| split manifest 与 metadata | 未生成 |
| group overlap、样本完整性和确定性验证 | 未开展 |
| Train 内 group-aware 5-fold 可行性 | 未评估 |

官方网页公布的总量和类别计数只能作为后续下载后的交叉核对基准，不能替代对正式文件的本地流式统计。本报告不把这些发布方摘要写成“实际审计结果”。

## 4. Group 与划分结论

当前无法从真实列中确认是否存在 `capture_id`、`source_file`、`scenario_id`、`activity_id` 或可可靠重建活动边界的字段。因此：

- 未提出或推荐时间桶、IP 组合等 group 规则；
- 未生成 random row split；
- 未生成任何临时 70/15/15 split；
- Internal Test 尚未冻结；
- 不存在可报告的 per-class group count 或 split group overlap。

这避免了在缺少字段和生成过程证据时，把任意时间窗口或端点关系误当作独立攻击活动。

## 5. 后续恢复条件

满足以下任一条件后，才能继续 Phase 0：

1. 在网络可正常解析并访问 UQ 官方对象存储的环境中重新下载；或
2. 由用户从同一 UQ 官方下载入口取得 ZIP，并放入项目约定的 `data/raw/` 目录。

恢复后应先完成：

1. 记录 ZIP 文件名、字节数和 SHA-256；
2. 只读列出压缩包成员，确认内容与体量；
3. 抽取表头并核验 V3 身份；
4. 使用 PyArrow 或 chunked CSV 进行流式审计；
5. 基于真实字段比较 2～3 个 group 候选策略；
6. 只有 group 依据通过审查后，才生成确定性 70/15/15 split 和 manifest。

## 6. 已知限制与人工处理项

- 当前阻塞是数据获取环境问题，不是 group 方法学决策。
- 需要用户修复/更换可正常访问 UQ S3 的网络，或手动从 UQ 官方入口提供原始 ZIP。
- 在正式文件到位前，不应实现依赖具体列名的 Schema 和 feature-role 配置，也不应进入 60 秒上下文、LightGBM、OOF、Reviewer 或外部数据阶段。

## 7. Phase 0 判定

**Phase 0 未通过。**

官方数据对象身份已经确认，但原始文件、实际 Schema、质量统计、group 依据和 split 均未完成。当前准确状态为：

```text
Official dataset record verified.
Raw-file acquisition blocked by unsafe/inconsistent endpoint resolution.
Phase 0 data audit pending.
Final split not frozen.
```
