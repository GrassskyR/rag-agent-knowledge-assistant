# LangSmith RAG 评估报告

- Dataset: 设备手册RAG评测集100题-v1 (`527bc11f-6d49-41ba-ad24-d66228744d46`)
- Experiment: 设备手册100题-DeepSeek-v4-pro裁判-15c33b1b (`5faecb35-0106-4a95-97f6-82e93886626f`)
- Runs: 100
- Error rate: 0.0
- P50 latency: 0:00:57.402336
- P99 latency: 0:02:18.395336
- Avg latency: 72.322s
- Avg tokens: N/A
- Target errors: 0
- Evaluator errors: 0

## Overall Metrics

| Metric | N | Avg | Pass Rate | Min | Max |
| --- | ---: | ---: | ---: | ---: | ---: |
| context_recall | 85 | 0.888 | 88.2% | 0.000 | 1.000 |
| context_precision | 85 | 0.745 | 64.7% | 0.000 | 1.000 |
| faithfulness | 100 | 0.923 | 85.0% | 0.000 | 1.000 |
| answer_correctness | 100 | 0.880 | 45.0% | 0.000 | 1.000 |
| retrieval_hit_at_k | 85 | 0.835 | 83.5% | 0.000 | 1.000 |
| retrieval_mrr_at_k | 85 | 0.752 | 69.4% | 0.000 | 1.000 |
| refusal_accuracy | 15 | 0.867 | 86.7% | 0.000 | 1.000 |

## By Category

### error_code_troubleshooting

| Metric | N | Avg | Pass Rate |
| --- | ---: | ---: | ---: |
| context_recall | 35 | 0.771 | 77.1% |
| context_precision | 35 | 0.629 | 60.0% |
| faithfulness | 35 | 0.850 | 74.3% |
| answer_correctness | 35 | 0.790 | 34.3% |
| retrieval_hit_at_k | 35 | 0.657 | 65.7% |
| retrieval_mrr_at_k | 35 | 0.629 | 60.0% |
| refusal_accuracy | 0 | N/A | N/A |

### multi_step_comparison

| Metric | N | Avg | Pass Rate |
| --- | ---: | ---: | ---: |
| context_recall | 20 | 0.925 | 90.0% |
| context_precision | 20 | 0.823 | 60.0% |
| faithfulness | 20 | 0.968 | 90.0% |
| answer_correctness | 20 | 0.938 | 80.0% |
| retrieval_hit_at_k | 20 | 0.950 | 95.0% |
| retrieval_mrr_at_k | 20 | 0.854 | 80.0% |
| refusal_accuracy | 0 | N/A | N/A |

### negative_refusal

| Metric | N | Avg | Pass Rate |
| --- | ---: | ---: | ---: |
| context_recall | 0 | N/A | N/A |
| context_precision | 0 | N/A | N/A |
| faithfulness | 15 | 0.881 | 73.3% |
| answer_correctness | 15 | 0.843 | 20.0% |
| retrieval_hit_at_k | 0 | N/A | N/A |
| retrieval_mrr_at_k | 0 | N/A | N/A |
| refusal_accuracy | 15 | 0.867 | 86.7% |

### warranty_liability

| Metric | N | Avg | Pass Rate |
| --- | ---: | ---: | ---: |
| context_recall | 30 | 1.000 | 100.0% |
| context_precision | 30 | 0.829 | 73.3% |
| faithfulness | 30 | 1.000 | 100.0% |
| answer_correctness | 30 | 0.966 | 46.7% |
| retrieval_hit_at_k | 30 | 0.967 | 96.7% |
| retrieval_mrr_at_k | 30 | 0.829 | 73.3% |
| refusal_accuracy | 0 | N/A | N/A |

## Low Score Samples

- `01a07b93-f52d-7d21-97ae-f93e019ccbff` / error_code_troubleshooting / context_precision=0.000, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: e-STUDIO2551C 报 1C10 时，是先重新开机重试，还是直接换主板？重试仍失败怎么办？
  - A: 根据e-STUDIO2551C的故障排除手册，当报错误代码1C10（系统访问异常）时： 1. **不需要直接更换主板，首先应进行重启重试**：请关闭设备电源，然后再打开电源，重新执行出错的作业[6]。 2. 如果重新开机重试后问题仍然存在，**请联系您的服务维修代表处理**，不需要自行直接更换主板[6]。
