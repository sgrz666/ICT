# artifacts — 运行期产物（预留）

**当前为空目录，尚未投入使用。**

规划用途：EduForge 运行期产生的交付产物（实验包、导出文件等）。当前实现里，产物交付走 API 链路的 `storage_key` 直接返回登记哈希锁定的字节（见 `tests/python/test_gate5_api_chain.py` 的产物完整性用例），并不落地到本目录；离线包形态的候选在 [`../candidates/`](../candidates/README.md)。待交付形态稳定后再决定是否把落盘位置统一到此。
