/**
 * video_frames.js —— 页面诊断与截图辅助工具（委托 ../04_review_agent/checks_browser.js）
 */
const path = require('path');
const { spawnSync } = require('child_process');
const target = process.argv[2] || '';
const checker = path.join(__dirname, '..', '04_review_agent', 'checks_browser.js');
if (target) {
  const r = spawnSync(process.execPath, [checker, target], { stdio: 'inherit' });
  process.exit(r.status || 0);
} else {
  console.log('用法: node video_frames.js <html路径>');
}
