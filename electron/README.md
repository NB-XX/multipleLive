# MultipleLive Desktop Player

基于 Electron 的无边框可置顶桌面播放器。

## 功能特性

- 🖥️ **无边框窗口**：现代化的无边框设计
- 📌 **置顶功能**：支持窗口置顶，快捷键 Ctrl+T
- 🖼️ **全屏模式**：F11 全屏切换
- 📱 **系统托盘**：最小化到系统托盘
- ⌨️ **快捷键支持**：
  - `Ctrl+T`: 置顶切换
  - `Ctrl+M`: 最小化到托盘
  - `F11`: 全屏切换
  - `Ctrl+Q`: 退出应用

## 安装和运行

### 方法1：使用启动脚本（推荐）
1. 双击运行 `start.bat`
2. 脚本会自动检查并安装依赖
3. 启动桌面播放器

### 方法2：手动安装
1. 确保已安装 Node.js (https://nodejs.org/)
2. 在 electron 目录下运行：
   ```bash
   npm install
   npm start
   ```

### 开发模式
```bash
npm run dev
```

## 打包发布

### Windows
```bash
npm run build-win
```

### macOS
```bash
npm run build-mac
```

### Linux
```bash
npm run build-linux
```

## 使用说明

1. 启动桌面播放器后，会自动加载播放器界面
2. 使用右上角的窗口控制按钮：
   - `−`: 最小化
   - `□`: 最大化/还原
   - `×`: 关闭（最小化到托盘）
3. 右键系统托盘图标可以快速控制窗口
4. 所有原有的播放器功能都保持不变

## 注意事项

- 首次运行需要安装依赖，可能需要几分钟时间
- 确保后端服务（Python 应用）正在运行
- 如果遇到问题，可以尝试删除 `node_modules` 文件夹后重新安装