- `01a07b94-963f-74b0-b001-3d2d5d9c101a` / error_code_troubleshooting / context_recall=0.000, context_precision=0.000, answer_correctness=0.350, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: e-STUDIO2551C 互联网传真报 1C71，已经启用 SSL，除用户名和密码还要核对什么？
  - A: 当e-STUDIO2551C启用SSL（TLS）后互联网传真报1C71错误，除核对用户名和密码外，还需要检查核对以下内容： 1. 检查SMTP服务器侧TLS服务器证书相关配置：确认签署TLS服务器证书使用的CA证书是否已在本机注册[1]；同时检查SMTP服务器侧的TLS服务器证书本身是否正确[1]。 2. 如果开启了<确认 SMTP 发送的 TLS 证书>选项，还需要核对TLS证书的有效性、证书链的可靠性，并确认证书的通用名（CN）是否...[截断]
- `01a07b95-82e0-7731-95ba-3c9373e20309` / error_code_troubleshooting / context_recall=0.000, context_precision=0.000, faithfulness=0.000, answer_correctness=0.025, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: 富士施乐 DocuCentre-VII C2273 报 016-799 是硬件坏了吗？第一步应重启还是报修？
  - A: 根据富士施乐 DocuCentre-VII C2273 的官方故障排除说明： 1. **该错误不一定是硬件损坏**，第一步操作应该是**重启设备**：关闭设备电源，等待触摸屏显示空白后再重新打开电源[2][5]。 2. 如果重启设备后仍然显示该错误代码，再联系富士施乐客户支持中心进行报修[2][4][5]。 综上，第一步应先尝试重启设备，若问题依旧再报修。
- `01a07b95-b296-7e40-beee-8a3e168eff2d` / error_code_troubleshooting / context_recall=0.000, context_precision=0.000, faithfulness=0.600, answer_correctness=0.025, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: DocuCentre-VII C2273 报 016-798，能只靠修改打印参数解决吗？
  - A: 根据DocuCentre-VII C2273官方手册中错误代码的规律，016开头的错误多为打印数据或打印参数不匹配相关问题。类似的相邻错误代码016-799的原因为：应用程序的打印数据中包含无效的打印参数，或打印数据和打印设定不匹配，对应的解决措施就是检查应用程序的打印数据和打印设置，修改后再次尝试打印[6]。 因此报错016-798可以先尝试通过修改打印参数解决，如果修改参数后重新打印仍然无法解决该问题，请联系官方客户支持中心进一步排...[截断]
- `01a07b97-bca6-7cc0-8770-446defe7a0de` / error_code_troubleshooting / context_recall=0.000
  - Q: DocuCentre-VII C2273 报 016-726，发送 PostScript 数据需要补充哪个组件？
  - A: 根据DocuCentre-VII C2273的设备文档，发送PostScript数据需要补充安装**Adobe PostScript 3组件**，该组件可以将设备用作PostScript打印机，支持PostScript数据处理和打印[1]。
- `01a07b98-1c17-7b60-b5bc-6426c60a9a55` / error_code_troubleshooting / context_recall=0.000, context_precision=0.000, faithfulness=0.500, answer_correctness=0.000, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: imageRUNNER ADVANCE C356 传真报 #005，有哪两种原因需要检查？
  - A: 对不起，没有找到关于imageRUNNER ADVANCE C356 传真报#005的相关故障原因信息，无法为您解答。建议您联系佳能官方客户服务中心获取专业支持。
- `01a07b97-a7ed-7860-ab29-793c41546fbc` / error_code_troubleshooting / context_precision=0.000, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: DocuCentre-VII C2273 报 016-790，邮件分割发送失败有哪些调整办法？
  - A: 针对DocuCentre-VII C2273报016-790（邮件分割发送失败）的问题，可参考以下调整办法： 该错误的原因是**超出允许的最大分割数，无法使用邮件分割方式发送邮件**，可采取以下调整措施[6]： 1. 降低[画质/文件大小]的设置，减小扫描生成的文件总大小[6]。 2. 增加「分割发送时的最大分割数」的数值：该设置位于设备的**电子邮件/Internet 传真设定**菜单中，可以在 2 到 500 的范围内指定更大的分割...[截断]
