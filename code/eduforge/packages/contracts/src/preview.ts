/**
 * §5.3 预览桥接协议。放在契约包里，是为了让浏览器端与 Engine Host 用同一份定义：
 * 这条协议不在 OpenAPI 里（它走 postMessage 而不是 HTTP），所以必须显式维护，
 * 不能靠"两边各写一遍、刚好一样"。
 *
 * 只有确实实现了的三类消息。加一类就得两边同时改。
 */
export type PreviewMessage =
  | { type: "eduforge.ready"; revision_id: string }
  | { type: "eduforge.parameter_changed"; entity_id: string; parameter: string; value: number }
  | { type: "eduforge.error"; code: string; message: string };

/** 父页 → 包装页：请求改一个已登记参数。服务端不认就回 error。 */
export type SetParameterRequest = {
  type: "eduforge.set_parameter";
  entity_id: string;
  parameter: string;
  value: number;
};
