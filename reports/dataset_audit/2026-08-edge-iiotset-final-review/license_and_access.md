# 许可与访问核验

## 来源链

1. 原论文：Ferrag 等，*Edge-IIoTset: A New Comprehensive Realistic Cyber Security Dataset of IoT and IIoT Applications for Centralized and Federated Learning*，DOI `10.1109/ACCESS.2022.3165809`。
2. 数据集 DOI：`10.21227/mbc1-1h68`（IEEE DataPort）。
3. 实际下载：论文第一作者 Mohamed Amine Ferrag 的 Kaggle 发布页，版本 5（2022-03-18），而非来源不明的二次整理包。

作者 Kaggle 页面将许可标为 **CC BY-NC-SA 4.0**。本地 `Readme.txt` 说明学术使用可免费使用并要求引用论文，商业用途需联系主要作者。当前论文研究属于非商业学术用途，但公开派生数据、模型数据卡和论文均应保留署名、许可与引用信息；若未来用途变化，应重新进行许可审查。

## 实际访问过程

- Kaggle API 可匿名列出作者数据集元数据和 52 个文件，并可获取下载地址。
- 本地最初没有 Kaggle CLI/凭据；审查期间仅在系统临时目录安装官方 Kaggle CLI，用于元数据和访问探测，没有写入项目依赖。
- 浏览器页面会要求登录，但 API 下载链路可用，因此最终未判定为 `BLOCKED_BY_ACCESS`。
- 完整 ZIP 的本地 MD5 与作者发布对象的 MD5 完全一致；详见 `source_manifest.json`。

## 引用与合规建议

论文和仓库数据说明应同时引用原论文和数据 DOI；不提交原始数据到 Git；服务器上传仅限研究所需的派生数据，并延续非商业、署名和同许可约束。此处是工程合规记录，不替代机构或法律意见。
