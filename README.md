# MultipleLive - 前端直连混合直播工具
<img width="1935" height="1222" alt="PixPin_2025-10-15_16-06-46" src="https://github.com/user-attachments/assets/4ab0692a-3e65-4986-9b25-09fbdf12ac7e" />

## 功能
- **前端音画混合**：视频流与音频流分别直连 B 站 m3u8，前端通过双播放器合成（视频静音 + 隐藏音频），音频流音量独立可调。
- **多房间弹幕**：后端通过 blivedm 采集多个房间，WebSocket 实时推送到前端，DPlayer 通过 `dp.danmaku.draw()` 绘制，支持按房间颜色区分。
- **自动解析与回退**：将房间 URL/短号/长号统一解析为真实 room_id 与 m3u8 直链，支持原画 qn=25000 优先与多档回退（20000/10000...），携带 SESSDATA 可获取更高清晰度。

## 目录结构
```
app/
  main.py                    # 后端入口：日志配置与 aiohttp 应用组装
  state.py                   # 全局状态管理（弹幕采集、WS 客户端、广播任务）
  routes/
    static.py                # 静态路由（首页）
    api.py                   # API 路由（/api/resolve、/api/danmaku/start、/api/stop）
    ws.py                    # WebSocket 路由（/ws/danmaku）
  services/
    stream_resolver.py       # 直播流解析（resolve_room_id、pick_best_hls）
    danmaku_service.py       # 弹幕采集（DanmakuCollector）
  models/                    # 共享数据模型（预留）
web/
  index.html                 # 前端（DPlayer + hls.js + 侧栏控制面板）
blivedm/                     # 第三方依赖（vendored）
requirements.txt             # Python 依赖
```

## 快速开始
```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python -m app.main

# 浏览器访问
# http://127.0.0.1:8090/
```

## 使用说明
打开 `http://127.0.0.1:8090/`，在右侧控制面板：
1. **直播源**：填写视频源与音频源（支持房间 ID/URL 或直接 m3u8）
2. **SESSDATA**（可选）：点击"自动获取"，按提示在 B 站页面控制台运行命令导入，或手动填写，用于请求原画（25000）
3. **弹幕来源与颜色**：点击"添加来源"，填写房间并选择颜色；预设颜色可快速点选
4. **音量控制**：调节音频流音量（0~100%）
5. **开始/停止**：点击"开始"即启动；"停止"会同时停止音频、视频与弹幕

## 核心特性
- **自动房间号重定向**：输入短号会自动解析为真实 room_id，颜色映射无缝对齐
- **多档清晰度回退**：原画 → 高清 → 标清自动降级，最大化成功率
- **直播弹幕最佳实践**：使用 DPlayer `apiBackend` + `dp.danmaku.draw()` 实时绘制，颜色按房间区分
- **音画同步与智能丢弃**：暂停/切换标签页时丢弃积压弹幕，恢复时清空历史避免"弹幕爆发"
- **彩色日志与降噪**：关键事件（启动/连接/停止）高亮输出，第三方库日志降级

## API 接口
- `GET /`：返回前端页面
- `POST /api/resolve`：解析房间为 m3u8 与真实 room_id（支持 sessdata）
- `POST /api/danmaku/start`：启动多房间弹幕采集（rooms、colors、sessdata）
- `POST /api/stop`：停止弹幕采集与广播
- `WS /ws/danmaku`：弹幕实时推送（JSON: {room_id, uname, msg, ts_ms, color}）

## 技术栈
- 后端：aiohttp、blivedm（WebSocket 弹幕）、requests（直播流解析）
- 前端：DPlayer（播放器 + 弹幕）、hls.js（HLS 播放）、原生 Web API（音频独立控制）
- 架构：模块化分层（routes/services/state）、前端直连音画混合、无服务端转码

## 注意事项
- 原画需登录 B 站账号并有相应权限；部分房间即使带 SESSDATA 也可能仅返回较低画质（B 站限制）。
- 不同房间的码率/时基可能不同，音画同步受网络抖动影响；可通过音量控制微调听感。
