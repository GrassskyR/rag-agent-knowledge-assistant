# LangSmith RAG 评估报告

- Dataset: 设备手册RAG评测集100题-v1 (`527bc11f-6d49-41ba-ad24-d66228744d46`)
- Experiment: 设备手册100题-DeepSeek-v4-pro裁判-重跑-4d3a3730 (`08fbe6e7-aa77-40b7-891a-f1a0a0b99c0d`)
- Runs: 100
- Error rate: 0.0
- P50 latency: 0:00:55.151485
- P99 latency: 0:02:10.335558
- Avg latency: 61.283s
- Avg tokens: N/A
- Target errors: 0
- Evaluator errors: 1

## Overall Metrics

| Metric | N | Avg | Pass Rate | Min | Max |
| --- | ---: | ---: | ---: | ---: | ---: |
| context_recall | 85 | 0.878 | 87.1% | 0.000 | 1.000 |
| context_precision | 85 | 0.858 | 78.8% | 0.000 | 1.000 |
| faithfulness | 99 | 0.939 | 87.9% | 0.000 | 1.000 |
| answer_correctness | 100 | 0.876 | 44.0% | 0.000 | 1.000 |
| retrieval_hit_at_k | 85 | 0.918 | 91.8% | 0.000 | 1.000 |
| retrieval_mrr_at_k | 85 | 0.862 | 82.4% | 0.000 | 1.000 |
| refusal_accuracy | 15 | 0.867 | 86.7% | 0.000 | 1.000 |

## By Category

### error_code_troubleshooting

| Metric | N | Avg | Pass Rate |
| --- | ---: | ---: | ---: |
| context_recall | 35 | 0.800 | 80.0% |
| context_precision | 35 | 0.814 | 80.0% |
| faithfulness | 35 | 0.882 | 74.3% |
| answer_correctness | 35 | 0.819 | 34.3% |
| retrieval_hit_at_k | 35 | 0.829 | 82.9% |
| retrieval_mrr_at_k | 35 | 0.814 | 80.0% |
| refusal_accuracy | 0 | N/A | N/A |

### multi_step_comparison

| Metric | N | Avg | Pass Rate |
| --- | ---: | ---: | ---: |
| context_recall | 20 | 0.833 | 80.0% |
| context_precision | 20 | 0.829 | 65.0% |
| faithfulness | 20 | 0.975 | 95.0% |
| answer_correctness | 20 | 0.858 | 70.0% |
| retrieval_hit_at_k | 20 | 0.950 | 95.0% |
| retrieval_mrr_at_k | 20 | 0.850 | 80.0% |
| refusal_accuracy | 0 | N/A | N/A |

### negative_refusal

| Metric | N | Avg | Pass Rate |
| --- | ---: | ---: | ---: |
| context_recall | 0 | N/A | N/A |
| context_precision | 0 | N/A | N/A |
| faithfulness | 15 | 0.907 | 86.7% |
| answer_correctness | 15 | 0.839 | 6.7% |
| retrieval_hit_at_k | 0 | N/A | N/A |
| retrieval_mrr_at_k | 0 | N/A | N/A |
| refusal_accuracy | 15 | 0.867 | 86.7% |

### warranty_liability

| Metric | N | Avg | Pass Rate |
| --- | ---: | ---: | ---: |
| context_recall | 30 | 1.000 | 100.0% |
| context_precision | 30 | 0.928 | 86.7% |
| faithfulness | 29 | 1.000 | 100.0% |
| answer_correctness | 30 | 0.974 | 56.7% |
| retrieval_hit_at_k | 30 | 1.000 | 100.0% |
| retrieval_mrr_at_k | 30 | 0.925 | 86.7% |
| refusal_accuracy | 0 | N/A | N/A |

## Low Score Samples

- `01a08659-bdb1-7d41-a303-3b3598fdbe2b` / error_code_troubleshooting / context_recall=0.000, context_precision=0.000, answer_correctness=0.363, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: e-STUDIO2551C 互联网传真报 1C71，已经启用 SSL，除用户名和密码还要核对什么？
  - A: For e-STUDIO2551C internet fax error 1C71 when SSL is already enabled, besides confirming the username and password, you also need to check the following items: 1. **TLS server certificate verification configuration** If...[截断]
