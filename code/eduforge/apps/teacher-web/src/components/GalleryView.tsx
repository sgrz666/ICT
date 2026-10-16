import { useMemo, useState } from "react";
import galleryItems from "../data/galleryData.json";

export type GalleryItem = typeof galleryItems[number];

export type GalleryViewProps = {
  onOpenInSimulator: (sceneUrl: string) => void;
  onImportToStudio?: (sceneUrl: string, title: string) => void;
};

const CATEGORIES = [
  { id: "all", name: "全部案例" },
  { id: "reflection", name: "光的反射" },
  { id: "refraction", name: "光的折射" },
  { id: "lens", name: "透镜" },
  { id: "combination-of-lenses", name: "透镜组合" },
  { id: "GRIN-optics", name: "渐变折射率光学" },
  { id: "miscellaneous", name: "其他" },
];

export function GalleryView({ onOpenInSimulator, onImportToStudio }: GalleryViewProps) {
  const [selectedCat, setSelectedCat] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");

  const filteredItems = useMemo(() => {
    return galleryItems.filter(item => {
      const matchCat = selectedCat === "all" || item.category === selectedCat;
      if (!matchCat) return false;
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      return (
        item.title.toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q) ||
        item.categoryName.toLowerCase().includes(q) ||
        item.contributors.some(c => c.toLowerCase().includes(q))
      );
    });
  }, [selectedCat, searchQuery]);

  return (
    <div className="gallery-container">
      <div className="gallery-header">
        <div>
          <h2>81 个交互式光学演示案例库 (Demo Gallery)</h2>
          <p className="muted">
            涵盖几何光学全领域的交互式演示案例。可直接在模拟器中进行光线追踪物理仿真，也可一键导入 EduForge AI 工坊进行二次教学定制。
          </p>
        </div>
        <div className="gallery-search">
          <input
            type="search"
            placeholder="搜索案例（如：透镜、折射、望远镜、棱镜）..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="search-input"
          />
        </div>
      </div>

      <div className="gallery-categories">
        {CATEGORIES.map(cat => {
          const count = cat.id === "all"
            ? galleryItems.length
            : galleryItems.filter(x => x.category === cat.id).length;
          return (
            <button
              key={cat.id}
              className={`category-pill ${selectedCat === cat.id ? "active" : ""}`}
              onClick={() => setSelectedCat(cat.id)}
            >
              {cat.name} ({count})
            </button>
          );
        })}
      </div>

      <div className="gallery-grid">
        {filteredItems.map(item => (
          <div key={item.id} className="gallery-card">
            <div className="card-header">
              <span className="card-badge">{item.categoryName}</span>
              <span className="card-author">{item.contributors[0] || "Ray Optics"}</span>
            </div>
            <h3 className="card-title">{item.title}</h3>
            <p className="card-desc">{item.description}</p>
            <div className="card-actions">
              <button
                className="btn-primary"
                onClick={() => onOpenInSimulator(item.sceneUrl)}
                title="在内置光学仿真模拟器中打开"
              >
                ⚡ 在模拟器中运行
              </button>
              {onImportToStudio ? (
                <button
                  className="ghost btn-sm"
                  onClick={() => onImportToStudio(item.sceneUrl, item.title)}
                  title="导入 EduForge AI 工坊进行教学定制"
                >
                  🤖 AI 定制
                </button>
              ) : null}
              <a
                href={item.pageUrl}
                target="_blank"
                rel="noreferrer"
                className="card-link"
                title="查看原版案例原理页面"
              >
                详情 ↗
              </a>
            </div>
          </div>
        ))}
      </div>

      {filteredItems.length === 0 ? (
        <div className="gallery-empty">
          <p>没有找到与 “{searchQuery}” 匹配的光学案例</p>
          <button className="ghost" onClick={() => { setSearchQuery(""); setSelectedCat("all"); }}>
            清除筛选条件
          </button>
        </div>
      ) : null}
    </div>
  );
}
