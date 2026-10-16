import { useState } from "react";
import galleryItems from "../data/galleryData.json";

export type SimulatorViewProps = {
  activeScene: string | null;
  onSelectScene: (sceneUrl: string) => void;
  onImportToStudio?: (sceneUrl: string, title: string) => void;
};

const POPULAR_PRESETS = [
  { name: "凸透镜", url: "../cn/gallery/convex-lens" },
  { name: "凹透镜", url: "../cn/gallery/concave-lens" },
  { name: "抛物面镜", url: "../cn/gallery/parabolic-mirror" },
  { name: "棱镜折射", url: "../cn/gallery/prisms" },
  { name: "牛顿望远镜", url: "../cn/gallery/newtonian-telescope" },
  { name: "潜望镜", url: "../cn/gallery/periscope" },
  { name: "两面镜子成像", url: "../cn/gallery/images-formed-by-two-mirrors" },
];

export function SimulatorView({ activeScene, onSelectScene, onImportToStudio }: SimulatorViewProps) {
  const [fullscreen, setFullscreen] = useState(false);

  // 构造模拟器 iframe 的完整 URL
  const currentScene = activeScene || "";
  const iframeSrc = currentScene
    ? `/simulator/?zh-CN#${currentScene}`
    : `/simulator/?zh-CN`;

  const currentItem = galleryItems.find(x => x.sceneUrl === currentScene);

  return (
    <div className={`simulator-container ${fullscreen ? "fullscreen-mode" : ""}`}>
      <div className="simulator-toolbar">
        <div className="toolbar-left">
          <span className="toolbar-label">当前场景：</span>
          <select
            className="scene-selector"
            value={currentScene}
            onChange={e => onSelectScene(e.target.value)}
          >
            <option value="">⚡ 新建空白场景 (自由绘制光学元件)</option>
            <optgroup label="81 个光学交互案例库">
              {galleryItems.map(item => (
                <option key={item.id} value={item.sceneUrl}>
                  [{item.categoryName}] {item.title}
                </option>
              ))}
            </optgroup>
          </select>
          {currentItem ? (
            <span className="scene-badge">{currentItem.categoryName}</span>
          ) : null}
        </div>

        <div className="toolbar-right">
          {currentItem && onImportToStudio ? (
            <button
              className="ghost"
              onClick={() => onImportToStudio(currentItem.sceneUrl, currentItem.title)}
              title="将此案例载入 EduForge AI 定制工坊进行教学调参和Prompt二次创作"
            >
              🤖 导入 AI 定制工坊
            </button>
          ) : null}
          <a
            href={iframeSrc}
            target="_blank"
            rel="noreferrer"
            className="button-link"
            title="在新标签页全屏独立打开原生 Ray Optics 模拟器"
          >
            ↗ 独立窗口打开
          </a>
          <button
            className="ghost"
            onClick={() => setFullscreen(!fullscreen)}
            title="切换全屏沉浸模式"
          >
            {fullscreen ? "退出全屏" : "⛶ 沉浸全屏"}
          </button>
          <button
            className="ghost"
            onClick={() => onSelectScene("")}
            title="清空当前场景"
          >
            清空重置
          </button>
        </div>
      </div>

      {/* 快捷推荐预置条 */}
      <div className="preset-bar">
        <span className="preset-title">精选场景直开：</span>
        <button
          className={`preset-btn ${!currentScene ? "active" : ""}`}
          onClick={() => onSelectScene("")}
        >
          ✨ 空白画布
        </button>
        {POPULAR_PRESETS.map(p => (
          <button
            key={p.url}
            className={`preset-btn ${currentScene === p.url ? "active" : ""}`}
            onClick={() => onSelectScene(p.url)}
          >
            {p.name}
          </button>
        ))}
      </div>

      <div className="simulator-frame-wrapper">
        <iframe
          key={iframeSrc}
          src={iframeSrc}
          title="Ray Optics 射线光学模拟器"
          allow="fullscreen; clipboard-read; clipboard-write"
          className="simulator-iframe"
        />
      </div>

      {currentItem ? (
        <div className="simulator-scene-info">
          <h3>{currentItem.title}</h3>
          <p className="scene-desc">{currentItem.description}</p>
          <div className="scene-meta">
            <span>贡献者：{currentItem.contributors.join(", ") || "Ray Optics 团队"}</span>
            <a href={currentItem.pageUrl} target="_blank" rel="noreferrer" className="meta-link">
              查看案例原理单页 →
            </a>
          </div>
        </div>
      ) : (
        <div className="simulator-scene-info">
          <h3>自由几何光学实验台</h3>
          <p className="scene-desc">
            可以在上方菜单栏中选择【工具】放置点光源、光束、平行光、球面镜、平面镜、理想透镜、双曲面镜、棱镜与光栅等各类光学元件，
            支持实时光线追迹、多色波长模拟与探测器测量。
          </p>
        </div>
      )}
    </div>
  );
}