- `01a0865a-d63f-7542-87ad-db872d929c95` / error_code_troubleshooting / context_recall=0.000, context_precision=0.000, answer_correctness=0.350, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: DocuCentre-VII C2273 报 016-798，能只靠修改打印参数解决吗？
  - A: 根据现有知识库，未查询到DocuCentre-VII C2273报错016-798的相关说明，无法确认该问题是否只靠修改打印参数解决，建议您联系富士施乐官方客户支持中心获取帮助，服务热线：800-820-5146（固定电话）、400-820-5146（手机）。
- `01a0865a-bed6-72e2-96f5-3d4e940f148c` / error_code_troubleshooting / context_recall=0.000, context_precision=0.000, faithfulness=0.000, answer_correctness=0.062, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: 富士施乐 DocuCentre-VII C2273 报 016-799 是硬件坏了吗？第一步应重启还是报修？
  - A: 根据富士施乐DocuCentre-VII C2273的官方故障排除规则： 1. **不一定是硬件损坏**，该错误代码016-799可能由临时的打印数据错误、系统软件临时故障等非硬件问题引发。 2. **第一步应该先重启设备**：关闭设备电源，等待触摸屏空白后重新打开电源，重启后观察错误是否消失[2][6][7]。如果重启后错误仍然存在，再联络富士施乐客户支持中心报修处理[2][9]。
- `01a0865c-fe2f-7d62-8869-462c5e10e82c` / error_code_troubleshooting / context_recall=0.000
  - Q: DocuCentre-VII C2273 报 016-726，发送 PostScript 数据需要补充哪个组件？
  - A: 根据你提供的设备信息和错误代码，DocuCentre-VII C2273 发送 PostScript 数据需要补充的组件是 **Adobe PostScript 3 组件**。该组件可以将设备用作PostScript打印机，支持PostScript数据打印和从Macintosh设备打印 [1]。
- `01a0865d-3eaa-7402-9e5d-ed8d847af55d` / error_code_troubleshooting / context_recall=0.000, context_precision=0.000, faithfulness=0.167, answer_correctness=0.025, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: imageRUNNER ADVANCE C356 出现 #009，除了补纸还应检查什么？
  - A: 根据现有知识库检索结果，未查询到针对佳能imageRUNNER ADVANCE C356错误代码#009的明确对应说明。结合数码复合机同类错误的通用处理经验，除补纸外，还建议你做以下检查： 1. **检查卡纸残留**：彻底检查设备所有纸道（纸盒、走纸通道、定影区域、输稿器），确认是否残留有小块卡纸或纸屑，残留卡纸会引发纸张检测错误[1][5]。 2. **检查纸张传感器**：确认进纸位置的纸张传感器是否被纸屑遮挡，传感器异常会导致无法正...[截断]
- `01a0865d-1757-74d1-8b64-c9a94697afdf` / error_code_troubleshooting / context_recall=0.000, context_precision=0.000, faithfulness=0.500, answer_correctness=0.000, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: imageRUNNER ADVANCE C356 传真报 #005，有哪两种原因需要检查？
  - A: 根据当前检索到的知识库信息，没有找到关于imageRUNNER ADVANCE C356传真报错#005对应的具体需要检查的原因，无法回答该问题，建议您联系佳能官方售后服务获取专业帮助。
- `01a0865d-e4ab-7780-83b2-b6493eb64292` / error_code_troubleshooting / context_recall=0.000, context_precision=0.000, answer_correctness=0.000, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: imageRUNNER ADVANCE C356 出现 #034，为什么不能只认定为子地址填错？
  - A: 根据现有检索到的资料，未找到imageRUNNER ADVANCE C356错误代码#034的相关具体说明，无法回答您的问题。建议您查阅该设备官方用户指南中错误代码对应章节，或联系本地佳能授权经销商获取专业支持。
- `01a08665-0307-74b3-99dd-f3fd8c34e0c5` / multi_step_comparison / context_recall=0.000, context_precision=0.250, faithfulness=0.500, answer_correctness=0.512, retrieval_mrr_at_k=0.250
  - Q: HP LaserJet Pro M402/M403 系列手册中，纸盘 1、2、可选纸盘 3 的容量，以及 A4 和 Letter 打印速度分别是多少？
  - A: 根据现有检索到的信息，整理HP LaserJet Pro M402/M403系列相关参数如下： ### 纸盘容量 1. 纸盘1（多用途纸盘）：可容纳100页80g/m²（21磅证券纸）普通纸[2]。 2. 纸盘2：可容纳250页80g/m²（21磅证券纸）普通纸[2][4]。 3. 可选纸盘3：为550页进纸器，容量为550页[4]。 ### 打印速度 现有资料中未检索到该系列打印机A4和Letter规格的打印速度相关信息，无法提供对应...[截断]