- `01a07b98-38c1-7141-9ff4-56f629481032` / error_code_troubleshooting / context_recall=0.000, context_precision=0.000, faithfulness=0.000, answer_correctness=0.037, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: imageRUNNER ADVANCE C356 出现 #009，除了补纸还应检查什么？
  - A: 根据imageRUNNER ADVANCE C356的官方手册，出现#009错误（属于纸张相关错误），在补纸之外，还需要检查以下项目： 1. 检查是否有卡纸残留：打开机器各个可能卡纸的部位（输稿器、主机内部、定影组件、纸盒、分页装订处理器等），确认是否有遗留纸张，彻底清除所有残留纸张[6]。 2. 检查进纸情况：确认送入的纸张是否存在重叠，如果发生重叠，改变方向重新摆放纸张后再尝试[6]。 3. 检查纸张类型设置：在<状态确认/取消>屏...[截断]
- `01a07b98-ef74-72b1-9cd5-d687505f8f1c` / error_code_troubleshooting / context_precision=0.000, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: imageRUNNER ADVANCE C356 报 #033，还应继续使用机密通信或子地址发送吗？
  - A: 当imageRUNNER ADVANCE C356报#033错误时，**不应该继续使用机密通信或子地址发送**。该错误表示对方设备不支持机密通信或子地址，正确的处理方式是发送时不使用机密通信或子地址 [6]。
- `01a07b99-1d4c-7bf1-a617-d349e99d648d` / error_code_troubleshooting / context_recall=0.000, context_precision=0.000, faithfulness=0.000, answer_correctness=0.025, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: imageRUNNER ADVANCE C356 出现 #034，为什么不能只认定为子地址填错？
  - A: 根据检索到的资料，不能只将imageRUNNER ADVANCE C356出现#034错误认定为子地址填错，是因为该错误的成因不止子地址填写错误这一种： 1. 除了子地址填写错误，还可能是**目标接收设备本身不支持子地址（SUB）接收**，这种情况即便子地址填写正确也会触发错误[7]； 2. 此外传真传输过程中的线路连接异常、通信故障等其他问题也可能引发该错误，因此需要对多种可能原因进行排查，不能只简单归结为子地址填错。 如果修正子地址...[截断]
- `01a07b99-74a5-73c0-9861-243b1e1c3ccf` / error_code_troubleshooting / context_recall=0.000, context_precision=0.000, answer_correctness=0.025, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: imageRUNNER ADVANCE C356 #035 表示什么？对方不支持转发时怎么发？
  - A: imageRUNNER ADVANCE C356是佳能推出的一款彩色数码多功能复合机[1]，设备屏幕或日志中显示的以#开头的数字属于错误代码，用于提示不同类型的故障[5]。目前在该设备的官方公开文档中未查询到#035错误代码的明确说明，你可以查阅设备说明书的错误代码章节，或联系佳能官方售后获取对应解决方案。 当对方设备不支持接收转发时，可按以下方法调整后重新发送： 1. 发送前先确认对方设备支持的接收功能，在发送设置中指定对方支持的接收...[截断]
- `01a07b9a-786e-78a1-a15c-65e3187a6380` / error_code_troubleshooting / context_precision=0.000, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: HP LaserJet Pro MFP M28-M31 报 Er/81，需要换碳粉盒还是装入正确固件？
  - A: 根据HP LaserJet Pro MFP M28-M31的官方用户指南，报错误代码Er/81表示**装入的固件不正确**，处理方式为：按下“开始复印”按钮以继续，之后装入正确的固件即可解决问题[6]。该错误并非提示需要更换碳粉盒。
- `01a07b99-ed81-7313-ac53-f2b018960411` / error_code_troubleshooting / context_precision=0.000, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: HP M436 显示“IP 冲突”，这是碳粉或成像装置的问题吗？
  - A: HP M436 显示“IP 冲突”**不是**碳粉或成像装置的问题，这是一个网络相关的故障提示[6]。 该提示的含义是：您为打印机设置的网络IP地址已经被网络中的其他设备占用，和碳粉、成像装置这类耗材硬件没有关系。建议解决方案是：检查打印机当前的IP地址设置，如有必要重新设置一个未被占用的IP地址即可[6]。
- `01a07b9b-f072-70a1-86e4-91dab7c333f9` / warranty_liability / context_precision=0.000, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: HP M436 在超出公布环境规格的场所运行而损坏，有限保修是否仍然覆盖？
  - A: 根据HP M436的有限保修声明，有限保修不适用于"运行环境在该产品公布的环境规格范围之外"原因造成的缺陷损坏[7]。因此，如果HP M436在超出公布环境规格的场所运行而导致损坏，该损坏不在有限保修的覆盖范围内。
