# config — 项目组合配置与上游锁定

职责：保存实际启用的原生插件和教学/开发预设。

内容：`web.json` 为启智 Web 的完整组合；`sdk.json` 为无界面开发内核；`upstream.lock.json` 锁定上游提交、裁剪清单与品牌哈希；`brand-baseline.patch` 保存 tracked 品牌修改，`brand-local-source.zip` 保存未入上游版本库的启智品牌源文件。

关系：由 `../src/snapshot.mjs` 生成，启动时转为官方 Loader YAML。LabKit 地址在启动时解析。

纪律：还原品牌时须同时使用 tracked 补丁和本地品牌源码 ZIP；发行清单额外记录实际编译资源哈希。配置可合成不等于运行通过。