- `01a08666-37a1-7c63-a1fd-cc2b8768b295` / multi_step_comparison / context_recall=0.000, answer_correctness=0.100
  - Q: DocuCentre-VII C2273 的复合纸盘 3、4 和手送纸盘标称容量各是多少？手送纸盘的堆叠高度上限呢？
  - A: 根据查询到的规格信息： 1. DocuCentre-VII C2273 复合纸盘模块中，纸盘3标称容量为810张，纸盘4标称容量为1175张，手送纸盘标称容量为90张[1]。 2. 现有资料中未查询到该机型手送纸盘的堆叠高度上限相关信息，无法提供该数据。 [1]: 05_40319_DocuCentre_-VII_C2273.pdf (Page 1046)
- `01a08666-9b31-7ba2-931d-e7096d4b3035` / multi_step_comparison / context_recall=0.000, context_precision=0.000, answer_correctness=0.000, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: 对照 N15 与 N18 手册，日夜模式和语音播报有什么差别？不要把 N18 的新增描述套给 N15。
  - A: 很抱歉，现有知识库中未找到N15与N18对应手册中关于日夜模式和语音播报的对比信息，无法回答您的问题。
- `01a08667-5617-7ab0-93a5-94bca8882a46` / negative_refusal / faithfulness=0.600, answer_correctness=0.000, refusal_accuracy=0.000
  - Q: DocuCentre-VII C2273 支持蓝牙 5.3 隔空打印 3D 模型切片吗？请给出配对步骤。
  - A: DocuCentre-VII C2273是富士施乐的常规办公数码复合机，仅支持普通纸张的打印复印，**不支持3D模型切片打印**，官方也未标注该机型支持蓝牙5.3规格。该机型支持通过蓝牙连接AirPrint实现普通文档的隔空打印，配对配置步骤如下： ### 打印机端配置步骤： #### 方式1：使用远程用户界面配置 1. 启动远程用户界面并登录管理员账户，依次点击「设置/注册」→「网络设置」→「蓝牙设置」[1]； 2. 勾选「使用蓝牙」...[截断]
- `01a08669-93c5-7fc2-a598-5e97112d4580` / negative_refusal / faithfulness=0.000, answer_correctness=0.000, refusal_accuracy=0.000
  - Q: HP M14-M17 不连电脑和无线网络，能用 NFC 碰一碰手机就打印吗？请写 NFC 配对 PIN。
  - A: HP M14-M17（带NFC功能的无线型号）**不连接电脑和公共无线网络，是可以使用NFC碰一碰手机打印的**。NFC打印配合Wi-Fi Direct功能实现，不需要打印机连接到现有无线网络或电脑，手机通过NFC碰一碰即可触发直接连接到打印机的Wi-Fi Direct，完成打印[1][2]。 关于NFC配对PIN：当连接方式设置为手动配对时，配对PIN码会**直接显示在打印机的控制面板上**；也可以通过HP嵌入式Web服务器（EWS）...[截断]
- `01a08661-e116-76d0-8401-297173977883` / warranty_liability / context_precision=0.250, retrieval_mrr_at_k=0.250
  - Q: ThinkPad Edge E535 的电池被自行拆开或改装后，这块电池还在保修范围内吗？
  - A: 根据ThinkPad Edge E535官方保修和安全指南的明确说明：**拆开或改装过的电池不在保修范围内**[4]。 官方指南中明确指出：请勿试图拆开或改装电池，非 Lenovo 指定的电池、拆开或改装过的电池不在保修范围内[4]。因此，ThinkPad Edge E535 的电池被自行拆开或改装后，将不再享受保修服务。