- `01a07ba1-faa4-7250-bf74-0be9ef49114f` / multi_step_comparison / context_recall=0.000, answer_correctness=0.087
  - Q: DocuCentre-VII C2273 的复合纸盘 3、4 和手送纸盘标称容量各是多少？手送纸盘的堆叠高度上限呢？
  - A: 根据现有文档信息： DocuCentre-VII C2273复合纸盘模块中，纸盘3标称容量为810张，纸盘4标称容量为1175张，手送纸盘（纸盘5）标称容量为90张[1]。 现有公开文档资料中未查询到该机型手送纸盘堆叠高度上限的相关信息，无法为你提供该部分内容。
- `01a07ba2-ad51-74a2-8ee0-8ffe13ad95f1` / multi_step_comparison / context_precision=0.000, retrieval_hit_at_k=0.000, retrieval_mrr_at_k=0.000
  - Q: 430i 的照片分辨率最高是多少？连拍是否沿用最高分辨率？高于 800×600 后还能缩放吗？
  - A: 根据430i系统使用手册，相关问题解答如下： 1. 430i支持的最高照片分辨率为**1600 × 1200**，可选分辨率范围包括320 x 240、336 x 252、400 x 300、640 x 480、800 x 600、1280 x 960、1600 x 1200[6][7][8]。 2. 连拍功能不沿用当前设置的最高分辨率：开启连拍后，每次连拍的相片会固定为**640 × 480**分辨率[6]。 3. 当分辨率设置**高...[截断]
- `01a07ba5-c31e-7861-b140-4c36dbbe8c7b` / negative_refusal / faithfulness=0.400, answer_correctness=0.000, refusal_accuracy=0.000
  - Q: HP M14-M17 不连电脑和无线网络，能用 NFC 碰一碰手机就打印吗？请写 NFC 配对 PIN。
  - A: 未查询到HP M14-M17关于该功能的专属说明，根据HP打印机NFC打印的通用规则： 1. 若该机型支持NFC打印功能，则可以在不连接电脑和外部无线网络的情况下，使用NFC碰一碰配合Wi-Fi Direct实现手机直接打印，该功能本身不需要打印机连接到现有无线网络或电脑，可直接和手机建立一对一连接打印[1][2]。 2. 未查询到HP M14-M17的默认NFC配对PIN码信息，一般HP打印机默认配对PIN可尝试`0000`或`123...[截断]
- `01a07ba6-98c6-7100-9057-e83d3a534204` / negative_refusal / faithfulness=0.600, answer_correctness=0.000, refusal_accuracy=0.000
  - Q: imageRUNNER ADVANCE C356 有个 #AIGC-888 错误，说是云端大模型欠费，怎样充值才能解锁打印？
  - A: 根据现有检索到的官方文档信息，佳能imageRUNNER ADVANCE C356的官方资料中未收录#AIGC-888错误相关内容[1][3][6]。结合错误提示"云端大模型欠费"，该错误一般是由第三方加装的云端AI打印/服务导致，建议你按照以下步骤处理： 1. 首先联系提供该云端AI服务的服务商，确认具体的充值入口和充值方式，完成充值后即可解锁对应功能； 2. 如果该服务是设备原厂绑定的佳能云端服务，你可以先尝试重启设备：按下电源开关...[截断]
- `01a07b9d-cdb7-73b2-bb7f-b8a60b96f513` / warranty_liability / context_precision=0.200, retrieval_mrr_at_k=0.200
  - Q: ThinkPad Edge E535 的电池被自行拆开或改装后，这块电池还在保修范围内吗？
  - A: 根据ThinkPad Edge E535的官方保修安全说明，**非 Lenovo 指定的电池、经过自行拆开或改装过的电池不在保修范围内**[5]。因此这块电池拆开改装后不再享受保修服务。
- `01a07ba1-945b-74f1-a935-068c5d02a929` / multi_step_comparison / context_precision=0.250, retrieval_mrr_at_k=0.250
  - Q: HP LaserJet Pro M14-M17 手册列出的 Wi-Fi Direct 和 AirPrint 对机型有什么限制？完整支持移动打印前还建议做什么？
  - A: 根据HP LaserJet Pro M14-M17手册的内容，相关限制和建议如下： 1. **机型限制**：Wi-Fi Direct和移动打印功能（含AirPrint）仅支持该系列中的**无线型号**[4]，同时Wi-Fi Direct不支持所有移动操作系统，如果移动设备不支持Wi-Fi Direct，需要手动将设备的无线网络连接切换到打印机的Wi-Fi Direct连接才能打印[4]。 2. **完整支持移动打印前的建议**：在完整启...[截断]