- `01a08665-d191-7261-be8b-c70c0c436023` / multi_step_comparison / context_precision=0.250, retrieval_mrr_at_k=0.250
  - Q: HP LaserJet Pro M14-M17 手册列出的 Wi-Fi Direct 和 AirPrint 对机型有什么限制？完整支持移动打印前还建议做什么？
  - A: 根据HP LaserJet Pro M14-M17手册的相关内容，相关限制和建议如下： ### 机型限制 1. **Wi-Fi Direct 和 AirPrint 都仅限该系列的无线型号支持**，非无线型号不提供这两项功能[4]。 2. 额外限制：Wi-Fi Direct 不支持所有移动操作系统，如果你的移动设备不支持Wi-Fi Direct，需要手动将设备的无线网络连接切换为打印机的Wi-Fi Direct连接后才能进行打印[4]。 ...[截断]
- `01a0865c-8b6b-70a3-96cb-e04a0c031127` / error_code_troubleshooting / faithfulness=0.500, answer_correctness=0.713
  - Q: DocuCentre-VII C2273 报 016-790，邮件分割发送失败有哪些调整办法？
  - A: 针对DocuCentre-VII C2273报016-790（邮件分割发送失败），可采取以下调整办法[1]： 1. 降低 **[画质/文件大小]** 设置里的文件大小，降低单份分割文件的体积，减少需要的分割数量。 2. 增加 **[分割发送时的最大分割数]** 的设置数值，允许更大的分割数量，适配当前的文件大小。
- `01a0865c-6a76-7742-84ee-8bfaf73e2e7c` / error_code_troubleshooting / context_precision=0.500, retrieval_mrr_at_k=0.500
  - Q: DocuCentre-VII C2273 的 016-780 能仅按“空间不足”删除文件处理吗？
  - A: 根据DocuCentre-VII C2273的官方错误代码说明，**016-780错误不能仅按“空间不足”删除文件处理**[2]： 该错误代码的原因是：扫描的图像转换处理期间硬盘发生硬件错误，并非单纯硬盘空间不足。官方给出的处理措施是：硬盘可能损坏，需要更换硬盘，请联系官方客户支持中心处理[2]。 补充说明：如果是因为硬盘空间不足导致的同类错误（016-778），才可以通过删除硬盘中不必要的数据来释放空间解决。
- `01a08662-f2e2-7b10-aea8-361aeacf92d4` / warranty_liability / context_precision=0.500, retrieval_mrr_at_k=0.500
  - Q: ThinkPad S230u 的内置可充电锂离子电池需要更换时，指南要求客户自行拆机换，还是联系谁处理？
  - A: 根据ThinkPad S230u的官方指南要求： 请勿尝试自行更换内部可充电锂离子电池，当需要更换时，请联系Lenovo支持人员进行返厂更换[2]。
- `01a08662-f9d3-7330-89eb-7344b3d6aa6e` / warranty_liability / context_precision=0.500, retrieval_mrr_at_k=0.500
  - Q: 按高德车载导航 V6.10 手册，随产品提供的 SD 卡免费保修多久，需要什么购买凭证？
  - A: 根据高德车载导航V6.10用户手册说明： 随产品提供的SD卡**自购买日起一年内免费保修**，保修需要提供**购买发票**作为凭证[2]。
- `01a08663-f964-7581-a590-15d584e1b23f` / warranty_liability / context_precision=0.583, retrieval_mrr_at_k=0.500
  - Q: 按《专业便携式车载 GPS》手册，安装导航器挡住驾驶视线或安全气囊并造成损失，厂商是否作出赔偿承诺？
  - A: 根据《专业便携式车载 GPS》手册中的说明：**对于错误安装导致导航器挡住驾驶视线或安全气囊并由此造成的产品故障、其他财产损失和人身损害，本产品制造商不承担任何赔偿责任**，厂商不会作出赔偿承诺[2][3]。
- `01a08665-332b-7d42-b798-6c75787b2a64` / multi_step_comparison / context_precision=0.500, retrieval_mrr_at_k=0.500
  - Q: HP M402/M403 完全打开与完全合上时，高度和厚度各变化多少，宽度是否改变？
  - A: 根据HP官方规格文档，不同配置下HP M402/M403的尺寸变化如下： ### 1. 单台打印机（不带可选纸盘） - **高度变化**：完全合上时为216毫米，完全打开时为241毫米，打开后高度增加**25毫米** [2] - **厚度变化**：完全合上时为357毫米，完全打开时为781毫米，打开后厚度增加**424毫米** [2] - **宽度**：完全合上和完全打开均为381毫米，宽度**无变化** [2] ### 2. 带可选5...[截断]
